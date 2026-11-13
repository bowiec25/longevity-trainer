# Setup Log: what we did, and why

A plain-English record of each step: **what** it does, **why** it's best practice, and anything worth remembering. New entries go at the bottom.

---

## 🟢 Quick summary

| Step | What we did | Why |
|---|---|---|
| M0.1 | Wrote the plan (milestones, where questions come from, how to share quizkit) | Decide what "done" looks like before building |
| M0.2 | Made the folder a Python project with a change history (git) on `main` | The code has a home, and every change can be undone |
| M0.3a | Added the safety files and checks, mostly copied from the Mandarin project; folded the primer into the plan | Mistakes and leaks get caught early, and the plan covers what you actually want to learn |
| M0.3b | Started the build map, a picture of the project, and made "name & recall" the core kind of card | You can see at a glance what exists; the quiz trains the building blocks first |
| M0.4 | Uploaded to GitHub (public); CI ran green | Backup, and GitHub re-runs the checks on a fresh computer |
| M0.5 | Locked `main`: changes only arrive through a PR with green CI, for everyone | Nothing broken or unreviewed can reach the main copy, by accident or in a hurry |
| M1.1 | Gave each milestone one tool to learn | Your goal: learn the tools while building something useful |
| M1.2 | Copied quizkit (the generic quiz parts) and its tests from HSK | Reuse proven parts instead of rebuilding; 537 tests came with them |
| M1.3 | Copied Claude's safety rails: the `.env` lock, auto-format, permissions | Claude can't read secrets, and its code is always tidy |
| M1.4 | Wrote the first 5 decision records (ADRs) | So nobody undoes a decision by accident, and future you knows why |
| M1.5 | Defined what you want to learn and what a good question is | Cards (and the agent that writes them later) follow your standard, not my guesses |
| M1.6 | 15 hallmark cards, each with a quote a script finds in the pinned review | Proves the receipt idea on real content before any agent writes cards |
| M1.7 | `longevity quiz`: play the 15 cards, see the receipt after each | The first thing you can actually use |
| Loop | The build loop restored and enforced: SPEC → independent test-writer → build → reviewers → PR | Steps 6–7 skipped it; now CI fails if anyone does |
| M2.1 | Topic map: every primer section → topics → card kinds → quiz now / later / never | Decides what M2 needs sources for, and what M3 writes cards on |
| M2.2 | ADR 0007: what counts as a trusted source, and what we may commit | The agents in Step 5 get a clear brief; a script can check it |
| M2.3 | Pinned 3 real sources by hand and wrote down what goes wrong | Real pages before any SPEC (HSK lesson): Step 4 changed because of it |
| M2.4 | Claude marks open answers in the quiz (source checker postponed) | User: fixed answer lists are "a nightmare" for open questions; the receipt work was taking all the time |
| M3.1 | `source_text`: plain text from PDF, web pages and journal XML | 3 of our 4 sources aren't PDFs; the quote check and the card writer both need their text |
| M3.2 | An exam for the card checker, written before the checker | Set the bar before building (HSK lesson), so the result can't be bent to fit |
| M3.3 | Card checker (Claude Haiku) measured on the exam and on fresh held-out cards | A judgment needs an eval, and an eval you tuned on overstates the score |
| M3.4 | Card writer (Claude Sonnet): drafts cards from a source; code and the checker keep only the good ones | Writing a question needs judgment; the gates make sure nothing unchecked reaches the bank |
| M3.5–6 | First bank of 63 cards; `--pages` for long sources; `--add` to grow topics over time | A bank you never update goes stale (your steer); long reviews need one section at a time |
| M4.1 | The quiz remembers: spaced repetition and saved progress, from quizkit's blocks | A daily quiz must bring back what you miss and leave what you know; quizkit already had it |
| M4.2 | Marking eval: 23 answers you labelled; Claude agrees on 21, never says yes to a wrong one | An AI marker needs an exam too, or we're just hoping it's fair |
| M4.3a | One quiz brain (`quiz_round`) for the terminal and the coming web page (ADR 0009) | Two screens with their own copies would drift; HSK did the same before its web page |

