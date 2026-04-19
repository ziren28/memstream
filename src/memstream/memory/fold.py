"""Fold distilled modules into daily/weekly/monthly summaries."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

from ..core.db import get_conn
from ..llm.base import LLMAdapter, get_default_adapter


FOLD_PROMPT = """你是记忆折叠器。下面是一批模块元数据，请综合成当期摘要。
严格返回 JSON（无 markdown）：
{
  "summary": "300 字内当期主线，按主题分段",
  "key_events": ["最重要的 3-5 个 module_id"],
  "categories_count": {"investment": 3, ...}
}

期间: {period}
模块列表:
{modules_text}
"""


def _modules_in_range(start_ts: float, end_ts: float) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        """SELECT id, category, title, summary, tags FROM modules
           WHERE start_ts >= ? AND start_ts < ? AND status = 'distilled'
           ORDER BY start_ts ASC""",
        (start_ts, end_ts),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _extract_json(text: str) -> dict:
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}


def fold_period(level: str, period: str, start_ts: float, end_ts: float,
                adapter: LLMAdapter | None = None) -> bool:
    conn = get_conn()
    fold_id = f"{level}:{period}"
    if conn.execute("SELECT id FROM foldings WHERE id = ?", (fold_id,)).fetchone():
        conn.close()
        return False

    mods = _modules_in_range(start_ts, end_ts)
    if not mods:
        conn.close()
        return False

    adapter = adapter or get_default_adapter()
    lines = [f"[{m['category']}] {m['id'][:8]} {m['title'][:50]} — {(m['summary'] or '')[:80]}"
             for m in mods]
    prompt = (FOLD_PROMPT.replace("{period}", period)
                         .replace("{modules_text}", "\n".join(lines)))
    response = adapter.complete(prompt, timeout=120)
    data = _extract_json(response)
    if not data:
        conn.close()
        return False

    conn.execute(
        """INSERT INTO foldings (id, level, period, module_count, summary, key_events, token_spent)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (fold_id, level, period, len(mods),
         (data.get("summary") or "")[:3000],
         json.dumps(data.get("key_events", []), ensure_ascii=False),
         sum(len(l) for l in lines) // 4),
    )
    for m in mods:
        conn.execute(
            "UPDATE modules SET folded_into = ? WHERE id = ? AND status = 'distilled'",
            (fold_id, m["id"]),
        )
    conn.commit()
    conn.close()
    return True


def fold_daily(date_str: str | None = None, adapter: LLMAdapter | None = None) -> bool:
    d = (datetime.now(timezone.utc) - timedelta(days=1)) if not date_str else \
        datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    start = d.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return fold_period("daily", start.strftime("%Y-%m-%d"),
                       start.timestamp(), end.timestamp(), adapter=adapter)


def fold_weekly(adapter: LLMAdapter | None = None) -> bool:
    today = datetime.now(timezone.utc)
    d = (today - timedelta(days=today.weekday() + 7)).replace(
        hour=0, minute=0, second=0, microsecond=0,
    )
    start = d
    end = d + timedelta(days=7)
    period = f"{start:%G-W%V}"
    return fold_period("weekly", period, start.timestamp(), end.timestamp(), adapter=adapter)


def fold_monthly(adapter: LLMAdapter | None = None) -> bool:
    today = datetime.now(timezone.utc)
    first = today.replace(day=1)
    d = (first - timedelta(days=1)).replace(day=1)
    end_month = (d.replace(day=28) + timedelta(days=5)).replace(day=1)
    return fold_period("monthly", f"{d:%Y-%m}", d.timestamp(),
                       end_month.timestamp(), adapter=adapter)
