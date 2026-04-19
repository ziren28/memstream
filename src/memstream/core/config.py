"""memstream config & XDG paths."""
from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    """Return XDG data directory, fall back to ~/.memstream."""
    env = os.environ.get("MEMSTREAM_DIR")
    if env:
        p = Path(env)
    else:
        xdg = os.environ.get("XDG_DATA_HOME")
        p = (Path(xdg) / "memstream") if xdg else (Path.home() / ".memstream")
    p.mkdir(parents=True, exist_ok=True)
    return p


def db_path() -> Path:
    return data_dir() / "memstream.db"


def raw_dir() -> Path:
    p = data_dir() / "raw"
    p.mkdir(parents=True, exist_ok=True)
    return p


def load_env(path: Path | str | None = None) -> dict[str, str]:
    """Load KEY=VALUE lines from a .env file into a dict (and os.environ).

    Does not overwrite already-set env vars.
    """
    env: dict[str, str] = {}
    path = Path(path) if path else (data_dir() / ".env")
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        env[k] = v
        os.environ.setdefault(k, v)
    return env
