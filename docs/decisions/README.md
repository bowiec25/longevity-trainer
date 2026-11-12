# Decision records (ADRs)

> **In plain words:** short notes that say *"we decided X, because Y"*. Code shows **what** was built. These notes show **why**, so nobody "fixes" something that was done on purpose.

One file per big decision, numbered in order. Never deleted or rewritten: if a decision changes, write a new ADR and mark the old one **Superseded by 00XX**.

## All decisions
| # | Decision | Status |
|---|---|---|
| [0001](0001-scope.md) | A quiz for longevity knowledge; the primer is the syllabus; v1 = name & recall + science | Accepted |
| [0002](0002-script-vs-agent.md) | Script if code can check it; agent if it needs judgment, always checked by a script | Accepted |
| [0003](0003-quizkit-copied.md) | quizkit is copied from mandarin-hsk-trainer (`caa969a`), not installed | Accepted |
| [0004](0004-every-card-carries-a-receipt.md) | Every card carries a receipt: a pinned trusted source + a quote a script finds in it | Accepted |
| [0005](0005-testable-and-kinds-of-card.md) | What counts as testable, and the kinds of card | Accepted |
| [0006](0006-the-build-loop-enforced.md) | The build loop (SPEC → test-writer → build → reviewers → PR), enforced by CI | Accepted |
| [0007](0007-trusted-sources-and-licences.md) | Trusted sources: guidelines (A), major-journal reviews (B), a study only for itself (C); commit records + short quotes, never documents | Accepted |
| [0008](0008-card-writer-uses-claude-p.md) | The card writer uses `claude -p` (one call, JSON reply, no tools), not the Agent SDK; replaces 0002 guardrail 5 | Accepted |

## Template
```markdown
# 00XX: <decision title>

- **Status:** Proposed | Accepted (YYYY-MM-DD) | Superseded by 00YY
- **In plain words:** one or two sentences.

## Context
## Decision
## Why / alternatives considered
## Consequences
```
