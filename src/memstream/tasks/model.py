"""Task + Plan + TaskRun — declarative intentions."""
from __future__ import annotations

import dataclasses
import json
import time
import uuid
from typing import Any


@dataclasses.dataclass
class PlanStep:
    """A single skill invocation inside a plan."""
    skill: str                           # e.g. "http.get"
    args: dict[str, Any] = dataclasses.field(default_factory=dict)
    store_as: str | None = None          # name under which to save output
    if_: str | None = None               # conditional expression (references earlier store_as)
    on_error: str = "fail"               # fail / skip / continue

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PlanStep":
        return cls(
            skill=d["skill"],
            args=d.get("args") or {},
            store_as=d.get("store_as"),
            if_=d.get("if"),
            on_error=d.get("on_error", "fail"),
        )

    def to_dict(self) -> dict[str, Any]:
        out = {"skill": self.skill, "args": self.args}
        if self.store_as:
            out["store_as"] = self.store_as
        if self.if_:
            out["if"] = self.if_
        if self.on_error != "fail":
            out["on_error"] = self.on_error
        return out


@dataclasses.dataclass
class Task:
    id: str
    title: str
    goal: str = ""
    trigger_kind: str = "manual"         # cron / due / signal / manual / chain
    trigger_spec: str = ""
    plan: list[PlanStep] = dataclasses.field(default_factory=list)
    result_schema: dict[str, Any] | None = None

    priority: int = 3
    status: str = "pending"
    tags: list[str] = dataclasses.field(default_factory=list)

    created_at: float = dataclasses.field(default_factory=time.time)
    scheduled_at: float | None = None
    due_at: float | None = None
    next_run: float | None = None
    last_run: float | None = None
    run_count: int = 0

    source: str = "user"
    linked_module_id: str | None = None
    parent_task_id: str | None = None
    notes: str = ""

    @classmethod
    def new(cls, title: str, plan: list[PlanStep], **kwargs: Any) -> "Task":
        tid = kwargs.pop("id", None) or f"task-{uuid.uuid4().hex[:12]}"
        return cls(id=tid, title=title, plan=plan, **kwargs)

    def to_row(self) -> tuple:
        """Flatten to the tasks-table tuple."""
        return (
            self.id, self.title, self.goal,
            self.trigger_kind, self.trigger_spec,
            json.dumps([s.to_dict() for s in self.plan], ensure_ascii=False),
            json.dumps(self.result_schema, ensure_ascii=False) if self.result_schema else None,
            self.priority, self.status, ",".join(self.tags),
            self.created_at, self.scheduled_at, self.due_at, self.next_run,
            self.last_run, self.run_count,
            self.source, self.linked_module_id, self.parent_task_id, self.notes,
        )

    @classmethod
    def from_row(cls, row: dict[str, Any] | Any) -> "Task":
        # row may be sqlite3.Row or plain dict
        r = dict(row) if not isinstance(row, dict) else row
        plan_raw = r.get("plan") or "[]"
        plan = [PlanStep.from_dict(s) for s in json.loads(plan_raw)]
        result_schema = json.loads(r["result_schema"]) if r.get("result_schema") else None
        tags_raw = r.get("tags") or ""
        tags = [t for t in tags_raw.split(",") if t]
        return cls(
            id=r["id"], title=r["title"], goal=r.get("goal", "") or "",
            trigger_kind=r.get("trigger_kind", "manual"),
            trigger_spec=r.get("trigger_spec", "") or "",
            plan=plan, result_schema=result_schema,
            priority=r.get("priority", 3), status=r.get("status", "pending"), tags=tags,
            created_at=r.get("created_at", 0) or 0,
            scheduled_at=r.get("scheduled_at"), due_at=r.get("due_at"),
            next_run=r.get("next_run"), last_run=r.get("last_run"),
            run_count=r.get("run_count", 0) or 0,
            source=r.get("source", "user") or "user",
            linked_module_id=r.get("linked_module_id"),
            parent_task_id=r.get("parent_task_id"),
            notes=r.get("notes", "") or "",
        )


@dataclasses.dataclass
class TaskRun:
    id: int | None
    task_id: str
    started_at: float
    finished_at: float | None
    status: str                          # success / failure / partial / cancelled
    output: dict[str, Any]
    error: str | None
    skill_trace: list[dict[str, Any]]

    def to_row(self) -> tuple:
        return (
            self.task_id, self.started_at, self.finished_at, self.status,
            json.dumps(self.output, ensure_ascii=False, default=str),
            self.error,
            json.dumps(self.skill_trace, ensure_ascii=False, default=str),
        )
