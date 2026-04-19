"""ClaudeCliAdapter — call the local ``claude`` CLI (Claude Code's OAuth).

Pros: zero API cost (uses the user's Claude Code subscription), always-fresh
model choice follows CLI updates.

Cons: requires ``claude`` on PATH and an authenticated ``~/.claude/.credentials.json``.
"""
from __future__ import annotations

import subprocess
from typing import Any

from .base import LLMAdapter


class ClaudeCliAdapter(LLMAdapter):
    name = "claude_cli"

    def complete(self, prompt: str, **kwargs: Any) -> str:
        timeout = kwargs.get("timeout", 120)
        try:
            proc = subprocess.run(
                ["claude", "-p", "--output-format", "text"],
                input=prompt, capture_output=True, text=True, timeout=timeout,
            )
        except FileNotFoundError:
            return ""
        except subprocess.TimeoutExpired:
            return ""
        out = proc.stdout or ""
        # Strip intercept banner lines (seen in some CI environments)
        lines = [l for l in out.splitlines() if not l.startswith("[ic v3]")]
        return "\n".join(lines).strip()
