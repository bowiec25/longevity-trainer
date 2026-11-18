# Block: `topic_map`

> **In plain words:** Sort the cards onto broad shelves: map each card's topic to its topic-map entry and that entry's area (How we age, Drugs & treatments, ...)

## Goal
Sort the cards onto broad shelves: map each card's topic to its topic-map entry and that entry's area (How we age, Drugs & treatments, ...)

A bookshop: the web page's topic box lists the **shelves** (areas), and each card is a book on one. Before this, the box mixed levels ("hallmarks" next to "metformin"; user, 2026-11-18: "metformin and rapamycin are like drugs category, not their own"). The shelves live in `data/topics.jsonl` (each topic's `area`), so moving a topic to another shelf is a data change, not a code change. It also ties every card to its topic-map entry, so a card filed under another name (`physical-activity`, whose entry is `exercise`) is found through the entry's `aliases`.

**Not in scope:** dealing cards (`study`), the page (`web_pages/quiz.py`), the card writer's own topic list (`card_writer.load_topics`).

## Kind
**script.** Looking up a topic in a table needs no judgment, and code can check every answer.

## Inputs
| Input | Type | Plain meaning |
|---|---|---|
| `path` | `Path \| None` | The topic map file (default `None`: `TOPICS_FILE`, looked up when called) |
| `card_topic` | `str` | A card's `topic`, e.g. `"hallmarks: senescence"`, `"rapamycin"`, `"NAD+ boosters"` |
| `topics` | `list[Topic]` | The loaded topic map |
| `cards` | `list[LongevityCard]` | Cards to sort onto shelves |

**How it's called** (importable from `longevity_trainer.blocks.topic_map`):
```python
topics = load_topic_map()
area_of("hallmarks: senescence", topics)  # "How we age"
areas_in(load_cards(), topics)  # ["How we age", "Big ideas", "Drugs & treatments", ...]
```

## Outputs
| Output | Type | Plain meaning |
|---|---|---|
| `TOPICS_FILE` | `Path` | `ROOT / "data" / "topics.jsonl"` |
| `AREAS` | `tuple[str, ...]` | The shelves, in the order the page shows them: `("How we age", "Big ideas", "Drugs & treatments", "Supplements", "Lifestyle", "Measuring ageing", "Evidence & trials", "Industry")` |
| `Topic` | pydantic model | One topic-map line: `id`, `topic`, `group`, `area` (one of `AREAS`), `status`, `aliases: list[str] = []` (other names cards may be filed under, e.g. `["physical-activity"]`). Other keys in the line (`primer`, `kinds`) are allowed and ignored |
| `load_topic_map(path=None)` | `list[Topic]` | Every line of the file as a `Topic`, in file order (all statuses); blank lines skipped |
| `area_of(card_topic, topics)` | `str \| None` | The card's shelf: take the card topic's group (the text before the first `:`, as `study.group_of`), slug it (lower case, letters/digits/hyphens, the same rule as `card_writer.slug`, kept in this block so quiz-time code doesn't import the card writer: `"NAD+ boosters"` → `nad-boosters`), and find the topic whose `id` or one of whose `aliases` equals it; return that topic's `area`. No match → `None` |
| `areas_in(cards, topics)` | `list[str]` | The shelves that hold at least one of the cards, in `AREAS` order, each once (what the page's box offers). Cards with no shelf are left out |

## Tools
- `longevity_trainer.blocks.card_bank`: `ROOT`, `LongevityCard`
- `longevity_trainer.blocks.study.group_of`
- `pydantic`

## Failure modes
| Situation | What it does |
|---|---|
| The topic map file is missing | `load_topic_map` raises `FileNotFoundError` |
| A line isn't JSON, isn't an object, or lacks a string `id` / `topic` / `group` / `area` / `status` | Raises `ValueError` naming the line number |
| A line's `area` isn't one of `AREAS` | Raises `ValueError` naming the line number and the area |
| An `id` repeats, or an alias equals another topic's id or alias | Raises `ValueError` naming the line number (a card name must lead to one topic) |
| A card's topic matches no id or alias | `area_of` returns `None`; `areas_in` leaves the card out (the real-data test below keeps the bank from having such cards) |

## How to test
Automatic tests in `tests/blocks/test_topic_map.py`, with small topic files written in the test:
- **load_topic_map:** reads every line in order (all statuses), skips blank lines, `aliases` defaults to `[]`, extra keys (`primer`, `kinds`) are accepted; missing file → `FileNotFoundError`; not JSON, not an object, a missing or non-string required field → `ValueError` naming the line; an unknown area → `ValueError` naming it; a repeated id, an alias equal to another id, and an alias used twice → `ValueError`; with no argument it follows a monkeypatched `TOPICS_FILE`
- **area_of:** `"hallmarks: senescence"` → the `hallmarks` topic's area; `"NAD+ boosters"` → `nad-boosters`'s; `"Physical Activity"` → found through an alias; an unknown topic → `None`
- **areas_in:** shelves in `AREAS` order (not card order), each once; a card with no shelf is left out; no cards → `[]`
- **Real data:** the real `data/topics.jsonl` loads; every card in the real bank (`load_cards()`) has a shelf (so a new card file under an unknown name fails CI: give its topic an alias or use the topic id); `rapamycin` and `metformin` are on `"Drugs & treatments"`, `hallmarks` on `"How we age"`
- **Contract test:** folder parts exist and `BLOCK_SPEC` matches this SPEC
