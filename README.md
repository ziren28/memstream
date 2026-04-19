# memstream

**Personal AI OS kernel** — time-stream memory + task scheduler + skill registry. LLM-pluggable, offline-tolerant.

> memstream is the *reliable base layer* for personal AI agents. It keeps remembering, scheduling, and executing even when your LLM is offline, rate-limited, or swapped out for a different model.

## 🎯 Why

Most AI agent systems die when the LLM goes down. memstream flips the dependency:

```
  user ↔ [WX/TG/Email/Webhook]  ↔  memstream  ↔  hands (skills)  ↔  world
                                       ↕
                                     LLM (optional UX layer)
```

- **memstream is always running** — scheduled tasks fire, reminders push, data gets archived.
- **LLM is an optional tenant** — Claude / GPT / Llama all speak the same schema; swap freely.
- **Permission boundary** — the LLM can write tasks and notes; it can't rewrite the kernel.

## 🧱 Four core primitives

| Primitive | Purpose |
|-----------|---------|
| **Record** | append-only event stream (your time-stream memory) |
| **Task**   | future intentions + declarative skill plan + cron/due trigger |
| **Skill**  | schema-defined atomic operation (notify, http, shell, …) |
| **Channel**| direct I/O to the user (WX, Telegram, Email, webhook) |

## 🚀 Install (once published)

```bash
pip install memstream
memstream init
memstream skill list
memstream task create --file my-task.yaml
memstream scheduler serve
```

## 📐 Status

`v0.1.0` — alpha. Bootstrap built on 2026-04-19.

## 📜 Heritage

memstream extracts and generalizes the memory system originally built inside
[paipai](https://github.com/ziren28/claude_paipai) (2026-04-19 sessions). Inspired by:

- [AI 时间流全息记忆系统脑图](https://mydemo-5eq.pages.dev/) — time-stream architecture
- Event Sourcing / CQRS patterns
- Kahneman's System 1 / System 2 — mechanical vs LLM hands
- Unix/Postgres privilege model — kernel vs userspace

## 📄 License

MIT © 2026 ziren28
