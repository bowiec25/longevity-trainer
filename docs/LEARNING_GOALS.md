# Learning goals and the question standard

> **In plain words:** what I want to be able to do after studying each topic, and what makes a question good. This file is the **single source of truth**: the card writer (M3) must follow it, the fact-auditor checks cards against it, and the eval set is built from the labelled examples below.

**Status:** Agreed (2026-11-12). Section 3 labelled by the user.

---

## 1. What I want to learn: five questions per topic

For every drug, supplement, intervention or mechanism, I should be able to answer:

| # | Question | What a good answer shows |
|---|---|---|
| 1 | **What is it?** | What kind of thing it is, and what it's normally used for |
| 2 | **How does it work?** | The mechanism in plain words: what it acts on, and what changes in the body |
| 3 | **How sure are we it helps longevity?** | The evidence grade (A–E) **and why**: in which species or people, which trials, which outcome |
| 4 | **What's the catch?** | Side effects, failed trials, open questions, why the evidence is weaker than it sounds |
| 5 | **Is it growing in popularity?** | The trend (rising, flat, falling) and what's driving it. A **dated** fact: the card carries an "as of" date and is re-checked by the M5 freshness job |

Not every topic needs all five (a hallmark has no "side effects" or trend), but questions 2 and 3 matter most: **mechanism and conviction**. Names come first, as vocabulary.

### Worked example: rapamycin
| # | What I should know |
|---|---|
| 1 | A transplant anti-rejection drug |
| 2 | Turns down mTOR, the cell's master "grow" switch; with mTOR down, the cell shifts from building to cleaning and repair |
| 3 | Grade D for lifespan: the only compound that reliably extends life in both sexes in the most rigorous mouse-testing programme, even started in old age; unproven in people |
| 4 | PEARL (114 healthy people, 48 weeks) missed its main goal; the compounded form may have been poorly absorbed; side effects reported by users (infections, cholesterol, blood sugar) |
| 5 | Flat: it plateaued after the 2022–24 hype (as of Oct 2026) |

(From the primer, section 6.5. Each fact still needs a receipt from a trusted source before it becomes a card.)

---

## 2. What makes a question good (draft rules)

A good question:
1. **Names are welcome, but never alone.** "Which hallmark is the shortening of chromosome ends?" is good vocabulary (user, 2026-11-12). Each topic must *also* have how/why questions; a topic tested only by names is incomplete.
2. **Always covers conviction for interventions.** Every drug or supplement gets at least one "how sure are we?" question, and the answer names the species or population (mice ≠ healthy people ≠ high-risk patients).
3. **Has one clear right answer that a trusted source states**, and is still true in about 2 years (ADR 0005).
4. **Is worth knowing in a conversation about the field.** No trivia: no dates of celebrity decisions, no "which month", no exact figures nobody would quote.
5. **Doesn't oversell.** It never uses grade-A language for grade-C/D evidence ("reverses ageing").
6. **Stands alone.** It makes sense without having read the source.

7. **Trend questions carry a date.** "Is it growing in popularity?" is welcome (user, 2026-11-12), with an "as of" date and a source for the trend.

A bad question: is trivia (user: 👎 #8), is vague or oversells (user: 👎 #9), or hides the population behind the claim.

---

## 3. Examples to label (user: 👍 or 👎, and why)

| # | Question | Answer | Topic Q | My guess | User's label |
|---|---|---|---|---|---|
| 1 | What was rapamycin originally used for? | Preventing transplant rejection | What is it? | 👍 | 👍 |
| 2 | Rapamycin turns down which "master grow switch" inside cells? | mTOR | How? | 👍 | 👍 |
| 3 | When mTOR is turned down, what does the cell switch to doing? | Cleaning and repair (autophagy) | How? | 👍 | 👍 |
| 4 | Explain in your own words why turning down mTOR might slow ageing. | Less "build", more cleaning and repair of damage | How? (explain) | 👍 | 👍 |
| 5 | What grade of evidence is there that rapamycin extends **human** lifespan, and why? | D: reliably extends life in mice (both sexes, even started late), unproven in people | How sure? | 👍 | 👍 |
| 6 | What did PEARL, the main human rapamycin trial, find? | Missed its main goal; safe at low weekly doses; some muscle gain in women on the higher dose | How sure? | 👍 | 👍 |
| 7 | Why might PEARL have under-tested rapamycin? | The compounded form may have been poorly absorbed | Catch | 👍 | 👍 |
| 8 | In which month did Bryan Johnson stop taking rapamycin? | September 2024 | none | 👎 trivia, dated | 👎 |
| 9 | True or false: rapamycin reverses ageing. | ? | none | 👎 vague, oversells | 👎 |
| 10 | Which hallmark is the shortening of chromosome ends with each division? | Telomere attrition | name | 👎 tests a name, not how | 👍 names are good vocabulary |

| 11 | Is rapamycin use growing, flat or falling, and why? (as of Oct 2026) | Flat: plateaued after the 2022–24 hype | Popularity | added by the user's steer | 👍 (kind requested) |

The user's labels became rules 1 and 7 in section 2, and the labelled questions become the card writer's eval set (M3).

---

## 4. How this file is used
- **Card writer (M3):** its prompt includes this file word for word; a test fails if they drift apart.
- **Fact-auditor (M3):** checks each card against section 2 and flags bad ones (flagged = removed).
- **Eval set (M3):** the labelled examples in section 3, plus more as we go.
- **Changing the standard:** edit this file in a PR; the card writer and auditor pick it up automatically.
