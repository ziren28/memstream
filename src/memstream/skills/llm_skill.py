"""llm.* — make the LLM itself callable from a task plan.

When included, the LLM becomes a "privileged Skill" rather than the kernel
itself. Plans can freely compose System-1 skills (http/file/mem) with
System-2 thinking (llm.complete) while memstream still owns scheduling,
memory, and permissions.
"""
from __future__ import annotations

import json
import re
from typing import Any

from ..llm.base import get_default_adapter
from .base import Skill, SkillResult


class LlmCompleteSkill(Skill):
    name = "llm.complete"
    description = (
        "Send a prompt to the configured LLM adapter and return the text. "
        "Optional `expect_json` parses the first {..} blob from the reply."
    )
    input_schema = {
        "type": "object",
        "required": ["prompt"],
        "properties": {
            "prompt": {"type": "string"},
            "timeout": {"type": "number", "default": 180},
            "expect_json": {"type": "boolean", "default": False},
            "expect_list": {"type": "boolean", "default": False,
                            "description": "Parse first [...] blob instead of {...}"},
        },
    }
    output_schema = {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "parsed": {"description": "Parsed JSON if expect_json/expect_list"},
        },
    }
    privileged = True
    tags = ["llm", "system2"]

    def run(self, **kwargs: Any) -> SkillResult:
        adapter = get_default_adapter()
        prompt = kwargs["prompt"]
        timeout = kwargs.get("timeout", 180)
        try:
            text = adapter.complete(prompt, timeout=timeout)
        except Exception as e:
            return SkillResult(ok=False, output={"text": ""}, error=str(e))

        if not text:
            return SkillResult(ok=False, output={"text": ""}, error="empty LLM response")

        parsed: Any = None
        if kwargs.get("expect_json"):
            m = re.search(r"\{[\s\S]*\}", text)
            if m:
                try:
                    parsed = json.loads(m.group(0))
                except json.JSONDecodeError:
                    pass
        elif kwargs.get("expect_list"):
            m = re.search(r"\[[\s\S]*\]", text)
            if m:
                try:
                    parsed = json.loads(m.group(0))
                except json.JSONDecodeError:
                    pass

        output: dict[str, Any] = {"text": text}
        if parsed is not None:
            output["parsed"] = parsed
        return SkillResult(ok=True, output=output)
