# Block: `writer_exam`

> **In plain words:** an exam for the card writer. A fixed list of writing jobs (a topic and its paper), each run as a dry run. We count how many drafts survive, why the rest died (too niche, quote not found, a repeat…), how many jobs end with nothing, and the cost, then check that against a bar. The card checker has the same kind of exam (`card_checker`); this one tests the agent that writes the cards (user, 2026-11-20, after Anthropic's "Writing tools for agents": "double lines of defence").

## Goal
Score the card writer on a fixed list of writing jobs: drafts kept, why the rest died, empty jobs and invented quotes, against a bar. Run before and after every writer change, so a change is kept only if the score says it helps.

## Kind
**script.** The judging is done by the agents already inside the writer (the writer drafts, the card checker judges, code checks quotes); this block only runs the jobs and counts. Counting needs no judgment (ADR 0002).

## Inputs
- **The jobs file** `tests/data/writer_exam.jsonl` (`JOBS_FILE`): one JSON job per line:
  `{"id": "taurine", "topic": "taurine", "source": "taurine-humans-2025", "primer_pages": [34, 35], "pages": null, "asks": null, "n": 4, "holdout": false, "why": "..."}`
  - `id`: unique, letters/digits/hyphens; `topic`, `source`: as for `write-cards`. `id`, `topic`, `source` and `why` are required; the others may be left out and take their defaults. `load_jobs` doesn't check sources (the writer reports a missing one as that job's error); a test checks the real file's sources all have a record in `data/sources/`.
  - `primer_pages`: `[first, last]` or `null`; `pages`: the source's `[first, last]` or `null`; for both, `1 <= first <= last`; `asks`: some of the writer's asks or `null` (all); `n`: 1-20 (default 4); `holdout`: `true` for jobs never used to tune the writer (default `false`); `why`: why this job is in the exam (not empty).
- `load_jobs(path=JOBS_FILE) -> list[ExamJob]`: reads the file; a bad line (not JSON, missing or extra field, bad value, repeated id) → `ValueError` naming the file and line number. Blank lines are skipped. An empty file → `ValueError`.
- `run_writer_exam(jobs, write=write_cards, check=check_card, primer=None, show=print, model="sonnet") -> WriterExamReport`:
  - `write`: the writer function (the real `card_writer.write_cards` by default; tests pass a fake).
  - `check`: the card checker given to the writer; the block wraps it to count, per job, the drafts the checker failed under rule 4 (too niche).
  - `primer`: the primer's pages as a list of strings (page 1 = index 0), or `None`. A job with `primer_pages` and `primer=None` is an error for that job ("no primer"), not a crash.
  - Each job calls `write(topic, source, n=n, model=model, check=<wrapped>, pages=pages, primer_text=<the job's primer pages, as write-cards builds them: "[primer page k]\n<text>" joined by a blank line>, only_asks=asks, taken_ids=set(), taken_questions=set())`. The bank is not passed, so the score doesn't drift as the bank grows.

