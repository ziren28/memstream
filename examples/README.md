# memstream example tasks

Copy-paste a YAML file, then:

```bash
memstream task create --file examples/rklb_watcher.yaml
memstream task list
memstream task run <id>       # manual trigger
memstream scheduler serve &   # auto-fire when cron matches
```

## Available examples

- `hello.yaml` — push a one-shot notification every day at 09:00
- `fetch_rss.yaml` — hourly: fetch RSS, extract title, store if new
- `stock_watcher.yaml` — conditional: notify only when price drops below threshold
- `nightly_brief.yaml` — 23:00 daily: generate a recall brief and push to stdout

Run them with your own channel (`channel: stdout` for testing, `channel: webhook:https://...` to ping a real endpoint). For WX/TG, wait for the v0.2 channel adapters.
