"""Tests for .github/scripts/check_reviews.py (the build loop's reviews, ticked in the PR)."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / ".github" / "scripts" / "check_reviews.py"
TEMPLATE = ROOT / ".github" / "pull_request_template.md"

spec = importlib.util.spec_from_file_location("check_reviews", SCRIPT)
check_reviews = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_reviews)
check = check_reviews.check

DONE = """## What
x

## Reviews
- [x] test-writer wrote tests from the SPEC
- [x] block-reviewer: ready
- [x] /code-review: 2 findings fixed

## How tested
pytest
"""


def test_all_ticked_passes():
    assert check(DONE) is None


def test_windows_line_endings_pass():
    assert check(DONE.replace("\n", "\r\n")) is None


def test_na_with_reason_passes():
    body = DONE.replace(
        "- [x] test-writer wrote tests from the SPEC",
        "- [ ] test-writer n/a: docs only, no code",
    )
    assert check(body) is None


@pytest.mark.parametrize(
    "body",
    [
        "",
        "## What\nno reviews section\n",
        DONE.replace("- [x] block-reviewer", "- [ ] block-reviewer"),  # unticked
        DONE.replace("- [x] /code-review: 2 findings fixed\n", ""),  # line missing
        DONE.replace(
            "- [x] test-writer wrote tests from the SPEC", "- [ ] test-writer n/a"
        ),  # no reason
    ],
)
def test_missing_or_unticked_fails(body):
    assert check(body) is not None


def test_ticks_under_the_next_heading_do_not_count():
    body = "## Reviews\n\n## Notes\n- [x] test-writer\n- [x] block-reviewer\n- [x] /code-review\n"
    assert check(body) is not None


def test_ticks_inside_a_hint_do_not_count():
    body = "## Reviews\n<!--\n- [x] test-writer\n- [x] block-reviewer\n- [x] /code-review\n-->\n"
    assert check(body) is not None


def test_unfilled_template_fails_but_has_the_section():
    template = TEMPLATE.read_text(encoding="utf-8")
    assert "## Reviews" in template
    assert check(template) is not None


def test_one_ticked_line_cannot_count_for_other_items():
    """code-review finding: an item must START its own checkbox line."""
    body = (
        "## Reviews\n"
        "- [x] block-reviewer: done (see /code-review notes and test-writer later)\n"
        "- [ ] test-writer\n"
        "- [ ] /code-review\n"
    )
    assert check(body) is not None


def test_reviews_heading_inside_a_code_block_is_ignored():
    body = "```\n## Reviews\n- [x] test-writer\n- [x] block-reviewer\n- [x] /code-review\n```\n"
    assert check(body) is not None
