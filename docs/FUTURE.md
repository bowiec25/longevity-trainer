# Future extensions

Ideas for later milestones, so they don't get lost. Each line says **what**, **why**, and **what already makes it easier**. When one gets planned into a milestone, move it to `docs/PLAN.md` and mark it here.

| Idea | Why | Already makes it easier | Where it would go |
|---|---|---|---|
| **quizkit as its own repo** (added 2026-11-12) | Today quizkit is copied from `mandarin-hsk-trainer` (commit `caa969a`), so the two copies can drift. When a fix needs to flow between the projects, one shared package is better | quizkit already has no Mandarin code (a scan test guards it), only needs `pydantic` + `rapidfuzz`, and the copy records its source commit | A small `quizkit` repo; both projects `uv add git+https://...@<sha>` |
| **Dated-fact cards from primer Parts 3–5** (added 2026-11-12) | Prices, companies, trials, regulators and deals are a big part of the primer, but they go stale within months | The card kinds (PLAN.md) already include "dated fact" with an "as of" date; M5 builds the freshness re-check | After M5: dated cards that expire and get re-checked |
| **"Check the primer" report** (added 2026-11-12) | Finding receipts for primer facts also shows where the primer is wrong, out of date, or unsupported | Every card's receipt check (M3) runs anyway | A list of primer claims that found no trusted source, or a different number, to fix in the primer's next version |
