"""LLMAdapter — the pluggable interface for any LLM provider.

Providers MUST implement ``complete(prompt, **kwargs) -> str``. Optional
methods (``stream``, ``tools``, ``embed``) can be added in future versions.

The default adapter is chosen via ``MEMSTREAM_LLM_ADAPTER`` env var:
  ``claude_cli`` (default) | ``null`` | ``anthropic_api`` | ``openai_api``
"""
from __future__ import annotations

import abc
import os
from typing import Any


class LLMAdapter(abc.ABC):
    name: str = ""

    @abc.abstractmethod
    def complete(self, prompt: str, **kwargs: Any) -> str:
        """Return the plain-text completion of the prompt, or '' on failure."""
        raise NotImplementedError

    def ping(self) -> bool:
        """Return True if the adapter is likely operational."""
        try:
            r = self.complete("ping", timeout=10)
            return bool(r and r.strip())
        except Exception:
            return False


class NullAdapter(LLMAdapter):
    """Returns empty strings — use for 'LLM offline' / tests."""
    name = "null"

    def complete(self, prompt: str, **kwargs: Any) -> str:
        return ""


_DEFAULT: LLMAdapter | None = None


def get_default_adapter() -> LLMAdapter:
    global _DEFAULT
    if _DEFAULT is not None:
        return _DEFAULT
    choice = os.environ.get("MEMSTREAM_LLM_ADAPTER", "claude_cli").lower()
    if choice in ("null", "off", "none"):
        _DEFAULT = NullAdapter()
    elif choice in ("claude_cli", "claude"):
        from .claude_cli import ClaudeCliAdapter
        _DEFAULT = ClaudeCliAdapter()
    elif choice in ("anthropic_api", "anthropic"):
        try:
            from .anthropic_api import AnthropicApiAdapter
            _DEFAULT = AnthropicApiAdapter()
        except ImportError:
            _DEFAULT = NullAdapter()
    else:
        _DEFAULT = NullAdapter()
    return _DEFAULT


def set_default_adapter(adapter: LLMAdapter) -> None:
    global _DEFAULT
    _DEFAULT = adapter
