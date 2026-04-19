"""Keyword + time-weighted search over modules (Record primitive).

This module exposes a standalone search() function used by the CLI, the
mem.search skill, and the hook brief helper. CJK-friendly LIKE matching
so we don't require a vector store for v0.1.
"""
from __future__ import annotations

import math
import time
from datetime import datetime
from typing import Any

from ..core.db import get_conn


def search(query: str | None = None, category: str | None = None,
           limit: int = 10, half_life_days: float = 20.0) -> list[dict[str, Any]]:
    """Return top modules matching ``query`` ranked by term-hits × time-weight.

    If ``query`` is None, returns latest modules (optionally filtered by category).
    """
    lambda_ = math.log(2) / max(half_life_days, 0.1)
    conn = get_conn()
    now = time.time()

    if query:
        terms = [t.strip() for t in query.split() if t.strip()]
        if not terms:
            conn.close()
            return []
        where_parts = []
        params: list[Any] = []
        for t in terms:
            like = f"%{t}%"
            where_parts.append(
                "(title LIKE ? OR summary LIKE ? OR tags LIKE ? OR entities LIKE ?)"
            )
            params.extend([like, like, like, like])
        sql = ("SELECT id, source, start_ts, category, title, summary, tags, entities, raw_pointer, "
               f"{len(terms)} as hit_count FROM modules WHERE ({' AND '.join(where_parts)})")
        if category:
            sql += " AND category = ?"
            params.append(category)
        sql += " LIMIT 200"
        rows = conn.execute(sql, params).fetchall()
    else:
        sql = "SELECT id, source, start_ts, category, title, summary, tags, entities, raw_pointer, 0 as hit_count FROM modules"
        params = []
        if category:
            sql += " WHERE category = ?"
            params.append(category)
        sql += " ORDER BY start_ts DESC LIMIT ?"
        params.append(limit * 2)
        rows = conn.execute(sql, params).fetchall()

    conn.close()

    results = []
    for r in rows:
        days = max((now - r["start_ts"]) / 86400, 0)
        score = (r["hit_count"] + 0.5) * math.exp(-lambda_ * days)
        results.append({
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
    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:limit]
