# Block: `marking`

> **In plain words:** Mark a typed answer with Claude when the answer list says no: word-level for names and facts, main-idea for explanations.

## Goal
Mark a typed answer with Claude when the answer list says no: word-level for names and facts, main-idea for explanations.

It exists because fixed answer lists can't mark open answers (user: "fixed answers are always a nightmare with these more open ended questions"), and even names need wiggle room ("telomeres getting shorter" for "telomere attrition"). It builds this quiz's judge from quizkit's `ClaudeJudge`: one subject sentence, two rubrics, routed by the card's kind.

**Not in scope:** asking Claude (that's `quizkit.blocks.judge.ClaudeJudge`, with its cache, timeout, schema-checked reply and "couldn't check" fallback); deciding when to ask (the engine asks only after the answer list says wrong); the learner's own mark when Claude can't check (the CLI).

## Kind
**agent.** Whether an explanation gets the main idea can't be checked by code. It's one Claude call per answer, no tools; the reply's shape is forced and checked by `ClaudeJudge`. Quality is measured by a labelled eval set (How to test).

## Inputs
| Input | Type | Plain meaning |
|---|---|---|
| `question` | `quizkit.models.Question` | The question asked. Its `mode` is the card's kind: `name`, `fact`, `term` or `explain` (the CLI sets it). `shown["question"]` is the question text; `accepted_answers` the model answers |
| `typed` | `str` | What the learner typed |
| `cache_file` | `Path \| None` | Where verdicts are saved, so the same answer is never asked twice (default `None` = no saving) |
| `ask` | callable | How to reach Claude (default: quizkit's `ask_claude`, the `claude -p` command on the user's subscription). Tests pass a fake |
| `before_asking` | `Callable[[], None] \| None` | Called just before a **real** Claude call (not for a cached verdict, a blank or too-long answer, or when marking is switched off), e.g. to print "asking Claude…" |
| `cases` | `list[MarkingCase]` | For the eval: answers the user labelled right or wrong (`tests/data/marking_eval.jsonl`) |
| `cards` | `list[LongevityCard]` | For the eval: the bank, to find each case's card (its question, answers and kind) |

**How it's called** (importable from `longevity_trainer.blocks.marking`):
```python
judge = make_judge(
    cache_file=Path("data/judge_cache.jsonl"), ask=ask_claude, before_asking=None
)
verdict = judge(question, typed)  # a quizkit.models.Verdict

report = run_marking_eval(load_marking_cases(), load_cards(), make_judge())
```
From the command line: `uv run longevity check-marking-eval [--limit N] [--dry-run]` (real Claude, no cache, so every answer the answer list rejects is really marked; prints one line per case, the report, the model(s) that answered and the judge's prompt version (ADR 0002's log), and the Claude calls, tokens and cost; exit code 0 = the bar is met). `--dry-run` lists the cases and calls no Claude; `--limit N` uses the first N. Every problem (a missing, empty or bad eval file, a card id not in the bank, a bad card file) is printed in full as the reason, with exit code 1, never a traceback; `--dry-run` checks the card ids too. If any case comes back not checked, it says so: Claude didn't answer (offline or not logged in?), so the result isn't about marking.

