# Changelog

All notable changes to memstream are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
memstream follows [semantic versioning](https://semver.org/).

## [0.1.0] — 2026-04-19

First public release. Ships the four core primitives and a CLI.

### Added

- **Core**
  - SQLite schema for `modules`, `events`, `foldings`, `tasks`, `task_runs`,
    `skills`, `channels` (+ FTS5 table for future use).
  - XDG-friendly data dir (`~/.memstream` by default; `MEMSTREAM_DIR` override).
  - Three-role permission layer (`root` / `llm` / `observer`).
- **Memory (Record primitive)**
  - `ClaudeCodeIngester` — imports `~/.claude/projects/**/*.jsonl`.
  - LLM-adapter driven distillation with strict JSON contract.
  - Daily / weekly / monthly folding.
  - CJK-friendly time-weighted LIKE search (exp decay, 20d half-life default).
- **Tasks (Task primitive)**
  - Task/PlanStep/TaskRun dataclasses, full CRUD.
  - Plan executor with template substitution (`{{ref.path}}`) and conditional
    steps (`if:` via `mem.condition`).
  - Minimal 5-field cron parser; `due` and `manual` triggers.
  - Scheduler daemon loop (`memstream scheduler serve`).
- **Skills (Skill primitive)**
  - Registry with JSON-schema describe().
  - Built-ins: `notify`, `http.get`, `http.post`, `mem.search`,
    `mem.write_note`, `mem.condition`, `shell.run` (privileged),
    `file.read`, `file.write` (privileged).
- **Channels (Channel primitive)**
  - ABC in `memstream.channels.base`.
  - `wx` adapter compatible with the paipai iLink Bot state format.
- **LLM adapters**
  - `ClaudeCliAdapter` (default; uses `claude -p` subprocess).
  - `NullAdapter` for offline-only operation.
  - Hook into distill/fold via `get_default_adapter()`.
- **CLI** (`memstream`)
  - `init`, `skill {list,schema,run}`, `task {create,list,get,run,cancel}`,
    `scheduler serve`, `mem {search,ingest,distill,fold,brief,note}`,
    `parse` (fallback parser), `hook install`.
- **Ops**
  - `systemd/` units for scheduler, ingest, distill, fold.
  - `examples/` — four starter task YAMLs.

### Known limitations

- Vector search not yet implemented (FTS table reserved for v0.2).
- WX adapter requires a state file migrated from paipai; no fresh onboarding yet.
- TG / Email channels are scaffolding only.
