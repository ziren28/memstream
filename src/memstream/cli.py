"""memstream CLI — the user and LLM facing command surface.

Usage:
  memstream init                                init DB + skills registry
  memstream skill list                          list all skills + schemas
  memstream skill schema <name>                 print JSON schema for one skill
  memstream skill run <name> --args '{...}'     invoke a skill directly

  memstream task create --file spec.yaml        create task from YAML/JSON spec
  memstream task list [--status pending]        list tasks
  memstream task get <id>                       show a task + last run
  memstream task run <id>                       run a task once (manual trigger)
  memstream task cancel <id>                    mark task cancelled
  memstream scheduler serve [--interval 30]     run the scheduler loop

  memstream mem search <query> [--limit 10]     search memory
  memstream mem ingest --source claude_code     pull new sessions into raw lake
  memstream mem distill [--limit 10]            distill raw modules
  memstream mem fold <daily|weekly|monthly>     produce a period summary
  memstream mem brief                           print SessionStart brief
  memstream mem note --title "X" --content "Y"  add a manual memory note
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .core import config, db
from .llm import base as llm_base
from .memory import distill, fold, ingest, recall, search as mem_search
from .skills import registry as skills_registry
from .skills.base import execute as skill_execute
from .tasks import scheduler, store
from .tasks.model import PlanStep, Task


# ---- helpers --------------------------------------------------------------

def _load_spec(path: str) -> dict:
    text = Path(path).read_text()
    if path.endswith((".yaml", ".yml")):
        try:
            import yaml
        except ImportError as e:
            raise SystemExit("PyYAML needed for .yaml specs; pip install pyyaml") from e
        return yaml.safe_load(text)
    return json.loads(text)


def _print_json(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


# ---- command handlers -----------------------------------------------------

def cmd_init(args) -> int:
    p = db.init()
    skills_registry.register_builtins()
    skills_registry.sync_to_db()
    print(f"✅ memstream initialized at {p}")
    print(f"   {len(skills_registry.all_skills())} skills registered")
    return 0


def cmd_skill_list(args) -> int:
    skills_registry.register_builtins()
    for s in skills_registry.all_skills():
        lock = "🔒" if s.privileged else "  "
        print(f"{lock} {s.name:<20} {s.description[:70]}")
    return 0


def cmd_skill_schema(args) -> int:
    skills_registry.register_builtins()
    s = skills_registry.get(args.name)
    if not s:
        print(f"unknown skill: {args.name}", file=sys.stderr)
        return 1
    _print_json(s.describe())
    return 0


def cmd_skill_run(args) -> int:
    skills_registry.register_builtins()
    s = skills_registry.get(args.name)
    if not s:
        print(f"unknown skill: {args.name}", file=sys.stderr)
        return 1
    kwargs = json.loads(args.args or "{}")
    result = skill_execute(s, kwargs)
    _print_json({"ok": result.ok, "output": result.output, "error": result.error})
    return 0 if result.ok else 2


def cmd_task_create(args) -> int:
    spec = _load_spec(args.file)
    plan = [PlanStep.from_dict(s) for s in spec.get("plan", [])]
    t = Task.new(
        title=spec["title"],
        plan=plan,
        goal=spec.get("goal", ""),
        trigger_kind=spec.get("trigger_kind", "manual"),
        trigger_spec=spec.get("trigger_spec", ""),
        priority=spec.get("priority", 3),
        tags=spec.get("tags", []),
        scheduled_at=spec.get("scheduled_at"),
        due_at=spec.get("due_at"),
        source=spec.get("source", "user"),
    )
    if t.trigger_kind == "cron":
        from datetime import datetime as dt
        nxt = scheduler.compute_next_run(t, dt.now())
        t.next_run = nxt
    elif t.trigger_kind == "due" and t.due_at:
        t.next_run = t.due_at
    store.save(t)
    print(f"✅ task created: {t.id}")
    if t.next_run:
        print(f"   next_run: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(t.next_run))}")
    return 0


def cmd_task_list(args) -> int:
    tasks = store.list_tasks(status=args.status, limit=args.limit)
    if not tasks:
        print("(no tasks)")
        return 0
    for t in tasks:
        nxt = time.strftime("%m-%d %H:%M", time.localtime(t.next_run)) if t.next_run else "---"
        print(f"{t.id}  [{t.status:<9}] pri={t.priority} next={nxt}  {t.title[:50]}")
    return 0


def cmd_task_get(args) -> int:
    t = store.get(args.id)
    if not t:
        print(f"task {args.id} not found", file=sys.stderr)
        return 1
    run = store.last_run(args.id)
    data = {
        "id": t.id, "title": t.title, "status": t.status,
        "trigger": {"kind": t.trigger_kind, "spec": t.trigger_spec},
        "priority": t.priority, "tags": t.tags,
        "plan": [s.to_dict() for s in t.plan],
        "next_run": t.next_run, "last_run": t.last_run,
        "run_count": t.run_count,
    }
    if run:
        data["last_run_detail"] = {
            "status": run.status, "error": run.error,
            "finished_at": run.finished_at,
            "output_keys": list(run.output.keys()),
            "steps": len(run.skill_trace),
        }
    _print_json(data)
    return 0


def cmd_task_run(args) -> int:
    from .tasks.executor import execute_plan
    t = store.get(args.id)
    if not t:
        print(f"task {args.id} not found", file=sys.stderr)
        return 1
    skills_registry.register_builtins()
    run = execute_plan(t)
    store.record_run(run)
    print(f"status: {run.status}  error: {run.error or '—'}")
    for trace in run.skill_trace:
        ok = "✅" if trace.get("ok") else ("⏭️" if trace.get("skipped") else "❌")
        print(f"  {ok} step={trace.get('step')} skill={trace.get('skill')} "
              f"duration_ms={trace.get('duration_ms', 0)}")
    return 0 if run.status == "success" else 2


def cmd_task_cancel(args) -> int:
    t = store.get(args.id)
    if not t:
        return 1
    t.status = "cancelled"
    t.next_run = None
    store.save(t)
    print(f"✅ cancelled {args.id}")
    return 0


def cmd_scheduler_serve(args) -> int:
    skills_registry.register_builtins()
    print(f"🟢 scheduler running (interval={args.interval}s) — Ctrl-C to stop")
    scheduler.serve(interval=args.interval)
    return 0


def cmd_mem_search(args) -> int:
    hits = mem_search.search(args.query, limit=args.limit, category=args.category)
    if not hits:
        print("(no match)")
        return 0
    for h in hits:
        print(f"⚡{h['score']}  📅 {h['date']} ({h['days_ago']}d)  [{h.get('category') or '?'}]")
        print(f"   {h['title']}")
        if h['summary']:
            print(f"   💬 {h['summary'][:140]}")
        print()
    return 0


def cmd_mem_ingest(args) -> int:
    if args.source == "claude_code":
        ig = ingest.ClaudeCodeIngester()
    else:
        print(f"unknown source: {args.source}", file=sys.stderr)
        return 1
    n = ingest.run_ingester(ig)
    print(f"✅ ingested {n} new module(s)")
    return 0


def cmd_mem_distill(args) -> int:
    n = distill.distill_raw(limit=args.limit)
    print(f"✅ distilled {n} module(s)")
    return 0


def cmd_mem_fold(args) -> int:
    {"daily": fold.fold_daily, "weekly": fold.fold_weekly,
     "monthly": fold.fold_monthly}[args.level]()
    print(f"✅ folded {args.level}")
    return 0


def cmd_mem_brief(args) -> int:
    text = recall.brief()
    if not text:
        print("(no foldings yet)")
        return 0
    print(text)
    return 0


def cmd_mem_note(args) -> int:
    skills_registry.register_builtins()
    s = skills_registry.get("mem.write_note")
    result = skill_execute(s, {"title": args.title, "content": args.content,
                                "category": args.category, "tags": args.tag or []})
    if result.ok:
        print(f"✅ note created: {result.output.get('id')}")
        return 0
    print(f"❌ {result.error}", file=sys.stderr)
    return 1


# ---- entry point ----------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="memstream",
                                  description="Personal AI OS kernel.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="initialize memstream state directory + DB")

    # skill
    p_skill = sub.add_parser("skill")
    ss = p_skill.add_subparsers(dest="sub", required=True)
    ss.add_parser("list")
    ps = ss.add_parser("schema"); ps.add_argument("name")
    pr = ss.add_parser("run")
    pr.add_argument("name"); pr.add_argument("--args", default="{}")

    # task
    p_task = sub.add_parser("task")
    ts = p_task.add_subparsers(dest="sub", required=True)
    pc = ts.add_parser("create"); pc.add_argument("--file", required=True)
    pl = ts.add_parser("list"); pl.add_argument("--status"); pl.add_argument("--limit", type=int, default=50)
    pg = ts.add_parser("get"); pg.add_argument("id")
    pru = ts.add_parser("run"); pru.add_argument("id")
    pca = ts.add_parser("cancel"); pca.add_argument("id")

    # scheduler
    p_sched = sub.add_parser("scheduler")
    sch = p_sched.add_subparsers(dest="sub", required=True)
    ssrv = sch.add_parser("serve"); ssrv.add_argument("--interval", type=float, default=30)

    # mem
    p_mem = sub.add_parser("mem")
    ms = p_mem.add_subparsers(dest="sub", required=True)
    ps2 = ms.add_parser("search"); ps2.add_argument("query")
    ps2.add_argument("--limit", type=int, default=10); ps2.add_argument("--category")
    pin = ms.add_parser("ingest"); pin.add_argument("--source", default="claude_code")
    pdi = ms.add_parser("distill"); pdi.add_argument("--limit", type=int, default=10)
    pfo = ms.add_parser("fold"); pfo.add_argument("level", choices=["daily", "weekly", "monthly"])
    ms.add_parser("brief")
    pn = ms.add_parser("note")
    pn.add_argument("--title", required=True); pn.add_argument("--content", required=True)
    pn.add_argument("--category"); pn.add_argument("--tag", action="append")

    return ap


HANDLERS = {
    ("init", None):        cmd_init,
    ("skill", "list"):     cmd_skill_list,
    ("skill", "schema"):   cmd_skill_schema,
    ("skill", "run"):      cmd_skill_run,
    ("task", "create"):    cmd_task_create,
    ("task", "list"):      cmd_task_list,
    ("task", "get"):       cmd_task_get,
    ("task", "run"):       cmd_task_run,
    ("task", "cancel"):    cmd_task_cancel,
    ("scheduler", "serve"): cmd_scheduler_serve,
    ("mem", "search"):     cmd_mem_search,
    ("mem", "ingest"):     cmd_mem_ingest,
    ("mem", "distill"):    cmd_mem_distill,
    ("mem", "fold"):       cmd_mem_fold,
    ("mem", "brief"):      cmd_mem_brief,
    ("mem", "note"):       cmd_mem_note,
}


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    key = (args.cmd, getattr(args, "sub", None))
    handler = HANDLERS.get(key)
    if not handler:
        ap.print_help()
        return 1
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
