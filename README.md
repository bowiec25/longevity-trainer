# Longevity Trainer

A quiz that tests my longevity knowledge: ageing science, sleep, exercise, nutrition, and the evidence behind them.

**Every answer carries a receipt.** A question only exists if a trusted source (a guideline, a consensus statement, a systematic review) states its answer, and a script has found the supporting quote, word for word, in a pinned copy of that source. After each answer the quiz shows the receipt.

> Status: **M0 setup**, no quiz yet. Progress: [`docs/PLAN.md`](docs/PLAN.md).

## Run it
```
uv sync                    # install (exact versions from uv.lock)
uv run longevity-trainer   # the app (just a hello for now)
uv run pytest              # tests
```

## How it's built
- Same approach as [mandarin-hsk-trainer](https://github.com/bowiec25/mandarin-hsk-trainer) (its `docs/PLAYBOOK.md` is the checklist).
- Generic quiz parts (`quizkit`: cards, grader, deck, engine, Claude judge, Leitner progress) are copied from there (M1).
- Docs: [`docs/PLAN.md`](docs/PLAN.md) (plan + progress), [`docs/SETUP_LOG.md`](docs/SETUP_LOG.md) (why each step), [`docs/FUTURE.md`](docs/FUTURE.md) (ideas for later).
