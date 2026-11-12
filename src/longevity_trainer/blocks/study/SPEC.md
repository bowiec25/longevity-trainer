# Block: `study`

> **In plain words:** Deal the cards to study (due first, then new) by topic group, save each answer and its Leitner box, and summarise progress per group.

## Goal
Deal the cards to study (due first, then new) by topic group, save each answer and its Leitner box, and summarise progress per group.

Flashcards in boxes: a card you get right moves to a box you check less often; one you miss goes back to box 1 and comes back first. This block is the longevity glue around quizkit's generic parts (`deck_builder` deals, `leitner` moves boxes, `progress_store` saves, `quizkit.progress` saves and counts), so `cli.py` only reads the keyboard and prints.

**Not in scope:** asking and marking questions (`quizkit.blocks.engine`, `marking`, the CLI's `play`); the box waits (quizkit's `DEFAULT_RULE`: 0, 1, 3, 7, 21 days).

## Kind
**script.** Dealing, saving and counting can all be checked in code (ADR 0002).

## Inputs
| Input | Type | Plain meaning |
|---|---|---|
| `cards` | `list[LongevityCard]` | The bank (from `card_bank.load_cards`) |
| `n` | `int` | How many cards to deal (at least 1) |
| `topic` | `str \| None` | Only cards whose topic contains this text, ignoring case (e.g. `"hallmarks"`, `"rapa"`); `None` = all |
| `schedule` | `dict[str, datetime] \| None` | When each answered card is next due (from `schedule(store)`); `None` = no progress (shuffled) |
| `now` | `datetime \| None` | The time to compare due dates with (timezone-aware; default: now, UTC) |
| `seed` | `int \| None` | Same seed → same order (tests) |
| `practise` | `bool` | Also deal cards that aren't due yet (a review the caller doesn't save; default `False`) |
| `store` | `quizkit.blocks.progress_store.ProgressStore \| None` | Where progress is saved; `None` for `stats_lines` = nothing saved yet |

**How it's called** (importable from `longevity_trainer.blocks.study`):
```python
store = ProgressStore(PROGRESS_FILE)
cards = deal(load_cards(), 10, topic="hallmarks", schedule=schedule(store))
play(cards, on_answer=Saver(store))  # the CLI's quiz loop
for line in stats_lines(load_cards(), store, datetime.now(UTC)):
    print(line)
```

