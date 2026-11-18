# Block: `quiz_round`

> **In plain words:** Run one quiz round for any screen: set it up (deal, progress, judge), mark each answer, and say what to show after it (verdict, model answer, receipt)

## Goal
Run one quiz round for any screen: set it up (deal, progress, judge), mark each answer, and say what to show after it (verdict, model answer, receipt).

It exists so the terminal (`longevity quiz`) and the web page (M4 Step 3b) are two screens on **one** brain: the same cards dealt, the same marking order, the same words after each answer, the same saving. Before this block that logic lived in `cli.py` and a web page would have had to copy it (ADR 0009). The web half, `QuizScreen`, copies HSK's `WebQuiz` pattern (HSK ADR 0014): a page that reruns on every click only passes the click in and draws what the brain says.

**Not in scope:** reading the keyboard or drawing (the screens); dealing, boxes and saving themselves (`study`); marking itself (quizkit grader + `marking`'s judge).

## Kind
**script.** Every output (what's dealt, what's shown, what's saved) is checkable by code; the only judgment (Claude's marking) is the `marking` block's, passed in.

## Inputs
| Input | Type | Plain meaning |
|---|---|---|
| `options` | `RoundOptions` (frozen dataclass) | `topic: str \| tuple[str, ...] \| None = None` (a topic or group, or several (a tuple: cards matching any), matched as `study.deal` matches; an empty tuple = all), `n: int = 10` (≥1), `practise: bool = False` (deal cards not due yet too; nothing saved), `judge: bool = True` (Claude marks answers the answer list rejects), `save: bool = True`, `seed: int \| None = None` (fixed order, for tests) |
| `files` | `RoundFiles` (frozen dataclass) | `progress: Path` (default `PROGRESS_FILE` = `data/progress.db`), `judge_cache: Path` (default `JUDGE_CACHE` = `data/judge_cache.jsonl`). Screens pass their own (tests pass temp paths) |
| `bank` | `list[LongevityCard]` | The cards to deal from (default: `card_bank.load_cards()` when the round starts) |
| `now` | `datetime` (timezone-aware) | When "due" is judged (default: now, UTC) |
| `make_judge` | callable | Builds the judge, called as `make_judge(cache_file=..., before_asking=...)` (default `marking.make_judge`; tests pass a fake). Not called when `options.judge` is False |
| `before_asking` | `Callable[[], None] \| None` | Passed to `make_judge` (the terminal prints "asking Claude…"; the web page shows a spinner instead) |
| `warn` | `Callable[[str], None]` | Where the `Saver`'s one "progress not saved" warning goes (terminal: `print`) |
| `clock` | `Callable[[], datetime] \| None` | Stamps each saved answer (default: the real time, UTC). `QuizScreen` passes its own `now` |
| `practise_hint` | `str` | How the screen says "review anyway" in the nothing-due line (terminal: `"--practise"`, web: `"turn on Practise"`) |
| *per answer:* `attempt`, `card` | quizkit `Attempt`, `LongevityCard` | For the wording functions |

**How it's called** (importable from `longevity_trainer.blocks.quiz_round`):
```python
# Terminal: set up, then its own loop using the wording functions
round_ = setup(RoundOptions(topic="hallmarks"), RoundFiles(progress, cache),
               bank=load_cards(), before_asking=..., practise_hint="--practise")
# -> Round(cards, judge, saver); raises SetupProblem(lines, nothing_due)
feedback(attempt, card) -> list[str]; own_mark_line(True) -> "✓ Counted"
receipt_line(card) -> 'Receipt: "…" (source, p. 3)'; score_line(result) -> "Score: 3 / 5"

# Web: one object per browser tab, kept between reruns
screen = QuizScreen(files=..., bank=None, make_judge=make_judge)
screen.start(RoundOptions(...)); screen.submit(typed, card_id)
screen.mark(got_it, card_id); screen.next(card_id); screen.stop(); screen.new_quiz()
```

## Outputs
| Output | Type | Plain meaning |
|---|---|---|
| `RoundOptions`, `RoundFiles` | frozen dataclasses | As in Inputs. `RoundOptions(n=0)` raises `ValueError` |
| `PROGRESS_FILE`, `JUDGE_CACHE` | `Path` | `ROOT / "data" / "progress.db"`, `ROOT / "data" / "judge_cache.jsonl"` (both gitignored). `RoundFiles()` reads these module names **when it is built** (not when the class is defined), so `tests/conftest.py` can point them at temp files for every test |
| `setup(options, files, bank=None, now=None, make_judge=marking.make_judge, before_asking=None, warn=print, practise_hint="--practise", clock=None)` | `Round` | Opens the progress file **only if it exists** (to read when cards are due), deals with `study.deal` (due, then new; `practise` adds not-due cards), then, only if a quiz will start and saving is on (`save` and not `practise`), creates/opens the progress store; builds the judge if `options.judge`. `Round` (frozen dataclass): `cards: list[LongevityCard]` (in quiz order), `judge: Judge \| None`, `saver: study.Saver \| None` (None when not saving; stamps answers with `clock`) |
| `SetupProblem` | `Exception` with `lines: list[str]`, `nothing_due: bool` | Why no quiz starts (see Failure modes). `nothing_due=True` only for "Nothing due" (the terminal exits 0 then, 1 otherwise) |
| `SELF_YES`, `SELF_NO` | quizkit `Verdict` (`source="self"`) | Your own mark: reasons `"you marked it right"` / `"you marked it wrong"` |
| `OWN_MARK_QUESTION` | `str` | `"Count it as right?"` |
| `feedback(attempt, card)` | `list[str]` | What to say right after an answer, before any own mark (no indent, no wrapping). Claude's verdict "checked" = a verdict whose source isn't `not_checked`. **Right and checked:** `"✓ Right (Claude: <reason>)"`, `"Model answer: <first answer>"`. **Right, not checked** (answer list): `"✓ Right"`. **Wrong:** `"✗ Claude: <reason>"` if checked, or `"(Claude: <reason>)"` if Claude couldn't check, nothing if not asked; then `"Answer: <first answer>"`. Only for an answer before your own mark (a `self` verdict is outside its contract: screens add `own_mark_line` instead) |
| `own_mark_line(got_it)` | `str` | `"✓ Counted"` / `"✗ Not this time"` |
| `NOT_THIS_TIME` | `str` | `"✗ Not this time"`: the last line for a wrong answer that can't take your mark (blank, or Claude said no) |
| `receipt_line(card)` | `str` | `'Receipt: "<quote>" (<source>, p. <page>)'` |
| `score_line(result)` | `str` | `"Score: <correct> / <answered>"` (quizkit `QuizResult`) |
| `QuizScreen` | class (below) | The quiz for a screen that redraws on every click |

**`QuizScreen`** (one per browser tab). Constructor: `QuizScreen(files=RoundFiles(), bank=None, make_judge=marking.make_judge, now=None)`; `now` is a `Callable[[], datetime]` (default: now, UTC), read at `start` and when saving.
- **Phases** (`phase`): `"setup"` → `start` → `"asking"` → `submit` → `"own_mark"` (exactly when `QuizSession.can_own_mark`: wrong by the answer list, typed, nobody could check; the terminal asks "count it as right?" on the same rule) or `"result"` → `mark` → `"result"` → `next` → `"asking"` … → `"ended"` (no questions left, or `stop`) → `new_quiz` → `"setup"`.
- **Clicks:** `start(options)` (only in setup or ended; a `SetupProblem` puts its lines in `problems`, `nothing_due` in `nothing_due`, and stays in setup; the judge gets `before_asking=None`, the Saver warns into the screen, `practise_hint="turn on Practise"`), `submit(typed, card_id)`, `mark(got_it, card_id)`, `next(card_id)`, `stop()`, `new_quiz()`. **A click in the wrong phase, or naming a card that isn't the current one (a double or late click), does nothing.**
- **What to draw** (reading these never moves the quiz on):
  - `view: QuestionView | None`: `card_id`, `number` (1-based), `total`, `question` (the card's text), `topic`.
  - `marking: MarkView | None` (phase own_mark): `card_id`, `typed`, `lines` (= `feedback(...)`), `question` (= `OWN_MARK_QUESTION`).
  - `result: ResultView | None` (phase result): `card_id`, `typed`, `right` (bool), `lines` (= `feedback(...)`, then `own_mark_line(...)` if you marked it, or `NOT_THIS_TIME` if wrong and not markable), `receipt` (the card's `Receipt`: `quote`, `source`, `page`), `warning` (the save warning, if this answer's save failed and it's the first failure; else None).
  - `summary: list[str]` (phase ended): `score_line(...)`, then, when saving, `"<saved> answers saved"` (always, even 0) and `"<unsaved> answers not saved"` if any; `"Practise: nothing saved"` when practising; only the score line with `save=False`. An answer stopped at its own mark counts as answered and not right in the score (as in the terminal), but isn't saved.
  - Outside their phases `problems` is `[]`, `nothing_due` False, `summary` `[]`.
  - `problems: list[str]`, `nothing_due: bool` (after a failed start).
- **Saving:** an answer is saved (through `study.Saver`) the moment it's final: at `submit` when no own mark is needed, or at `mark`. `stop()` in own_mark **doesn't** save the unmarked answer (as the terminal: quitting at the y/n prompt saves nothing).

The terminal's `play()` keeps its own loop (read, write, quit words) but takes every line from the wording functions, and `longevity quiz` uses `setup`; its output is unchanged.

## Tools
- `longevity_trainer.blocks.study`: `deal`, `schedule`, `next_due`, `groups`, `Saver`
- `longevity_trainer.blocks.marking.make_judge` (default)
- `longevity_trainer.blocks.card_bank`: `LongevityCard` (`to_question()`), `load_cards`, `ROOT`
- quizkit: `QuizSession` (`answer`, `can_own_mark`, `own_mark`, `result`), `ProgressStore`, `ProgressFileError`, `Verdict`

## Failure modes
`setup` (and `QuizScreen.start`, into `problems`) never lets a progress-file error escape; each case is a `SetupProblem`:
| Situation | `lines` |
|---|---|
| The progress file exists but can't be opened | `["can't use progress.db: <why>"]` |
| It opens but can't be read | `["can't read progress.db: <why>"]` |
| Nothing to deal, but some matching card is due later | `["Nothing due. Next card due <Thu 13 Nov 09:00, local time>. (<practise_hint> to review anyway)"]`, `nothing_due=True` |
| Nothing matches the topic | `["no cards on a topic containing '<topic>'. Topics:", "  <group>", …]` (each group of the bank, sorted); for several topics the first line names each, joined by " or " (`"no cards on a topic containing 'a' or 'b'. Topics:"`). **No progress file is created** |
| The bank is empty (no topic given) | `["no cards in the bank"]` |
| The progress file can't be created when saving starts | `["can't use progress.db: <why>"]` |

(The file name shown is `files.progress.name`.) A save that fails mid-quiz: the `Saver` warns once and the quiz goes on (study's rule). `RoundOptions` with `n < 1` → `ValueError`. A `make_judge` that raises is not caught (a bug, loud).

## How to test
Automatic tests in `tests/blocks/test_quiz_round.py`: real cards from the bank or small hand-made `LongevityCard`s, a **fake judge** (never real Claude), progress in `tmp_path`, a fixed `now`.
- **Wording:** each `feedback` case (right by the list; right by Claude with the model answer; wrong by Claude; wrong and Claude couldn't check; wrong, not asked); `own_mark_line`; `receipt_line`; `score_line`
- **setup:** deals due then new; `practise` deals not-due cards and gives no saver; `save=False` → no saver and no file; each failure mode's lines (nothing due with the hint, unknown topic lists groups and creates no file, a tuple of topics deals from each of them and an unknown pair names both, blank texts are left out of the message (an empty bank with `("",)` says "no cards in the bank"), unusable file); `judge=False` → `make_judge` not called; `before_asking` passed through
- **QuizScreen:** a full round right/wrong to `ended` with the summary; own mark yes/no lands in `result.lines` and is saved; stop in own_mark saves nothing; stale and double clicks (wrong phase, old card id) change nothing; a failed start shows `problems`; `new_quiz` back to setup; the result carries the card's receipt; a save failure shows `warning` once
- **The terminal still says the same:** `tests/test_cli.py` and `tests/test_cli_progress.py` pass (one test there patches `quiz_round.schedule` instead of `cli.schedule`, since setup moved here)
- **Contract test:** folder parts exist and `BLOCK_SPEC` matches this SPEC
