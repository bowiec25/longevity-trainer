# Block: `card_writer`

> **In plain words:** Draft quiz cards on one topic from one pinned source, keep only those whose quote is really in the source and that pass the card checker.

## Goal
Draft quiz cards on one topic from one pinned source, keep only those whose quote is really in the source and that pass the card checker.

It's the student writing flashcards from a textbook. Claude reads the source and drafts cards that cover the five questions per topic (what is it, how does it work, how sure are we, what's the catch); then three gates, in order: **code** checks each card's shape and finds its quote word for word in the source (`receipts`); **code** drops repeats; the **card checker** (`card_checker`, Haiku) rejects any card that breaks a rule. What survives is written to `data/cards/<topic>.jsonl` and plays in `longevity quiz`.

**Not in scope:** finding or pinning sources (records in `data/sources/`, documents via `receipts.ensure_source`); trend cards (rule 7, M5); fixing rejected cards (the next run drafts again); marking answers (`marking`).

## Kind
**agent.** Writing a good question needs judgment. One Claude call per run via `claude -p` (no tools, no Agent SDK: ADR 0008), reply forced by a JSON schema; then the script gates above validate every card. Quality is measured by the writer eval (How to test).

## Inputs
| Input | Type | Plain meaning |
|---|---|---|
| `topic` | `str` | What the cards are about, e.g. `"rapamycin"`. Becomes each card's `topic` and, slugged (lower case, letters/digits/hyphens), the start of its id and the file name |
| `source_id` | `str` | The pinned source to write from (`data/sources/<source_id>.json`) |
| `n` | `int` | How many cards to ask Claude for (default 8, 1–20) |
| `ask` | callable | How to reach Claude (default quizkit's `ask_claude`). Tests pass a fake |
| `model` | `str` | The writer's model (default `"sonnet"`) |
| `check` | `Callable[[LongevityCard], CardVerdict]` | The card checker (default `card_checker.check_card`, Haiku). Tests pass a fake |
| `taken_ids` | `set[str]` | Card ids already in the bank, so new ids never clash (default: empty) |
| `sources_dir` | `Path` | Where source records live (default `data/sources`) |
| `root` | `Path` | The project root the record's `local_path` is relative to (default `ROOT`) |
| `fetch` | `Callable[[str], bytes]` | Downloads a missing document (default quizkit's `http_get`). Tests pass a fake |

**How it's called** (importable from `longevity_trainer.blocks.card_writer`):
```python
result = write_cards("rapamycin", "pearl-2025", n=8, taken_ids=ids)  # WriterResult
```
From the command line: `uv run longevity write-cards --topic rapamycin --source pearl-2025 [--n 8] [--model sonnet] [--dry-run] [--replace]`. It prints one line per draft (kept, or the gate that dropped it and why) and the report. Without `--dry-run`, and only if the report passes, it writes the kept cards to `data/cards/<topic-slug>.jsonl` (a run that misses the bar writes nothing: look at its drops, then run again); if that file exists it refuses (exit 1) unless `--replace`. The file is written to `<file>.tmp` first and then swapped in, so a failed write keeps the old cards (exit 1, one line). `--dry-run` drafts and gates but writes nothing, and is allowed when the file exists (it still calls Claude: it's for looking before saving). After the report it prints one line with the number of Claude calls (writer + checker), tokens and cost (ADR 0002 guardrail 4; `--n` is the limit). Exit code 0 = the writer bar is met.

**`taken_ids` from the CLI:** the ids in every `data/cards/*.jsonl` **except** the topic's own file (with `--replace` its old ids are free again). No cards yet (no folder, no files, or only blank files) = empty. If any other card file has a bad line or a repeated id, it prints one line ("the card bank has a problem …") and exits 1 without calling Claude, so new ids never clash with cards it couldn't read. The topic's own file is not read, so a broken one can still be replaced. The CLI looks `write_cards` up on the `cli` module, so a test can replace `longevity_trainer.cli.write_cards`.

## Outputs
| Output | Type | Plain meaning |
|---|---|---|
| `write_cards` | `WriterResult` | `kept: list[LongevityCard]` (in draft order), `drops: list[Drop]`, `report: WriterReport` |
| `Draft` | pydantic model | One drafted card as Claude returns it: `asks` (`"what"`, `"how"`, `"how_sure"` or `"catch"`: which of the five questions it answers), `kind` (`name`/`fact`/`term`/`explain`), `question`, `answers` (1+), `quote` (copied word for word from the source) |
| `Drop` | pydantic model | `question` (the draft's), `gate` (`"shape"`, `"quote"`, `"repeat"` or `"checker"`), `reason` (one line) |
| `WriterReport` | pydantic model | `drafted`, `kept`, `dropped_shape`, `dropped_quote`, `dropped_repeat`, `dropped_checker`, `checker_errors`, `asks_kept` (the distinct `asks` values among kept cards, sorted, each once), `model`, `prompt_version`, and `passed` (kept in `model_dump()`) |
| `PROMPT_VERSION` | `str` | Bumped when the prompt changes; in every report |
| `slug` | `str` | `slug("Epigenetic clocks!")` → `"epigenetic-clocks"` |

**Card ids:** `<topic-slug>-<asks>-<k>` with `_` in `asks` turned into `-` (e.g. `rapamycin-how-sure-1`). Only **kept** cards are numbered: `k` counts from 1 per `asks` value over the kept cards, in draft order, skipping any id in `taken_ids`. (The checker sees each card with a provisional id; the id plays no part in its verdict.)

**Receipts:** `source` = `source_id`; `quote` = the draft's quote; `page` = the page `receipts.find_quote` finds it on (1 for html and jats-xml).

**The gates, in order** (a draft that fails one is dropped there, with a `Drop`):
1. **shape:** the draft makes a valid `LongevityCard` (e.g. question ≥ 10 characters, no blank answer, quote key ≥ 20 characters)
2. **quote:** `find_quote` finds the quote in the source's page keys
3. **repeat:** a question already kept in this run, compared case- and space-insensitively, is dropped (a question the checker rejected, or errored on, doesn't block a later draft with the same wording)
4. **checker:** `check(card)`; `ok=False` drops it with the checker's rules and reason; a `ClaudeError` from the checker drops it too (gate `"checker"`, reason starting `"checker error"`) and counts in `checker_errors`

**The writer bar** (`passed`): `drafted > 0`; at least 80% of drafts pass the quote gate (`dropped_quote <= drafted * 0.2`: a writer that invents quotes is broken); `kept >= drafted / 2`; and `asks_kept` includes `"what"`, `"how"` and `"how_sure"` (rule 1: never names alone; rule 2: every intervention gets a "how sure" card). `"catch"` is wanted but not required (not every source discusses a catch). The bar is on what Claude drafted, not on `n`: a short reply (3 cards when 8 were asked) that still covers what/how/how_sure passes, on purpose: a thin source can't fill 8 good cards.

What the prompt contains:
- **System:** you write quiz cards for someone learning longevity science; the whole of `docs/LEARNING_GOALS.md`, word for word, read at import (its own §4 says the writer's prompt includes it); write `n` cards on the topic from the source text below and nothing else; every card's quote must be copied **exactly** from the source (a script checks it), one to three consecutive sentences, never paraphrased; **the quote alone must back the whole card** (one short claim per answer, taken from the quote; the question asserts nothing the quote doesn't; no open lists); if the source is split into `[page N]` parts, each quote must come from inside one page; cover what / how / how sure / catch; name the population in any "how sure" answer; no trivia (sample sizes, p-values, registry numbers); questions must stand alone (no "the trial", "the authors", "Figure 2"); no trend questions.
- **Prompt:** the topic, `n`, the source's title, and its full plain text (`source_text.text_pages`). A one-page source (html, jats-xml, a one-page PDF) is its text as is; a source with 2+ pages has each page start with a line `[page N]` (N from 1), pages joined with blank lines, because `find_quote` looks for a quote on one page at a time and a quote across a page break would always be dropped.
- `PROMPT_VERSION` is `"3"` (v2 added "the quote alone must back the whole card"; v3 the page markers).
- **Reply schema:** `{"cards": [Draft, ...]}`.

## Tools
- `quizkit.claude.ask_claude`, `ClaudeError`
- `quizkit.blocks.receipts`: `load_source`, `ensure_source`, `page_keys`, `find_quote`
- `quizkit.blocks.source_text.text_pages`
- `longevity_trainer.blocks.card_bank`: `LongevityCard`, `ROOT`, `CARDS_DIR`, `load_cards`
- `longevity_trainer.blocks.card_checker`: `check_card`, `CardVerdict`

## Failure modes
| Situation | What it does |
|---|---|
| `docs/LEARNING_GOALS.md` is missing | Raises `RuntimeError` at import: a writer without its standard must not run |
| The record `<source_id>.json` holds a different `id` | Raises `ValueError` ("<source_id>.json is for '<id>'") before any Claude call |
| No record `data/sources/<source_id>.json`, or the document can't be fetched or verified | Raises (`FileNotFoundError` / `DownloadError`), before any Claude call; the CLI prints one line, exit 1 |
| The source's text is over 200,000 characters | Raises `ValueError` ("source too long …") before any Claude call (too big for one call; split it later) |
| `n` outside 1–20 | Raises `ValueError` |
| An empty or unsluggable topic (`"!!!"`) | Raises `ValueError` |
| Claude can't be reached, or its reply isn't valid JSON or breaks the schema | Raises `ClaudeError` ("bad reply: …"); nothing is written |
| Claude returns more cards than asked | Only the first `n` are used |
| Claude returns 0 cards | A report with `drafted=0`, `passed=False` |
| The checker fails on one card | That card is dropped (`checker error`), the run goes on |
| `data/cards/<slug>.jsonl` exists (CLI, no `--replace`, no `--dry-run`) | Exit 1 with one line; nothing drafted (checked before calling Claude). With `--dry-run` it goes ahead (nothing is written) |
| Another card file has a bad line or repeated id (CLI) | Exit 1 with one line; nothing drafted |
| The card file can't be written (CLI) | Exit 1 with one line; the old file is unchanged |
| Every draft dropped, or the report doesn't pass | Nothing written; exit 1 |
| A draft with an `asks` or `kind` value outside the lists | The reply breaks the schema: `ClaudeError` ("bad reply"); a too-short question or blank answer is the `shape` gate instead |

## How to test
Automatic tests in `tests/blocks/test_card_writer.py`, with a **fake `ask`** and a **fake `check`** (never real Claude), and small source files written in the test (an html source with a matching `Source` record and fake fetch, or a pre-placed file whose size and SHA-256 match):
- **Prompt:** the system prompt contains the whole of `docs/LEARNING_GOALS.md`; the user prompt contains the topic and the source text; the schema and model are passed; `n` is in the prompt
- **Gates:** a draft with a 5-character question → `shape`; a quote not in the source → `quote`; the same question twice (different case/spacing) → second is `repeat`; the same question twice where the checker rejects the first → the second is checked (and kept if it passes), not `repeat`; checker `ok=False` → `checker` with its reason; checker raising `ClaudeError` → `checker`, `checker_errors` 1, run goes on; drops are listed in draft order
- **Cards:** ids follow `<slug>-<asks>-<k>` (`how_sure` → `how-sure`), skip `taken_ids` and repeats within the run; receipt source/quote/page are right (page from `find_quote`, e.g. 2 for a two-page PDF-like source of page keys); topic is the given topic
- **Report and bar:** counts add up (`kept + all drops == drafted`); passes with what/how/how_sure kept and ≥80% quotes found and ≥ half kept; fails when "how_sure" is missing, when 3 of 10 quotes are missing, when fewer than half are kept, and when nothing was drafted; `model_dump()` has `passed`
- **Prompt pages:** a one-page source has no `[page` marker in the prompt; a two-page source has `[page 1]` before page 1's text and `[page 2]` before page 2's
- **Errors:** missing source record, a record whose `id` isn't `source_id` → `ValueError` before any Claude call, too-long source, `n` 0 and 21, topic `"!!!"`, a bad reply → `ClaudeError`, more than `n` drafts → first `n` used
- **slug:** `"Epigenetic clocks!"` → `"epigenetic-clocks"`, `"  mTOR  "` → `"mtor"`
- **CLI** (fake `write_cards`): writes `data/cards/<slug>.jsonl` under a temporary `CARDS_DIR` (monkeypatch `longevity_trainer.cli.CARDS_DIR`); `--dry-run` writes nothing; an existing file without `--replace` → exit 1 and `write_cards` not called; with `--replace` it's overwritten; exit 1 when the report doesn't pass or nothing was kept; the written lines load back with `load_cards`; `--dry-run` with the file already there calls `write_cards` and writes nothing; `write_cards` gets `taken_ids` = the ids in the other card files, not those in the topic's own file; another card file with a bad line → exit 1 and `write_cards` not called; a broken topic file is still replaced with `--replace`; no `.tmp` file is left behind; the output includes a line with "Claude calls"
- **Contract test:** folder parts exist and `BLOCK_SPEC` matches this SPEC

**The writer eval (by hand, real Claude):** `write-cards --dry-run` on 3 topics (rapamycin / `pearl-2025`, epigenetic clocks / `measuring-biological-aging-2020`, physical activity / `who-physical-activity`). Bar: each run passes the writer bar. Then the user spot-checks 10 kept cards 👍/👎; every 👎 becomes a rule in LEARNING_GOALS or a line in the exam.
