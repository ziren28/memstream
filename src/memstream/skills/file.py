"""file — read/write plain text files under a configured sandbox root.

By default sandbox root = ``MEMSTREAM_DIR/files/``. Operators can widen this
via ``MEMSTREAM_FILE_ROOTS=/path1:/path2``. Any path outside the allowlist
is rejected.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ..core.config import data_dir
from .base import Skill, SkillResult


def _allowed_roots() -> list[Path]:
    roots = [data_dir() / "files"]
    roots[0].mkdir(parents=True, exist_ok=True)
    extra = os.environ.get("MEMSTREAM_FILE_ROOTS", "")
    for p in extra.split(":"):
        if p.strip():
            roots.append(Path(p.strip()).resolve())
    return roots


def _safe(path: str) -> Path:
    p = Path(path).resolve()
    for root in _allowed_roots():
        try:
            p.relative_to(root)
            return p
        except ValueError:
            continue
    raise PermissionError(f"path {p} not under any allowed root")


class FileReadSkill(Skill):
    name = "file.read"
    description = "Read a text file within the sandbox. Size-capped at 1 MB."
    input_schema = {
        "type": "object",
        "required": ["path"],
        "properties": {
            "path": {"type": "string"},
            "encoding": {"type": "string", "default": "utf-8"},
        },
    }
    output_schema = {
        "type": "object",
        "properties": {"content": {"type": "string"}, "bytes": {"type": "integer"}},
    }
    tags = ["io"]

    def run(self, **kwargs: Any) -> SkillResult:
        try:
            p = _safe(kwargs["path"])
            data = p.read_bytes()
            if len(data) > 1_048_576:
                return SkillResult(ok=False, output={"content": "", "bytes": len(data)},
                                   error="file too large (>1MB)")
            return SkillResult(ok=True, output={
                "content": data.decode(kwargs.get("encoding", "utf-8"), errors="replace"),
                "bytes": len(data),
            })
        except Exception as e:
            return SkillResult(ok=False, output={"content": "", "bytes": 0}, error=str(e))


class FileWriteSkill(Skill):
    name = "file.write"
    description = "Write a text file inside the sandbox (creates parents)."
    input_schema = {
        "type": "object",
        "required": ["path", "content"],
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
            "append": {"type": "boolean", "default": False},
            "encoding": {"type": "string", "default": "utf-8"},
        },
    }
    output_schema = {
        "type": "object",
        "properties": {"bytes": {"type": "integer"}, "path": {"type": "string"}},
    }
    privileged = True
    tags = ["io"]

    def run(self, **kwargs: Any) -> SkillResult:
        try:
            p = _safe(kwargs["path"])
            p.parent.mkdir(parents=True, exist_ok=True)
            content = kwargs["content"]
            mode = "a" if kwargs.get("append") else "w"
            with open(p, mode, encoding=kwargs.get("encoding", "utf-8")) as f:
                f.write(content)
            return SkillResult(ok=True, output={"bytes": len(content.encode()), "path": str(p)})
        except Exception as e:
            return SkillResult(ok=False, output={"bytes": 0, "path": ""}, error=str(e))
