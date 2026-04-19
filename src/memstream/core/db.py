"""memstream SQLite schema + connection helper.

Schema covers all four core primitives:
  - records  (modules + events + foldings)  → append-only time stream
  - tasks    (intentions + plans)             → future actions
  - skills   (registry metadata)              → known handlers
  - channels (inbox/outbox adapters)          → user I/O (stub in v0.1)
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .config import db_path


SCHEMA = """
-- ========== Memory (Records) ==========

CREATE TABLE IF NOT EXISTS modules (
    id              TEXT PRIMARY KEY,
    source          TEXT NOT NULL,
    start_ts        REAL NOT NULL,
    end_ts          REAL,
    category        TEXT,
    title           TEXT,
    summary         TEXT,
    tags            TEXT,
    entities        TEXT,
    token_spent     INTEGER DEFAULT 0,
    raw_pointer     TEXT,                 -- local path or s3:// URI
    status          TEXT DEFAULT 'raw',   -- raw / distilled / folded
    folded_into     TEXT,
    created_at      REAL DEFAULT (strftime('%s','now')),
    updated_at      REAL DEFAULT (strftime('%s','now'))
);
CREATE INDEX IF NOT EXISTS idx_modules_start_ts ON modules(start_ts DESC);
CREATE INDEX IF NOT EXISTS idx_modules_category ON modules(category);
CREATE INDEX IF NOT EXISTS idx_modules_status   ON modules(status);

CREATE TABLE IF NOT EXISTS events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    module_id       TEXT REFERENCES modules(id),
    ts              REAL NOT NULL,
    role            TEXT NOT NULL,
    content         TEXT,
    tokens          INTEGER,
    created_at      REAL DEFAULT (strftime('%s','now'))
);
CREATE INDEX IF NOT EXISTS idx_events_module ON events(module_id);
CREATE INDEX IF NOT EXISTS idx_events_ts     ON events(ts DESC);

CREATE TABLE IF NOT EXISTS foldings (
    id              TEXT PRIMARY KEY,     -- e.g. 'daily:2026-04-19'
    level           TEXT NOT NULL,        -- daily / weekly / monthly
    period          TEXT NOT NULL,        -- 2026-04-19 / 2026-W16 / 2026-04
    module_count    INTEGER,
    summary         TEXT,
    key_events      TEXT,                 -- JSON
    token_spent     INTEGER,
    created_at      REAL DEFAULT (strftime('%s','now'))
);
CREATE INDEX IF NOT EXISTS idx_foldings_level_period ON foldings(level, period);

CREATE VIRTUAL TABLE IF NOT EXISTS modules_fts USING fts5(
    id UNINDEXED, title, summary, tags, entities,
    tokenize='unicode61'
);

-- ========== Tasks ==========

CREATE TABLE IF NOT EXISTS tasks (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    goal            TEXT,

    trigger_kind    TEXT NOT NULL,        -- cron / due / signal / manual / chain
    trigger_spec    TEXT,                 -- cron expression / ISO timestamp / JSON

    plan            TEXT NOT NULL,        -- JSON array of skill steps
    result_schema   TEXT,                 -- JSON schema hint

    priority        INTEGER DEFAULT 3,    -- 1=urgent .. 5=low
    status          TEXT DEFAULT 'pending',-- pending / scheduled / running / done / failed / cancelled
    tags            TEXT,

    created_at      REAL DEFAULT (strftime('%s','now')),
    scheduled_at    REAL,
    due_at          REAL,
    next_run        REAL,                 -- when scheduler will fire next
    last_run        REAL,
    run_count       INTEGER DEFAULT 0,

    source          TEXT,                 -- 'user' / 'llm' / 'chain' / 'system'
    linked_module_id TEXT,
    parent_task_id  TEXT,
    notes           TEXT
);
CREATE INDEX IF NOT EXISTS idx_tasks_next_run ON tasks(next_run);
CREATE INDEX IF NOT EXISTS idx_tasks_status   ON tasks(status);

CREATE TABLE IF NOT EXISTS task_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id         TEXT REFERENCES tasks(id),
    started_at      REAL NOT NULL,
    finished_at     REAL,
    status          TEXT NOT NULL,        -- success / failure / partial / cancelled
    output          TEXT,                 -- JSON result
    error           TEXT,
    skill_trace     TEXT                  -- JSON array of per-step records
);
CREATE INDEX IF NOT EXISTS idx_task_runs_task ON task_runs(task_id, started_at DESC);

-- ========== Skills registry ==========

CREATE TABLE IF NOT EXISTS skills (
    name            TEXT PRIMARY KEY,
    description     TEXT,
    input_schema    TEXT,                 -- JSON schema
    output_schema   TEXT,
    privileged      INTEGER DEFAULT 0,    -- 1 = requires elevated permission
    registered_at   REAL DEFAULT (strftime('%s','now'))
);

-- ========== Channels (user I/O adapters) ==========

CREATE TABLE IF NOT EXISTS channels (
    id              TEXT PRIMARY KEY,     -- wx:main / tg:ziren / email:inbox / webhook:slack
    kind            TEXT NOT NULL,        -- wx / tg / email / webhook
    config          TEXT,                 -- JSON, handler-specific
    direction       TEXT NOT NULL,        -- in / out / bidir
    enabled         INTEGER DEFAULT 1,
    created_at      REAL DEFAULT (strftime('%s','now'))
);

-- ========== Digest items + user feedback ==========

CREATE TABLE IF NOT EXISTS digest_items (
    id              TEXT PRIMARY KEY,     -- YYYYMMDD-NNN (date + zero-padded sequence)
    created_at      REAL DEFAULT (strftime('%s','now')),
    source          TEXT,                 -- 'ithome' / 'hn' / 'nodeseek' / ...
    original_url    TEXT,
    title           TEXT,
    summary         TEXT,                 -- LLM's commentary
    tags            TEXT,
    llm_score       INTEGER,              -- 1-10, LLM's judgment of value
    llm_reason      TEXT,                 -- why LLM scored this way
    diversity       INTEGER DEFAULT 0,    -- 1 = included as 'low-value counterweight'
    user_score      INTEGER,              -- 1-10, filled when user scores
    user_score_at   REAL,
    user_note       TEXT,                 -- optional user annotation
    digest_batch    TEXT                  -- timestamp key grouping a digest run
);
CREATE INDEX IF NOT EXISTS idx_digest_items_created ON digest_items(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_digest_items_batch   ON digest_items(digest_batch);
CREATE INDEX IF NOT EXISTS idx_digest_items_user    ON digest_items(user_score);
"""


def get_conn(path: str | Path | None = None) -> sqlite3.Connection:
    """Return a SQLite connection with row factory + FK enabled."""
    p = Path(path) if path else db_path()
    conn = sqlite3.connect(p, timeout=10)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def init(path: str | Path | None = None) -> Path:
    """Create DB + schema. Idempotent."""
    p = Path(path) if path else db_path()
    conn = get_conn(p)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    return p


def reindex_fts(conn: sqlite3.Connection | None = None) -> None:
    """Rebuild modules_fts from modules."""
    close = False
    if conn is None:
        conn = get_conn()
        close = True
    conn.execute("DELETE FROM modules_fts")
    conn.execute(
        """INSERT INTO modules_fts(id, title, summary, tags, entities)
           SELECT id, COALESCE(title,''), COALESCE(summary,''),
                  COALESCE(tags,''), COALESCE(entities,'')
           FROM modules"""
    )
    conn.commit()
    if close:
        conn.close()
