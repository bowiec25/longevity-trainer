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
