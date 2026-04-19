"""mem — skills that operate on memstream's own records.

These are the primary way an LLM (or a task plan) interacts with memory.
"""
from __future__ import annotations

import json
import math
import time
from datetime import datetime
from typing import Any

from ..core.db import get_conn
from .base import Skill, SkillResult


class MemSearchSkill(Skill):
    name = "mem.search"
    description = (
        "Keyword search across module titles/summaries/tags/entities, "
        "ranked by term-hit count × time-weight (recent > older). "
        "CJK-friendly LIKE matching; no vector DB required."
    )
    input_schema = {
        "type": "object",
        "required": ["query"],
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "default": 10, "minimum": 1, "maximum": 100},
            "category": {"type": "string"},
            "half_life_days": {"type": "number", "default": 20},
        },
    }
    output_schema = {
        "type": "object",
        "properties": {
            "hits": {"type": "array"},
            "count": {"type": "integer"},
        },
    }
    tags = ["memory", "read"]

    def run(self, **kwargs: Any) -> SkillResult:
        query = kwargs["query"]
        limit = kwargs.get("limit", 10)
        category = kwargs.get("category")
        half_life = kwargs.get("half_life_days", 20)
        lambda_ = math.log(2) / max(half_life, 0.1)

        terms = [t.strip() for t in query.split() if t.strip()]
        if not terms:
            return SkillResult(ok=True, output={"hits": [], "count": 0})

        where_parts = []
        params: list[Any] = []
        for t in terms:
            like = f"%{t}%"
            where_parts.append(
                "(title LIKE ? OR summary LIKE ? OR tags LIKE ? OR entities LIKE ?)"
            )
            params.extend([like, like, like, like])
        sql = (
            "SELECT id, source, start_ts, category, title, summary, tags, entities, raw_pointer "
            f"FROM modules WHERE ({' AND '.join(where_parts)})"
        )
        if category:
            sql += " AND category = ?"
            params.append(category)
        sql += " LIMIT 100"

        conn = get_conn()
        rows = conn.execute(sql, params).fetchall()
        conn.close()

        now = time.time()
        hits = []
        for r in rows:
            days = max((now - r["start_ts"]) / 86400, 0)
            score = (len(terms) + 0.5) * math.exp(-lambda_ * days)
            hits.append({
                "id": r["id"],
                "source": r["source"],
                "date": datetime.fromtimestamp(r["start_ts"]).strftime("%Y-%m-%d %H:%M"),
                "category": r["category"],
                "title": r["title"],
                "summary": r["summary"],
                "tags": r["tags"],
                "entities": r["entities"],
                "pointer": r["raw_pointer"],
                "score": round(score, 3),
                "days_ago": round(days, 1),
            })
        hits.sort(key=lambda h: h["score"], reverse=True)
        hits = hits[:limit]
        return SkillResult(ok=True, output={"hits": hits, "count": len(hits)})


class MemWriteNoteSkill(Skill):
    name = "mem.write_note"
    description = "Append a note-style module to memory (source='note')."
    input_schema = {
        "type": "object",
        "required": ["title", "content"],
        "properties": {
            "title": {"type": "string", "maxLength": 200},
            "content": {"type": "string"},
            "category": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
    }
    output_schema = {"type": "object", "properties": {"id": {"type": "string"}}}
    tags = ["memory", "write"]

    def run(self, **kwargs: Any) -> SkillResult:
        import uuid
        mid = f"note-{uuid.uuid4().hex[:12]}"
        conn = get_conn()
        conn.execute(
            """INSERT INTO modules (id, source, start_ts, end_ts, category, title, summary, tags, status)
               VALUES (?, 'note', ?, ?, ?, ?, ?, ?, 'distilled')""",
            (
                mid, time.time(), time.time(),
                kwargs.get("category", "note"),
                kwargs["title"], kwargs["content"][:3000],
                ",".join(kwargs.get("tags", [])),
            ),
        )
        conn.commit()
        conn.close()
        return SkillResult(ok=True, output={"id": mid})


class MemConditionSkill(Skill):
    name = "mem.condition"
    description = (
        "Evaluate a simple boolean expression against previous step outputs. "
        "Supports python-like: ==, !=, <, <=, >, >=, and, or, not, in, 'contains'. "
        "Example: 'price.price < 70 and news.count > 0'."
    )
    input_schema = {
        "type": "object",
        "required": ["expr"],
        "properties": {
            "expr": {"type": "string"},
            "context": {"type": "object", "description": "Named outputs of previous steps."},
        },
    }
    output_schema = {"type": "object", "properties": {"result": {"type": "boolean"}}}
    tags = ["control-flow"]

    def run(self, **kwargs: Any) -> SkillResult:
        expr = kwargs["expr"]
        ctx = kwargs.get("context") or {}
        try:
            # Restricted eval — expose ctx + a whitelist of safe builtins only.
            safe_builtins = {
                "len": len, "abs": abs, "min": min, "max": max,
                "sum": sum, "any": any, "all": all, "bool": bool,
                "int": int, "float": float, "str": str, "list": list,
                "set": set, "dict": dict, "tuple": tuple,
                "round": round, "sorted": sorted,
            }
            safe = {"__builtins__": safe_builtins}
            safe.update(ctx)
            value = bool(eval(expr, safe, {}))  # noqa: S307 (restricted globals)
            return SkillResult(ok=True, output={"result": value})
        except Exception as e:
            return SkillResult(ok=False, output={"result": False}, error=str(e))
