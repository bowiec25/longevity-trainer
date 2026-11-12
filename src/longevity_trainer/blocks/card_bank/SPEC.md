# Block: `card_bank`

> **In plain words:** Load the longevity cards (question, answers, receipt) from data/cards and turn them into quizkit cards.

## Goal
Load the longevity cards (question, answers, receipt) from data/cards and turn them into quizkit cards.

It exists so every part of the app (the quiz, the receipt check, later the card writer and auditor) reads the cards one way and gets the same validated objects. A bad card fails loudly when loaded, not halfway through a quiz.

**Not in scope:** checking the quotes (the `quizkit` `receipts` block), judging whether a question is good (the fact-auditor agent, M3, against `docs/LEARNING_GOALS.md`), choosing which cards to ask (`deck_builder`).

## Kind
**script.** Code can check the output: a line is valid JSON with the right fields, or it isn't (ADR 0002).

## Inputs
| Input | Type | Plain meaning |
|---|---|---|
| `cards_dir` | `Path` | A folder of `*.jsonl` files, one card per line (default: `data/cards/` in the project). Blank lines are skipped but still counted in line numbers (like an editor). Files are read in name order; other files and subfolders are ignored |

One line = one card:
```json
{"id": "hm-telomeres-name", "kind": "name", "topic": "telomere attrition",
 "question": "Which hallmark is ...?", "answers": ["telomere attrition", "telomere shortening"],
 "receipt": {"source": "hallmarks-of-aging-2023", "quote": "after several rounds ...", "page": 9}}
```

**How it's called** (importable from `longevity_trainer.blocks.card_bank`):
```python
load_cards(cards_dir=CARDS_DIR) -> list[LongevityCard]
card.to_quizkit() -> quizkit.models.Card
```

## Outputs
| Output | Type | Plain meaning |
|---|---|---|
| `LongevityCard` | pydantic model, frozen | `id` (non-empty), `kind` (one of `name`, `fact`, `term`, `explain`: ADR 0005), `topic` (non-empty), `question` (at least 10 characters), `answers` (at least one, none blank), `receipt` (a `quizkit.blocks.receipts.Receipt`). Surrounding spaces are stripped from every text field, `kind` included (and inside the receipt, per the receipts SPEC). Unknown fields are rejected |
| `load_cards` | `list[LongevityCard]` | Every card, in file order then line order |
| `to_quizkit` | `quizkit.models.Card` | Same `id` and `answers`; `fields` = `{"question", "kind", "topic"}`; `level` = 1. The quiz builds its questions from this (one mapping, not two) |
| `ROOT` | `Path` | The project folder (works from the source tree, the uv default; not from an installed wheel) |
| `CARDS_DIR` | `Path` | `ROOT / "data" / "cards"`, the default `cards_dir` |

Nothing is written.

## Tools
- `quizkit.blocks.jsonl_loader.load_jsonl_dir` (reading the folder: order, line numbers, repeats, empty; BOM-safe)
- pydantic (models)
- `quizkit.blocks.receipts.Receipt` (the receipt shape, shared with other quizzes)
- `quizkit.models.Card`

## Failure modes
| Situation | What it does |
|---|---|
| A line that isn't valid JSON, has a missing or unknown field, an unknown `kind`, a blank answer, no answers, or a bad receipt | **Raises `ValueError`** naming the file and the line number (e.g. `hallmarks.jsonl line 3: ...`) |
| Two cards with the same `id` (in one file or across files) | **Raises `ValueError`** listing the repeated ids |
| A file that isn't valid UTF-8 | **Raises `ValueError`** naming the file (a UTF-8 byte-order mark is fine) |
| The folder has no cards at all (no `.jsonl` files, or only blank lines) | **Raises `ValueError`** ("no cards found in …"): a quiz with nothing in it is a bug upstream |
| The folder doesn't exist | **Raises `FileNotFoundError`** |

## How to test
Automatic tests in `tests/blocks/test_card_bank.py`, using small card files written to `tmp_path` (no network, no PDF).
- **Loads:** two files, cards in file then line order; blank lines skipped; spaces stripped
- **to_quizkit:** id, answers, the three fields, level 1
- **Each failure mode:** bad JSON, missing field, unknown field, unknown kind, blank answer, short quote in the receipt → `ValueError` with file name and line number; repeated id (same file, and across files) → `ValueError`; empty folder → `ValueError`; missing folder → `FileNotFoundError`
- **The real bank:** `data/cards/` loads, has at least 15 cards (it grows), every card's `kind` is valid (a guard on the committed data)
- **Contract test:** folder parts exist and `BLOCK_SPEC` matches this SPEC

Manual check: none (the play-test goes through `longevity quiz`).
