"""Shared test helpers (pytest loads this file automatically). Copied from HSK, trimmed."""

import pytest


@pytest.fixture(autouse=True)
def no_real_claude(monkeypatch):
    """Safety net: no test starts the real `claude` (slow, online, uses the
    subscription). It looks "not installed"; a test that fakes it overrides this."""
    from quizkit import claude

    monkeypatch.setattr(claude.shutil, "which", lambda name: None)


@pytest.fixture(autouse=True)
def no_real_progress(tmp_path, monkeypatch):
    """Safety net: no test reads or writes your real data/progress.db or
    data/judge_cache.jsonl (the terminal's paths and quiz_round's defaults)."""
    from longevity_trainer import cli
    from longevity_trainer.blocks import quiz_round

    for module in (cli, quiz_round):
        monkeypatch.setattr(module, "PROGRESS_FILE", tmp_path / "progress-guard.db")
        monkeypatch.setattr(module, "JUDGE_CACHE", tmp_path / "judge-cache-guard.jsonl")
