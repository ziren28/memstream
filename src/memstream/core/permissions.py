"""Permission layer — what the LLM (and external API clients) may touch.

v0.1 is single-tenant; we rely on a single ``role`` per caller:

  * ``root``     — full access (admin CLI, human operator)
  * ``llm``      — may create/cancel tasks, write notes, read everything
  * ``observer`` — read-only (for dashboards)

Enforcement points:
  * CLI: ``memstream`` is ``root`` by default; pass ``--role llm`` to restrict.
  * Future: HTTP/MCP server will derive the role from the API token.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Permission:
    resource: str
    verb: str


# What each role is allowed to do. Anything not listed is denied.
ROLE_RULES: dict[str, set[Permission]] = {
    "root": set(),  # wildcard — see is_allowed()
    "llm": {
        Permission("task", "create"),
        Permission("task", "run"),
        Permission("task", "cancel"),
        Permission("task", "update_own"),
        Permission("task", "read"),
        Permission("module", "read"),
        Permission("module", "search"),
        Permission("module", "write_note"),
        Permission("folding", "read"),
        Permission("skill", "list"),
        Permission("skill", "schema"),
    },
    "observer": {
        Permission("task", "read"),
        Permission("module", "read"),
        Permission("module", "search"),
        Permission("folding", "read"),
        Permission("skill", "list"),
    },
}


def current_role() -> str:
    return os.environ.get("MEMSTREAM_ROLE", "root").lower()


def is_allowed(resource: str, verb: str, role: str | None = None) -> bool:
    role = role or current_role()
    if role == "root":
        return True
    return Permission(resource, verb) in ROLE_RULES.get(role, set())


def require(resource: str, verb: str, role: str | None = None) -> None:
    if not is_allowed(resource, verb, role):
        raise PermissionError(
            f"role '{role or current_role()}' is not allowed to {verb} {resource}"
        )
