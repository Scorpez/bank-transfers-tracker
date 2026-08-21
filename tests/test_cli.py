"""Tests for CLI argument parsing and help output."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_help_shows_all_commands():
    result = subprocess.run(
        [sys.executable, "main.py", "--help"],
        capture_output=True, text=True,
        cwd=str(Path(__file__).resolve().parent.parent),
    )
    assert result.returncode == 0
    assert "sync" in result.stdout
    assert "list-wise-balances" in result.stdout
    assert "import-revolut" in result.stdout


def test_no_command_exits_with_error():
    result = subprocess.run(
        [sys.executable, "main.py"],
        capture_output=True, text=True,
        cwd=str(Path(__file__).resolve().parent.parent),
    )
    assert result.returncode == 1
