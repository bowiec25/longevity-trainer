"""Shared test helpers (pytest loads this file automatically). Copied from HSK, trimmed."""

import pytest


@pytest.fixture(autouse=True)
def no_real_claude(monkeypatch):
    """Safety net: no test starts the real `claude` (slow, online, uses the
    subscription). It looks "not installed"; a test that fakes it overrides this."""
    from quizkit import claude

    monkeypatch.setattr(claude.shutil, "which", lambda name: None)
