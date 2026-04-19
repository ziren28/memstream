"""High-level recall helpers — what the hook + LLM mostly call."""
from __future__ import annotations

from datetime import datetime

from ..core.db import get_conn
from .search import search


def recent_foldings(level: str = "daily", count: int = 3) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        """SELECT id, period, module_count, summary FROM foldings
           WHERE level = ? ORDER BY period DESC LIMIT ?""",
        (level, count),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def brief() -> str:
    """Produce a compact brief suitable for a SessionStart hook."""
    daily = recent_foldings("daily", 2)
    weekly = recent_foldings("weekly", 1)
    monthly = recent_foldings("monthly", 1)

    parts: list[str] = []
    if monthly:
        m = monthly[0]
        parts.append(f"\n📅 上月 ({m['period']}) · {m['module_count']} 个模块")
        parts.append(f"  {m['summary'][:300]}")
    if weekly:
        w = weekly[0]
        parts.append(f"\n📅 上周 ({w['period']}) · {w['module_count']} 个模块")
        parts.append(f"  {w['summary'][:400]}")
    for d in daily:
        parts.append(f"\n📅 {d['period']} · {d['module_count']} 个模块")
        parts.append(f"  {d['summary'][:500]}")

    if not parts:
        return ""
    return "📚 memstream 记忆简报" + "\n".join(parts)
