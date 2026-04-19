"""Plan executor — run a Task's plan, step by step, against the skill registry.

Design:
  * Each step can reference earlier steps' outputs via ``store_as``.
  * ``args`` values support ``{{ref.path}}`` template substitution.
  * ``if`` field is evaluated against the store (via mem.condition).
  * On skill failure: default is abort; set ``on_error: skip`` to continue.
"""
from __future__ import annotations

import re
import time
from typing import Any

from ..skills import registry
from ..skills.base import execute, SkillResult
from .model import Task, TaskRun, PlanStep


TEMPLATE_RE = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")


def _resolve_path(ctx: dict[str, Any], path: str) -> Any:
    """Resolve 'foo.bar.baz' inside ctx."""
    cur: Any = ctx
    for seg in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(seg)
        elif isinstance(cur, list):
            try:
                cur = cur[int(seg)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return cur


def _substitute(value: Any, ctx: dict[str, Any]) -> Any:
    if isinstance(value, str):
        def replace(m: re.Match) -> str:
            resolved = _resolve_path(ctx, m.group(1))
            return str(resolved) if resolved is not None else m.group(0)
        return TEMPLATE_RE.sub(replace, value)
    if isinstance(value, dict):
        return {k: _substitute(v, ctx) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute(v, ctx) for v in value]
    return value


def _eval_if(expr: str, ctx: dict[str, Any]) -> bool:
    if not expr:
        return True
    cond_skill = registry.get("mem.condition")
    if cond_skill is None:
        # Registry wasn't initialized; fail closed.
        return False
    r = execute(cond_skill, {"expr": expr, "context": ctx})
    return bool(r.ok and r.output.get("result"))


def execute_plan(task: Task) -> TaskRun:
    """Run all steps of ``task.plan`` and return a TaskRun."""
    ctx: dict[str, Any] = {}
    trace: list[dict[str, Any]] = []
    started = time.time()
    overall_status = "success"
    error_text: str | None = None

    for i, step in enumerate(task.plan):
        if not _eval_if(step.if_ or "", ctx):
            trace.append({"step": i, "skill": step.skill, "skipped": True, "reason": "if_false"})
            continue

        skill_obj = registry.get(step.skill)
        if skill_obj is None:
            trace.append({"step": i, "skill": step.skill, "error": "unknown skill"})
            if step.on_error == "skip":
                continue
            overall_status = "failure"
            error_text = f"unknown skill '{step.skill}'"
            break

        resolved_args = _substitute(step.args, ctx)
        # Special: mem.condition always sees the full ctx (no manual passing needed)
        if step.skill == "mem.condition":
            resolved_args.setdefault("context", {})
            resolved_args["context"] = {**ctx, **(resolved_args.get("context") or {})}
        result: SkillResult = execute(skill_obj, resolved_args)

        trace.append({
            "step": i, "skill": step.skill, "ok": result.ok,
            "duration_ms": int((result.finished_at - result.started_at) * 1000),
            "error": result.error,
            "store_as": step.store_as,
        })

        if step.store_as:
            ctx[step.store_as] = result.output

        if not result.ok:
            if step.on_error == "skip":
                continue
            if step.on_error == "continue":
                overall_status = "partial"
                continue
            overall_status = "failure"
            error_text = result.error
            break

    return TaskRun(
        id=None,
        task_id=task.id,
        started_at=started,
        finished_at=time.time(),
        status=overall_status,
        output=ctx,
        error=error_text,
        skill_trace=trace,
    )
