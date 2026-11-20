# 0011: Every agent has an exam, and changes to an agent go through it

- **Status:** Accepted (2026-11-20)
- **In plain words:** each Claude agent in the app gets an exam: cards or jobs whose right answer we already know. When we change an agent's instructions, it sits the exam again, and the change stays only if the score holds or improves, including on held-out cases it was never tuned on. Like a teacher marking with an answer key, then marking the teacher.

## Context
- The user read Anthropic's "Writing tools for agents" (2026-11-20) and took three points from it: define what each agent is given, evaluate it properly, and define everything clearly enough that it is used as intended. Its loop: realistic tasks with known outcomes → run → read why it fails → let Claude improve the agent → re-run, with a held-out set against overfitting.
- Before this, the card checker and the marker had exams, but the card writer had none: the user was its filter, cutting niche cards by hand (70 cut in one wide review). The checker's exam had no "too niche" cases, so it let them through.

## Decision
1. **Every agent block has an exam** with a held-out part: `card_checker` (`check-cards-exam`, cards labelled pass/fail), `marking` (`check-marking-eval`, answers the user labelled), `card_writer` (`writer-exam`, fixed writing jobs scored by drafts kept, why the rest died, empty jobs). `primer_check` gets one from the user's next spot-check of its tags.
2. **Changing an agent's prompt follows the loop:** run its exam (the "before"); read the reasons it fails (each exam prints them); let a separate Claude propose a general change (never naming exam cases); apply it, bump `PROMPT_VERSION`; run the exam again, main and held-out, twice where the result is close. Keep the change only if the main score holds or improves and the held-out score holds. Record before and after in `docs/SETUP_LOG.md`.
3. **Exams grow from real mistakes:** a card the user cuts, or a mark the user disputes, becomes a labelled case (with the user's reason) in the right agent's exam.
4. **Held-out cases stay unseen:** they are never read while writing a change. If a change was written after seeing one, that case moves to the main exam and an unseen case replaces it.
5. **No tools by default.** The app's agents get everything in the prompt (`--tools ""`, ADR 0008). A tool is added only where an exam shows the agent needs one (e.g. "search this paper" if the writer drifts). The agentic source finder in `docs/FUTURE.md` will be the first agent with tools, and its exam comes with it.

## Why / alternatives considered
- **The user as the only filter:** worked, but costs the user's time and doesn't scale; it also hid why cards were bad.
- **Fine-tuning a model:** not needed; changing the written instructions (prompt tuning) is cheaper and reversible, and the exam measures it.
- **Tune on everything:** faster, but then a good score proves only memory. The held-out part is what shows a change generalises.

## Consequences
- First run of the loop (2026-11-20): the checker caught 26 of 33 niche cards before and 30–31 of 35 after (prompt v4); the writer kept 2 of 7 held-out drafts before and 5 of 8 after (prompt v10).
- Exams cost real Claude calls (cents for the checker, about $1 for the writer), so they run by hand, not in CI.
- `CLAUDE.md` carries the loop as a working rule, so it doesn't depend on memory.
