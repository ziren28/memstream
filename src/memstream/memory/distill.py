"""Distill raw modules into structured metadata via an LLMAdapter.

Distiller doesn't care *which* LLM — it asks the configured adapter for a JSON
response matching a fixed schema. The schema is part of memstream's contract
with the LLM layer.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from ..core.db import get_conn
from ..llm.base import LLMAdapter, get_default_adapter


PROMPT = """你是记忆系统的蒸馏器。下面是一段会话或消息的原始 JSONL。
严格返回 JSON（无 markdown），字段：
{
  "title": "20 字内",
  "category": "investment | infra | chitchat | debug | research | setup | other",
  "summary": "200 字内",
  "tags": ["3-6 个关键词"],
  "entities": ["股票代码/公司/项目/人名"]
}

原文:
{raw_text}
"""


def _extract_text_from_content(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict):
                if b.get("type") == "text":
                    parts.append(b.get("text", ""))
                elif b.get("type") == "tool_use":
                    parts.append(f"[tool:{b.get('name','?')}]")
        return "\n".join(parts)
    return ""


def compact_jsonl(raw: str, max_chars: int = 18000) -> str:
    out = []
    for line in raw.splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        etype = e.get("type")
        if etype not in ("user", "assistant"):
            continue
        msg = e.get("message", {})
        if not isinstance(msg, dict):
            continue
        text = _extract_text_from_content(msg.get("content", "")).strip()
        if not text:
            continue
        prefix = "U:" if etype == "user" else "A:"
        out.append(f"{prefix} {text[:600]}")
        if sum(len(s) for s in out) > max_chars:
            break
    return "\n".join(out)[:max_chars]


def _load_raw(pointer: str) -> str:
    if pointer.startswith(("s3://", "r2://", "http://", "https://")):
        return ""  # external; adapter-specific fetcher can override later
    p = Path(pointer)
    if p.exists():
        return p.read_text(errors="replace")
    return ""


def _extract_json(text: str) -> dict:
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}


def distill_module(module_row: dict, adapter: LLMAdapter | None = None) -> bool:
    adapter = adapter or get_default_adapter()
    raw = _load_raw(module_row.get("raw_pointer") or "")
    if not raw:
        return False
    compact = compact_jsonl(raw)
    if not compact:
        return False
    prompt = PROMPT.replace("{raw_text}", compact)
    response = adapter.complete(prompt, timeout=120)
    data = _extract_json(response)
    if not data.get("title"):
        return False

    tags = ",".join(data.get("tags") or []) if isinstance(data.get("tags"), list) else str(data.get("tags", ""))
    entities = json.dumps(data.get("entities") or [], ensure_ascii=False)

    conn = get_conn()
    conn.execute(
        """UPDATE modules SET
             title=?, category=?, summary=?, tags=?, entities=?, token_spent=?,
             status='distilled', updated_at=strftime('%s','now')
           WHERE id = ?""",
        (
            (data.get("title") or "")[:80],
            data.get("category", "other"),
            (data.get("summary") or "")[:1000],
            tags[:200],
            entities[:400],
            len(compact) // 4,
            module_row["id"],
        ),
    )
    conn.commit()
    conn.close()
    return True


def distill_raw(limit: int = 10, adapter: LLMAdapter | None = None) -> int:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM modules WHERE status='raw' ORDER BY start_ts DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    ok = 0
    for r in rows:
        if distill_module(dict(r), adapter=adapter):
            ok += 1
    return ok
