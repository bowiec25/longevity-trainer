"""The web quiz page (ADR 0009): the first page `uv run longevity web` opens.

Thin on purpose: Streamlit reruns this whole script on every click, so it only
(1) passes the click to the quiz's brain (`QuizScreen`, kept in session state) and
(2) draws what the brain says. Claude's marking gets a spinner.
"""

import streamlit as st

from longevity_trainer.blocks.card_bank import load_cards
from longevity_trainer.blocks.quiz_round import QuizScreen, RoundOptions
from longevity_trainer.blocks.study import groups
from quizkit.blocks.web_launch import safe

ALL = "All topics"

if "quiz" not in st.session_state:  # a test may put its own (fake judge) here first
    st.session_state["quiz"] = QuizScreen()
quiz: QuizScreen = st.session_state["quiz"]
running = quiz.phase in ("asking", "own_mark", "result")


def _lines(lines: list[str]) -> None:
    for line in lines:
        st.markdown(safe(line))


# --- Settings (locked while a quiz runs) -------------------------------------------
with st.sidebar:
    st.header("Quiz")
    topics = [ALL, *groups(quiz.bank if quiz.bank is not None else load_cards())]
    topic = st.selectbox("Topic", topics, key="topic", disabled=running)
    n = st.number_input(
        "How many", min_value=1, max_value=200, value=10, key="n", disabled=running
    )
    practise = st.checkbox(
        "Practise",
        value=False,
        key="practise",
        disabled=running,
        help="Review cards that aren't due yet. Nothing is saved.",
    )
    judge = st.checkbox(
        "Claude marking",
        value=True,
        key="judge",
        disabled=running,
        help="Ask Claude about answers the answer list misses (needs `claude`, online).",
    )
    save = st.checkbox(
        "Save progress",
        value=True,
        key="save",
        disabled=running,
        help="Save your answers and each card's box, so missed cards come back first.",
    )
    if not running and st.button("Start quiz", type="primary", key="start"):
        quiz.start(
            RoundOptions(
                topic=None if topic == ALL else topic,
                n=int(n),
                practise=practise,
                judge=judge,
                save=save,
            )
        )
        st.rerun()
    if running and st.button("Stop quiz", key="stop"):
        quiz.stop()
        st.rerun()

# --- The quiz ----------------------------------------------------------------------
st.title("🧬 Longevity Trainer")

if quiz.phase == "setup":
    st.write("Pick a topic on the left, then **Start quiz**.")
    for line in quiz.problems:
        (st.info if quiz.nothing_due else st.error)(safe(line))

elif quiz.view is not None and quiz.phase in ("asking", "own_mark", "result"):
    view = quiz.view
    st.subheader(f"Question {view.number} of {view.total}")
    st.caption(safe(view.topic))
    st.markdown(f"#### {safe(view.question)}")

    if quiz.phase == "asking":
        with st.form(f"answer-{view.number}", clear_on_submit=True):
            typed = st.text_area(
                "Your answer (a word, a name, or a sentence or two)",
                key=f"typed-{view.number}",
                height=90,
            )
            checked = st.form_submit_button("Check", type="primary")
        if checked:
            with st.spinner("Checking (Claude can take a few seconds)…"):
                quiz.submit(typed, view.card_id)
            st.rerun()

    elif quiz.phase == "own_mark" and quiz.marking is not None:
        mark = quiz.marking
        st.text(f"You wrote: {mark.typed}")
        _lines(mark.lines)
        st.markdown(f"**{safe(mark.question)}** Mark it yourself (Y / N):")
        yes, no = st.columns(2)
        if yes.button("Yes", key=f"yes-{view.number}", width="stretch", shortcut="Y"):
            quiz.mark(True, mark.card_id)
            st.rerun()
        if no.button("No", key=f"no-{view.number}", width="stretch", shortcut="N"):
            quiz.mark(False, mark.card_id)
            st.rerun()

    elif quiz.phase == "result" and quiz.result is not None:
        res = quiz.result
        st.text(f"You wrote: {res.typed}" if res.typed.strip() else "(no answer)")
        first, *rest = res.lines
        (st.success if res.right else st.error)(safe(first))
        _lines(rest)
        r = res.receipt
        st.info(safe(f'"{r.quote}"'), icon="🧾")
        st.caption(safe(f"Receipt: {r.source}, p. {r.page}"))
        if res.warning:
            st.warning(safe(res.warning))
        if st.button(  # Enter: no typing box on this screen, so it's free
            "Next →", type="primary", key=f"next-{view.number}", shortcut="Enter"
        ):
            quiz.next(res.card_id)
            st.rerun()

elif quiz.phase == "ended":
    st.subheader("Done")
    _lines(quiz.summary)
    if st.button("New quiz", type="primary", key="new"):
        quiz.new_quiz()
        st.rerun()