---

## M0 Step 1: the plan (2026-11-12)

> **In plain words:** before laying bricks, we drew the house. Seven milestones, and one big rule: every quiz answer carries a "receipt" (a trusted source and a word-for-word quote).

- **Started from the Mandarin playbook** (`../mandarin-hsk-trainer/docs/PLAYBOOK.md`). Its first planning lesson: write down what "done" looks like. The milestone table in `PLAN.md` does that.
- **Skipped "once per computer" steps:** checked, not assumed. `gh` is logged in as bowiec25 with the `workflow` permission, `uv` is 0.13.6, git uses the noreply email.
- **The big question, raised first:** longevity facts can be wrong or go stale. So a card needs a pinned source + a quote a script can find in it, a read-only auditor checks the meaning, and a scheduled job re-checks sources (M5).
- **quizkit is copied, not installed:** installing from the Mandarin repo would drag in the Mandarin code and its libraries; we expect to change quizkit here. Extracting it into its own repo is in `FUTURE.md`.

## M0 Step 2: project + git (2026-11-12)

> **In plain words:** we turned an empty folder into a Python project, and switched on its "undo history" (git).

- **`uv init --package --python 3.13`** made `pyproject.toml` (the project's settings), `src/longevity_trainer/` (where code lives), `.python-version` and a starter `.gitignore`. `uv run longevity-trainer` prints a hello, so the wiring works.
- **The branch trap, again:** uv started git on `master`, just like in the Mandarin project. We checked (`git branch --show-current`) and renamed it to `main`. Playbook lesson: check what a tool actually did. (Optional fix for next time: `git config --global init.defaultBranch main`.)
- **`.gitattributes`** (copied from Mandarin): stores text with Linux line endings, so Windows and CI agree. And `data/raw/** -text` keeps downloaded source files byte-for-byte, so their fingerprints (M2) still match on any computer.
- Nothing committed yet: the first commit comes with the skeleton in Step 3.

## M0 Step 3a: skeleton + the primer (2026-11-12)

> **In plain words:** we moved the scaffolding and safety rails over from the Mandarin house, checked each one still fits, and made the first save point (commit). Your primer became the syllabus.

**Copied from HSK, then adapted** (quicker, and keeps lessons already learned):
- `ci.yml`: GitHub's referee. Same checks as HSK (PR description check → install → ruff → format → pytest).
- `check_pr_body.py` + its 22 tests: fails a PR whose "Still the right thing?" section is empty. Generic, so copied as-is.
- PR template, issue form: trimmed the checklist to what exists now (block and subagent lines come in M1).
- `.gitignore`: Mandarin data files dropped; `*.pdf` added so the primer can never be uploaded by accident.

**Looked up, not copied** (playbook lesson: a guessed version broke HSK's first CI run): `actions/checkout` is now v7.0.1 and `setup-uv` is still v10.3.3. Both are pinned to an exact commit (SHA), because a tag can be moved to different code.

**Written fresh:** README ("every answer carries a receipt"), a short `CLAUDE.md` (your working style, the receipt rule, "primer = syllabus"), `.env.example` (no keys needed: Claude runs on your subscription), a smoke test.

**The primer** (92 pages) changed the plan:
- It's **the syllabus, not a source**: your own synthesis, with almost no citations, and dated. Each fact still needs a trusted receipt, which also checks the primer.
- **"Testable"** now has a meaning: one clear answer, stated by a trusted source, true for about 2+ years.
- **Kinds of card** (fact, term, explain-the-idea, grade-the-evidence, dated fact, read-don't-quiz) are how to learn the whole doc. v1 = mechanisms, science, history.

**Checks:** ruff ✅, format ✅, pytest 24 passed. First commit made by naming each file (not `git add -A`).

## M0 Step 3b: the build map + "name & recall" (2026-11-12)

> **In plain words:** a one-page picture of the project: what exists, what's planned, which checks guard a change. It's updated after every step, and keeps a frozen copy of each version.

- **Same look as the HSK map** (its stylesheet copied), so the two read alike. Sections: the planned pipeline (primer → sources → card_writer → quote check → fact-auditor → cards), kinds of card, the gates, tests, reused vs new, where notes live, "How it grew".
- **Kept in git** (`docs/build-map/index.html` + `snapshots/m0-step3.html`) and **published** as the "Longevity Trainer Build Map" artifact. Playbook lesson: an artifact that lives only in a chat session gets lost. The slug is in `CLAUDE.md`, so every step can republish it.
- **Your steer: naming and recall underpin the work** (the 12 hallmarks, pathways, drugs and what they do). That's now the core v1 kind of card. One thing it needs that quizkit lacks: a **list grader** ("name the 12 hallmarks" = order-free, partial score). Planned for when we build the quiz.

## M0 Step 4: GitHub repo + first CI run (2026-11-12)

> **In plain words:** the project now has a home online. Every upload is re-checked by GitHub on a fresh computer, and it passed first time.

- **You ran it, not me:** Claude Code's safety check blocked me from creating a *public* repo (publishing is outward-facing). So you ran `! gh repo create ... --public --source . --push`. That's the right split: anything that makes things public is your call.
- **Why public:** on GitHub's free plan, branch protection (Step 5) only works on public repos. Nothing private is in it (no `.env`, the primer is ignored).
- **First CI run green, and checked:** green isn't the same as checked (playbook M3 lesson), so I read the log: ruff ✅, format ✅, **24 passed**. The PR-description check was skipped, which is expected: it only runs on PRs.
- **GitHub's own safety nets are on:** secret scanning + push protection (blocks uploads containing known API key formats).
- **A notice to know about:** GitHub says `ubuntu-latest` moves to Ubuntu 26 from 19 Oct 2026. Nothing to do: CI follows it automatically, and `uv sync --locked` keeps our Python tools identical.

## M0 Step 5: protect `main` (2026-11-12)

> **In plain words:** a lock on the main copy. From now on, every change goes on a side branch, opens a PR, passes CI, and is squashed into one tidy commit. Applies to everyone, you included.

- **Copied HSK's exact settings** (read them from its repo, not from memory): PR required, the `check` CI job must pass and the branch must be up to date with `main`, **admins included**, no force-push, no deleting `main`. Merges are squash-only, and branches are deleted after merging.
- **0 approvals needed:** a PR is required, but no human sign-off on it (your "no human approval gates" rule). CI is the gate; you still choose when to merge.
- **Tested, not assumed:** a direct push to `main` was **rejected** by GitHub. The commit with this step's docs then went up on a branch as the **first PR**, which is also the first real run of the "Still the right thing?" check.
- **Hooks are different:** this lock is GitHub's, for everyone. Hooks (M1) are Claude-only scripts on your PC. Layers beat one lock.

## M1 Step 1: one tool per milestone (2026-11-12)

> **In plain words:** each milestone now gives you something useful *and* teaches one new tool: M1 reuse + tests, M2 a fan-out workflow, M3 the Agent SDK + subagents, M4 `claude -p` + evals.

- First change through the full routine: issue #2 → branch → PR → CI → you merge.

## M1 Step 2: copy quizkit (2026-11-12)

> **In plain words:** we moved HSK's generic quiz parts (cards, marking, dealing, the quiz loop, the Claude judge, the Leitner boxes) into this project, with their 513 tests. Now 537 tests pass here.

- **Copied, not installed** (decided in M0): from HSK commit `caa969a`. quizkit is identical at HSK's latest commit, so nothing was missed.
- **Only one code change:** `scaffold.py` (the `/new-block` file maker) now writes to `longevity_trainer` instead of `hsk_trainer`.
- **Tests use HSK words as sample data** (e.g. 爸爸 = dad). That's fine: they test the marking machinery, not Mandarin.
- **Two safety nets came along:** `test_reuse.py` fails if quizkit ever imports our longevity code, and `conftest.py` makes sure no test calls the real Claude.
- **The capitals example** came too, and still plays with our package blocked: proof the parts really are generic.

## M1 Step 3: Claude's safety rails (2026-11-12)

> **In plain words:** two little scripts that run around every action Claude takes in this repo. One **blocks** anything touching `.env` (secrets). One **tidies** Python files after each edit. Plus a list of commands Claude may run without asking.

- **Copied from HSK, unchanged**, with their 19 tests (556 tests now).
- **You ran the copy, not me:** Claude Code stops Claude from changing its own settings (`.claude/`). Same idea as the public-repo block: Claude can't loosen its own limits.
- **Live test still to do:** hooks only load in a session started inside this folder. This chat started in your home folder, so my `.env` read wasn't blocked here. Next session: start `claude` in `code/longevity-trainer` and ask it to read `.env`. It should be blocked.
- These rails stop **Claude only**. GitHub's protected `main` stops everyone. Layers beat one lock.

## M1 Step 4: the first five ADRs (2026-11-12)

> **In plain words:** five short notes saying "we decided X, because Y", in `docs/decisions/`. Code shows *what*; ADRs show *why*.

- **0001 scope:** the primer is the syllabus; v1 = name & recall + science.
- **0002 script vs agent:** code checks what it can; agents only where judgment is needed, always checked by a script. Also: `claude -p` vs the Agent SDK.
- **0003 quizkit copied:** from HSK `caa969a`, and why not installed.
- **0004 receipts:** the six layers of trust, from source list to freshness.
- **0005 testable + kinds of card:** the definition and the seven kinds.
- Accepted ADRs are never rewritten: a change gets a new ADR, so the history stays readable (HSK lesson).

## M1 Step 5: learning goals + the question standard (2026-11-12)

> **In plain words:** before writing any cards, we wrote down what you want to be tested on, and what makes a question good. The card writer agent (M3) must follow this file.

- **Your steer:** "we need to spend more time defining what a good question is". Right call: it needs no extra infrastructure, and it becomes the agent's instructions and the test of its output.
- **Five questions per topic:** what is it · how does it work · how sure are we it helps longevity (grade + why) · what's the catch · is it growing in popularity (dated, re-checked in M5).
- **You labelled 10 examples.** One surprise: I marked the plain name question (#10) bad; you marked it good. So names are welcome as vocabulary, as long as each topic also gets how/why questions. Trivia (#8) and vague overselling (#9): bad.
- **Why this is best practice:** one file is the single source of truth. The card writer's prompt includes it word for word (a test will check), the fact-auditor checks cards against it, and your labelled examples become the eval set.

## M1 Step 6: 15 hallmark cards with receipts (2026-11-12)

> **In plain words:** 15 questions on the hallmarks of ageing, each carrying a word-for-word quote from the 2023 *Cell* review. A script opens the PDF and checks every quote is really there, on the page the card says.

- **The source is pinned, not committed:** `data/sources/hallmarks-of-aging-2023.json` has the URL, size and SHA-256. The PDF downloads to `data/raw/` (gitignored), because its licence is unclear (the repository says CC BY-NC-ND, the PDF says © Elsevier).
- **Quote matching ignores PDF mess** (ligatures, hyphens at line ends, curly quotes, accents) by comparing letters and digits only. Changing one word still fails (a test checks this).
- **Following your standard:** 10 name/fact cards (vocabulary) and 5 how/why/term cards (mechanism).
- **In CI** the real-PDF test skips (no download there); the format tests run. Locally: `uv run longevity check-receipts` → `15/15 quotes found`.

## M1 Step 7: play the cards (2026-11-12)

> **In plain words:** `uv run longevity quiz` asks the 15 questions in a random order. After each answer you see the right answer and its receipt (the quote and page).

- **Marking is free and instant for now:** names and facts are checked by quizkit's grader (small typos forgiven). For "explain" answers, or any answer it calls wrong, you see the model answer and mark yourself (y/n). The Claude judge comes in M4, with an eval set to test its marking.
- **Reuse:** the quiz loop is quizkit's `QuizSession`, including its "own mark" feature from HSK; this step only added the screen code (`cli.py`).
- **Not yet:** progress isn't saved (Leitner boxes come later).

## The build loop, restored and enforced (2026-11-12)

> **In plain words:** in HSK, a separate Claude wrote each block's tests from its job description (SPEC), and another reviewed it, before any PR. I didn't copy that here, so steps 6–7 were built and tested by me alone. You caught it. Now it's back, and CI fails if it's skipped.

- **Your steer:** "don't save in memory, you always forget: work out how we embed this properly". So the guard is a failing check, not a note: `tests/test_process.py` (code must be a block with a SPEC and its own tests) and `check_reviews.py` (the PR must tick the three reviews).
- **Redone through the loop:** the quote checker and the folder loader are now quizkit blocks any quiz can use; the cards are a longevity block.
- **What the independent agents found** (none caught by my own tests): a card kind with spaces was rejected; the quote key treated `IL-1α` = `IL-1β` and `1.5` = `15`; a "quote" of dots could match anything; a line splitter that shifted error line numbers; a path that could land a download outside the project.
- **Still to do:** the Claude GitHub review needs a token from you (`CLAUDE_CODE_OAUTH_TOKEN`).

## M2 Step 1: the topic map (2026-11-12)

> **In plain words:** a list of the 73 things the primer covers, and for each: which kinds of card suit it, and whether we quiz it now, after the M5 freshness checks, or never.

- **59 quiz now:** the science (ageing, hallmarks, the big ideas, reading evidence) and, for each drug, supplement and intervention, what it is, how it works and how strong the evidence is.
- **9 wait for M5:** prices, companies, rules and deals change within months, so they need an "as of" date and a re-check.
- **5 read-don't-quiz:** news sources, people, events.
- **Groups:** the 59 are split into 9 groups; in Step 5 one agent per group looks for trusted sources.
- **Public repo:** only topic names and primer section numbers are committed, never the primer's text.
- **No code in this step**, so the PR's reviews are "n/a" (the CI check accepts n/a with a reason).

## M2 Step 2: trusted sources and licences (2026-11-12)

> **In plain words:** a written rule for which sources a card may quote, so the agents that look for sources (Step 5) and the script that checks them (Step 4) agree.

- **Three tiers:** A official guidelines (NIH, NHS, WHO, Cochrane…), B review articles in major journals (Cell, Lancet…), C a study's own paper, but only for claims about that study.
- **Never:** news, blogs, company or clinic sites, preprints, Wikipedia, AI answers, or the primer.
- **Mice ≠ people:** a mouse study can't back a human claim; when tiers disagree, the higher one wins and the card says so.
- **Licences, one rule:** commit the source's record and short quotes, never the document (it downloads locally, checked by its fingerprint).

## M2 Step 3: three real sources, by hand (2026-11-12)

> **In plain words:** before writing the source checker, I saved one guideline page (WHO), one journal review and one trial paper, to see the real problems. Findings are in `docs/SOURCE_FORMATS.md`.

- **Many official sites block programs** (NIH supplements office, NIA, CDC). Claude Code won't let me disguise the downloader as a browser, which is right, so those sites are skipped unless they offer an official API.
- **Three formats:** PDF, web page (HTML) and journal XML. M1's quote check only read PDFs, so Step 4 now starts with a block that gets plain text from all three.
- **Europe PMC** (a free service for programs) gives open journal articles as clean XML, with the licence stated inside. It becomes the agents' first stop in Step 5.
- **Also:** paywalled reviews are skipped; preprint copies (like PEARL's) are rejected; web pages change, which M5 will handle.
- **Safety fix:** `data/raw/` is now ignored as a whole (before, only PDFs were), so downloaded pages can't be committed by accident.

## M2 Step 4: Claude marks your answers (2026-11-12)

> **In plain words:** like a teacher reading your answer instead of a key that only accepts exact words. If your answer isn't on the list, Claude decides if you meant the same thing.

- **New block `marking`:** names and facts are marked word-level (synonyms, small slips OK); explanations are marked on the main idea, up to 400 characters. Rejects: missing parts, overselling ("reverses ageing"), and moving a mouse result to people.
- **Answers are saved** in `data/judge_cache.jsonl` (gitignored), so the same answer is never asked twice.
- **Offline-safe:** if Claude fails twice in a row, marking switches off for the run and you mark yourself.
- **Changed plan:** the source-checker steps are postponed; the user found them the least useful part.

## M3 Step 1: reading any source (2026-11-12)

> **In plain words:** before an agent can write cards from a source, something has to turn the source into plain text, like photocopying a page before you highlight it. The quote check could only read PDFs; now it reads web pages and journal XML too.

- **New quizkit block `source_text`:** PDF → one text per page; a web page or journal article → one long text. Standard library only, no new dependency, and it never goes online (checked: XML bombs and external entities are refused).
- **What counts as the text:** visible page text only (not scripts, menus hidden by the page, or the tab title); for articles, the title, abstract, body and captions, but **not** the reference list (PEARL hides it inside the body), author/funding notes or formula code. Otherwise a quote could be "found" in someone else's paper title.
- **Receipts:** each source record now says its `format`; the 15 hallmark quotes are still all found.
- **The loop earned its keep:** the test-writer caught that `rapa<italic>my</italic>cin` came out as "rapa my cin", and that PEARL's reference list sat inside the body. The reviewers caught charset, hidden-element and wrapped-article gaps.

## M3 Step 2: the exam before the student (2026-11-12)

> **In plain words:** like writing the answer key before the exam. 29 cards, each already marked good or bad (and which rule it breaks). The card checker in Step 3 has to match these marks: catch every bad card, wrongly flag at most one good one.

- **Where they come from:** your labelled examples from LEARNING_GOALS, reviewed hallmark cards, and bad cards planted on purpose (mice answered as if people, overselling, trivia, quotes that don't back the answer, questions that need the paper to make sense).
- **Every quote is real:** a test checks each one, word for word, in its pinned source.
- **The exam was reviewed too:** an independent agent found 11 unfair labels (good cards saying slightly more than their quotes, bad cards breaking two rules at once). Fixed; a bad card now lists every rule a correct checker could name.
- **Your steer became a rule:** for a trial, know that it exists and what it meant for the field, not its sample size (LEARNING_GOALS rule 4).

## M3 Step 3: the strict teacher (2026-11-12)

> **In plain words:** like airport security for cards. The checker reads each card and its quote and rejects anything that breaks a rule. A strict guard means some extra bag checks (good cards rejected), but nothing dangerous gets through (no bad card accepted).

| Run | Model, prompt | Bad cards caught | Good cards wrongly rejected |
|---|---|---|---|
| 1 | Haiku v1 | 16/16 | 8/13 (prompt too literal; but 4 were real flaws in my exam cards) |
| 2–5 | Haiku / Sonnet v2 | 17/17 every run | Haiku 3/12, Sonnet 4–6/12 |
| 6–9 | Haiku / Sonnet v2, after fair fixes | 17/17 every run | Haiku 3, Sonnet 4–5 |
| 10–13 | Haiku v2: main exam + **held-out** | 17/17 and 6/6 | 3–4/12 and 2/6 |

- **Haiku chosen:** catches everything, rejects fewer good cards than Sonnet, costs about $0.01 per 29 cards.
- **Fairness:** exam changes after seeing results were ruled on by an independent agent (it agreed with the checker on 3 cards, disagreed on 3, which stay as they are). Then an agent that never saw the prompt wrote 12 **held-out** cards; the checker caught all their bad cards too, so it isn't just fitted to our exam.
- **The bar moved twice, by your decision:** "≤1 good card rejected" became "≤ a third", because a rejected card costs a redraft but a bad card teaches a mistake. To revisit when tuning.
- **Safety rails:** `check-cards-exam --dry-run` (no Claude), `--limit N`, `--holdout`; every real run prints its calls, tokens and cost.

## M3 Step 4: the student who writes flashcards (2026-11-12)

> **In plain words:** a student reads a textbook and writes flashcards (Sonnet). Then three checks: is the quote really in the book (code), is it a repeat (code), does it follow the rules (the strict teacher from Step 3). Only cards that pass all three go in the box.

| Run | Prompt | Rapamycin (PEARL) | Epigenetic clocks | Physical activity (WHO) |
|---|---|---|---|---|
| 1 | v1 | kept 1/8 ❌ | 3/8 ❌ | 4/8 ❌ |
| 2 | v2 | 4/8 ❌ (no "how" card) | 6/8 ✅ | 5/8 ✅ |
| 3 | v2 | 4/8 ✅ | 5/8 ❌ (no "how" card) | 5/8 ✅ |

- **The writer never invented a quote:** 0 quote drops in all 9 runs. Almost every drop was the checker's rule 3 (the answer said more than the quote). So v2 told the writer: **the quote alone must back the whole card** (one short claim per answer, no open lists). That more than doubled the kept cards.
- **Tests first this time:** the test-writer wrote 72 tests from the SPEC before any code (red, then green), plus more after the reviews.
- **Your spot-check:** 10 kept cards, all 👍 ("these all look pretty good"). Your steer: Step 5's bank should be science first (drugs and supplements, hallmarks, exercise/sleep/diet), companies later as M5 dated cards.
- **Reviews caught:** a broken card file could make new ids clash with old ones (now it stops and says so); a rejected question blocked a later good draft of the same question; quotes across a PDF page break could never be found (prompt v3 marks pages; the eval sources were all one page, so the v2 numbers stand); no cost line (now: calls, tokens, cost); `--replace` could lose cards if the write failed (now temp file + swap).
- **ADR 0008:** the writer uses `claude -p` (one call, JSON reply, no tools), not the Agent SDK that ADR 0002 planned: no API key, no extra cost.
- **Variance:** the "how" card is the one most often missing; a run that misses the bar writes nothing, so you just run it again.

## M3 Steps 5–6: the first bank, and a bank that grows (2026-11-12)

> **In plain words:** the flashcard box got its first real load, and a way to keep adding to it. `--add` is like topping up a box: new cards go in, and any question the box already holds is skipped.

| Topic | Source | Cards | Runs |
|---|---|---|---|
| Physical activity | WHO fact sheet | 7 | 1 |
| Rapamycin | PEARL trial | 8 (no "how" yet) | 6 (3 saved) |
| Epigenetic clocks | Measuring biological ageing review | 8 | 5 (2 saved) |
| Hallmarks, 4 sections | Hallmarks of aging 2023, `--pages` | 25 | 6 (5 saved) |
| Hallmarks (hand-made, M1) | same | 15 | |

- **Your steer, "a bank we update as we go":** `write-cards --add` tops up a topic. The writer is shown the questions already in the bank so it asks about new facts (prompt v4: 0 repeats in its first run, against 3 in the run before).
- **The bar changed:** runs kept 3–4 cards that passed every check and then threw them away for missing one kind of question. Now every card that passes is saved; "covers what / how / how sure" is a goal for the topic, shown after each run ("missing: how, run again with --add"). The writer eval keeps the stricter bar, because it measures the prompt, not whether cards may be saved.
- **`--pages`:** the hallmarks review (215,000 characters) is too long for one call, and one run would only skim it. Four runs of 3–9 pages each cover all 12 hallmarks. Receipt pages still match `check-receipts`.
- **The strict checker costs runs:** it rejects about half the drafts, mostly for small wording slips (dropping "fully" or "probably" from the source). Nothing bad gets in, but topics need 2–3 runs. Cost: about $0.03–0.12 a run.
- **Reviews caught:** a receipt page could disagree with `check-receipts` when a sentence appears twice; the coverage line ignored cards already in the file; the topic file was read twice (two runs could hand out the same id; now it stops if the file changed during the run).

## M4 Step 1: the quiz remembers (2026-11-12)

> **In plain words:** flashcards in boxes. Get a card right and it moves to a box you check less often (1 day, 3, 7, 21); miss it and it goes back to box 1 and comes back first. The quiz now deals what's due, then new cards, and saves where every card is.

- **Reused, not rebuilt:** quizkit (copied from HSK) already had the parts: `deck_builder` (due first), `leitner` (boxes), `progress_store` (SQLite), `quizkit.progress` (save + stats). A new longevity block, `study`, wraps them; `cli.py` only reads the keyboard and prints.
- **Structure kept:** my first version put the logic straight into `cli.py`; `/code-review` caught that it skipped the build loop, so it became a block with a SPEC and 44 tests by the test-writer (written before the code).
- **The bug the reviewer caught:** dealing filled a 10-card quiz with cards not due yet, and a right answer moves a card up a box whether it was due or not, so a small topic would race to the top box in a week. Now only due and new cards are dealt; `--practise` reviews anything without saving.
- **Your data is safe from tests:** a test had written an (empty) `data/progress.db`; now a guard in `tests/conftest.py` points every test at a temp file.
- **Commands:** `uv run longevity quiz` (10 cards; `-n`, `--topic hallmarks`, `--practise`, `--no-save`), `uv run longevity stats`.

## M4 Step 2: an exam for the marker (2026-11-12)

> **In plain words:** before trusting a new teacher to mark your homework, you mark 23 answers yourself and see if they agree with you. They agreed on 21, and never passed an answer you'd fail.

- **Your labels:** 23 borderline answers across names, facts, terms and explanations (synonyms, half answers, mice→people, wrong order). You checked them ("answers I think okay").
- **Marked like the real quiz:** the answer list first (typos forgiven), Claude only when it says no. `/code-review` spotted that my first version skipped the answer list, so a near-typo of a right answer could have been passed in the quiz but never tested.
- **Result, two runs with real Claude (Haiku):** 21/23 both times, no wrong "yes", PASSED. Both misses were answers you'd accept that Claude found too short: "inflammation that gets worse with age" (no "chronic, body-wide") and just "inflammation" (no fibrosis). Strict on the safe side, so no rule change yet. Under 1 cent a run.
- **Reuse, not copies (block-reviewer):** the counting of right / wrong yes / wrong no was copied from quizkit's HSK eval; it's now one shared `score` in quizkit that both use. Reading one JSONL file moved into quizkit's loader (so a Windows BOM is fine). A card turns into a question in one place, `card.to_question()`, for the quiz, the eval and the coming web page. **To port back to HSK:** `score`, `ScoreItem`, `verdict_mark` and `load_jsonl_file`.
- **Your 👎:** the sedentary-behaviour card ("a shit Q") is gone (62 cards) and is now example 12 in LEARNING_GOALS, so the writer learns from it.
- **Command:** `uv run longevity check-marking-eval` (`--dry-run`, `--limit N`). Re-run when the marking rules or model change.

## M4 Step 3a: one brain, two screens (2026-11-13)

> **In plain words:** the TV and the phone show the same programme. The quiz's rules (which cards, how answers are marked, what's said after each one, what's saved) now live in one block, and both the terminal and the coming web page are screens on it.

- **Why first:** what to say after an answer, the "count it as right?" rule and setting up a round all lived inside the terminal program. A web page would have had to copy them, and copies drift.
- **New block `quiz_round`:**
  - `setup` builds a round: it deals the cards, opens your progress file and builds Claude's marker.
  - The wording functions are `feedback`, `own_mark_line`, `receipt_line` and `score_line`.
  - `QuizScreen` is the click-by-click quiz for a web page. It ignores double or late clicks, and it saves each answer once, when it's final. Copied from HSK's `WebQuiz`.
- **Terminal unchanged:** every CLI test passes. One test now points at the block, because the setup moved there.
- **Safety net grown:** tests also can't touch the block's default progress and Claude-cache files.
- **ADR 0009:** a local Streamlit page on one shared brain. Next (3b): the page itself.

