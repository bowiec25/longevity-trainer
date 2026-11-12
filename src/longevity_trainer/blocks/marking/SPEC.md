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

**How it's called** (importable from `longevity_trainer.blocks.marking`):
```python
judge = make_judge(
    cache_file=Path("data/judge_cache.jsonl"), ask=ask_claude, before_asking=None
)
verdict = judge(question, typed)  # a quizkit.models.Verdict
```

## Outputs
| Output | Type | Plain meaning |
|---|---|---|
| `make_judge` | a `Judge` (`(Question, str) -> Verdict`) | Routes by `question.mode`: `name` and `fact` go to a judge with quizkit's `WORD_RUBRIC` (same meaning, synonyms, small slips); `term` and `explain` go to a judge with `CONCEPT_RUBRIC` and room for a sentence or two (up to 400 characters) |
| `SUBJECT` | `str` | The one sentence telling Claude what the quiz is: longevity science, where the learner types a short answer or explanation in their own words |
| `CONCEPT_RUBRIC` | `str` | The marking rules for explanations. **Accept:** own words; a simpler wording if the key idea (the mechanism, or the main point of the model answer) is there and every part the question asks for is covered; extra correct detail; small slips. **Reject:** a wrong or missing key idea; a related but different mechanism; an answer covering only some of the parts asked for; anything stated that contradicts the model answer; moving a finding to a different species or group (mice → people, patients → healthy people); overselling (e.g. "reverses ageing" when the answer says "unproven in people"); a vague answer that would fit many questions. Unsure → wrong |
| `Verdict` | `quizkit.models.Verdict` | As `ClaudeJudge` returns it: `correct`, a short `reason`, `source` (`claude`, `cache`, or `not_checked` when Claude couldn't be asked) |

Both routes share the one `cache_file`; a verdict's cache key includes its rubric, so the two never mix. They also share **one failure count**: Claude failing 2 times in a row, on either route, switches marking off for the run (every later answer gets a `not_checked` verdict at once, without waiting).

## Tools
- `quizkit.blocks.judge.ClaudeJudge`, `WORD_RUBRIC`
- `quizkit.claude.ask_claude` (default `ask`)
- `quizkit.models.Question`, `Verdict`

## Failure modes
| Situation | What it does |
|---|---|
| A `mode` that isn't one of the four kinds | **Raises `ValueError`** naming the mode (a front-end bug must be loud) |
| A card kind in `card_bank`'s `Kind` with no marking rule here | **Raises `ImportError`** when the block is imported, so it fails before any quiz starts, not on a wrong answer mid-quiz |
| Claude can't be reached, times out, or replies badly | Whatever `ClaudeJudge` does: a `Verdict` with `source="not_checked"`, `correct=False` and the reason (the CLI then asks the learner to mark it). After 2 failures in a row on either route, Claude isn't called again this run |
| A blank answer | `ClaudeJudge`'s "no answer" verdict (`not_checked`); Claude isn't asked |
| An explanation over 400 characters, or a name/fact answer over 100 | `ClaudeJudge`'s "too long to check" verdict; Claude isn't asked |

## How to test
Automatic tests in `tests/blocks/test_marking.py`, with a **fake `ask`** (never the real Claude, `tests/conftest.py`):
- **Routing:** a `name` and a `fact` question reach Claude with `WORD_RUBRIC` in the system prompt; a `term` and an `explain` question with `CONCEPT_RUBRIC`
- **The subject** sentence is in every prompt
- **Length limits:** a 150-character explanation is sent to Claude; a 150-character name answer is "too long"; a 401-character explanation is "too long"
- **Verdicts pass through:** the fake's yes/no and reason come back as the `Verdict`; a failing `ask` gives `not_checked`
- **Cache:** the same answer to the same question asks Claude once; the cache file is shared by both routes
- **Unknown mode** → `ValueError`
- **Contract test:** folder parts exist and `BLOCK_SPEC` matches this SPEC

**Eval set (quality, real Claude, run by hand):** about 20 answers to the 15 hallmark cards that the user labels right or wrong, run through `quizkit.blocks.judge.eval` style scoring: how often Claude agrees with the user. Built with the user after this block lands (M4 grows it).
