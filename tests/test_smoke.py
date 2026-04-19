"""Smoke tests — ensure the four core primitives wire together end-to-end."""
from __future__ import annotations

import os
import tempfile

import pytest


@pytest.fixture(autouse=True)
def isolated_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("MEMSTREAM_DIR", str(tmp_path))
    # Ensure any cached modules pick up the fresh dir
    for mod in list(os.sys.modules):
        if mod.startswith("memstream"):
            os.sys.modules.pop(mod, None)
    yield


def test_init_creates_schema():
    from memstream.core import db
    p = db.init()
    assert p.exists()
    conn = db.get_conn()
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    conn.close()
    for expected in ("modules", "events", "foldings", "tasks", "task_runs",
                     "skills", "channels"):
        assert expected in tables


def test_skills_registered():
    from memstream.core import db
    from memstream.skills import registry
    db.init()
    registry.register_builtins()
    names = {s.name for s in registry.all_skills()}
    for expected in ("notify", "http.get", "mem.search", "mem.condition",
                     "mem.write_note", "shell.run"):
        assert expected in names


def test_notify_stdout_roundtrip(capsys):
    from memstream.core import db
    from memstream.skills import registry
    from memstream.skills.base import execute
    db.init()
    registry.register_builtins()
    r = execute(registry.get("notify"), {"channel": "stdout", "text": "hi"})
    captured = capsys.readouterr()
    assert r.ok
    assert "hi" in captured.out


def test_task_create_and_run():
    from memstream.core import db
    from memstream.skills import registry
    from memstream.tasks import store
    from memstream.tasks.model import PlanStep, Task
    from memstream.tasks.executor import execute_plan
    db.init()
    registry.register_builtins()
    t = Task.new(
        title="smoke",
        plan=[
            PlanStep(skill="notify", args={"channel": "stdout", "text": "x"}),
        ],
    )
    store.save(t)
    assert store.get(t.id) is not None
    run = execute_plan(t)
    assert run.status == "success"


def test_mem_condition_branching():
    from memstream.core import db
    from memstream.skills import registry
    from memstream.skills.base import execute
    db.init()
    registry.register_builtins()
    r = execute(registry.get("mem.condition"),
                {"expr": "1 < 2"})
    assert r.ok and r.output["result"] is True
    r2 = execute(registry.get("mem.condition"),
                 {"expr": "foo['bar'] == 1", "context": {"foo": {"bar": 1}}})
    assert r2.ok and r2.output["result"] is True


def test_cron_parser():
    from datetime import datetime
    from memstream.tasks.scheduler import cron_matches, next_cron_run
    assert cron_matches("0 9 * * 1", datetime(2026, 4, 20, 9, 0))   # Mon 09:00
    assert not cron_matches("0 9 * * 1", datetime(2026, 4, 20, 9, 1))
    assert next_cron_run("0 9 * * 1", datetime(2026, 4, 19, 0, 0)) == datetime(2026, 4, 20, 9, 0)


def test_fallback_parser():
    from memstream.core import db
    from memstream.llm.parser import parse
    db.init()
    reply = parse("/help")
    assert reply and "/help" in reply
    assert parse("not a command") is None
