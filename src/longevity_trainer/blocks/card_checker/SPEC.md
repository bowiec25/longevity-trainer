# Block: `card_checker`

> **In plain words:** Check one card and its quote against the question rules in docs/LEARNING_GOALS.md, and score that check on the labelled card exam.

## Goal
Check one card and its quote against the question rules in docs/LEARNING_GOALS.md, and score that check on the labelled card exam.

It's the strict teacher in M3: the card writer (Step 4) drafts cards, a script checks each quote is real, then this block reads each card like a teacher and fails any that break a rule (mice answered as if people, overselling, trivia, a quote that doesn't back the answer, a question that needs the paper). Because it's a Claude judgment, it is **measured** on the exam in `tests/data/card_eval.jsonl` (bar in `tests/data/card_eval.md`) before anything relies on it.

**Not in scope:** checking that the quote is really in the source (`receipts`, a script, runs first); topic-level rules (rule 1: names never alone, the writer's coverage check); trend cards (rule 7, M5); writing or fixing cards.

## Kind
**agent.** Whether an answer oversells or a question is trivia needs judgment. It's one Claude call per card, no tools; the reply's shape is forced by a JSON schema and checked by code (a script validator). Quality is measured by the exam, run by hand with real Claude.

## Inputs
| Input | Type | Plain meaning |
|---|---|---|
| `card` | `LongevityCard` | The card to check: kind, question, accepted answers, and the receipt quote |
| `ask` | callable | How to reach Claude (default quizkit's `ask_claude`, `claude -p` on the user's subscription). Tests pass a fake |
| `model` | `str` | Which Claude model (`"haiku"` default; the exam picks it) |
| `cases_file` | `Path` | The exam (default `tests/data/card_eval.jsonl`; the held-out cards are `tests/data/card_eval_holdout.jsonl`) |
| `show` | `Callable[[str], None]` | Where the exam prints one line per card and the report (default `print`) |

**How it's called** (importable from `longevity_trainer.blocks.card_checker`):
```python
verdict = check_card(card, ask=ask_claude, model="haiku")  # CardVerdict
report = run_exam(
    load_exam(cases_file), check=check_card, show=print, model="haiku"
)  # ExamReport; `check(card)` is called with the card only; `model` is just the label in the report
```
From the command line: `uv run longevity check-cards-exam --model haiku` (exit code 0 = the bar is met). `--holdout` uses `tests/data/card_eval_holdout.jsonl` instead: cards written by an agent that never saw the checker's prompt or the exam, so the prompt was never tuned on them (the main exam was used to tune prompt v2, so passing it overstates how the checker does on new cards). `--limit N` checks only the first N cards; `--dry-run` lists the cards and calls no Claude. After a real run it prints the number of Claude calls, tokens and cost (ADR 0002 guardrails). The CLI (`longevity_trainer.cli.main`) calls `run_exam(load_exam(EXAM_FILE), check=<check_card with that model>)`, looking both names up on the `cli` module, so a test can replace `longevity_trainer.cli.run_exam` with a fake.

## Outputs
| Output | Type | Plain meaning |
|---|---|---|
| `check_card` | `CardVerdict` | `ok: bool`; `rules: list[int]` (the rule numbers broken, from 2–6; empty when `ok`); `reason: str` (one or two sentences, never empty) |
| `CardVerdict` | pydantic model | As above. `ok=True` with rules, or `ok=False` with none, is invalid |
| `RULES_TEXT` | `str` | Section 2 of `docs/LEARNING_GOALS.md` ("What makes a question good"): from the line starting `## 2.` (included) up to the next `## ` heading, read from `ROOT / "docs"` at import, word for word. It is in every prompt, so changing the standard changes the checker (no copy to drift) |
| `MAX_FALSE_FLAG_SHARE` | `float` | Most of the good cards the checker may wrongly fail and still pass: 1/3 |
| `MAX_RULES_NAMED` | `int` | A verdict naming more rules than this (3) never counts as the right rule |
| `PROMPT_VERSION` | `str` | Bumped when the prompt wording changes; printed in the exam report |
| `ExamCase` | pydantic model | One exam line: `id`, `expected` (`"pass"`/`"fail"`), `rules` (accepted rule numbers for a fail; empty for a pass), `why`, `origin`, `card` |
| `load_exam` | `list[ExamCase]` | The exam lines, validated (a bad line names its line number) |
| `run_exam` | `ExamReport` | Checks every case once and prints one line per case: `✓`/`✗`, the id, expected vs got, and the reason for every miss |
| `ExamReport` | pydantic model | `total`, `bad_cards`, `caught` (bad cards failed), `right_rule` (caught, naming at least one of the case's accepted rules, and naming at most `MAX_RULES_NAMED` rules: a shotgun verdict doesn't score), `false_flags` (good cards failed), `errors` (Claude failed or replied badly), `seconds`, `model`, `prompt_version`, and `passed` (kept in `model_dump()`) |

**The bar** (`passed`, from `tests/data/card_eval.md`): every bad card caught (`caught == bad_cards`), `right_rule >= bad_cards - 2`, `false_flags <= good cards × MAX_FALSE_FLAG_SHARE` (1/3: 4 of 12, 2 of 6), and `errors == 0`. History (user, 2026-11-12): first ≤1, then ≤3 (a wrongly rejected good card costs one redraft; a bad card let through teaches a mistake), then a third of the good cards, after Haiku caught every bad card in all 14 runs (incl. the held-out cards) while rejecting about 30% of good ones. To be revisited when tuning (docs/FUTURE.md).

What the prompt contains:
- **System:** you're a strict but fair reviewer of quiz cards for a learner of longevity science; the rules (`RULES_TEXT`); judge only rules 2–6 (rule 1 is per topic, rule 7 is for trend cards); judge from the card and quote alone (the quote is an excerpt about the card's topic: "it" or "these effects" refer to it); the quote is already verified to be in a trusted source, so the question is whether **it backs the card**: every factual claim in the answer, and any fact the question asserts, is stated by the quote; a plain-English paraphrase is fine, a stronger claim, wider group or added fact is not; rule 2 applies to claims about effects (in whom?), not to how a drug works or what it's used for; rule 4: what a trial tested, found, meant and its main limitation are worth knowing, its sample size, p-values and registry number are trivia; rule 6: naming a known trial or term is fine, "the trial" / "the authors" / "Figure 2" is not; when unsure, fail the card (a bad card teaches a mistake). Prompt v1 was too literal ("any word"): it failed 8 of 13 good cards, 4 of them wrongly.
- **Prompt:** the card's kind, topic, question, accepted answers, source id and quote.
- **Reply schema:** `{"ok": boolean, "rules": [integers 2–6], "reason": string}`.

