# Block: `topic_map`

> **In plain words:** Sort the cards onto broad shelves: map each card's topic to its topic-map entry and that entry's area (How we age, Drugs & treatments, ...)

## Goal
Sort the cards onto broad shelves: map each card's topic to its topic-map entry and that entry's area (How we age, Drugs & treatments, ...)

A bookshop: the web page's topic box lists the **shelves** (areas), and each card is a book on one. Before this, the box mixed levels ("hallmarks" next to "metformin"; user, 2026-11-18: "metformin and rapamycin are like drugs category, not their own"). The shelves live in `data/topics.jsonl` (each topic's `area`), so moving a topic to another shelf is a data change, not a code change. It also ties every card to its topic-map entry, so a card filed under another name (`physical-activity`, whose entry is `exercise`) is found through the entry's `aliases`.

**Parts, so you learn them all** (user, 2026-11-18: "as a learner it's important I learn all"): a topic can list its **parts**, e.g. the 12 hallmarks. A card on one part is filed `"<topic>: <part>"` (e.g. `"hallmarks: cellular senescence"`), and a coverage report shows, per part, whether easy mode has a "what" card and a "how" card for it. The gaps are what to write next.

**Writing cards for one part:** `write-cards --topic "hallmarks: <part>"` (a new per-part card file, e.g. `hallmarks-cellular-senescence.jsonl`). The four older bundle files (`hallmarks-genome-telomeres-and-epigenetics.jsonl` etc.) keep their re-filed cards but take no `--add`: adding with the old bundle topic would file new cards under no part, and the real-data test below would fail.

**Not in scope:** dealing cards (`study`), the page (`web_pages/quiz.py`), the card writer's own topic list (`card_writer.load_topics`).

## Kind
**script.** Looking up a topic in a table needs no judgment, and code can check every answer.

## Inputs
| Input | Type | Plain meaning |
|---|---|---|
| `path` | `Path \| None` | The topic map file (default `None`: `TOPICS_FILE`, looked up when called) |
| `card_topic` | `str` | A card's `topic`, e.g. `"hallmarks: senescence"`, `"rapamycin"`, `"NAD+ boosters"` |
| `topics` | `list[Topic]` | The loaded topic map |
| `cards` | `list[LongevityCard]` | Cards to sort onto shelves (or to count per part) |
| `topic_id` | `str` | For `coverage_lines`: the topic whose parts to report, e.g. `"hallmarks"` |

**How it's called** (importable from `longevity_trainer.blocks.topic_map`):
```python
topics = load_topic_map()
area_of("hallmarks: cellular senescence", topics)  # "How we age"
areas_in(load_cards(), topics)  # ["How we age", "Big ideas", "Drugs & treatments", ...]
coverage_lines(load_cards(), topics, "hallmarks")  # the report below
misfiled(load_cards(), topics)  # [] when every part-card names a real part
```

**From the command line:** `uv run longevity coverage <topic id>` prints `coverage_lines` (exit 0). An unknown topic, or one without parts, gives one line naming the topics that have parts (exit 1). It never calls Claude.

