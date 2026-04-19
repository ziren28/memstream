"""WX (微信 iLink Bot) channel adapter.

Reads bot credentials from a state JSON file (shape compatible with paipai):

```
{
  "bot_token": "...",
  "base_url": "https://ilinkai.weixin.qq.com",
  "owner_user_id": "..."
}
```

Path is resolved from ``MEMSTREAM_WX_STATE`` env var; default is
``~/.memstream/wx_state.json``.
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

import httpx

from ..core.config import data_dir
from .base import Channel


class WxChannel(Channel):
    name = "wx"
    direction = "bidir"

    def __init__(self, state_path: str | Path | None = None):
        if state_path is None:
            state_path = os.environ.get("MEMSTREAM_WX_STATE") or (data_dir() / "wx_state.json")
        self.state_path = Path(state_path)

    def _state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            raise FileNotFoundError(f"wx state missing: {self.state_path}")
        return json.loads(self.state_path.read_text())

    def send(self, user: str, text: str, **kwargs: Any) -> bool:
        st = self._state()
        token = st["bot_token"]
        base = st["base_url"].rstrip("/")
        to = user or st.get("owner_user_id")
        if not to:
            return False
        body = {"msg": {
            "from_user_id": "",
            "to_user_id": to,
            "client_id": f"memstream-{uuid.uuid4().hex[:10]}",
            "message_type": 2, "message_state": 2,
            "item_list": [{"type": 1, "text_item": {"text": text[:3900]}}],
        }}
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "AuthorizationType": "ilink_bot_token",
        }
        try:
            r = httpx.post(f"{base}/ilink/bot/sendmessage",
                           json=body, headers=headers, timeout=15)
            return r.status_code == 200
        except Exception:
            return False
