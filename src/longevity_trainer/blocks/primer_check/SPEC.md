# Block: `primer_check`

> **In plain words:** Tag each card easy or hard: easy when the user's primer states the card's fact, proven by a word-for-word primer passage

## Goal
Tag each card easy or hard: easy when the user's primer states the card's fact, proven by a word-for-word primer passage

The exam on the textbook you were given, and the extra reading. The user (2026-11-18): "even if I fully memorised the source document I'm not sure I'd get 100%". The card writer reads whole sources, so many cards go beyond the primer. This block sorts them: **easy** cards are facts the primer states (if you knew the primer cold, you'd get them all), **hard** cards are the extra reading. A tag needs proof, like a card needs a receipt: Claude must quote the primer word for word, and **code** finds that quote in the primer, or the card is hard. The primer stays a checker, never a receipt, and its text never enters the repo (ADR 0010).

**Not in scope:** dealing easy or hard cards (`quiz_round`, next step); writing cards (`card_writer`); judging whether a card is good (`card_checker`).

## Kind
**agent.** Whether the primer states a card's fact, in other words, needs judgment. One Claude call per batch via `claude -p` (ADR 0008), reply forced by a JSON schema; then the script check above decides.

## Inputs
| Input | Type | Plain meaning |
|---|---|---|
| `cards` | `list[LongevityCard]` | The cards to tag (the CLI sends one topic group per call, e.g. all hallmark cards) |
| `primer_pages` | `list[str]` | The primer's text, one string per page (`load_primer()`) |
| `ask` | callable | How to reach Claude (default quizkit's `ask_claude`). Tests pass a fake |
| `model` | `str` | default `"sonnet"` |
| `path` | `Path \| None` | For `load_primer`: the primer PDF (default `None`: `PRIMER_FILE`, looked up when called) |

**How it's called** (importable from `longevity_trainer.blocks.primer_check`):
```python
pages = load_primer()
result = tag_cards(hallmark_cards, pages)  # TagResult
result.difficulty["hm-telomeres-name"]  # "easy"
```

**From the command line:** `uv run longevity tag-levels [--dry-run] [--retag] [--primer PATH]`.
- It reads the primer (default `PRIMER_FILE`) and every card file in `CARDS_DIR`. It groups the cards by topic group (`study.group_of`) and calls `tag_cards` once per group that has cards to tag.
- Cards that already have a difficulty are skipped, unless `--retag` is given. A group with nothing to tag isn't sent.
- It prints one line per card (`easy <id>` or `hard <id> (<reason>)`), then a summary line per group (`<group>: <e> easy, <h> hard`), then (if anything was tagged) one line with the model and prompt version (`sonnet (prompt v1)`), then the Claude-cost line (calls, tokens, cost). **The primer's text is never printed or written** (only ids, easy/hard and the three fixed reasons).
- **Without `--dry-run`** it writes each changed card file with `difficulty` set: each card's line is `model_dump_json()`, in the same order, and other cards are unchanged. Each file goes to `<file>.tmp` first and is then swapped in, so a failed write keeps the old file (exit 1, one line).
- **One read:** if a card file's content changed during the run, it isn't written ("… changed during the run, run again", exit 1). The other files are still written.
- **Exit 1 with one line, before any Claude call:** the primer is missing or can't be read (any error from reading the PDF), or has no text on any page (a scan), or the card bank has a problem (a bad line or a repeated id). A card id with spaces around it in the file is matched after stripping, as the loader strips it.
- A `ClaudeError` for one group prints one line naming the group. That group's cards stay untagged, the other groups go on, and the exit code is 1.
- **Exit 0** when everything it sent was tagged.
- The CLI looks `tag_cards` and `load_primer` up on the `cli` module, so tests can replace them.

## Outputs
| Output | Type | Plain meaning |
|---|---|---|
| `PRIMER_FILE` | `Path` | `Path.home() / "Desktop" / "Longevity_Platform_Blueprint" / "1_DOCS" / "longevity_trends_primer.pdf"`: the user's own primer, outside the repo, never committed |
| `load_primer(path=None)` | `list[str]` | The primer's pages as text (`source_text.text_pages(path, "pdf")`). Missing file → `FileNotFoundError` |
| `tag_cards(cards, primer_pages, ask=ask_claude, model="sonnet")` | `TagResult` | One Claude call for all the cards; returns each card's difficulty and why. No cards → an empty result, and Claude isn't called |
| `TagResult` | pydantic model | `difficulty: dict[str, "easy" \| "hard"]` (every card id given, nothing else), `reasons: dict[str, str]` (for each **hard** card, one of `"not in the primer"`, `"primer quote not found"`, `"no verdict"`), `model`, `prompt_version` |
| `PROMPT_VERSION` | `str` | `"1"`; bumped when the prompt changes |
| `MIN_QUOTE_KEY` | `int` | `30`: the shortest quote key that counts as proof |

**The rule, per card:**
- Claude's reply holds, per card: `card_id`, `in_primer` (bool), and `primer_quote` (1 to 3 consecutive sentences copied exactly from the primer that state the card's answer; `""` when `in_primer` is false).
- `in_primer` true **and** the quote's key (`to_key`) has at least `MIN_QUOTE_KEY` = 30 characters **and** it is found in the primer (`receipts.find_quote` over `to_key` of each page) → **easy**.
- `in_primer` true but the quote is too short (a word like "mTOR" is found somewhere in any primer) or isn't found → **hard**, `"primer quote not found"`.
- `in_primer` false → **hard**, `"not in the primer"`.
- A card missing from the reply → **hard**, `"no verdict"`.
- Reply entries for ids not sent are ignored. If an id appears twice, the first entry counts.

**What the prompt contains:**
- **System:**
  - You decide, for each quiz card, whether the user's primer states the fact the card's answer gives: the same claim, not merely the same topic. A paraphrase in the primer counts, a related but different fact doesn't.
  - When it does, copy 1 to 3 consecutive sentences exactly from the primer (a script checks them). Never paraphrase the quote, and keep it inside one `[page N]` part.
  - When unsure, answer false: hard is the safe side.
- **Prompt:** the cards (id, question, accepted answers), then the primer's text with each page starting `[page N]`.
- **Reply schema:** `{"verdicts": [{"card_id": str, "in_primer": bool, "primer_quote": str}, ...]}`.

## Tools
- `quizkit.claude.ask_claude`, `ClaudeError`
- `quizkit.blocks.receipts`: `find_quote`, `to_key`
- `quizkit.blocks.source_text.text_pages`
- `longevity_trainer.blocks.card_bank`: `LongevityCard` (the CLI also uses `CARDS_DIR`, `load_cards`)
- the CLI only: `longevity_trainer.blocks.study.group_of` (grouping)

## Failure modes
| Situation | What it does |
|---|---|
| The primer file is missing | `load_primer` raises `FileNotFoundError`; the CLI prints one line, exit 1, no Claude call |
| Claude can't be reached, or its reply isn't valid JSON or breaks the schema | `tag_cards` raises `ClaudeError` (`"bad reply: …"`); the CLI reports that group and goes on (exit 1) |
| A verdict quotes something not in the primer | That card is hard (`"primer quote not found"`): no proof, no easy tag |
| A card is missing from the reply | That card is hard (`"no verdict"`) |
| `cards` is empty | Empty `TagResult`; no Claude call |
| A card file has a bad line or repeated id (CLI) | One line, exit 1, no Claude call |
| A card file changed during the run, or can't be written (CLI) | That file isn't written (one line); the old file stays; exit 1 |

## How to test
Automatic tests in `tests/blocks/test_primer_check.py`, with a **fake `ask`** (never real Claude) and a fake primer (a few page strings written in the test, never the real PDF):
- **tag_cards, short quote:** a real one-word primer quote (e.g. `"telomeres"`) with `in_primer` true → hard `"primer quote not found"`; `MIN_QUOTE_KEY == 30`
- **tag_cards:** the rule above, one test per branch (easy with a quote on page 2; `in_primer` with a made-up quote → hard `"primer quote not found"`; `in_primer` false → hard `"not in the primer"`; a missing card → hard `"no verdict"`); extra ids ignored; a repeated id → the first entry counts; `difficulty` has exactly the ids sent; `reasons` only for hard cards; no cards → no call
- **Prompt:** the system prompt says same claim not same topic, quote exactly, unsure = false; the user prompt has each card's id, question and answers, and the primer's pages marked `[page 1]`, `[page 2]`; the schema and model are passed; a bad reply → `ClaudeError`
- **load_primer:** with no argument it follows a monkeypatched `PRIMER_FILE`; a missing file → `FileNotFoundError`
- **CLI** (fake `tag_cards` and `load_primer`, a temporary `CARDS_DIR`):
  - output and grouping: one call per group that needs tagging; cards with a difficulty are skipped unless `--retag`; the per-card lines and the per-group summary are printed; the cost line includes "Claude calls"
  - writing: without `--dry-run` the files get `difficulty`, other cards' lines are unchanged in content and order, and the files load back with `load_cards`; `--dry-run` writes nothing; no `.tmp` file is left
  - privacy: a fake `tag_cards`/primer whose pages hold a distinctive sentence → that sentence appears neither in the output nor in any card file
  - the model line (`<model> (prompt v<version>)`) is printed when something was tagged
  - failures: a missing primer → exit 1 with no `tag_cards` call; a primer whose load raises a non-OS error (e.g. a `RuntimeError`) → one line, exit 1, no call; a primer with only blank pages → one line, exit 1, no call; a bad card file → exit 1 with no call; a `ClaudeError` for one group leaves its cards untagged while another group is still written (exit 1); a file edited during the run (the fake edits it) isn't written (exit 1)
- **Contract test:** folder parts exist and `BLOCK_SPEC` matches this SPEC

**By hand (real Claude):** `tag-levels --dry-run` on the bank. The user spot-checks 10 tags 👍/👎. Each 👎 becomes a line in the prompt, which bumps `PROMPT_VERSION`.
