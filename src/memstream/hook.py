"""memstream hook — generate SessionStart hook script for Claude Code / similar.

The hook injects the memstream recall brief at agent start so the LLM begins
each session with time-stream context already loaded.
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path


SCRIPT = """#!/usr/bin/env bash
# memstream SessionStart hook — injects recent folding brief as additionalContext.

BRIEF=$(timeout 10 memstream mem brief 2>/dev/null || true)

python3 - "$BRIEF" <<'PYEOF'
import json, sys
brief = sys.argv[1].strip()
ctx = brief if brief else ''
print(json.dumps({
    'hookSpecificOutput': {
        'hookEventName': 'SessionStart',
        'additionalContext': ctx,
    }
}, ensure_ascii=False))
PYEOF
exit 0
"""


def install(target_dir: str | Path | None = None) -> Path:
    """Write the hook script to ``target_dir/memstream-hook.sh``.

    Default target = ``~/.claude/hooks/`` (Claude Code convention).
    """
    target_dir = Path(target_dir) if target_dir else (Path.home() / ".claude" / "hooks")
    target_dir.mkdir(parents=True, exist_ok=True)
    p = target_dir / "memstream-hook.sh"
    p.write_text(SCRIPT)
    p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return p


def settings_snippet(hook_path: str | Path | None = None) -> dict:
    """Return a Claude Code settings.json snippet to register the hook."""
    p = str(hook_path or (Path.home() / ".claude" / "hooks" / "memstream-hook.sh"))
    return {
        "hooks": {
            "SessionStart": [
                {"hooks": [{"type": "command", "command": f"bash {p}"}]}
            ]
        }
    }
