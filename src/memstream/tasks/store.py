"""Task CRUD against the SQLite store."""
from __future__ import annotations

import json
import time
from typing import Iterable

from ..core.db import get_conn
from .model import Task, TaskRun


INSERT_SQL = """
INSERT INTO tasks (
    id, title, goal, trigger_kind, trigger_spec, plan, result_schema,
    priority, status, tags,
    created_at, scheduled_at, due_at, next_run,
    last_run, run_count,
    source, linked_module_id, parent_task_id, notes
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(id) DO UPDATE SET
    title = excluded.title, goal = excluded.goal,
    trigger_kind = excluded.trigger_kind, trigger_spec = excluded.trigger_spec,
    plan = excluded.plan, result_schema = excluded.result_schema,
    priority = excluded.priority, status = excluded.status, tags = excluded.tags,
    scheduled_at = excluded.scheduled_at, due_at = excluded.due_at,
    next_run = excluded.next_run, last_run = excluded.last_run,
    run_count = excluded.run_count, source = excluded.source,
    linked_module_id = excluded.linked_module_id,
    parent_task_id = excluded.parent_task_id, notes = excluded.notes
"""


def save(task: Task) -> None:
    conn = get_conn()
    conn.execute(INSERT_SQL, task.to_row())
    conn.commit()
    conn.close()


def get(task_id: str) -> Task | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    return Task.from_row(row) if row else None


def list_tasks(status: str | None = None, limit: int = 50) -> list[Task]:
    conn = get_conn()
    if status:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE status = ? ORDER BY priority ASC, created_at DESC LIMIT ?",
            (status, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM tasks ORDER BY priority ASC, created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    conn.close()
    return [Task.from_row(r) for r in rows]


def due_now(now: float | None = None) -> list[Task]:
    """Return tasks whose next_run is due (or scheduled_at if no next_run)."""
    now = now if now is not None else time.time()
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM tasks
           WHERE status IN ('pending','scheduled')
             AND (next_run IS NOT NULL AND next_run <= ?)
           ORDER BY priority ASC, next_run ASC""",
        (now,),
    ).fetchall()
    conn.close()
    return [Task.from_row(r) for r in rows]


def update_after_run(task: Task, next_run: float | None, status: str) -> None:
    conn = get_conn()
    conn.execute(
        """UPDATE tasks SET last_run = ?, next_run = ?, run_count = run_count + 1,
                            status = ? WHERE id = ?""",
        (time.time(), next_run, status, task.id),
    )
    conn.commit()
    conn.close()


def record_run(run: TaskRun) -> int:
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO task_runs (task_id, started_at, finished_at, status, output, error, skill_trace)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        run.to_row(),
    )
    rid = cur.lastrowid
    conn.commit()
    conn.close()
    return rid or 0


def last_run(task_id: str) -> TaskRun | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM task_runs WHERE task_id = ? ORDER BY started_at DESC LIMIT 1",
        (task_id,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return TaskRun(
        id=row["id"], task_id=row["task_id"],
        started_at=row["started_at"], finished_at=row["finished_at"],
        status=row["status"],
        output=json.loads(row["output"] or "{}"),
        error=row["error"],
        skill_trace=json.loads(row["skill_trace"] or "[]"),
    )
