"""Tests for state module — JSON persistence and last-sync tracking."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from src import state


def test_load_empty(tmp_path):
    with patch("src.config.STATE_FILE", tmp_path / "state.json"):
        assert state.load() == {}


def test_save_and_load(tmp_path):
    state_file = tmp_path / "state.json"
    with patch("src.config.STATE_FILE", state_file):
        state.save({"wise_last_sync": "2025-01-01T00:00:00+00:00"})
        assert state_file.exists()

        data = state.load()
        assert data["wise_last_sync"] == "2025-01-01T00:00:00+00:00"


def test_get_last_sync_default(tmp_path):
    with patch("src.config.STATE_FILE", tmp_path / "state.json"):
        result = state.get_last_sync("wise")
        expected_approx = datetime.now(timezone.utc) - timedelta(days=30)
        diff = abs((result - expected_approx).total_seconds())
        assert diff < 5


def test_get_last_sync_saved(tmp_path):
    state_file = tmp_path / "state.json"
    ts = "2025-06-15T12:00:00+00:00"
    state_file.write_text(json.dumps({"wise_last_sync": ts}))

    with patch("src.config.STATE_FILE", state_file):
        result = state.get_last_sync("wise")
        assert result == datetime.fromisoformat(ts)


def test_set_last_sync(tmp_path):
    state_file = tmp_path / "state.json"
    with patch("src.config.STATE_FILE", state_file):
        now = datetime.now(timezone.utc)
        state.set_last_sync("revolut", now)

        data = json.loads(state_file.read_text())
        assert data["revolut_last_sync"] == now.isoformat()


def test_multiple_sources_independent(tmp_path):
    state_file = tmp_path / "state.json"
    with patch("src.config.STATE_FILE", state_file):
        t1 = datetime(2025, 1, 1, tzinfo=timezone.utc)
        t2 = datetime(2025, 6, 1, tzinfo=timezone.utc)

        state.set_last_sync("wise", t1)
        state.set_last_sync("revolut", t2)

        assert state.get_last_sync("wise") == t1
        assert state.get_last_sync("revolut") == t2