## Outputs
| Output | Type | Plain meaning |
|---|---|---|
| `SKILL` | `str` | `"recall"`: the one skill every card practises, so each card has one Leitner box |
| `group_of(topic)` | `str` | A topic's group: the text before the first `:`, stripped (`"hallmarks: dysbiosis"` → `"hallmarks"`; `"rapamycin"` → `"rapamycin"`) |
| `deal(cards, n, topic=None, schedule=None, now=None, seed=None, practise=False)` | `list[LongevityCard]` | Up to `n` cards, no card twice, through quizkit's `build_deck`. With a schedule: only **due** cards (most overdue first), then **new** ones (not in the schedule); cards **not due yet are left out**, so a quiz never fills up with them (answering one early would move it up a box early and break the spacing). `practise=True` also deals not-due cards after those (soonest first), for a review the caller doesn't save. Without a schedule: shuffled, all cards. No card matches `topic` (or nothing is due or new) → `[]` (the caller says why) |
| `next_due(cards, schedule, topic=None)` | `datetime \| None` | The soonest due time among the matching cards in the schedule (for "nothing due; next card due …"); `None` if none of them is in the schedule |
| `groups(cards)` | `list[str]` | The distinct groups (`group_of` each topic), sorted: what to list when a `--topic` matches nothing |
| `schedule(store)` | `dict[str, datetime]` | Card id → next due time, for the `SKILL` boxes in `store` |
| `Saver(store, now=..., warn=print)` | callable | Called with each finally-marked `Attempt`: saves the answer and the card's new box with quizkit's `save_attempt` (skill `SKILL`, time `now()`). Right: box up (a new card answered right goes to box 2); wrong: box 1, due again at once. Attributes: `saved` (answers saved), `unsaved` (answers that couldn't be saved) |
| `stats_lines(cards, store, now)` | `list[str]` | The stats screen. With `store=None`: `"<N> cards, all new (no progress saved yet):"` and one `"  <group>: <k> cards"` line per group (sorted). With a store: one line per group, `"  <group>: <k> cards · new <x> · box 1: <a> · box 2: <b> … · due now: <d>"` (only boxes in use), then `"All: …"` in the same shape for every card, `"Last 7 days: <right> / <answered> right"`, and, if any, `"Most missed:"` and up to 5 lines `"<times>× <question>"` (most first). Counts come from quizkit's `skill_stats` |

## Tools
- `quizkit.blocks.deck_builder.build_deck` (with a one-mode `Mode(name="recall", show=["question"], skill=SKILL)` only to choose the order; the CLI builds each card's own question)
- `quizkit.blocks.progress_store`: `ProgressStore`, `ProgressFileError`
- `quizkit.progress`: `save_attempt`, `skill_stats`
- `longevity_trainer.blocks.card_bank.LongevityCard`

## Failure modes
| Situation | What it does |
|---|---|
| `n < 1` | `deal` raises `ValueError` |
| No card matches `topic` | `deal` returns `[]` |
| A schedule entry for a card not in `cards` | Ignored |
| Saving fails mid-quiz (`ProgressFileError`: the file is busy, too new, not a database) | `Saver` counts it in `unsaved`, calls `warn` the first time only (`"progress not saved: <reason>. The quiz goes on; later answers are still tried."`), and tries again on the next answer (a busy file is often free a moment later); it never raises |
| `now` without a timezone | `ValueError` (from quizkit) |

The CLI (not this block) turns a `ProgressFileError` (opening the store, or reading it for the schedule or stats) into one line and exit 1. It creates the progress file only once a quiz is about to start (a mistyped `--topic` creates nothing), opens none for `--no-save`, `--practise`, or `stats` with no file yet. An answer left unmarked because you quit at the "count it as right?" prompt isn't saved.

## How to test
Automatic tests in `tests/blocks/test_study.py` with real bank cards or small `LongevityCard`s made in the test, and a `ProgressStore` in a temp folder:
- **group_of:** `"hallmarks: dysbiosis"` → `"hallmarks"`, `"rapamycin"` → `"rapamycin"`, `"  sleep :  naps"` → `"sleep"`
- **deal:** due (most overdue first) → new, and **not-due cards left out** (even when that gives fewer than `n`), with a fixed `now` and `seed`; with `practise=True` the not-due cards come after (soonest first); everything not due and nothing new → `[]`; without a schedule all cards can be dealt; `n` limits and no repeats; `topic` is case-insensitive and matches part of a topic (`"HALLMARKS"` picks every `hallmarks: …` card); no match → `[]`; `n=0` → `ValueError`; returns the `LongevityCard`s (receipts intact); same seed → same order
- **schedule:** after saving, has the card ids and their due times
- **next_due:** the soonest due among matching cards; `topic` narrows it; no matching card in the schedule → `None`
- **groups:** the four writer `hallmarks: …` sections and the hand-made `hallmarks: …` cards give one `hallmarks`; sorted, no repeats
- **Saver:** right on a new card → box 2; wrong → box 1 and due == the saved time; `saved` counts; the store's answers have skill `"recall"`; a store whose `record` raises `ProgressFileError` → `warn` called once with "progress not saved", `unsaved` 1; a second failing call doesn't raise or warn again (`unsaved` 2); if `record` works again on a third call, that answer is saved (`saved` 1)
- **A missed card comes back first:** save a wrong answer, then `deal` with `schedule(store)` puts it first
- **stats_lines:** with `None`: the total and one line per group (the four writer `hallmarks: …` sections and the hand-made ones count under one `hallmarks` line); with a store after one right and one wrong answer: `box 1: 1`, `box 2: 1`, `due now: 1`, `1 / 2 right`, and the missed card's question under "Most missed"
- **Contract test:** folder parts exist and `BLOCK_SPEC` matches this SPEC
