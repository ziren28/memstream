"""Fallback command parser — handles ``/cmd args`` when the LLM is offline.

Supported commands (all designed to be typed from a chat client):

  /help                                     — print commands
  /search <query>                           — memory search
  /brief                                    — recent foldings digest
  /tasks [pending|done|failed]              — list tasks
  /task <title> ; <cron_or_due> ; <channel> ; <text>  — quick create notify task
  /cancel <task_id>                         — cancel a task
  /note <title> : <content>                 — save a manual note

The parser is intentionally tiny — just enough to survive an LLM outage.
Complex task DAGs still need an LLM or a YAML file.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from ..memory import recall, search
from ..skills.base import execute as skill_execute
from ..skills import registry
from ..tasks import store, scheduler
from ..tasks.model import PlanStep, Task


HELP_TEXT = """memstream fallback parser — commands:
  /help                                     show this
  /search <query>                           memory search
  /brief                                    recent foldings
  /tasks [status]                           list tasks (pending/done/failed)
  /task <title>;<cron_or_iso>;<channel>;<text>
                                            quick notify task
  /cancel <task_id>                         cancel
  /note <title>:<content>                   manual memory note
"""


def _cmd_search(rest: str) -> str:
    hits = search.search(rest.strip(), limit=5)
    if not hits:
        return "(no match)"
    lines = []
    for h in hits:
        lines.append(f"• [{h['date']}] {h['title']}")
        if h["summary"]:
            lines.append(f"  {h['summary'][:100]}")
    return "\n".join(lines)


def _cmd_brief(_rest: str) -> str:
    return recall.brief() or "(no foldings yet)"


def _cmd_tasks(rest: str) -> str:
    status = rest.strip() or None
    tasks = store.list_tasks(status=status, limit=20)
    if not tasks:
        return "(no tasks)"
    lines = [f"[{t.status}] {t.id} {t.title[:50]}" for t in tasks]
    return "\n".join(lines)


def _cmd_task(rest: str) -> str:
    parts = [p.strip() for p in rest.split(";")]
    if len(parts) < 4:
        return "usage: /task <title>;<cron_or_iso>;<channel>;<text>"
    title, when, channel, text = parts[0], parts[1], parts[2], ";".join(parts[3:])
    if re.fullmatch(r"[\d\-: T]+", when):
        try:
            due = datetime.fromisoformat(when)
            task = Task.new(
                title=title, plan=[PlanStep(skill="notify", args={"channel": channel, "text": text})],
                trigger_kind="due", trigger_spec=when,
                due_at=due.timestamp(), next_run=due.timestamp(),
            )
        except ValueError:
            return f"bad ISO datetime: {when}"
    else:
        task = Task.new(
            title=title, plan=[PlanStep(skill="notify", args={"channel": channel, "text": text})],
            trigger_kind="cron", trigger_spec=when,
        )
        nxt = scheduler.compute_next_run(task, datetime.now())
        task.next_run = nxt
    store.save(task)
    next_at = datetime.fromtimestamp(task.next_run).strftime("%Y-%m-%d %H:%M") if task.next_run else "?"
    return f"✅ {task.id} created, next run: {next_at}"


def _cmd_cancel(rest: str) -> str:
    tid = rest.strip()
    t = store.get(tid)
    if not t:
        return f"(not found: {tid})"
    t.status = "cancelled"
    t.next_run = None
    store.save(t)
    return f"✅ cancelled {tid}"


def _cmd_note(rest: str) -> str:
    if ":" not in rest:
        return "usage: /note <title>:<content>"
    title, content = rest.split(":", 1)
    registry.register_builtins()
    s = registry.get("mem.write_note")
    r = skill_execute(s, {"title": title.strip(), "content": content.strip()})
    return f"✅ note {r.output.get('id')}" if r.ok else f"❌ {r.error}"


HANDLERS = {
    "/help": lambda _: HELP_TEXT,
    "/search": _cmd_search,
    "/brief": _cmd_brief,
    "/tasks": _cmd_tasks,
    "/task": _cmd_task,
    "/cancel": _cmd_cancel,
    "/note": _cmd_note,
}


def parse(line: str) -> str | None:
    """If ``line`` starts with a known command, handle it and return reply text."""
    line = line.strip()
    if not line.startswith("/"):
        return None
    cmd, _, rest = line.partition(" ")
    cmd = cmd.lower()
    handler = HANDLERS.get(cmd)
    if not handler:
        return None
    try:
        return handler(rest)
    except Exception as e:
        return f"error: {e}"