## Outputs
| Output | Type | Plain meaning |
|---|---|---|
| `make_judge` | a `Judge` (`(Question, str) -> Verdict`) | Routes by `question.mode`: `name` and `fact` go to a judge with quizkit's `WORD_RUBRIC` (same meaning, synonyms, small slips); `term` and `explain` go to a judge with `CONCEPT_RUBRIC` and room for a sentence or two (up to 400 characters) |
| `SUBJECT` | `str` | The one sentence telling Claude what the quiz is: longevity science, where the learner types a short answer or explanation in their own words |
| `CONCEPT_RUBRIC` | `str` | The marking rules for explanations. **Accept:** own words; a simpler wording if the key idea (the mechanism, or the main point of the model answer) is there and every part the question asks for is covered; extra correct detail; small slips. **Reject:** a wrong or missing key idea; a related but different mechanism; an answer covering only some of the parts asked for; anything stated that contradicts the model answer; moving a finding to a different species or group (mice → people, patients → healthy people); overselling (e.g. "reverses ageing" when the answer says "unproven in people"); a vague answer that would fit many questions. Unsure → wrong |
| `MarkingCase` | pydantic model (frozen, extra fields forbidden) | One labelled answer: `card_id` (a card in the bank), `typed` (not blank), `expected` (bool: should it count as right?), `why` (the label's reason, may be empty) |
| `MARKING_EVAL_FILE` | `Path` | `tests/data/marking_eval.jsonl` |
| `load_marking_cases(path=MARKING_EVAL_FILE)` | `list[MarkingCase]` | Read with quizkit's `load_jsonl_file` (no id check: one card can have many cases), so a BOM or `\r\n` is fine; a bad line raises `ValueError` naming its line number and the reason; a file with no cases raises `ValueError` ("no marking eval cases found…"); a missing file raises `FileNotFoundError` |
| `check_card_ids(cases, cards)` | `None` | Raises `ValueError` naming every `card_id` not in `cards` (in case order); used by `run_marking_eval` and the CLI's `--dry-run` |
| `run_marking_eval(cases, cards, judge, show=print)` | quizkit's `EvalReport` | Calls `check_card_ids` first. Then marks each case **exactly as the quiz does**: the card's `to_question()` goes into a one-question quizkit `QuizSession` with `judge`, and `typed` is answered there, so the answer list (typos forgiven) marks first and the judge is asked only when it says wrong. An answer-list yes counts as "yes" (reason: accepted by the answer list); the judge's verdict otherwise (`not_checked` → couldn't check). Counted by quizkit's shared `score`, exactly like quizkit's judge eval: `right`, `wrong_yes` (said right to an answer labelled wrong: the worst kind), `wrong_no`, `not_checked` (counts as not right), `seconds` per case; `passed` = at least 90% right and no wrong yes. `show` gets one line per case: `✓`, `✗ WRONG YES`, `✗ wrong no` or `?`, then the card id, the typed answer, the verdict and its reason |
| `Verdict` | `quizkit.models.Verdict` | As `ClaudeJudge` returns it: `correct`, a short `reason`, `source` (`claude`, `cache`, or `not_checked` when Claude couldn't be asked) |

Both routes share the one `cache_file`; a verdict's cache key includes its rubric, so the two never mix. They also share **one failure count**: Claude failing 2 times in a row, on either route, switches marking off for the run (every later answer gets a `not_checked` verdict at once, without waiting).

## Tools
- `quizkit.blocks.judge.ClaudeJudge`, `WORD_RUBRIC`
- `quizkit.claude.ask_claude` (default `ask`)
- `quizkit.models.Question`, `Verdict`
- `quizkit.blocks.judge.eval.score`, `ScoreItem`, `EvalReport` (counting, the markers and the bar, shared)
- `quizkit.blocks.engine.QuizSession` (the quiz's own marking order: answer list, then judge)
- `quizkit.blocks.jsonl_loader.load_jsonl_file` (reading the eval file)
- `longevity_trainer.blocks.card_bank.LongevityCard` and its `to_question()` (the one place a card becomes a question)

## Failure modes
| Situation | What it does |
|---|---|
| A `mode` that isn't one of the four kinds | **Raises `ValueError`** naming the mode (a front-end bug must be loud) |
| A card kind in `card_bank`'s `Kind` with no marking rule here | **Raises `ImportError`** when the block is imported, so it fails before any quiz starts, not on a wrong answer mid-quiz |
| Claude can't be reached, times out, or replies badly | Whatever `ClaudeJudge` does: a `Verdict` with `source="not_checked"`, `correct=False` and the reason (the CLI then asks the learner to mark it). After 2 failures in a row on either route, Claude isn't called again this run |
| A blank answer | `ClaudeJudge`'s "no answer" verdict (`not_checked`); Claude isn't asked |
| An explanation over 400 characters, or a name/fact answer over 100 | `ClaudeJudge`'s "too long to check" verdict; Claude isn't asked |
| An eval case whose `card_id` isn't in the bank | `check_card_ids` (and so `run_marking_eval`) raises `ValueError` naming the id, before marking anything |
| No eval cases passed to `run_marking_eval` | Returns a report with `total=0` and `passed=False` |
| The eval file is missing, empty, not UTF-8 or has a bad line | `load_marking_cases` raises (`FileNotFoundError`, or `ValueError` with the reason); the CLI prints it, exit 1 |

## How to test
Automatic tests in `tests/blocks/test_marking.py`, with a **fake `ask`** (never the real Claude, `tests/conftest.py`):
- **Routing:** a `name` and a `fact` question reach Claude with `WORD_RUBRIC` in the system prompt; a `term` and an `explain` question with `CONCEPT_RUBRIC`
- **The subject** sentence is in every prompt
- **Length limits:** a 150-character explanation is sent to Claude; a 150-character name answer is "too long"; a 401-character explanation is "too long"
- **Verdicts pass through:** the fake's yes/no and reason come back as the `Verdict`; a failing `ask` gives `not_checked`
- **Cache:** the same answer to the same question asks Claude once; the cache file is shared by both routes
- **Unknown mode** → `ValueError`
- **Contract test:** folder parts exist and `BLOCK_SPEC` matches this SPEC

- **Eval runner (fake judge):** a judge agreeing with every label → all right, `passed`; one wrong yes → not passed even at 95%; a `not_checked` verdict counts as not right; the judge is called with the card's own question (equal to `card.to_question()`); a typed answer the answer list accepts (one of the card's answers, or a one-letter typo of a long one) is not sent to the judge and counts as yes (so labelled wrong → a wrong yes); `show` lines start with the right marker; an unknown `card_id` → `ValueError` before the judge is called; no cases → `passed=False`; `check_card_ids` names every unknown id
- **Loading:** `load_marking_cases` reads the real file (every `card_id` is in the bank, every case has a `why`, at least 20 cases); a bad line → `ValueError` naming its number and the bad field; a BOM and `\r\n` are fine; a blank-only file → `ValueError` ("no marking eval cases"); a missing file → `FileNotFoundError`
- **CLI** (fake judge / no Claude): `check-marking-eval --dry-run` lists the cases and calls nothing; exit 0 when the (faked) report passes, 1 when it doesn't; a missing eval file, an empty one, a bad line (the bad field's name is printed), or a case naming a card not in the bank → one message, exit 1, no traceback, for both the real run and `--dry-run`; any not-checked case → a line saying Claude didn't answer

**Eval set (quality, real Claude, run by hand):** `tests/data/marking_eval.jsonl`: 23 borderline answers (names, facts, terms, explanations; synonyms, half answers, mice→people, wrong order) that the user labelled (2026-11-12: "answers I think okay"). Bar: at least 90% agreement and no wrong yes, re-run whenever the rubrics or the model change.

**First runs (2026-11-12, Haiku, two runs):** 21/23 and 21/23, no wrong yes, nothing unchecked: PASSED both times, about 5 s and under 1 cent per run. The same 2 misses both times, both answers the user accepts that Claude found too short: "inflammation that gets worse with age" for inflammaging (no "chronic, body-wide") and "inflammation" alone for the senescence harm (no fibrosis). Strict on the safe side; no rubric change for now.
