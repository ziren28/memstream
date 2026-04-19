"""notify — push a short message to a user channel.

v0.1 knows two channel kinds: ``stdout`` (for tests) and ``webhook``
(arbitrary HTTP POST). Real WX/TG adapters live in `memstream.channels`.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from .base import Skill, SkillResult


class NotifySkill(Skill):
    name = "notify"
    description = "Push a short text notification to a channel (webhook/stdout)."
    input_schema = {
        "type": "object",
        "required": ["channel", "text"],
        "properties": {
            "channel": {
                "type": "string",
                "description": "Channel identifier: 'stdout', 'webhook:<url>', or a registered channel id.",
            },
            "text": {"type": "string", "maxLength": 4000},
            "priority": {"type": "string", "enum": ["normal", "urgent"], "default": "normal"},
        },
    }
    output_schema = {
        "type": "object",
        "properties": {
            "sent": {"type": "boolean"},
            "channel": {"type": "string"},
            "bytes": {"type": "integer"},
        },
    }
    tags = ["io", "user-facing"]

    def run(self, **kwargs: Any) -> SkillResult:
        channel = kwargs["channel"]
        text = kwargs["text"]

        if channel == "stdout":
            print(text)
            return SkillResult(ok=True, output={"sent": True, "channel": channel, "bytes": len(text)})

        if channel.startswith("webhook:"):
            url = channel[len("webhook:"):]
            try:
                r = httpx.post(url, json={"text": text}, timeout=15)
                r.raise_for_status()
                return SkillResult(ok=True, output={"sent": True, "channel": channel, "bytes": len(text)})
            except Exception as e:
                return SkillResult(ok=False, output={"sent": False, "channel": channel}, error=str(e))

        # Registered named channels (e.g. 'wx:owner', 'tg:main')
        if channel.startswith("wx"):
            from ..channels.wx import WxChannel
            _, _, user = channel.partition(":")
            try:
                ok = WxChannel().send(user, text)
                return SkillResult(ok=ok, output={"sent": ok, "channel": channel, "bytes": len(text)})
            except Exception as e:
                return SkillResult(ok=False, output={"sent": False, "channel": channel}, error=str(e))

        return SkillResult(
            ok=False, output={"sent": False, "channel": channel},
            error=f"unknown channel '{channel}' "
                  f"(v0.1 supports 'stdout', 'webhook:<url>', 'wx[:user_id]')",
        )
