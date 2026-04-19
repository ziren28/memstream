# memstream systemd units

Drop these into `/etc/systemd/system/` (or your distro's equivalent) and enable:

```bash
sudo cp *.service *.timer /etc/systemd/system/
sudo mkdir -p /var/log/memstream
sudo systemctl daemon-reload

# core scheduler (drives all due tasks)
sudo systemctl enable --now memstream-scheduler.service

# memory maintenance timers
sudo systemctl enable --now memstream-ingest.timer
sudo systemctl enable --now memstream-distill.timer
sudo systemctl enable --now memstream-fold.timer
```

## Units

| Unit                       | Kind      | When                  | Purpose                                          |
|----------------------------|-----------|-----------------------|--------------------------------------------------|
| memstream-scheduler        | service   | always                | 30s loop that fires due tasks                    |
| memstream-ingest           | oneshot   | every :45             | import new Claude Code sessions to raw lake      |
| memstream-distill          | oneshot   | hourly                | distill raw modules via LLM adapter              |
| memstream-fold             | oneshot   | daily 01:00 UTC       | daily/weekly/monthly summaries                   |

Logs land in `/var/log/memstream/` by default.

To use a non-default data directory or a different LLM adapter, add a drop-in:

```bash
sudo systemctl edit memstream-scheduler.service
# then add:
# [Service]
# Environment="MEMSTREAM_DIR=/srv/memstream"
# Environment="MEMSTREAM_LLM_ADAPTER=claude_cli"
```
