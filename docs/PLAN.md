# Where we are

- [x] Plan agreed (2026-11-12)
- [x] **M0 Plan + setup** (done 2026-11-12)
  - [x] 1. Plan written: `docs/PLAN.md`, `docs/SETUP_LOG.md`, `docs/FUTURE.md`
  - [x] 2. Project + git: `uv init --package` (Python 3.13; hello runs), branch renamed `master` → `main`, `.gitattributes` (LF + `data/raw/**` byte-for-byte)
  - [x] 3a. Skeleton (copied from HSK, then adapted): `.gitignore` (+ `*.pdf`), `.env.example` (no keys needed), README, `CLAUDE.md`, ruff + pytest, smoke test, CI (versions looked up: checkout v7.0.1 + setup-uv v10.3.3, both pinned to SHAs), PR template + "Still the right thing?" issue form + PR check (22 tests); 24 tests green; first commit
  - [x] 3b. Build map started: `docs/build-map/index.html` (HSK's look) + snapshot `m0-step3.html`, published as the "Longevity Trainer Build Map" artifact; plus the **name & recall** card kind (user: naming drugs, hallmarks etc. underpins the work)
  - [x] 4. GitHub repo created by the user (`! gh repo create`, public: github.com/bowiec25/longevity-trainer; Claude Code blocks Claude from making public repos), 3 commits pushed, first CI run green (log checked: 24 passed); push protection + secret scanning on
  - [x] 5. Protect `main` (mirrors HSK: PR + green `check` required, up to date with main, admins included, 0 approvals, no force-push / delete; squash-only, auto-delete branches); a direct push was rejected; this step's docs went in as the first PR
- [ ] **M1 Foundations + first playable slice** (issue #2)
  - [x] 1. Plan update: one tool to learn per milestone
  - [x] 2. Copied quizkit (HSK `caa969a`; identical at HSK HEAD `3d91733`) + its generic tests + the capitals example; only change: `scaffold.py` package name. 537 tests pass
  - [x] 3. Copied the Claude safety rails from HSK, unchanged (the user ran the copy: Claude Code blocks Claude editing its own `.claude/` settings): `.env` block hook, auto-format hook, allow/deny permissions, 19 hook tests. ⏳ Live test (Claude tries `.env`, is blocked) in the next session started inside this folder
  - [x] 4. ADRs 0001–0005 in `docs/decisions/`: scope, script vs agent, quizkit copied, receipts, testable + kinds of card
  - [x] 5. Learning goals + the question standard (`docs/LEARNING_GOALS.md`; user's steer: define what a good question is before making any): five questions per topic (what, how, how sure, catch, popularity); 11 examples labelled by the user
  - [x] 6. 15 hand-made hallmark cards with receipts (`data/cards/hallmarks.jsonl`), pinned source (`data/sources/`), quote check `uv run longevity check-receipts` (15/15 found)
  - [x] 7. Play them: `uv run longevity quiz` (grader for names; you mark explain answers yourself; receipt after each answer). Your play-test closes M1
- [x] **The build loop, restored and enforced** (ADR 0006; caught by the user after M1: steps 6–7 skipped HSK's loop)
  - [x] Copied HSK's `test-writer` + `block-reviewer` subagents and the Claude GitHub review workflow (⏳ needs the `CLAUDE_CODE_OAUTH_TOKEN` secret from the user)
  - [x] CI guards: `tests/test_process.py` (every module a block with a SPEC + its own tests) and `check_reviews.py` (PR must tick test-writer, block-reviewer, `/code-review`)
  - [x] Steps 6–7 redone through the loop: quizkit blocks `receipts` (quote check) and `jsonl_loader` (folder of records), longevity block `card_bank`; `longevity check-receipts` replaces `python -m longevity_trainer.receipts`
- [ ] **M2 Sources in** (issue #11)
  - [x] 1. Topic map: `docs/TOPIC_MAP.md` + `data/topics.jsonl`: 73 topics from the primer's sections; 59 quiz now (v1), 9 wait for M5 (dated), 5 read-don't-quiz; 9 groups for the fan-out
  - [ ] 2. ADR 0007: trusted sources + licences
  - [ ] 3. Pin 3 real sources by hand first (different tiers)
  - [ ] 4. `source_vetter` block (quizkit), through the loop
  - [ ] 5. Fan-out workflow: one agent per group finds sources; a script pins + vets
  - [ ] 6. Coverage check: every v1 topic has a source or is marked
- [ ] **M3 Questions with receipts**
- [ ] **M4 First playable quiz**
- [ ] **M5 Freshness**
- [ ] **M6 Smarts + web**

---

# The plan

## Goal
A quiz that tests my longevity knowledge: health, ageing, sleep, exercise, nutrition, and the science behind them. Built the same way as `mandarin-hsk-trainer` (its `docs/PLAYBOOK.md` is the checklist), reusing its generic `quizkit`.

## What's different from Mandarin
Mandarin had one fixed word list, so the truth was easy. Longevity facts can be **wrong, contested or out of date**. So the main design problem is **where questions come from and how we know they're right**, not the quiz itself. M2, M3 and M5 are about that.

## Where questions come from: every answer carries a receipt
A card can't exist without a pinned source and a word-for-word quote from it that backs the answer. (Decided in detail in M2 with an ADR.)

| Layer | Who | What it checks | Strictness |
|---|---|---|---|
| 1. Trusted source list | User + Claude, once (M2, ADR) | Only guidelines, consensus statements, systematic reviews from named bodies (e.g. NIH/NIA, WHO, CDC, NHS, Cochrane, AASM) | 🔴 code rejects other sources |
| 2. Pinned copy | Script | Source saved with URL, date, SHA-256 fingerprint | 🔴 |
| 3. Claude writes the card | Agent | Question + answer + the quote that supports it | n/a |
| 4. Quote check | Script | The quote appears word for word in the saved source | 🔴 |
| 5. Meaning check | Read-only `fact-auditor` subagent | Does the answer follow from the quote? Too strong? Missing caveat? Flagged = removed, no human gate | 🔵 + dated report |
| 6. Freshness | Script, on a schedule (M5) | Re-fetch sources; changed fingerprint or past a review-by date → card pulled until re-checked | 🟠 |

After each answer the quiz shows the receipt: source, year, quote.

**Open (decide in M2):** licences (a public repo re-publishes what we save: US-government pages are public domain, WHO/NHS/Cochrane have their own terms, so for some we may commit only short quotes + fingerprints); contested topics ("contested" label, or left out of v1); answer type (free text marked by the Claude judge vs multiple choice).

## The primer: the syllabus (added 2026-11-12)
`Desktop\Longevity_Platform_Blueprint\1_DOCS\longevity_trends_primer.pdf` (92 pages, 23 sections, the user's own synthesis, dated 2 Oct 2026) is **what to learn**, not a source: it has almost no citations and says "the field moves weekly". Every fact taken from it still needs a receipt from a trusted source, which also checks the primer. The PDF stays out of the public repo; we commit only a topic map in our own words.

**Testable** = one clear right answer, stated by a trusted source, true for about 2+ years. Otherwise "read, don't quiz".

**Kinds of card**, so the whole primer can be learned, not just the easy facts:

| Kind | Example | Marked by | Primer parts | When |
|---|---|---|---|---|
| **Name & recall** ⭐ the core (user, 2026-11-12) | "Name the 12 hallmarks of ageing" · "Rapamycin blocks which pathway?" → mTOR · "Semaglutide is which class?" → GLP-1 | grader per item; lists are order-free with a partial score (a **list grader is new**: quizkit marks one answer at a time) | 2 (hallmarks, nutrient-sensing dials), 3, 6–9 (drugs, supplements) | v1 |
| Fact recall | "Death risk doubles about every __ years" → 8 | grader (exact/typo) | 1, history, numbers | v1 |
| Term | "What is a senolytic?" | Claude judge, gist rubric (in quizkit) | Glossary, 1–4 | v1 |
| Explain the idea | "Why does geroscience expect to delay many diseases at once?" | judge, gist rubric vs the source | 1–3 | v1 |
| Grade the evidence | "Best evidence for NMN in healthy people?" → C (the primer's A–E grades) | exact | 2, scorecards | v1 |
| Dated fact | "UK monthly cost of GLP-1s?" | exact + "as of" date, expires | 3–5 | after M5 |
| Read, don't quiz | podcasts, events | not a card | 5 | never |

**v1 focus (user, 2026-11-12):** naming and recalling the building blocks (hallmarks, pathways, drugs and what they do) underpins everything; then mechanisms, science and history: sections 01–04, the science in 06–10, some of the testing in 11–13. "Think about how best to learn everything in the doc" → the card kinds above; dated industry facts wait for M5.

M1 adds an ADR "what's testable + kinds of card". M2 starts with a **topic map of the primer** (each section → card kinds → testable or not), then picks sources that can back those topics.

## The two hard parts: writing questions and marking them (user, 2026-11-12)
Curating the **card-writing agent** and **how answers are marked** will be a big part of this project, so each gets the HSK judge treatment (playbook M4 lesson: "an AI judge needs an eval, not just tests"):
- **card_writer (M3):** a prompt per kind of card; a hand-labelled set of good and bad cards (e.g. answer too strong for the quote, two right answers, trivia nobody needs); a bar set before running; the fact-auditor's planted test with an answer key.
- **Marking (M4):** a rule per kind of card (exact, typo, list grader, Claude judge with a rubric); a hand-labelled eval set of borderline answers **you** label (your labels become rules in the prompt, as with HSK's gist rubric); the bar: at least 90% right and no wrong "yes".
- Both are re-run whenever a prompt or model changes.

## Sharing quizkit: copy it in
Copy `src/quizkit/` (about 2,100 lines; needs only `pydantic` + `rapidfuzz`) and its tests from `mandarin-hsk-trainer` commit `caa969a`, and record that commit in an ADR (M1).
- **Not installed from the Mandarin repo:** that package ships quizkit *and* the Mandarin code, pulls in `pypinyin`, `streamlit` etc., and every quizkit change would need a Mandarin release.
- **Copy suits now:** this quiz will probably change quizkit (a source on cards, a receipt-checking judge rubric). Easier in place while learning.
- **Later:** extract quizkit into its own repo, installed by both (see `docs/FUTURE.md`).

## Milestones

**The user's goal (2026-11-12):** learn the tools, and build a useful way of learning that scales. So each milestone is useful on its own **and** teaches one new tool:

| Milestone | Useful result | Tool to learn |
|---|---|---|
| M1 | 15 hallmark cards, playable | reuse + tests |
| M2 | trusted sources for every topic | a fan-out workflow (one agent per topic) |
| M3 | cards written automatically | the **Agent SDK** + subagents (API key, small spend) |
| M4 | answers marked well | `claude -p` + eval sets |

| # | Name | "Done" looks like |
|---|---|---|
| M0 | Plan + setup | Public repo, CI green, `main` protected, docs + build map |
| M1 | Foundations | ADRs (scope, script vs agent, quizkit copy, sources + receipts, what's testable + kinds of card), quizkit copied with its tests passing, hooks / permissions / subagents / skills copied, reuse-scan test |
| M2 | Sources in | Topic map of the primer (section → card kinds → testable?); source list researched + pinned (fingerprints, licences); real pages looked at before any SPEC |
| M3 | Questions with receipts | `card_writer` agent (prompt per card kind + its own eval set) + quote-check script + `fact-auditor` (planted test); a first bank of about 50 checked cards |
| M4 | First playable quiz | CLI quiz on the quizkit engine; marking rule per card kind (incl. the new list grader) + a judge eval set you label; the receipt shown after each answer |
| M5 | Freshness | Scheduled re-check of sources; changed / expired → cards pulled; one-line summary |
| M6 | Smarts + web | Leitner progress + a Streamlit page (mostly reused) |

## How we work
- Small steps; stop after each one for the user's go-ahead.
- Short, plain messages: analogy first, then a tiny map of where the step fits; detail in closed `<details>` toggles.
- Plan mode for big or unclear steps. Every plan starts with **"Still the right thing?"**.
- No human approval gates: checks act on their own, the user gets a one-line summary.
- Every step: tick this file, add to `docs/SETUP_LOG.md`, `docs/FUTURE.md` for ideas, update the build map (from M0 Step 3).
