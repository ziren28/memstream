"""Channel — pluggable bi-directional user I/O adapters.

A Channel knows how to:
  * receive messages FROM the user (Inbox behavior, optional)
  * push messages TO the user (Outbox behavior, used by notify skill)

v0.1 ships scaffolding only. v0.2 includes WX (微信 iLink Bot) + TG adapters
extracted from the paipai reference implementation.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any


@dataclass
class InboundMessage:
    id: str
    source: str            # wx / tg / email / webhook / stdout
    user: str              # stable user identifier
    text: str
    context: dict[str, Any]


class Channel(abc.ABC):
    """Abstract Channel — subclasses implement send(). Receive is optional."""
    name: str = ""
    direction: str = "out"   # 'in' / 'out' / 'bidir'

    @abc.abstractmethod
    def send(self, user: str, text: str, **kwargs: Any) -> bool:
        """Push ``text`` to ``user`` via this channel. Return True on success."""
        raise NotImplementedError

    def receive_loop(self) -> None:
        """Optional: run a loop that yields InboundMessage and routes them."""
        raise NotImplementedError(f"{self.name} has no receive_loop")
