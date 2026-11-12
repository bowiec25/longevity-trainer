# 0001: Scope: a longevity knowledge quiz, with the primer as syllabus

- **Status:** Accepted (2026-11-12)
- **In plain words:** a quiz that tests what you know about ageing science, sleep, exercise, nutrition and the evidence behind them. Your primer decides **what** to learn. v1 trains the building blocks first: naming and recalling hallmarks, pathways and drugs.

## Context
The user wrote a 92-page primer (`longevity_trends_primer.pdf`, 2 Oct 2026, kept outside this public repo). It covers five parts: the science of ageing, what people take and do, tests and wearables, companies and regulators, and where news lives. The user's goals: learn the topic, and learn the tools while building something that scales.

## Decision
- **The primer is the syllabus, not a source.** It has almost no citations and says "the field moves weekly", so facts still need a trusted source (ADR 0004).
- **v1 scope:** name & recall (the 12 hallmarks, nutrient-sensing pathways, drugs and what they do) as the core, then mechanisms, science and history, plus some of the testing sections.
- **Later:** dated facts from Parts 3–5 (prices, companies, rules), after the M5 freshness checks exist.
- **Each milestone teaches one tool:** M1 reuse + tests, M2 a fan-out workflow, M3 the Agent SDK, M4 `claude -p` + evals.

## Why / alternatives considered
- **All five parts at once:** most of Parts 3–5 goes stale within months; quizzing it needs freshness checks first.
- **Science only, no recall:** the user's steer: naming and recall underpin everything else.

## Consequences
- ✅ v1 content is stable and well-sourced.
- ✅ Finding receipts for primer facts also checks the primer.
- ⚠️ The primer lives locally (`Desktop\Longevity_Platform_Blueprint\1_DOCS\`) and is never committed.
