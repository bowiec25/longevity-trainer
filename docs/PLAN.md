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
- [x] **M2 Sources in** (issue #11; closed early, rest postponed)
  - [x] 1. Topic map: `docs/TOPIC_MAP.md` + `data/topics.jsonl`: 73 topics from the primer's sections; 59 quiz now (v1), 9 wait for M5 (dated), 5 read-don't-quiz; 9 groups for the fan-out
  - [x] 2. ADR 0007: trusted sources + licences: tiers A guideline · B major-journal review · C the study itself (only for claims about it); never news, company sites, preprints or the primer; commit the record + short quotes, never the document
  - [x] 3. Pinned 3 real sources by hand (WHO page · Aging Cell review · PEARL), findings in `docs/SOURCE_FORMATS.md`: many official sites block programs (skipped); three formats (PDF, HTML, JATS XML); Europe PMC's API is the road to open journal articles, with machine-readable licences; preprint twins rejected
  - [x] 4. **Changed (2026-11-12): Claude marks open answers** (`marking` block): the user asked to drop the source-checker work ("the least important part") for now. `uv run longevity quiz` sends any answer the answer list calls wrong to Claude; `--no-judge` turns it off
  - ⏸ Postponed (see FUTURE.md): `source_vetter`, the fan-out source finder, the coverage check (`source_text` moved into M3 Step 1)
- [x] **M3 Questions with receipts** (issue #17, done 2026-11-12): an agent writes cards, a checker agent applies the LEARNING_GOALS rules, both measured on labelled eval sets. `claude -p` (subscription), not the Agent SDK + API key: one structured call per card needs no tools
  - [x] 1. `source_text` block (quizkit): plain text from PDF, HTML and journal XML; `receipts` now checks quotes in any format (source records gain `format`). Leaves out hidden page parts, reference lists, author notes and formula code
  - [x] 2. Card eval set before any agent: 29 labelled cards in `tests/data/card_eval.jsonl` (13 good, 16 bad; your labels + planted bad ones per rule; every quote checked). An independent review fixed 11 unfair labels. Your steer became rule 4: for a trial, know what it meant, not its sample size. Bar: every bad card caught, ≤1 good flagged
  - [x] 3. `card_checker` agent block (Haiku, prompt v2): reads each card like a strict teacher against LEARNING_GOALS §2. Across 14 real runs, incl. 12 fresh held-out cards it was never tuned on, **no bad card got through**; it wrongly rejects about 30% of good cards (bar: ≤ a third, your call; tuning later). Sonnet was stricter and dearer. The checker also caught 4 real flaws in our own exam cards
  - [x] 4. `card_writer` agent block (Sonnet, prompt v3): drafts cards from one source; code checks the quote is really there and drops repeats, then the checker. Writer eval: every run found all its quotes (0 invented); prompt v2 ("the quote alone must back the whole card") lifted kept cards from ~1/3 to ~5/8; 2 of 3 topics pass the bar each run (the miss: no "how" card; run again). Your spot-check: 10/10 👍. ADR 0008: `claude -p`, not the Agent SDK
  - [x] 5. First bank: **63 cards** (15 hand-made + 48 by the writer), every quote found: rapamycin 8, epigenetic clocks 8, physical activity 7, and the hallmarks review in 4 sections via `--pages` (25). Only gap: no "how" card for rapamycin (PEARL is a trial report, not a mechanism source). (User, 2026-11-12: science first: drugs and supplements, the hallmarks, and the factors (exercise, sleep, diet); companies later, as M5 dated cards)
  - [x] 6. Grow the bank as we go (user, 2026-11-12: "come up with new cards as we go, not just a bank we never update"): `write-cards --add` appends new cards to a topic and skips questions already in the bank (and the writer is shown them, so it doesn't reword them); every card that passes the gates is saved, and a coverage line says which asks a topic still needs. M5 then runs it on a schedule
- [x] **M4 A quiz you can use every day** (issue #23)
  - [x] 1. Saved progress + spaced repetition: new block `study` wraps quizkit's `deck_builder`, `leitner`, `progress_store` and `progress`. `longevity quiz` deals due cards, then new ones (never cards not due yet: answering early would move them up a box early); "Nothing due, next card due …" otherwise; `--topic hallmarks`, `--practise` (review anything, nothing saved), `--no-save`; `longevity stats` per topic group. Your progress lives in `data/progress.db` (gitignored); tests can't touch it
  - [x] 2. Marking eval: 23 borderline answers you labelled (`tests/data/marking_eval.jsonl`), marked exactly as the quiz marks (answer list first, then Claude). Two real runs: **21/23 both times, no wrong "yes": PASSED** (bar ≥90%, no wrong "yes"). The 2 misses are answers you'd accept that Claude found too short (strict on the safe side). `uv run longevity check-marking-eval`. Your 👎 on the sedentary-behaviour card removed it (bank: 62) and became LEARNING_GOALS example 12. Reuse: quizkit gained a shared eval scorer and a one-file JSONL loader; a card becomes a question in one place (`card.to_question()`)
  - [x] 3. A web page to play on (Streamlit, like HSK's `hsk web`): the quiz, the receipt after each answer, and stats, on the same blocks (user, 2026-11-12: "I'm gonna wait for the Streamlit setup to play")
    - [x] 3a. One brain for both screens: new block `quiz_round` (set up a round, what to say after each answer, and `QuizScreen`, the click-by-click quiz for a web page). The terminal now uses it, with unchanged output. ADR 0009
    - [x] 3b. The page: `uv run longevity web` opens it in your browser (this computer only). Quiz page: pick one or more topics (2026-11-14: tick several in one box), type answers, Claude marks them, "count it as right?" buttons when Claude can't check, the receipt quote after every answer. Stats page: the same lines as `longevity stats`. The launcher and Markdown-safe text are a new quizkit block, `web_launch`, generic for any quiz (port to HSK)
- [ ] **Questions that build an expert** (user, 2026-11-13: "the questions should be made up based on trying to make a longevity expert"; first pick: connecting things)
  - [x] 1. Connect cards: a fifth ask, "what does it connect to?" (LEARNING_GOALS question 6). The writer links a topic to another topic in `data/topics.jsonl` (what it acts on, its hallmark or pathway, what measures it, which trial tested it); a new code gate checks the link names a real other topic. First real run: rapamycin → dogs (TRIAD)
  - [ ] 2. Fill the bank: run the writer over more topics, so there's more to connect
    - [x] 2a. Drugs and supplements: 4 open-access reviews pinned (tier B: rapamycin/mTOR *GeroScience* 2021, metformin *Ageing Res Rev* 2025, NAD+ *Aging Cell* 2024, senolytics *J Intern Med* 2020); +19 cards (bank 81, 81/81 quotes found), incl. 4 connect cards (metformin → AMPK, NAD+ → sirtuins, senolytics → geroscience). Rapamycin now has its "how" card. Gaps: NAD+ has no "how sure", senolytics no "what"
- [x] **Shelves for topics** (user, 2026-11-18: the topic box mixed levels, "metformin and rapamycin are like drugs category, not their own"): 7 shelves (How we age, Big ideas, Drugs & treatments, Supplements, Lifestyle, Measuring ageing, Evidence & trials; + Industry later), an `area` on every line of `data/topics.jsonl`; new block `topic_map` maps each card to its shelf; the page's box lists shelves
- [ ] **Easy and hard mode, every hallmark covered** (user, 2026-11-18: "even if you fully memorized the full source document … I'm not sure you could get 100% right"; "as a learner it's important I learn all"; ADR 0010)
  - [x] 1. Tag each card easy (your primer states it, proven by a primer quote code finds) or hard: new agent block `primer_check`, `difficulty` on cards, `longevity tag-levels`. Whole bank tagged
  - [x] 2. The easy / hard switch: the page's "Hard mode" checkbox (off = easy), terminal `longevity quiz --hard`; `RoundOptions.easy` in `quiz_round`
  - [ ] 3. Every hallmark covered
    - [x] 3a. The 12 hallmarks are `parts` of `hallmarks` (`data/topics.jsonl`); the 25 bundle-topic cards re-filed to their one hallmark (only `topic` changed); one duplicate navitoclax card dropped; `longevity coverage hallmarks` shows each hallmark's easy what / how cards: 1 of 12 covered
    - [ ] 3b. Fill the gaps: now part of the chapter fills below (chapter 02)
  - [x] 4. The writer aims at the primer (`write-cards --primer-pages A-B`: the topic's primer pages go in the prompt, "facts the primer states first", quotes still from the source; prompt v6); every run that meets the bar tags its new cards easy/hard before writing
- [ ] **Every chapter covered** (user, 2026-11-18: "lets make sure we dont have gaps elsewhere too"; the primer's chapters are the topics, the lines of `data/topics.jsonl` their sub-topics)
  - [x] 1. The whole-syllabus report: `longevity coverage` with no topic lists every chapter and sub-topic with its easy / hard cards and gaps (`topic_map.syllabus_lines`). First run: 1 of 59 sub-topics covered in easy mode
  - [x] 2a. The writer fills gaps: `write-cards --ask how` writes only the missing ask; with `--primer-pages` it keeps only easy cards (and, for a how gap, hard how cards: 2d; both replaced by 2e: a gap fill keeps every card); prompt v7 writes for a well-read non-specialist (user, 2026-11-18: "these questions are too niche")
  - [x] 2c. Priorities (user, 2026-11-18: "we might need a way of prioritizing the important stuff"): every sub-topic is core (28), useful (20) or extra (11) in `data/topics.jsonl`; the report shows the score per tier; `longevity coverage --todo` lists what to fill next, core first. **Fills now go core first, across chapters.** User moved peptides and the clocks up to core
  - [x] 2h. Wide review of the whole bank (user, 2026-11-20: "use a wide view"): an independent agent read all 227 cards for niche, duplicate, misfiled, dated and lopsided topics; 70 cut, 11 moved, then the missing main ideas filled (SELECT, VITAL, ApoB...) plus 8 extras; bank 181 cards (PR #49)
  - [x] 2g. Cards must be useful to know in the longevity world (user, 2026-11-20: "the questions are forgetting that it needs to be useful to know in longevity space", after cutting many drafts as "way too niche"): the writer's FIRST RULE (prompt v9) and LEARNING_GOALS rule 4 (so the checker, prompt v3, applies it too). Mechanism = what it acts on, in plain words; not molecular steps, lab methods or regulatory details
  - [x] 2f. A "What's in each topic" page in the web app (user, 2026-11-20: "a brief summary of whats in each chapter topic I can select", not completion counts; a first version with counts was rejected): one folding section per quiz topic (area) with a one-line summary (`AREA_SUMMARIES`, our words) and its sub-topics. Read-only, from `topic_map.topic_guide`
  - [x] 2e. Covered = learnable (user, 2026-11-19): a what and a how card at any level; the report adds "In easy mode: k of n"; a gap fill keeps every card that passes the gates (the easy-only filter dropped core cards when the primer is brief); prompt v8 (a how card is kind explain). Evidence grades quiz GRADE (Cochrane Handbook ch. 14, tier A; user chose this over "read, don't quiz")
  - [x] 2d. A "how" card counts at any level (user, 2026-11-19, option 1: the primer gives most sub-topics one line, so an easy "how" is rarely possible). Covered = an easy what (easy mode) + a how card (any level, hard mode); the reports say "covered", not "covered in easy mode". A how gap fill keeps hard how cards (replaced by 2e). Hallmarks 10 of 12
  - [ ] 2b. Chapter 01 "What ageing is": 3 sources pinned (Kirkwood 2015 on Gompertz, Garmany 2021 on the healthspan gap, Flatt & Partridge 2018 on why we age); healthspan and why-we-age covered; Gompertz still needs an easy "how" (its source is about the maths)
  - [ ] 2. Fill chapter by chapter, in primer order (01-04 first): a trusted source per sub-topic (listed in each PR, the user can veto), then `write-cards --primer-pages` until the chapter shows covered. One PR per chapter
- [ ] **Exams for every agent** (user, 2026-11-20, after reading Anthropic's "Writing tools for agents": give each agent an exam, read why it fails, let Claude adjust its prompt, re-run the exam to prove it; "double lines of defence")
  - [x] 1. Checker exam gains the user's niche cuts: 24 cut cards (should fail) and 8 kept (should pass), split between the main exam and the held-out set. The old checker let 7 of them through on the main exam ("the mechanism is the point"); prompt v4 names what is too niche even when the quote backs it. The bar now allows a few fringe misses (a sixth; user: "im fine with a few fringe cases"). Sonnet did no better, so Haiku stays
  - [x] 2. Writer exam: new block `writer_exam` + `longevity writer-exam` (8 fixed jobs, 2 held out; dry runs, saves nothing). Scores drafts kept, why the rest died (niche counted separately), empty jobs, checker outages, cost; bar: 2 in 5 kept, at most 1 empty job, no invented quotes. Baseline (writer v9, checker v4): main 13/24 kept (54%, PASSED, 4 niche), held out 2/7 (28%, NOT PASSED, 2 niche); $1.10 for both
  - [ ] 3. Writer fixes, each proven on the writer exam: why drafts failed and a clear "nothing written"; only the topic's section of a paper
  - [ ] 4. The loop written into CLAUDE.md (exam, read failures, Claude proposes, exam decides); primer check gets a small lasting exam; marker's wrong marks join its exam
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
