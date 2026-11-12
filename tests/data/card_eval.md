# Card eval set (M3 Step 2)

> **In plain words:** an exam for the card checker, written before the checker exists. Each line in `card_eval.jsonl` is a card with the right verdict already filled in: **pass** (a good card) or **fail** (it breaks a rule in `docs/LEARNING_GOALS.md` §2). The checker passes the exam only if it catches every bad card and wrongly flags no more than one good one.

## What's in it (29 cards)
| | Count | Where they come from |
|---|---|---|
| **Good** (`pass`) | 13 | 6 of your 👍 examples from LEARNING_GOALS §3, now with real receipts (#1, #2, #4, #5, #6, #7); 3 planted good ones (incl. what PEARL meant for the field); 4 reviewed hallmark cards from M1 (a name card stands in for #10) |
| **Bad** (`fail`) | 16 | your 2 👎 examples (#8 trivia, #9 oversells), your label on PEARL's sample size (too much detail), plus 13 planted bad ones: at least two per rule |

A bad card may break more than one rule; `rules` lists every rule a correct checker could name (e.g. "proven in humans" from a mouse quote is both overselling, rule 5, and an answer the quote doesn't back, rule 3). Cards that can be caught under each rule:
- **Rule 2** (population hidden: mice answered as if people): 3
- **Rule 3** (the quote doesn't back the answer, or it won't stay true for 2 years): 9
- **Rule 4** (trivia: a month, a registry number, a p-value, a trial's sample size): 4
- **Rule 5** (oversells: "reverses ageing", "proven in humans", a hypothesis stated as the cause): 3
- **Rule 6** (doesn't stand alone: "the trial", "this group", "the authors"): 2

**Every good card is backed word for word.** An independent review (2026-11-12) found 5 good cards whose answers said a little more than their quotes ("missed its main goal", "a week", "chronic"); they were reworded, because a strict checker would rightly fail them and the exam would be unfair.

**Left out on purpose:** rule 1 (names never alone) is about a whole topic, not one card, so the card writer's coverage check tests it (Step 4). Rule 7 (trend cards) and your #11 wait for M5. Your #3 (autophagy) is covered by the M1 autophagy cards. **Not covered by any rule yet:** a question that gives away its answer, two questions in one, and jargon copied from the source without explaining it. If the card writer makes these, they become a new rule in LEARNING_GOALS and new lines here.

Every quote is real: `tests/test_card_eval_data.py` checks each one is found, word for word, on its page of the pinned source.

## The bar (fixed now, before the checker is built)
- **Every bad card caught** (16/16), naming one of its listed `rules` for at least 14 of them.
- **At most 1 good card wrongly flagged** (12/13 or better).
- Run twice; both runs must meet the bar. Haiku and Sonnet are compared; the cheaper one wins if both meet it.

## Line format
```json
{"id": "...", "expected": "pass" | "fail", "rules": [] | [2-6, ...], "why": "...", "origin": "user #N" | "planted" | "planted good" | "M1 card", "card": { a LongevityCard }}
```

## Changing it
Add cases in a PR. A card the checker gets wrong in real use becomes a new line here (with the right verdict), so the exam grows from real mistakes.
