"""The web Stats page (ADR 0009): the same lines as `longevity stats`.

Read-only: it never makes the progress file. The lines come from the study block's
`stats_lines` (shared with `longevity stats`), so the two always agree.
"""

from datetime import UTC, datetime

import streamlit as st

from longevity_trainer.blocks.card_bank import load_cards
from longevity_trainer.blocks.quiz_round import RoundFiles
from longevity_trainer.blocks.study import stats_lines
from quizkit.blocks.progress_store import ProgressFileError, ProgressStore
from quizkit.blocks.web_launch import safe

st.title("📊 Stats")
# The quiz's own files if a quiz screen exists (one source of truth), else defaults.
quiz = st.session_state.get("quiz")
files = getattr(quiz, "files", None) or RoundFiles()
bank = getattr(quiz, "bank", None)
try:
    store = ProgressStore(files.progress) if files.progress.exists() else None
    lines = stats_lines(
        bank if bank is not None else load_cards(), store, datetime.now(UTC)
    )
except ProgressFileError as err:
    st.error(safe(f"can't read {files.progress.name}: {err}"))
    st.stop()
for line in lines:
    st.text(line)
