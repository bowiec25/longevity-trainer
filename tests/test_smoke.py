"""Smoke test: the package imports and the command runs."""

import subprocess
import sys


def test_package_imports():
    import longevity_trainer

    assert callable(longevity_trainer.main)


def test_command_runs():
    result = subprocess.run(
        [sys.executable, "-c", "import longevity_trainer; longevity_trainer.main()"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "longevity-trainer" in result.stdout
