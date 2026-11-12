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
