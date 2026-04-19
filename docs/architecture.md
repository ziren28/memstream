# memstream architecture

```
          ┌─ WX / TG / Email / Webhook ─┐
          │  (direct channels, always on) │
          ▼                              ▼
        user ◀────── memstream gateway ──────▶ user
                         │
                     ┌───┴──────┐
                     ▼          ▼
                  memory    skills ◀────── LLM (optional)
                     │          │              (claude_cli /
                     │          ▼               anthropic_api /
                     │   mechanical hands       ollama / null)
                     │   (http, shell, file,
                     │    notify, mem.*,
                     │    condition, chain)
                     │
                     └──── L3 raw lake
                           (local + R2/S3 future)
```

## The four primitives

**Record** (`modules`, `events`, `foldings`) — append-only time-stream memory.
Modules represent bounded episodes (a session, a message batch, a reasoning trace).
Foldings roll many modules into daily/weekly/monthly summaries.

**Task** (`tasks`, `task_runs`) — declarative future intentions.
A Task has a *trigger* (cron/due/manual/signal) and a *plan* — an ordered list of
skill invocations with optional conditionals. Execution is deterministic and logged.

**Skill** (`skills`) — atomic, schema-described operations.
Each skill declares its `input_schema` and `output_schema` so an external LLM can
compose plans without hallucinating. Skills never invoke LLMs themselves; that
keeps the executor deterministic and debuggable. System 2 (LLM) is a Skill too,
added as a plugin in v0.2+.

**Channel** (`channels`) — pluggable user I/O adapters. `wx`, `tg`, `email`, `webhook`.

## Why the LLM is optional

Traditional agent systems treat the LLM as the kernel. memstream flips that:
the kernel is the scheduler + memory store; the LLM is a **tenant**. Triggered
tasks fire whether the LLM is online or not. New natural-language requests from
users go through:

1. A rule-based fallback parser (`/help`, `/task`, `/search`, `/note`, `/brief`)
2. The LLM (if available) via an adapter
3. Queued message ("LLM offline, will reply once it's back")

This lets memstream survive LLM outages, rate-limits, and model swaps.

## The LLM contract

When present, the LLM sees memstream as a JSON-schema-driven API:

| Call                    | Role permission | Purpose                              |
|-------------------------|-----------------|--------------------------------------|
| `list_skills()`         | any             | Enumerate available skills + schemas |
| `get_skill(name)`       | any             | Return one skill's schema            |
| `create_task(spec)`     | `llm`           | Create a new task                    |
| `list_tasks(...)`       | `llm`           | Query tasks                          |
| `get_task(id)`          | `llm`           | Retrieve one task + latest run       |
| `cancel_task(id)`       | `llm`           | Cancel a pending task                |
| `search_memory(query)`  | `llm`           | Time-weighted search                 |
| `add_memory_note(...)`  | `llm`           | Write a manual note                  |

The LLM cannot:
- Modify skill definitions or handler code
- Write to `modules` rows with `status='distilled'/'folded'` (history is immutable)
- Change role rules or credentials
- Cross-user data (multi-tenant future)

## Data flow

**Creating a task (user dictates, LLM composes)**

```
user ─► LLM adapter ─► LLM reads list_skills() ─► LLM emits task YAML ─►
  memstream.core validates ─► store.save() ─► scheduler sees next_run ─►
  when due, executor runs plan ─► skill results stored ─►
  next user query reads back via search_memory
```

**Memory pipeline (hourly, autonomous)**

```
Claude sessions ─► ingest.py ─► raw lake + module rows (status=raw)
                            ─► distill.py calls LLM ─► module rows (status=distilled)
                            ─► fold.py rolls up ─► foldings rows
                            ─► recall.brief() feeds SessionStart hook
```

## See also

- [`README.md`](../README.md) — overview + install
- [`CHANGELOG.md`](../CHANGELOG.md) — release notes
- [`systemd/README.md`](../systemd/README.md) — deployment
- [`examples/`](../examples/) — starter task specs