## Tools
- `quizkit.claude.ask_claude` (default `ask`), `ClaudeError`
- `longevity_trainer.blocks.card_bank.LongevityCard`, `ROOT`
- `quizkit.blocks.jsonl_loader` style line-numbered errors for the exam file
- pydantic

## Failure modes
| Situation | What it does |
|---|---|
| Claude can't be reached or times out | `check_card` raises `ClaudeError`; `run_exam` counts it as an error, prints the reason, and goes on |
| Claude's reply isn't valid JSON, or breaks the schema (missing field, rule outside 2–6, `ok` with rules, not-ok with none, empty reason) | `check_card` raises `ClaudeError` ("bad reply: …"); never guesses a verdict |
| Duplicate rule numbers in a reply | Kept once, in the order given |
| A reply with the wrong JSON types (`"ok": "false"`, `"rules": ["3"]`, `[[3]]`) | `ClaudeError` ("bad reply"): values are never coerced |
| Any other exception while checking one exam card | `run_exam` counts it as an error and goes on, so one odd failure never loses a whole (paid) run |
| `docs/LEARNING_GOALS.md` is missing, or has no section 2 heading | Raises `RuntimeError` at import: a checker without its rules must not run |
| A bad exam line (invalid JSON, invalid card, unknown `expected`, a fail with no rules or a pass with rules, a rule outside 2–6, an id already used on an earlier line) | `load_exam` raises `ValueError` naming the line number; `check-cards-exam` prints that one line and exits 1 |
| An empty exam | `run_exam` returns a report with `total=0` and `passed=False` |

## How to test
Automatic tests in `tests/blocks/test_card_checker.py`, with a **fake `ask`** (never real Claude, `tests/conftest.py`):
- **Prompt:** the system prompt contains `RULES_TEXT`, which equals section 2 of `docs/LEARNING_GOALS.md` (from its heading to the next `## ` heading); the user prompt contains the card's question, every accepted answer, the kind, the topic and the quote; the schema is passed; the chosen model is passed
- **Verdicts:** a fake reply passes through as a `CardVerdict`; each invalid reply → `ClaudeError`; a `ClaudeError` from `ask` propagates; duplicate rules de-duplicated
- **Exam scoring** (fake `check`): all right → `passed`; one bad card missed → not passed; caught with a rule not in the case's list → counts as caught but not right rule; 2 wrong rules still passes, 3 doesn't; with 12 good cards 4 false flags pass and 5 don't; with 6 good cards 2 pass and 3 don't (`MAX_FALSE_FLAG_SHARE`); one error → not passed; empty exam → not passed; each miss prints its reason
- **load_exam:** loads the real `tests/data/card_eval.jsonl` (29 cases); bad lines name their line number
- **CLI:** `longevity check-cards-exam` exits 0 when the (faked) report passes and 1 when it doesn't; `--dry-run` calls no Claude and exits 0; `--limit 2` checks 2 cards; `--holdout` loads the holdout file; a bad exam line prints one line and exits 1
- **Scoring:** a verdict naming one of the case's rules plus others (e.g. [2, 3] when the case allows [3]) is right rule; one naming 4 or more rules (e.g. all of 2–6) is caught but not right rule; one sharing no rule with the case is caught but not right rule; an exam line with a rule outside 2–6, or a repeated id, is rejected by `load_exam`; a missing `LEARNING_GOALS.md` → `RuntimeError`
- **Contract test:** folder parts exist and `BLOCK_SPEC` matches this SPEC

**The real exam (by hand, real Claude):** `uv run longevity check-cards-exam --model haiku` and `--model sonnet`, each twice. Results go in `docs/SETUP_LOG.md`; the cheaper model that meets the bar both times becomes the default.
