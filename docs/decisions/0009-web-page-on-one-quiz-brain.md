# 0009: A local Streamlit web page on one shared quiz brain

- **Status:** Accepted (2026-11-12)
- **In plain words:** the quiz gets a web page you open in your browser. It runs on your computer only, and it uses the same "brain" as the terminal quiz: the same cards dealt, the same marking, the same words after each answer, the same saving. Copied from how HSK did it (HSK ADR 0014).

## Context
- The user wants to play in a browser ("I'm gonna wait for the Streamlit setup to play").
- HSK already built one: Streamlit on 127.0.0.1, a brain with no Streamlit in it (`WebQuiz`) that a thin page draws, tested with Streamlit's AppTest. It works the same way here, because the quizkit engine already goes one step at a time (`current`, `answer`, `own_mark`, `result`).
- What to say after an answer, the "count it as right?" rule, and setting up a round (deal, progress file, judge) all lived in `cli.py`. A web page would have had to copy them.

## Decision
1. **One brain:** a new longevity block, `quiz_round`.
   - `setup` builds a round: it deals the cards, opens the progress file and builds the judge.
   - The wording functions say what to show after an answer: `feedback`, `own_mark_line`, `receipt_line` and `score_line`.
   - `QuizScreen` is the click-by-click quiz for a page that redraws on every click.
   - The terminal's `play()` keeps its own loop but takes every line from the block, so its output doesn't change.
2. **Streamlit, local only** (M4 Step 3b). `uv run longevity web` starts it on 127.0.0.1, sends no usage data and shows no Deploy button. Streamlit is added with `uv add`.
3. **The pages are front ends** (on `test_process.py`'s NOT_BLOCKS list): they only pass clicks to `QuizScreen` and draw what it says. They're tested with AppTest, with no browser.
4. **Generic web parts go to quizkit:** Markdown-safe text and the local launcher. HSK has both, so the rule of two is met. They'll be ported back to HSK.

## Why / alternatives considered
- **Copy the logic into the page:** two places to change, and they drift. We just removed exactly that kind of copy from the marking eval (M4.2).
- **A generic quizkit "web quiz brain":** HSK's brain is full of HSK parts (sentences, translate modes). Wait until a third quiz needs one (FUTURE).
- **Flask, FastAPI or a JavaScript front end:** more code to learn and test. Streamlit is what HSK uses, it is Python only, and AppTest runs it without a browser.

## Consequences
- ✅ The terminal and the web page can't disagree. One set of tests covers the rules.
- ✅ Your progress is shared: a card answered on the web counts in `longevity quiz` and in `stats`.
- ⚠️ Streamlit reruns the whole page on every click, so the brain must ignore stale or double clicks (it does, and it's tested).
- ⚠️ Local only, so no phone over the internet. Revisit if you want that (it needs hosting and a login).
