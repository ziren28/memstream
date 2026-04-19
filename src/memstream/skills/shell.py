"""shell — run a command via subprocess.

⚠️ This skill is ``privileged=True`` because arbitrary shell execution is a
kernel-level capability. Task authors should set a strict command allow-list
in config before enabling it in LLM-driven plans.
"""
from __future__ import annotations

import os
import subprocess
from typing import Any

from .base import Skill, SkillResult


class ShellRunSkill(Skill):
    name = "shell.run"
    description = "Run a shell command and capture stdout/stderr. Privileged."
    input_schema = {
        "type": "object",
        "required": ["cmd"],
        "properties": {
            "cmd": {"type": "string"},
            "timeout": {"type": "number", "default": 30},
            "cwd": {"type": "string"},
            "env": {"type": "object"},
        },
    }
    output_schema = {
        "type": "object",
        "properties": {
            "returncode": {"type": "integer"},
            "stdout": {"type": "string"},
            "stderr": {"type": "string"},
        },
    }
    privileged = True
    tags = ["system"]

    def run(self, **kwargs: Any) -> SkillResult:
        cmd = kwargs["cmd"]
        timeout = kwargs.get("timeout", 30)
        cwd = kwargs.get("cwd")
        env_override = kwargs.get("env") or {}

        env = os.environ.copy()
        env.update(env_override)

        try:
            proc = subprocess.run(
                cmd, shell=True, capture_output=True, text=True,
                timeout=timeout, cwd=cwd, env=env,
            )
            return SkillResult(ok=proc.returncode == 0, output={
                "returncode": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            })
        except subprocess.TimeoutExpired:
            return SkillResult(ok=False, output={"returncode": -1, "stdout": "", "stderr": ""},
                               error=f"timeout after {timeout}s")
        except Exception as e:
            return SkillResult(ok=False, output={"returncode": -1, "stdout": "", "stderr": ""},
                               error=str(e))
