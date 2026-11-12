# 0002: Script vs agent

- **Status:** Accepted (2026-11-12), same rule as mandarin-hsk-trainer's ADR 0002. Guardrail 5 superseded by [0008](0008-card-writer-uses-claude-p.md) for the card writer
- **In plain words:** if code can **check** the answer is right, write a **script**. If the job needs **judgment** (writing a good question, marking a free-text answer), use an **AI agent**, and a script always checks what the agent made.

## Context
Some jobs are mechanical (is this quote really in the source? run the quiz). Some need judgment (write a fair question from a source; is "cell ageing" close enough to "cellular senescence"?). AI can do both, but it is slower, costs tokens, and can be wrong in ways that are hard to spot.

## Decision
| Use a **script** when… | Use an **agent** when… |
|---|---|
| Correctness can be checked in code | Quality needs judgment |
| It runs often, must be free and instant | It runs rarely and its output is saved |
| e.g. quote check, dealing the deck, the quiz loop | e.g. writing cards, judging free text, auditing meaning |

**Guardrails for every agent:**
1. Agents run as **batch jobs** that write files; the quiz only reads saved cards. The one runtime exception is the optional Claude judge, which always has a fallback and an off switch.
2. **A script checks every agent output** before it's saved. An agent's own self-check helps, but never replaces the script.
3. **No human approval gates:** what fails a check is dropped or removed, and the user gets a one-line summary.
4. Every agent has `--limit N` and `--dry-run`, and logs model, prompt version and token cost.
5. **How we call Claude:** `claude -p` for single questions (subscription, e.g. the judge); the **Agent SDK** for the card writer (M3, API key), because it needs tools.

## Why / alternatives considered
- **All scripts:** can't write questions or judge free-text answers.
- **All agents:** slow, costly, results change between runs, hard to test.
- **Agent with no checking:** lets wrong or unsupported cards in.

## Consequences
- ✅ The quiz is free and instant; agent mistakes are caught by code.
- ⚠️ Each agent needs a matching checker script. That's extra work, and it's the point.
