# Card eval set (M3 Step 2)

> **In plain words:** an exam for the card checker, written before the checker exists. Each line in `card_eval.jsonl` is a card with the right verdict already filled in: **pass** (a good card) or **fail** (it breaks a rule in `docs/LEARNING_GOALS.md` §2). The checker passes the exam if it misses at most a sixth of the bad cards and wrongly flags no more than a third of the good ones.

## What's in it (64 cards; 29 until 2026-11-20, see the third change)
| | Count | Where they come from |
|---|---|---|
| **Good** (`pass`) | 12 | 6 of your 👍 examples from LEARNING_GOALS §3, now with real receipts (#1, #2, #4, #5, #6, #7); 3 planted good ones (incl. what PEARL meant for the field); 3 reviewed hallmark cards from M1 (a name card stands in for #10) |
| **Bad** (`fail`) | 17 | your 2 👎 examples (#8 trivia, #9 oversells), your label on PEARL's sample size (too much detail), the M1 IL-6 card (caught by the checker: other markers are right too), plus 13 planted bad ones: at least two per rule |

A bad card may break more than one rule; `rules` lists every rule a correct checker could name (e.g. "proven in humans" from a mouse quote is both overselling, rule 5, and an answer the quote doesn't back, rule 3). Cards that can be caught under each rule:
- **Rule 2** (population hidden: mice answered as if people): 3
- **Rule 3** (the quote doesn't back the answer, or it won't stay true for 2 years): 10
- **Rule 4** (trivia: a month, a registry number, a p-value, a trial's sample size): 4
- **Rule 5** (oversells: "reverses ageing", "proven in humans", a hypothesis stated as the cause): 3
- **Rule 6** (doesn't stand alone: "the trial", "this group", "the authors"): 2

**Every good card is backed word for word.** An independent review (2026-11-12) found 5 good cards whose answers said a little more than their quotes ("missed its main goal", "a week", "chronic"); they were reworded, because a strict checker would rightly fail them and the exam would be unfair.

**Left out on purpose:** rule 1 (names never alone) is about a whole topic, not one card, so the card writer's coverage check tests it (Step 4). Rule 7 (trend cards) and your #11 wait for M5. Your #3 (autophagy) is covered by the M1 autophagy cards. **Not covered by any rule yet:** a question that gives away its answer, two questions in one, and jargon copied from the source without explaining it. If the card writer makes these, they become a new rule in LEARNING_GOALS and new lines here.

Every quote is real: `tests/test_card_eval_data.py` checks each one is found, word for word, on its page of the pinned source.

## The bar (set before the checker was built; changed since, see below and the SPEC history)
- **At most a sixth of the bad cards missed** (5 of 35 here, 2 of 13 held out; was every bad card until 2026-11-20, user: "im fine with a few fringe cases"), and every caught card but 2 names one of its listed `rules`. A caught card with the wrong rule is still rejected, so that slack only affects the diagnosis, not what gets through.
- **At most a third of the good cards wrongly flagged** (6 of 18 here; 2 of 8 on the held-out cards). Was 1, then 3; changed by the user on 2026-11-12 after Haiku caught every bad card in all 14 runs, including the never-tuned-on held-out cards, while rejecting about 30% of good ones. A wrongly rejected card only costs the writer a redraft. To be revisited when tuning.
- **The held-out cards** (`card_eval_holdout.jsonl`, 21 cards: 12 written by an agent that never saw the checker's prompt or this exam, plus 9 user cuts from 2026-11-20 never used to tune; they come from the same wide review that shaped prompt v4's niche wording, so the held-out score may flatter the checker a little) must meet the same bar. This exam was used to tune prompt v2, so only the held-out score says how the checker does on new cards.
- Run twice; both runs must meet the bar. Haiku and Sonnet are compared; the cheaper one wins if both meet it.

## Line format
```json
{"id": "...", "expected": "pass" | "fail", "rules": [] | [2-6, ...], "why": "...", "origin": "user #N" | "planted" | "planted good" | "M1 card", "card": { a LongevityCard }}
```

## Changing it
**First change (2026-11-12):** the checker's first run (Haiku, prompt v1) rightly failed 4 "good" cards: an answer adding "including placebo", one adding "weak" and "works", a question claiming the SASP that its quote doesn't mention, and the M1 IL-6 card, which has other right answers. Three were reworded and IL-6 became a bad card. Its 4 other false flags were the prompt being too literal, fixed in prompt v2, not here.

**Second change (2026-11-12):** with prompt v2, both models still failed some good cards. An independent adjudicator (who didn't see my view) ruled the checker right on 3 (PEARL's result named no population; the senescence description fit several hallmarks; the clock quote says 5hC, not methylation), reworded here, and wrong on 3 (`ev-rapa-why`, `ev-pearl-women`, `ev-pearl-catch`), which stay exactly as they are: they test that the checker isn't too strict.

**Third change (2026-11-20): the user's niche cuts.** A wide review of the bank cut 70 cards the checker had let through, most of them niche (spelled-out acronyms, molecular steps, one-off lab experiments, definitions). 18 of them join this exam as `fail` (17 rule 4, one rule 6) and 6 cards the user kept join as `pass`; 7 more cut cards and 2 kept ones join the held-out set (they were never used to tune a prompt). Origins say `user cut 2026-11-20 (wide review)` or `user kept 2026-11-20`. The bar changed: a sixth of the bad cards may be missed (see The bar). After the first v4 run, 3 held-out cards moved here because v4's wording was written after seeing them (a BCL2-family card, a mouse bone experiment) or a main card shared their quote (apoB); 3 cut cards nobody had run took their place in the held-out set. Two cut cards were dropped from the exam after the first run: "about 25% of lifespan is genetic" and "low IGF-1 correlates with less cognitive decline" match their quotes and are wrong only against other sources, which the checker never sees (it judges the card and its quote alone).

**Fourth change (2026-11-20): 7 more niche cuts.** The first core refill with writer v10 produced 7 hallmark and Gompertz cards that the checker passed and the user cut as niche (history trivia, jargon, molecular detail, a technical term). They join the main exam as `fail` (rule 4), per ADR 0011, for the next time the checker is tuned. Not re-run yet: the checker's score on them is unknown until then. Two more cuts from the next refill joined the same way (62 cases). Then one more cut, and one card the user kept that the checker failed as too basic: a hallmark's basics (what it is, how it works) should pass (64 cases).

Add cases in a PR. A card the checker gets wrong in real use becomes a new line here (with the right verdict), so the exam grows from real mistakes.
