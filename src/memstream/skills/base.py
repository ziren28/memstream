"""Skill — a schema-defined atomic operation.

A Skill is the smallest unit of work `memstream` can perform without invoking
an LLM. Skills describe themselves with JSON-schema-compatible dicts so that
an external LLM can read the registry and compose plans without hallucinating.
"""
from __future__ import annotations

import abc
import dataclasses
import json
import time
from typing import Any


@dataclasses.dataclass
class SkillResult:
    """Return value from Skill.run()."""
    ok: bool
    output: dict[str, Any]
    error: str | None = None
    started_at: float = dataclasses.field(default_factory=time.time)
    finished_at: float = 0.0

    def to_json(self) -> str:
        return json.dumps(dataclasses.asdict(self), ensure_ascii=False, default=str)


class Skill(abc.ABC):
    """Base class for all Skills."""

    # Subclasses MUST set these.
    name: str = ""                        # e.g. "notify"
    description: str = ""                 # human-readable 1-line summary
    input_schema: dict[str, Any] = {}     # JSON schema for run()'s kwargs
    output_schema: dict[str, Any] = {}    # JSON schema for SkillResult.output
    privileged: bool = False              # True = requires elevated permission
    tags: list[str] = []

    def validate(self, **kwargs: Any) -> None:
        """Cheap validation — check required keys exist. Override for deeper."""
        required = self.input_schema.get("required", [])
        missing = [k for k in required if k not in kwargs]
        if missing:
            raise ValueError(f"{self.name}: missing required args: {missing}")

    @abc.abstractmethod
    def run(self, **kwargs: Any) -> SkillResult:
        """Execute the skill. MUST return a SkillResult.

        Implementations should be *deterministic* and *LLM-free* —
        this is the mechanical layer. For LLM-backed behavior, wrap
        an LLM adapter inside a skill labelled ``privileged=True``.
        """
        raise NotImplementedError

    def describe(self) -> dict[str, Any]:
        """Serialize to the format the LLM / CLI sees."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "privileged": self.privileged,
            "tags": list(self.tags),
        }


def execute(skill: Skill, args: dict[str, Any]) -> SkillResult:
    """Validate + run a skill, always returning a SkillResult (never raise)."""
    started = time.time()
    try:
        skill.validate(**args)
        result = skill.run(**args)
        if result.finished_at == 0.0:
            result.finished_at = time.time()
        return result
    except Exception as e:
        return SkillResult(
            ok=False, output={}, error=f"{type(e).__name__}: {e}",
            started_at=started, finished_at=time.time(),
        )
