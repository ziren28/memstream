"""Scheduler — drives triggers (cron / due / signal / manual / chain)."""
from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Iterable

from . import store
from .executor import execute_plan
from .model import Task


# ---- cron parser (minimalist: m h dom mon dow, all standard + */N) --------

def _match_cron_field(field: str, now_val: int) -> bool:
    if field == "*":
        return True
    if "/" in field:
        base, step = field.split("/", 1)
        step_i = max(int(step), 1)
        if base == "*":
            return now_val % step_i == 0
        return (now_val - int(base)) % step_i == 0 and now_val >= int(base)
    if "," in field:
        return any(_match_cron_field(part, now_val) for part in field.split(","))
    if "-" in field:
        lo, hi = field.split("-", 1)
        return int(lo) <= now_val <= int(hi)
    return now_val == int(field)


def cron_matches(expr: str, moment: datetime) -> bool:
    """Check if ``expr`` (5-field cron) matches ``moment``."""
    parts = expr.split()
    if len(parts) != 5:
        return False
    m, h, dom, mon, dow = parts
    if not _match_cron_field(m, moment.minute): return False
    if not _match_cron_field(h, moment.hour): return False
    if not _match_cron_field(dom, moment.day): return False
    if not _match_cron_field(mon, moment.month): return False
    # Python: weekday Monday=0..Sunday=6; cron: Sunday=0..Saturday=6
    cron_dow = (moment.weekday() + 1) % 7
    if not _match_cron_field(dow, cron_dow): return False
    return True


def next_cron_run(expr: str, after: datetime, lookahead_minutes: int = 60 * 24 * 7) -> datetime | None:
    """Find the next minute from ``after`` that matches ``expr``."""
    cur = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(lookahead_minutes):
        if cron_matches(expr, cur):
            return cur
        cur += timedelta(minutes=1)
    return None


# ---- trigger resolution ---------------------------------------------------

def compute_next_run(task: Task, now: datetime | None = None) -> float | None:
    """Given a task's trigger spec, compute the next UNIX timestamp to fire."""
    now = now or datetime.now()
    if task.trigger_kind == "cron":
        nxt = next_cron_run(task.trigger_spec, now)
        return nxt.timestamp() if nxt else None
    if task.trigger_kind == "due":
        if task.due_at and task.due_at > now.timestamp():
            return task.due_at
        return None
    if task.trigger_kind == "manual":
        return None
    # signal / chain handled elsewhere; no time-based fire
    return None


# ---- main loop ------------------------------------------------------------

def tick(now: float | None = None) -> list[dict]:
    """One scheduler iteration: fire all due tasks, record runs, reschedule."""
    now = now if now is not None else time.time()
    fired = []
    for task in store.due_now(now):
        run = execute_plan(task)
        store.record_run(run)
        # Recurring tasks reschedule; one-shot are done/failed
        if task.trigger_kind == "cron":
            nxt = compute_next_run(task, datetime.fromtimestamp(now))
            store.update_after_run(task, nxt, "pending" if nxt else "done")
        else:
            store.update_after_run(task, None, run.status if run.status == "success" else "failed")
        fired.append({"task_id": task.id, "status": run.status, "error": run.error})
    return fired


def serve(interval: float = 30.0) -> None:
    """Run the scheduler forever (systemd-friendly)."""
    while True:
        try:
            tick()
        except Exception as e:
            print(f"scheduler tick error: {type(e).__name__}: {e}", flush=True)
        time.sleep(interval)
