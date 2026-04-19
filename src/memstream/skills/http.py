"""http — fetch URLs (GET/POST) with size + timeout guardrails."""
from __future__ import annotations

from typing import Any

import httpx

from .base import Skill, SkillResult


MAX_BYTES = 10 * 1024 * 1024  # 10 MB safety cap


class HttpGetSkill(Skill):
    name = "http.get"
    description = "GET an HTTP URL and return body (text) + status."
    input_schema = {
        "type": "object",
        "required": ["url"],
        "properties": {
            "url": {"type": "string", "format": "uri"},
            "headers": {"type": "object"},
            "timeout": {"type": "number", "default": 20},
            "max_bytes": {"type": "integer", "default": MAX_BYTES},
        },
    }
    output_schema = {
        "type": "object",
        "properties": {
            "status": {"type": "integer"},
            "body": {"type": "string"},
            "headers": {"type": "object"},
            "truncated": {"type": "boolean"},
        },
    }
    tags = ["io", "fetch"]

    def run(self, **kwargs: Any) -> SkillResult:
        url = kwargs["url"]
        headers = kwargs.get("headers") or {}
        timeout = kwargs.get("timeout", 20)
        max_bytes = kwargs.get("max_bytes", MAX_BYTES)
        try:
            r = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
            body = r.content[:max_bytes].decode("utf-8", errors="replace")
            return SkillResult(ok=True, output={
                "status": r.status_code, "body": body,
                "headers": dict(r.headers),
                "truncated": len(r.content) > max_bytes,
            })
        except Exception as e:
            return SkillResult(ok=False, output={"status": 0, "body": ""}, error=str(e))


class HttpPostSkill(Skill):
    name = "http.post"
    description = "POST JSON or form data to an HTTP URL."
    input_schema = {
        "type": "object",
        "required": ["url"],
        "properties": {
            "url": {"type": "string", "format": "uri"},
            "json": {"type": "object"},
            "data": {"type": "object"},
            "headers": {"type": "object"},
            "timeout": {"type": "number", "default": 20},
        },
    }
    output_schema = HttpGetSkill.output_schema
    tags = ["io", "fetch"]

    def run(self, **kwargs: Any) -> SkillResult:
        url = kwargs["url"]
        payload_json = kwargs.get("json")
        payload_data = kwargs.get("data")
        headers = kwargs.get("headers") or {}
        timeout = kwargs.get("timeout", 20)
        try:
            r = httpx.post(url, json=payload_json, data=payload_data,
                           headers=headers, timeout=timeout, follow_redirects=True)
            body = r.content[:MAX_BYTES].decode("utf-8", errors="replace")
            return SkillResult(ok=True, output={
                "status": r.status_code, "body": body,
                "headers": dict(r.headers),
                "truncated": len(r.content) > MAX_BYTES,
            })
        except Exception as e:
            return SkillResult(ok=False, output={"status": 0, "body": ""}, error=str(e))
