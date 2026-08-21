"""Simple JSON-based state persistence for tracking sync progress."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from . import config


def load() -> dict:
    if config.STATE_FILE.exists():
        return json.loads(config.STATE_FILE.read_text())
    return {}


def save(state: dict):
    config.STATE_FILE.write_text(json.dumps(state, indent=2, default=str))


def get_last_sync(source: str) -> datetime:
    """Get the last sync time for a source, defaulting to 30 days ago."""
    data = load()
    ts = data.get(f"{source}_last_sync")
    if ts:
        return datetime.fromisoformat(ts)
    return datetime.now(timezone.utc) - timedelta(days=30)


def set_last_sync(source: str, dt: datetime):
    data = load()
    data[f"{source}_last_sync"] = dt.isoformat()
    save(data)
