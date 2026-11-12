# 0004: Every card carries a receipt

- **Status:** Accepted (2026-11-12)
- **In plain words:** a question can only exist if a trusted source states its answer, and a script has found the supporting quote, word for word, in a saved copy of that source. After each answer, the quiz shows the receipt.

## Context
Longevity facts can be wrong, contested or out of date, and the primer has almost no citations. HSK had a clean word list to trust; here, trust has to be built card by card.

## Decision
Each card stores a **receipt**: source id, quote, and where in the source it is. Each source is **pinned**: URL, date fetched, SHA-256 fingerprint, licence.

| Layer | Who | What it checks |
|---|---|---|
| 1. Trusted source list | User + Claude (M2) | Only guidelines, consensus statements, major reviews from named bodies |
| 2. Pinned copy | Script | URL, date, fingerprint |
| 3. Card written | By hand (M1), then the card writer agent (M3) | Question + answer + quote |
| 4. Quote check | **Script** | The quote is in the saved source, word for word |
| 5. Meaning check | Read-only fact-auditor (M3) | Does the answer follow from the quote? Too strong? Missing caveat? Flagged = removed |
| 6. Freshness | Script, on a schedule (M5) | Source changed or past its review date → card pulled |

## Why / alternatives considered
- **Trust Claude's knowledge:** no way to check it, and it can be confidently wrong.
- **Cite the primer:** it's a synthesis, not evidence.
- **A person approves each card:** doesn't scale, and a learner can't judge it anyway (same lesson as HSK ADR 0015).

## Consequences
- ✅ Every answer can be traced to its source; finding receipts also checks the primer.
- ⚠️ A public repo re-publishes saved sources: each source's licence decides whether we commit its text or only fingerprints and short quotes (decided per source, from M1 Step 5).
- ⚠️ PDF text can break word-for-word matching (hyphens, line breaks): the quote check normalises spaces and hyphenation, and its tests prove a changed word still fails.
