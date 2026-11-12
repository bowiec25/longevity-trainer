# 0008: The card writer uses `claude -p`, not the Agent SDK

- **Status:** Accepted (2026-11-12). Replaces guardrail 5 of [0002](0002-script-vs-agent.md) for the card writer; 0002's other guardrails stand.
- **In plain words:** writing cards turned out to be one question with a fixed reply shape ("here's a source, give me 8 cards as JSON"), so it uses the same `claude -p` call (your subscription) as the judge and the card checker. No API key, no tools.

## Context
ADR 0002 planned the Agent SDK (API key) for the card writer, "because it needs tools". When M3 was planned (issue #17) the writer needed none: the source text is read by code (`source_text`) and put in the prompt, and the reply is forced into a JSON schema. `quizkit.claude.ask_claude(..., json_schema=...)` already does exactly that.

## Decision
- The card writer (`card_writer`) makes **one** `claude -p` call (Sonnet by default) with the source text in the prompt and a JSON schema for the reply. No tools.
- Its gates (shape, quote found in the source, no repeats, the card checker) are its checker script (0002 guardrail 2), so the survivors are written straight to `data/cards/<topic>.jsonl`, not to a holding folder. A run that misses the writer bar writes nothing.
- 0002 guardrail 4 (`--limit N` and `--dry-run`, log model, prompt version and cost): `--n` (1–20) is the limit, and `write-cards` prints the model, prompt version, Claude calls, tokens and cost.

## Why / alternatives considered
- **Agent SDK as planned:** needs an API key and pay-per-token billing, and adds a dependency, for a job with no tool use.
- **A holding folder (`data/generated/`) reviewed before moving:** a human approval gate, which 0002 guardrail 3 rules out; the gates already decide.

## Consequences
- ✅ Free on the subscription, same call path and fakes as the judge and checker, easy to test.
- ⚠️ Sources must fit in one prompt (200,000 characters); a bigger source would need splitting, or the SDK with tools. Revisit then.