## Outputs
| Output | Type | Plain meaning |
|---|---|---|
| `TOPICS_FILE` | `Path` | `ROOT / "data" / "topics.jsonl"` |
| `AREAS` | `tuple[str, ...]` | The shelves, in the order the page shows them: `("How we age", "Big ideas", "Drugs & treatments", "Supplements", "Lifestyle", "Measuring ageing", "Evidence & trials", "Industry")` |
| `Topic` | pydantic model | One topic-map line: `id`, `topic`, `group`, `area` (one of `AREAS`), `status`, `aliases: list[str] = []` (other names cards may be filed under, e.g. `["physical-activity"]`), `parts: list[str] = []` (the named parts a learner should cover, e.g. the 12 hallmarks; a card on one is filed `"<topic id or alias>: <part>"`). Other keys in the line (`primer`, `kinds`) are allowed and ignored |
| `load_topic_map(path=None)` | `list[Topic]` | Every line of the file as a `Topic`, in file order (all statuses); blank lines skipped |
| `area_of(card_topic, topics)` | `str \| None` | The card's shelf: take the card topic's group (the text before the first `:`, as `study.group_of`), slug it (lower case, letters/digits/hyphens, the same rule as `card_writer.slug`, kept in this block so quiz-time code doesn't import the card writer: `"NAD+ boosters"` → `nad-boosters`), and find the topic whose `id` or one of whose `aliases` equals it; return that topic's `area`. No match → `None` |
| `coverage_lines(cards, topics, topic_id)` | `list[str]` | The parts report. **First line:** `"<the topic's id>: <c> of <n> parts covered in easy mode (each needs an easy what and how card)"`. **Then one line per part, in the topic's order:** `"  <part>: easy <w> what, <h> how; <x> hard"`, ending `" ✓"` when covered or `" (needs: easy what)"`, `" (needs: easy how)"` or `" (needs: easy what, easy how)"`. A card counts for a part when its group finds this topic (as `area_of` does) and the text after the first `:` slugs to the part's slug. **what** = kind `name`, `term` or `fact` (recall), **how** = kind `explain`, each counted only if `difficulty == "easy"`, so every easy card is one or the other; **hard** = every card on the part that isn't easy (untagged included, any kind). `topic_id` is found like a card's group: slugged, by id or alias (`"Hallmarks"` works). Unknown `topic_id`, or a topic with no parts → `ValueError` naming the topics that have parts |
| `misfiled(cards, topics)` | `list[str]` | One line per card filed `"<group>: <x>"` whose group finds a topic **with parts** but whose `x` is none of them: `"<card id>: '<x>' isn't one of <topic id>'s parts"`. Cards filed under the topic alone (`"hallmarks"`), and topics without parts, are fine. Empty = all filed well |
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
| A topic's `parts` repeat (same slug), or a part slugs to nothing (`""`, `"---"`) | Raises `ValueError` naming the line number |
| An `id` repeats, or an alias equals another topic's id or alias | Raises `ValueError` naming the line number (a card name must lead to one topic) |
| A card's topic matches no id or alias | `area_of` returns `None`; `areas_in` leaves the card out (the real-data test below keeps the bank from having such cards) |

## How to test
Automatic tests in `tests/blocks/test_topic_map.py`, with small topic files written in the test:
- **load_topic_map:** reads every line in order (all statuses), skips blank lines, `aliases` defaults to `[]`, extra keys (`primer`, `kinds`) are accepted; missing file → `FileNotFoundError`; not JSON, not an object, a missing or non-string required field → `ValueError` naming the line; an unknown area → `ValueError` naming it; a repeated id, an alias equal to another id, and an alias used twice → `ValueError`; with no argument it follows a monkeypatched `TOPICS_FILE`
- **area_of:** `"hallmarks: senescence"` → the `hallmarks` topic's area; `"NAD+ boosters"` → `nad-boosters`'s; `"Physical Activity"` → found through an alias; an unknown topic → `None`
- **parts:** `parts` defaults to `[]`; a repeated part (`"Dysbiosis"` and `"dysbiosis"`) → `ValueError` naming the line; a blank part (`""` or `"---"`) → `ValueError` naming the line
- **coverage_lines** (a small topic with 3 parts, hand-made cards): the first line's count; a part with an easy `name` and an easy `explain` card → `✓`; easy `term` and easy `fact` count as what; a part with only hard cards → `(needs: easy what, easy how)` and the hard count; `coverage_lines(..., "Hallmarks")` and an alias of the topic work like the id; untagged cards count as hard; card topics match by slug (`"Hallmarks: Cellular Senescence"`); a card filed under the topic alone counts for no part; parts listed in the topic's order; an unknown topic and a topic without parts → `ValueError` naming the topics with parts
- **misfiled:** a card on an unknown part is named (also when filed through the topic's alias); a card on a real part, a card on the topic alone, and a card on a topic without parts are not
- **CLI** (`longevity coverage`, a temporary topic file and cards via monkeypatched `TOPICS_FILE` / `cli.CARDS_DIR` or `load_cards`): prints the lines, exit 0; an unknown topic → one line, exit 1
- **areas_in:** shelves in `AREAS` order (not card order), each once; a card with no shelf is left out; no cards → `[]`
- **Real data:** the real `data/topics.jsonl` loads; every card in the real bank (`load_cards()`) has a shelf (so a new card file under an unknown name fails CI: give its topic an alias or use the topic id); `rapamycin` and `metformin` are on `"Drugs & treatments"`, `hallmarks` on `"How we age"`; `hallmarks` has the 12 parts of the 2023 review (genomic instability, telomere attrition, epigenetic alterations, loss of proteostasis, disabled macroautophagy, deregulated nutrient-sensing, mitochondrial dysfunction, cellular senescence, stem cell exhaustion, altered intercellular communication, chronic inflammation, dysbiosis); `misfiled(load_cards(), load_topic_map()) == []` (every hallmark card names one hallmark, or is filed under `hallmarks` alone)
- **Contract test:** folder parts exist and `BLOCK_SPEC` matches this SPEC
