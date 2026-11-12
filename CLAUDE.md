# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project
A quiz that tests the user's longevity knowledge (ageing science, sleep, exercise, nutrition, the evidence behind them). Built like `../mandarin-hsk-trainer` (its `docs/PLAYBOOK.md` is the checklist), reusing its generic `quizkit` (copied in M1, source commit recorded in an ADR).
Plan + progress: `docs/PLAN.md` (read "Where we are" first). Why each step: `docs/SETUP_LOG.md`. Ideas for later: `docs/FUTURE.md` (when the user mentions a future idea, add it there). Big decisions: `docs/decisions/` (ADRs, from M1); a new decision gets a new ADR, accepted ones aren't edited.

## Commands
- `uv sync`: install from `uv.lock` · `uv run longevity-trainer`: run the app
- `uv run ruff check` / `uv run ruff format`: lint / format (CI runs `ruff format --check`)
- `uv run pytest`: all tests; one test: `uv run pytest tests/test_smoke.py::test_package_imports`
- `uv add <pkg>` / `uv add --dev <pkg>`: add a dependency. Never `pip install`.

Before saying work is done, run `ruff check`, `ruff format --check` and `pytest`. CI (`.github/workflows/ci.yml`) runs the same with `uv sync --locked`.

## Architecture
- `src/quizkit/`: **generic** quiz parts copied from `mandarin-hsk-trainer` (`caa969a`): cards, grader, deck, engine, Claude judge, Leitner progress. Never imports `longevity_trainer` (`tests/test_reuse.py` fails if it does). Each block has a `SPEC.md`; read it before changing the block.
- `src/longevity_trainer/`: longevity-specific code.
- Tests never call the real Claude (`tests/conftest.py`).

## Content rules
- **Every card carries a receipt:** a source from the trusted list (M2), pinned (URL, date, SHA-256), plus a word-for-word quote a script finds in it. No receipt, no card.
- **The primer is the syllabus, not a source.** `Desktop\Longevity_Platform_Blueprint\1_DOCS\longevity_trends_primer.pdf` (the user's own synthesis) says *what* to learn; facts still need a trusted source. Never commit the PDF (the repo is public).
- **Testable** = one clear right answer, stated by a trusted source, true for about 2+ years. Otherwise "read, don't quiz". v1 focus: **name & recall** (hallmarks, pathways, drugs and what they do) as the core, then mechanisms, science, history (+ some testing); dated industry facts wait for M5 freshness checks.
- **Script vs agent:** if code can check the output, write a script. If it needs judgment, use an agent, and a script validates its output. No human approval gates: checks act on their own and the user gets a one-line summary.

## Workflow
- **The build loop, for every piece of code (enforced, not optional):**
  1. Make it a block: `uv run python -m quizkit.scaffold <name> --kind script|agent --package quizkit|longevity_trainer --goal "..."`. Generic (another quiz could use it) → `quizkit`.
  2. Fill in its `SPEC.md` (the 7 sections).
  3. The **`test-writer`** subagent writes `tests/blocks/test_<name>.py` from the SPEC alone, before the code (an exam from the syllabus, not from the answers).
  4. Build until those tests pass. Don't weaken its tests; if the SPEC was wrong, fix the SPEC and re-run the test-writer.
  5. The **`block-reviewer`** subagent (read-only) and `/code-review`; fix what they find.
  6. PR with the `## Reviews` section ticked → CI + the GitHub Claude review → the user merges.
  - **Enforced by:** `tests/test_process.py` (code outside a block, or a block without a complete SPEC or its own test file, fails CI) and `.github/scripts/check_reviews.py` (unticked reviews fail CI).
- The user is learning. Small steps; stop after each for a go-ahead. Short, plain messages: analogy first, then a tiny map of where the step fits; extra detail in closed `<details>` toggles.
- Plan mode for big or unclear steps. Every plan starts with **"Still the right thing?"**: re-test the plan against what we know now and say what changed. It's a required section in issues (`.github/ISSUE_TEMPLATE/step.yml`) and PRs (CI fails an empty one: `.github/scripts/check_pr_body.py`). `gh issue create` / `gh pr create --body` skip the forms, so write the section yourself.
- After each step: tick `docs/PLAN.md`, add a plain-English entry to `docs/SETUP_LOG.md`, add ideas to `docs/FUTURE.md`, update the build map: edit `docs/build-map/index.html` (tiles, diagram, gates, tests table, one line in "How it grew"), save a frozen copy as `docs/build-map/snapshots/<step>.html` linked from that line (in the copy, strip `snapshots/` from the timeline links and add the 📸 banner), and republish the folder to the "Longevity Trainer Build Map" artifact (slug `3dd79f10-f680-4225-84a4-fd70cc124d81`).
- Once `main` is protected (M0 Step 5): issue → branch → small commits → PR → green CI → squash-merge. Never commit to `main` directly. Stage files by name, not `git add -A`.
- Look up versions, tags and limits; don't guess.
- Secrets live in `.env` (gitignored; Claude is denied reading it). Document key names in `.env.example`.
- Hooks (`.claude/hooks/`, tested in `tests/test_hooks.py`, copied from HSK): `block_env.py` blocks any tool or shell command touching `.env`; `format_python.py` runs `ruff format` after every `.py` edit. They only load in a session started inside this folder. Claude Code blocks Claude from changing its own settings and hooks: the user runs those changes.
- Subagents (`.claude/agents/`, copied from HSK): `test-writer` (writes tests from a SPEC, only in `tests/`) and `block-reviewer` (read-only). In a session started outside this folder they aren't loaded: give a general-purpose agent the role file as its instructions.
