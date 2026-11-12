## What
<!-- One or two sentences: what does this PR change? -->

## Why
<!-- Link the issue (e.g. "Closes #3") and say why this change is needed. -->

## Still the right thing?
<!-- Required (CI fails if empty). What changed from the plan, and why? Or "Nothing changed, because ...". -->

## Reviews
<!-- Required (CI fails otherwise). Tick each, or write "n/a: <reason>" (e.g. "n/a: docs only, no code"). -->
- [ ] test-writer: tests written from the SPEC, before the code
- [ ] block-reviewer: report pasted below or summarised (✅ ready)
- [ ] /code-review: findings fixed (or none)

## How tested
<!-- Commands run, what you checked by hand. -->

## Checklist
- [ ] `uv run ruff check` and `uv run ruff format --check` pass
- [ ] `uv run pytest` passes
- [ ] No secrets (`.env`, API keys) and no primer PDF in the diff
- [ ] `docs/PLAN.md`, `docs/SETUP_LOG.md` and the build map updated for this step
