# 0006: The build loop, enforced by CI

- **Status:** Accepted (2026-11-12)
- **In plain words:** every piece of code is a block with a job description (SPEC). A separate test-writer agent writes its tests from the SPEC alone, before seeing the code; a separate read-only reviewer and `/code-review` check it; only then does a PR go in. CI fails if any of this is skipped, so it can't be forgotten.

## Context
HSK built everything this way (its PLAYBOOK, M2–M3: `test-writer` and `block-reviewer` subagents, `/code-review` before every PR, the Claude GitHub review). This repo copied quizkit but not the loop. M1 steps 6–7 (the receipt check, the cards, the quiz) were built and tested by the same Claude, with no SPECs and no review. The user caught it: "this is clearly critical". A rule in memory or CLAUDE.md alone had already failed once, so the loop needed a check that fails, not a reminder.

## Decision
1. **Every module is a block** (`src/<package>/blocks/<name>/` with `SPEC.md` + `tests/blocks/test_<name>.py`), made with `quizkit.scaffold`. Front ends and the shared files copied from HSK are on a short allow-list, each with its reason. **Generic blocks go in quizkit** (user: "keep adding to the quizkit… then we can use blocks for future stuff").
2. **Tests come from the SPEC, written by the `test-writer` subagent** (`.claude/agents/test-writer.md`), which never reads the block's code: an exam written from the syllabus, not from the answers.
3. **Review by fresh eyes:** the `block-reviewer` subagent (read-only, `.claude/agents/block-reviewer.md`) and `/code-review`; then the Claude GitHub review on the PR (`.github/workflows/claude-code-review.yml`, advice only).
4. **Enforced:** `tests/test_process.py` fails CI for code outside a block, or a block without a complete SPEC or its own test file. `.github/scripts/check_reviews.py` fails CI unless the PR's `## Reviews` section ticks test-writer, block-reviewer and `/code-review` (or says `n/a: <reason>`).

## Why / alternatives considered
- **A memory note or a CLAUDE.md rule only:** tried; it was skipped. Kept as the explanation, not the guard.
- **A hook that blocks `gh pr create`:** only works in sessions started inside the repo; CI works everywhere and also guards the user's own PRs.
- **The first run of the loop proved it:** on the redo of steps 6–7 the test writers found a real bug (a card kind with spaces was rejected), and the reviewers found three more (the quote key treated `IL-1α` and `IL-1β` as the same and `1.5` as `15`; a dotted "quote" could match anything; a JSON line splitter that shifted line numbers), plus a path that could make a download land outside the project. None had been caught by the builder's own tests.

## Consequences
- ✅ Every block has a SPEC a person can read, tests written independently, and a review on record in its PR.
- ✅ The quote checker and the folder loader became quizkit blocks (`receipts`, `jsonl_loader`) that any future quiz can use.
- ⚠️ Each step is slower: SPEC first, then agents, then fixes. HSK's lesson stands: the rework passes were where the bugs were found.
- ⚠️ The PR checks prove the boxes were ticked, not that the reviews were good. The evidence is the reviewer's report in the PR and the GitHub review.
