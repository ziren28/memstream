"""digest.* — skills that manage identified digest items with feedback loops.

Covers three core operations:
  - digest.assign_ids  : parse an LLM-produced item list, assign YYYYMMDD-NNN ids, persist.
  - digest.score       : record a user's 1-10 score on a prior item (drives future prompts).
  - digest.history     : dump recent scored items as a prompt-ready block for the LLM.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from typing import Any

from ..core.db import get_conn
from .base import Skill, SkillResult


# -------------- id allocation --------------

def _next_seq_for_today(conn) -> int:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    row = conn.execute(
        "SELECT COUNT(*) as c FROM digest_items WHERE id LIKE ?",
        (f"{today}-%",),
    ).fetchone()
    return (row["c"] or 0) + 1


def _today_id(conn) -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    seq = _next_seq_for_today(conn)
    return f"{today}-{seq:03d}"


# -------------- skills ---------------------

class DigestAssignIdsSkill(Skill):
    name = "digest.assign_ids"
    description = (
        "Parse an LLM-produced items JSON array, assign YYYYMMDD-NNN ids, "
        "persist to digest_items, and return rendered markdown for notify."
    )
    input_schema = {
        "type": "object",
        "required": ["items"],
        "properties": {
            "items": {
                "oneOf": [
                    {"type": "array",
                     "description": "List of {title, summary, url?, tags?, llm_score, llm_reason?, diversity?}"},
                    {"type": "object",
                     "description": "Parsed LLM object with 'items' field"},
                    {"type": "string",
                     "description": "Raw LLM text — will be parsed for a JSON array"},
                ],
            },
            "batch": {"type": "string", "description": "optional batch key"},
        },
    }
    output_schema = {
        "type": "object",
        "properties": {
            "stored": {"type": "integer"},
            "ids": {"type": "array"},
            "markdown": {"type": "string"},
            "batch": {"type": "string"},
        },
    }
    tags = ["digest"]

    def _normalize(self, items: Any) -> list[dict]:
        if isinstance(items, str):
            m = re.search(r"\[[\s\S]*\]", items)
            if not m:
                return []
            try:
                items = json.loads(m.group(0))
            except json.JSONDecodeError:
                return []
        if isinstance(items, dict):
            items = items.get("items") or items.get("data") or []
        if not isinstance(items, list):
            return []
        return [i for i in items if isinstance(i, dict) and i.get("title")]

    def run(self, **kwargs: Any) -> SkillResult:
        parsed = self._normalize(kwargs.get("items"))
        if not parsed:
            return SkillResult(ok=False, output={"stored": 0, "ids": [], "markdown": "", "batch": ""},
                               error="no valid items parsed")

        batch = kwargs.get("batch") or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M")
        conn = get_conn()
        assigned_ids = []
        rendered_lines = []
        try:
            for it in parsed:
                iid = _today_id(conn)
                conn.execute(
                    """INSERT INTO digest_items
                       (id, source, original_url, title, summary, tags,
                        llm_score, llm_reason, diversity, digest_batch)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        iid,
                        it.get("source", ""),
                        it.get("url", ""),
                        it.get("title", "")[:300],
                        it.get("summary", "")[:2000],
                        ",".join(it.get("tags", [])) if isinstance(it.get("tags"), list) else str(it.get("tags", "")),
                        int(it.get("llm_score", 5)),
                        (it.get("llm_reason") or "")[:500],
                        1 if it.get("diversity") else 0,
                        batch,
                    ),
                )
                assigned_ids.append(iid)
                badge = "🔍" if it.get("diversity") else "⭐"
                score = int(it.get("llm_score", 5))
                rendered_lines.append(f"{badge} [{iid}] ({score}/10) {it.get('title','')[:60]}")
                if it.get("summary"):
                    rendered_lines.append(f"   💬 {it['summary'][:120]}")
                if it.get("url"):
                    rendered_lines.append(f"   🔗 {it['url']}")
            conn.commit()
        finally:
            conn.close()

        md = "\n".join(rendered_lines)
        md += (f"\n\n💡 对任一条打分：回复 `<id> <1-10>` 例如 `{assigned_ids[0]} 8` "
               f"（分数用于未来筛选权重）" if assigned_ids else "")

        return SkillResult(ok=True, output={
            "stored": len(assigned_ids),
            "ids": assigned_ids,
            "markdown": md,
            "batch": batch,
        })


class DigestScoreSkill(Skill):
    name = "digest.score"
    description = "Record a user's 1-10 score for a digest item."
    input_schema = {
        "type": "object",
        "required": ["id", "score"],
        "properties": {
            "id": {"type": "string", "description": "YYYYMMDD-NNN"},
            "score": {"type": "integer", "minimum": 1, "maximum": 10},
            "note": {"type": "string"},
        },
    }
    output_schema = {
        "type": "object",
        "properties": {
            "updated": {"type": "boolean"},
            "title": {"type": "string"},
        },
    }
    tags = ["digest", "feedback"]

    def run(self, **kwargs: Any) -> SkillResult:
        iid = kwargs["id"].strip().upper()
        score = int(kwargs["score"])
        note = kwargs.get("note", "")
        if not 1 <= score <= 10:
            return SkillResult(ok=False, output={"updated": False, "title": ""},
                               error="score must be 1-10")
        conn = get_conn()
        row = conn.execute("SELECT title FROM digest_items WHERE id = ?", (iid,)).fetchone()
        if not row:
            conn.close()
            return SkillResult(ok=False, output={"updated": False, "title": ""},
                               error=f"item {iid} not found")
        conn.execute(
            """UPDATE digest_items SET user_score = ?, user_score_at = ?, user_note = ?
               WHERE id = ?""",
            (score, time.time(), note, iid),
        )
        conn.commit()
        title = row["title"] or ""
        conn.close()
        return SkillResult(ok=True, output={"updated": True, "title": title})


class DigestHistorySkill(Skill):
    name = "digest.history"
    description = (
        "Return recent user-scored items as a prompt-ready context block, "
        "so the next LLM pass can learn from Max's feedback."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "default": 30},
            "min_age_minutes": {"type": "integer", "default": 0,
                                "description": "Exclude items scored within the last N minutes."},
        },
    }
    output_schema = {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "count": {"type": "integer"},
        },
    }
    tags = ["digest", "feedback"]

    def run(self, **kwargs: Any) -> SkillResult:
        limit = kwargs.get("limit", 30)
        min_age = kwargs.get("min_age_minutes", 0)
        cutoff = time.time() - (min_age * 60) if min_age else time.time()
        conn = get_conn()
        rows = conn.execute(
            """SELECT id, title, source, tags, llm_score, user_score, user_note
               FROM digest_items
               WHERE user_score IS NOT NULL AND user_score_at <= ?
               ORDER BY user_score_at DESC LIMIT ?""",
            (cutoff, limit),
        ).fetchall()
        conn.close()
        if not rows:
            return SkillResult(ok=True, output={"text": "", "count": 0})
        lines = ["# Max 的历史打分样本（用于校准你的未来筛选权重）",
                 "| id | LLM分 | Max分 | 主题 |",
                 "|----|------|-------|------|"]
        for r in rows:
            lines.append(f"| {r['id']} | {r['llm_score']} | {r['user_score']} | {(r['title'] or '')[:50]} |")
        lines.append(
            "\n推断规则示例：当 Max 分明显高于 LLM 分 → 说明 LLM 低估了某类内容；"
            "Max 分明显低于 LLM 分 → 该类内容应降权。请在本次筛选里吸收这些偏好。"
        )
        return SkillResult(ok=True, output={"text": "\n".join(lines), "count": len(rows)})
