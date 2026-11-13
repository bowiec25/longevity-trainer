"""The build loop, enforced: every piece of code is a block with a SPEC and its own tests.

The loop (CLAUDE.md "Workflow"): SPEC first -> the test-writer subagent writes tests
from the SPEC alone -> build -> block-reviewer + /code-review -> PR. Memory and good
intentions failed (M1 steps 6-7 skipped it), so this test fails CI instead:

- every module under src/ lives in a block folder (blocks/<name>/), unless it is on
  the short, reasoned list below (front ends and the shared models copied from HSK);
- every block has a complete SPEC.md (the 7 sections, no TODO) and
  tests/blocks/test_<name>.py.

The PR check (.github/scripts/check_reviews.py) covers the other half: the reviews
must be ticked in the PR description.
"""

from pathlib import Path

from quizkit.blocks.base import SPEC_SECTIONS, missing_spec_sections, spec_section

ROOT = Path(__file__).parent.parent
SRC = ROOT / "src"
TESTS = ROOT / "tests" / "blocks"

# Modules allowed outside a block, each with its reason. Adding one needs a reason.
NOT_BLOCKS = {
    # front ends: screen and keyboard code that only wires blocks together
    "longevity_trainer/__init__.py": "package entry point",
    "longevity_trainer/blocks/__init__.py": "package marker",
    "longevity_trainer/cli.py": "terminal front end (wires blocks; tested in test_cli.py)",
    "longevity_trainer/web_app.py": "web front end entry: page menu only (test_web_app.py)",
    "longevity_trainer/web_pages/__init__.py": "package marker for the web pages",
    "longevity_trainer/web_pages/quiz.py": "web quiz page: draws QuizScreen (test_web_app.py)",
    "longevity_trainer/web_pages/stats.py": "web stats page: draws stats_lines (test_web_app.py)",
    # quizkit's shared parts, copied from HSK caa969a with their own tests (ADR 0003)
    "quizkit/__init__.py": "package marker",
    "quizkit/blocks/__init__.py": "package marker",
    "quizkit/blocks/base.py": "the block contract itself",
    "quizkit/claude.py": "shared Claude helper (test_claude_helper.py)",
    "quizkit/download.py": "shared download helper (test_quizkit_download.py)",
    "quizkit/files.py": "shared file helper",
    "quizkit/models.py": "shared data shapes (test_quizkit_models.py)",
    "quizkit/modes.py": "shared quiz modes (test_quizkit_modes.py)",
    "quizkit/progress.py": "shared progress shapes (test_quizkit_progress.py)",
    "quizkit/scaffold.py": "the block photocopier (test_scaffold.py)",
}


def modules() -> list[str]:
    return sorted(
        p.relative_to(SRC).as_posix()
        for p in SRC.rglob("*.py")
        if "__pycache__" not in p.parts
    )


def block_dirs() -> list[Path]:
    return sorted(
        d
        for blocks in SRC.glob("*/blocks")
        for d in blocks.iterdir()
        if d.is_dir() and d.name != "__pycache__"
    )


def test_all_code_lives_in_blocks():
    def in_a_block(module: str) -> bool:  # <package>/blocks/<name>/<file>.py
        parts = module.split("/")
        return len(parts) >= 4 and parts[1] == "blocks"

    strays = [m for m in modules() if not in_a_block(m) and m not in NOT_BLOCKS]
    assert not strays, (
        f"code outside a block: {strays}. Make it a block "
        "(uv run python -m quizkit.scaffold <name> ...), write its SPEC, have the "
        "test-writer write tests from the SPEC, then build it."
    )


def test_allow_list_has_no_dead_entries():
    dead = [m for m in NOT_BLOCKS if not (SRC / m).is_file()]
    assert not dead, f"remove these from NOT_BLOCKS, they no longer exist: {dead}"


def test_every_block_has_a_complete_spec_and_its_own_tests():
    problems = []
    for block in block_dirs():
        spec = block / "SPEC.md"
        if not spec.is_file():
            problems.append(f"{block.name}: no SPEC.md")
            continue
        missing = missing_spec_sections(spec)
        if missing:
            problems.append(f"{block.name}: SPEC.md misses {missing}")
        todo = [s for s in SPEC_SECTIONS if "TODO" in spec_section(spec, s)]
        if todo:
            problems.append(f"{block.name}: SPEC.md still has TODO in {todo}")
        if not (TESTS / f"test_{block.name}.py").is_file():
            problems.append(f"{block.name}: no tests/blocks/test_{block.name}.py")
    assert len(block_dirs()) >= 6  # the scan really found the blocks
    assert not problems, problems
