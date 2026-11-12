# Card eval set (M3 Step 2)

> **In plain words:** an exam for the card checker, written before the checker exists. Each line in `card_eval.jsonl` is a card with the right verdict already filled in: **pass** (a good card) or **fail** (it breaks a rule in `docs/LEARNING_GOALS.md` §2). The checker passes the exam only if it catches every bad card and wrongly flags no more than a third of the good ones.

## What's in it (29 cards)
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

## The bar (set before the checker was built; the false-flag limit raised after, see below)
- **Every bad card caught** (17/17), naming one of its listed `rules` for at least 15 of them.
- **At most a third of the good cards wrongly flagged** (4 of 12 here; 2 of 6 on the held-out cards). Was 1, then 3; changed by the user on 2026-11-12 after Haiku caught every bad card in all 14 runs, including the never-tuned-on held-out cards, while rejecting about 30% of good ones. A wrongly rejected card only costs the writer a redraft. To be revisited when tuning.
- **The held-out cards** (`card_eval_holdout.jsonl`, 12 cards written by an agent that never saw the checker's prompt or this exam) must meet the same bar. This exam was used to tune prompt v2, so only the held-out score says how the checker does on new cards.
- Run twice; both runs must meet the bar. Haiku and Sonnet are compared; the cheaper one wins if both meet it.

## Line format
```json
{"id": "...", "expected": "pass" | "fail", "rules": [] | [2-6, ...], "why": "...", "origin": "user #N" | "planted" | "planted good" | "M1 card", "card": { a LongevityCard }}
```

## Changing it
**First change (2026-11-12):** the checker's first run (Haiku, prompt v1) rightly failed 4 "good" cards: an answer adding "including placebo", one adding "weak" and "works", a question claiming the SASP that its quote doesn't mention, and the M1 IL-6 card, which has other right answers. Three were reworded and IL-6 became a bad card. Its 4 other false flags were the prompt being too literal, fixed in prompt v2, not here.

**Second change (2026-11-12):** with prompt v2, both models still failed some good cards. An independent adjudicator (who didn't see my view) ruled the checker right on 3 (PEARL's result named no population; the senescence description fit several hallmarks; the clock quote says 5hC, not methylation), reworded here, and wrong on 3 (`ev-rapa-why`, `ev-pearl-women`, `ev-pearl-catch`), which stay exactly as they are: they test that the checker isn't too strict.

Add cases in a PR. A card the checker gets wrong in real use becomes a new line here (with the right verdict), so the exam grows from real mistakes.
