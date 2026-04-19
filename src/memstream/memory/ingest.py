"""Ingesters — pull raw conversations/messages into the L3 raw lake + L2 index.

v0.1 ships with two built-in ingesters:
  * ``claude_code``: reads ``~/.claude/projects/**/*.jsonl`` sessions
  * ``jsonl_dir``: generic directory of JSONL files

Each ingester knows how to:
  1. Discover source records (files in some directory).
  2. Extract lightweight metadata (start/end timestamps, title hint).
  3. Copy raw content to the configured raw lake (local dir by default).
  4. Upsert a row in ``modules`` with status='raw'.

Distillation (memstream.memory.distill) turns 'raw' → 'distilled'.
"""
from __future__ import annotations

import abc
import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from ..core.config import raw_dir
from ..core.db import get_conn


@dataclass
class IngestResult:
    module_id: str
    source: str
    start_ts: float
    end_ts: float | None
    title_hint: str
    event_count: int
    raw_pointer: str


class Ingester(abc.ABC):
    name: str = ""

    @abc.abstractmethod
    def discover(self) -> Iterator[Path]:
        ...

    @abc.abstractmethod
    def parse(self, path: Path) -> IngestResult | None:
        ...

    def copy_to_lake(self, source: Path, module_id: str) -> str:
        dest = raw_dir() / self.name / f"{module_id}.jsonl"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(source, dest)
        return str(dest)


class ClaudeCodeIngester(Ingester):
    name = "claude_code"

    def __init__(self, root: Path | str | None = None):
        self.root = Path(root) if root else (Path.home() / ".claude" / "projects")

    def discover(self) -> Iterator[Path]:
        if not self.root.exists():
            return
        for p in self.root.rglob("*.jsonl"):
            yield p

    def parse(self, path: Path) -> IngestResult | None:
        session_id = path.stem
        start_ts = end_ts = None
        first_user_text = ""
        event_count = 0
        try:
            with open(path) as f:
                for line in f:
                    try:
                        e = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    event_count += 1
                    ts = e.get("timestamp") or e.get("ts")
                    if isinstance(ts, str):
                        try:
                            ts = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                        except Exception:
                            ts = None
                    if ts:
                        if start_ts is None or ts < start_ts: start_ts = ts
                        if end_ts is None or ts > end_ts: end_ts = ts
                    if not first_user_text and e.get("type") == "user":
                        msg = e.get("message", {})
                        if isinstance(msg, dict):
                            c = msg.get("content", "")
                            if isinstance(c, str):
                                first_user_text = c[:120]
                            elif isinstance(c, list):
                                for b in c:
                                    if isinstance(b, dict) and b.get("type") == "text":
                                        first_user_text = b.get("text", "")[:120]
                                        break
        except Exception:
            return None
        if start_ts is None:
            start_ts = path.stat().st_mtime
            end_ts = start_ts

        copied = self.copy_to_lake(path, session_id)
        return IngestResult(
            module_id=session_id, source=self.name,
            start_ts=start_ts, end_ts=end_ts,
            title_hint=first_user_text or f"session {session_id[:8]}",
            event_count=event_count, raw_pointer=copied,
        )


def run_ingester(ingester: Ingester) -> int:
    conn = get_conn()
    n = 0
    for path in ingester.discover():
        result = ingester.parse(path)
        if not result:
            continue
        existing = conn.execute(
            "SELECT status FROM modules WHERE id = ?", (result.module_id,),
        ).fetchone()
        if existing and existing["status"] in ("distilled", "folded"):
            continue
        conn.execute(
            """INSERT INTO modules (id, source, start_ts, end_ts, title, raw_pointer, status, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, 'raw', strftime('%s','now'))
               ON CONFLICT(id) DO UPDATE SET
                 end_ts = excluded.end_ts,
                 raw_pointer = excluded.raw_pointer,
                 updated_at = strftime('%s','now')""",
            (result.module_id, result.source, result.start_ts,
             result.end_ts, result.title_hint, result.raw_pointer),
        )
        n += 1
    conn.commit()
    conn.close()
    return n
