# 0003: quizkit is copied from mandarin-hsk-trainer, not installed

- **Status:** Accepted (2026-11-12)
- **In plain words:** we photocopied the generic quiz parts (quizkit) from the Mandarin project and wrote down where they came from, instead of installing that whole project as a library.

## Context
`mandarin-hsk-trainer` has `src/quizkit/`: cards, grader, deck builder, quiz engine, Claude judge, Leitner progress (about 2,100 lines, 513 tests, needs only `pydantic` + `rapidfuzz`). This quiz needs the same parts.

## Decision
- Copy `src/quizkit/`, its generic tests and `examples/capitals_quiz.py` from HSK commit **`caa969a`** (identical at HSK `3d91733`).
- Only change on copy: `scaffold.py` writes to `longevity_trainer` instead of `hsk_trainer`.
- `tests/test_reuse.py` fails if quizkit ever imports `longevity_trainer`, so it stays generic.
- Later quizkit changes made here (e.g. a list grader) are noted in `docs/SETUP_LOG.md`, so they can be ported back.

## Why / alternatives considered
- **Install from the HSK repo** (`uv add git+…`): that package ships quizkit *and* the Mandarin code, pulls in `pypinyin`, `streamlit` etc., and every quizkit change would need an HSK release.
- **Extract quizkit into its own repo now:** the cleanest long term, but extra setup before we know what this quiz needs to change. Deferred (`docs/FUTURE.md`).

## Consequences
- ✅ We can change quizkit here freely while learning.
- ⚠️ The two copies can drift. When a fix needs to flow between projects, extract quizkit into its own repo.
