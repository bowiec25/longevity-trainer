# 0005: What counts as testable, and the kinds of card

- **Status:** Accepted (2026-11-12)
- **In plain words:** a card needs one clear right answer, stated by a trusted source, that stays true for about 2+ years. Different content gets a different kind of card, so the whole primer can be learned, not just the easy facts.

## Context
The primer mixes stable science, contested debates, dated prices and lists of podcasts. Not all of it can be fairly quizzed.

## Decision
**Testable** = one clear right answer · stated by a trusted source · true for about 2+ years. Anything else: "read, don't quiz".

| Kind | Example | Marked by | When |
|---|---|---|---|
| **Name & recall** ⭐ core | "Name the 12 hallmarks" · "Rapamycin blocks which pathway?" → mTOR | grader per item; lists order-free with a partial score (a new list grader) | v1 |
| Fact recall | "Death risk doubles about every __ years" → 8 | grader (exact / typo) | v1 |
| Term | "What is a senolytic?" | Claude judge, gist rubric | v1 |
| Explain the idea | "Why would slowing ageing delay many diseases at once?" | Claude judge vs the source | v1 |
| Grade the evidence | "Best evidence for NMN in healthy people?" → C (the primer's A–E grades) | exact | v1 |
| Dated fact | "UK monthly cost of GLP-1s?" | exact + "as of" date, expires | after M5 |
| Read, don't quiz | podcasts, events | not a card | never |

## Why / alternatives considered
- **Only fact recall:** easy to build, but misses understanding and judging evidence, the primer's most useful habit.
- **Quiz everything:** dated facts go stale; lists of people and events aren't worth memorising.

## Consequences
- ✅ Each kind has a clear marking rule, so marking can be tested and given an eval set (M4).
- ⚠️ quizkit needs a **list grader** for "name all 12". It's generic, so it goes in quizkit (its own step).