## Outputs
- `ExamJob` (pydantic, frozen): the fields above.
- `JobScore` (pydantic, frozen): `id`, `holdout`, `drafted`, `kept` (both 0 for a job that errors), `dropped` (a dict gate → count, every gate of the writer's `Drop`: shape, ask, link, quote, repeat, checker), `niche` (checker drops naming rule 4), `error` (`""` or one line: why the job failed).
- `WriterExamReport` (pydantic, frozen): `jobs: list[JobScore]`, totals `drafted`, `kept`, `dropped` (gate → count), `niche`, `empty_jobs` (kept 0, errors included), `errors`, `model`, `prompt_version` (the writer's `PROMPT_VERSION`), and computed `passed`, included in `model_dump()`.
- **The bar** (`passed`): at least one job; `errors == 0`; `kept >= drafted × MIN_KEPT_SHARE` (0.4) with `drafted > 0`; `empty_jobs <= MAX_EMPTY_JOBS` (1); no invented quotes (`dropped["quote"] == 0`). Set before the first run (user, 2026-11-20); the first score is shown to the user before any writer change.
- `run_writer_exam` prints one line per job via `show`: `<id>: kept K/D; dropped quote q, checker c (niche x), repeat r, shape s, ask a, link l` (or `<id>: error: <reason>`), then nothing else (the CLI prints totals and cost).
- **CLI:** `uv run longevity writer-exam [--holdout] [--model sonnet] [--limit N] [--dry-run]`. Without `--holdout` it runs the jobs with `holdout: false`; with it, only `holdout: true`. `--limit N` runs the first N of those; `--dry-run` lists them, calls no Claude and exits 0. A bad jobs file prints one line and exits 1, before any job runs. It reads the primer only if a chosen job needs it (a missing primer makes those jobs errors). It prints the job lines, a totals line `<model> (writer prompt vP): kept K/D (S%, a whole-number percent); niche x; empty jobs e; quotes not found q; errors r -> PASSED|NOT PASSED`, then the cost line (as `write-cards` does). Exit code 0 when passed, 1 when not, 2 for bad arguments. It never writes cards. The CLI calls `run_writer_exam(load_jobs(), …)` through names looked up on the `cli` module, so a test can replace them.
- Constants: `JOBS_FILE`, `MIN_KEPT_SHARE = 0.4`, `MAX_EMPTY_JOBS = 1`.

## Tools
`card_writer.write_cards` (the writer), `card_checker.check_card` (the checker it hands the writer), pydantic. No Claude call of its own.

## Failure modes
- A job whose `write` raises (`ClaudeError`, `OSError`, `ValueError`, `DownloadError` or anything else) → that job scores `error` (one line, the exception's first line), counts as empty and as an error; the other jobs still run (one odd failure mustn't lose a paid run).
- A job needing the primer when `primer` is `None` → error for that job, no `write` call.
- `primer_pages` beyond the primer's length → error for that job, no `write` call.
- Bad jobs file → `ValueError` before any job runs.

## How to test
`tests/blocks/test_writer_exam.py`, with a fake `write` and fake `check` (never real Claude):
- **load_jobs:** reads a good file (blank lines skipped); a missing field, an extra field, `n` 0 or 21, a bad `asks` value, `primer_pages` `[5, 3]`, a repeated id, an empty `why`, and a non-JSON line each → `ValueError` naming the line; an empty file → `ValueError`; the real `JOBS_FILE` loads, has at least 6 non-holdout jobs and at least 2 holdout jobs, ids unique, and every `source` has a record in `data/sources/`.
- **Calling the writer:** the fake `write` receives the job's topic, source, n, pages, `only_asks`, model, empty `taken_ids`/`taken_questions`, and the primer text built from the chosen pages in the write-cards format; a job without `primer_pages` gets `primer_text=""`.
- **Counting:** totals add up over jobs (`drafted`, `kept`, every gate); `niche` counts checker drops whose verdict named rule 4 (a fail naming [3] isn't niche; [3, 4] is), counted through the wrapped `check`.
- **Bar:** passes at 4 kept of 10 and fails at 3 of 10; one empty job passes, two don't; one quote not found fails; one error fails; no jobs fails; 0 drafted fails.
- **Errors:** a `write` that raises → that job's `error` is its first line, it counts as empty and an error, later jobs still run; a primer job with `primer=None` and one with pages past the primer's end → error, `write` not called.
- **Output:** one line per job in the format above; `model_dump()` includes `passed`.
- **CLI** (with `run_writer_exam`/`load_jobs` replaced on the `cli` module): `--dry-run` lists the chosen jobs and calls nothing; `--holdout` picks only holdout jobs; `--limit 1` passes one job; exit code follows `passed`; a bad `--limit` (0, -1, x) exits 2.

**The real exam (by hand, real Claude, about $4–5):** `uv run longevity writer-exam` and `--holdout`. The first score is the baseline, recorded in `docs/SETUP_LOG.md` and shown to the user before any writer change. Then: read why drafts died, let Claude propose a writer change, run again; keep the change only if the score improves on the main jobs and holds on the held-out ones.
