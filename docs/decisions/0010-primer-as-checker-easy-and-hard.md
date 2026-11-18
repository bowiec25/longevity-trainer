# 0010: The primer as a checker: easy and hard cards

- **Status:** Accepted (2026-11-18)
- **In plain words:** each card is tagged **easy** (your primer states its fact) or **hard** (it goes beyond the primer, from the trusted sources). Easy mode is the exam on the textbook you were given; hard mode adds the extra reading. The primer is used to **check** cards, never as a card's receipt, and its text still never enters the repo.

## Context
- The primer is the syllabus, not a source (CLAUDE.md, ADR 0001); ADR 0004 says every card's receipt comes from a trusted source and rejects citing the primer.
- The card writer reads whole sources, though, and nothing kept questions inside the primer. The user (2026-11-18): "even if I fully memorised the source document I'm not sure I'd get 100%". They like the extra material, but want it separate from what was agreed.

## Decision
1. **A card has a difficulty:** `easy`, `hard`, or `None` (not checked yet).
2. **A new agent block, `primer_check`, sets it.**
   - Claude decides whether the primer states the card's fact and quotes the primer word for word.
   - **Code** finds that quote in the primer (`receipts.find_quote`), or the card is hard. A tag needs proof, as a card needs a receipt.
   - When unsure, the card is hard.
3. **The primer stays a checker, not a source.** Every card still carries its trusted-source receipt. Only the tag (a word) is committed, never the primer's text, and the primer PDF stays on the Desktop, outside the repo.
4. **Easy / hard in the quiz** comes in the next step: easy deals only easy cards, hard deals all. Untagged cards count as hard.

5. **Guardrails (ADR 0002):** the checker script is the primer-quote check in point 2. `tag-levels` prints the model, prompt version and cost. It has no `--limit`: a run is at most one call per topic group (8 today), already-tagged cards are skipped, and `--dry-run` shows the result first (the same waiver as ADR 0008's for `write-cards`).

## Why / alternatives considered
- **Only write cards from the primer's facts:** this loses the extra material the user likes. It also needs a receipt for each primer fact anyway, so it is the same work plus a new writer.
- **A human tags every card:** too slow, and the user wants no approval gates (CLAUDE.md). The spot-check of 10 tags is the eval instead.
- **Trust Claude's yes/no without a quote:** this can't be checked. The quote makes the yes provable by code, the project's pattern (ADR 0002).

## Consequences
- ✅ Easy mode is a fair test of the primer. Hard mode keeps the extra reading.
- ✅ Retagging is one command (`tag-levels --retag`) when the primer or the prompt changes.
- ⚠️ A run sends the whole primer (about 55k tokens) per topic group. That's fine at 8 groups, and could be split per section later.
- ⚠️ The check depends on the primer's PDF text. A primer sentence broken badly by the PDF can't be quoted, so the card falls to hard (the safe side).
