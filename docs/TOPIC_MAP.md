# Topic map

> **In plain words:** the list of everything the quiz could cover, taken from the primer's sections, and for each one: what kinds of card suit it, and whether we quiz it now, later, or never. The data lives in `data/topics.jsonl` (one topic per line); this page explains it.

**Status:** M2 Step 1 (2026-11-12). 73 topics: **59 quiz now (v1)**, 9 wait for M5 freshness checks, 5 are read-don't-quiz.

## The three statuses
| Status | Meaning | Examples |
|---|---|---|
| `v1` | Stable science with a clear answer: quiz now, once a trusted source backs it | the hallmarks, how rapamycin works, what PEARL found, what VO2 max is |
| `after-m5` | A dated fact (price, company, rule, deal): changes within months, so it needs the M5 freshness re-check and an "as of" date | GLP-1 prices, which peptides are legal, blood-test companies |
| `read` | Worth reading, not worth memorising | news sources, people, events, the consumer "eras" |

## Card kinds per topic
From ADR 0005: `name` (name & recall), `fact`, `term`, `explain`, `grade` (grade the evidence). Every drug, supplement or intervention gets `grade`, following `docs/LEARNING_GOALS.md` ("how sure are we it helps longevity?" is always asked). `grade` cards need their own marking rule; until then, M3 writes them as `explain` cards whose answer states the grade and why.

## Groups (one fan-out agent each in M2 Step 5)
| Group | v1 topics | What its sources look like |
|---|---|---|
| ageing-basics + evidence | 7 | demography and evidence-methods reviews; NIA, Cochrane handbook |
| hallmarks | 5 | the 2023 hallmarks review (pinned), nutrient-sensing reviews |
| big-ideas | 6 | reviews in Cell, Nature Aging; the ITP papers |
| drugs | 6 | outcome trials (SELECT, PEARL), guidelines (NICE, ACC/AHA), ITP |
| peptides + hormones | 5 | menopause and endocrine society statements, FDA/MHRA pages, reviews |
| supplements | 7 | NIH Office of Dietary Supplements fact sheets, VITAL, Cochrane |
| procedures + lifestyle | 7 | WHO / CDC activity and sleep guidance, AASM, UHMS (hyperbaric) |
| measurement | 11 | reviews of clocks and biomarkers, USPSTF on screening |
| pipeline | 5 | the trial registrations and papers (TAME, PEARL, TRIAD) |

## Rules
- **Topic names and primer section numbers only.** The primer's own text never goes in this public repo.
- **The primer is the syllabus, not a source.** A topic becomes cards only when a trusted source backs it (ADR 0004, and ADR 0007 in Step 2).
- **Changing the map:** edit `data/topics.jsonl` in a PR. A topic with no trusted source after Step 5 is marked, not dropped silently.
