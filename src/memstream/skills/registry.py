"""Skill registry — single source of truth for what skills exist."""
from __future__ import annotations

import json
from typing import Any

from ..core.db import get_conn
from .base import Skill


# In-memory registry; populated via register_builtins() at startup.
_REGISTRY: dict[str, Skill] = {}


def register(skill: Skill) -> None:
    _REGISTRY[skill.name] = skill


def get(name: str) -> Skill | None:
    return _REGISTRY.get(name)


def all_skills() -> list[Skill]:
    return list(_REGISTRY.values())


def sync_to_db() -> None:
    """Persist registry metadata to the skills table.

    Lets LLMs query memstream.api.list_skills() via CLI without loading Python.
    """
    conn = get_conn()
    for skill in _REGISTRY.values():
        conn.execute(
            """INSERT INTO skills (name, description, input_schema, output_schema, privileged)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET
                 description = excluded.description,
                 input_schema = excluded.input_schema,
                 output_schema = excluded.output_schema,
                 privileged = excluded.privileged""",
            (
                skill.name,
                skill.description,
                json.dumps(skill.input_schema, ensure_ascii=False),
                json.dumps(skill.output_schema, ensure_ascii=False),
                1 if skill.privileged else 0,
            ),
        )
    conn.commit()
    conn.close()


def register_builtins() -> None:
    """Register all skills that ship with memstream v0.1."""
    # Local imports to keep the registry module lightweight.
    from . import notify, http, mem, shell, file, llm_skill, digest
    register(notify.NotifySkill())
    register(http.HttpGetSkill())
    register(http.HttpPostSkill())
    register(mem.MemSearchSkill())
    register(mem.MemWriteNoteSkill())
    register(mem.MemConditionSkill())
    register(shell.ShellRunSkill())
    register(file.FileReadSkill())
    register(file.FileWriteSkill())
    register(llm_skill.LlmCompleteSkill())
    register(digest.DigestAssignIdsSkill())
    register(digest.DigestScoreSkill())
    register(digest.DigestHistorySkill())
