"""The web Syllabus page: every learnable sub-topic, chapter by chapter, at a glance.

Read-only (user, 2026-11-19: "see at a glance and high level what sits under each
topic"). The data comes from the topic_map block's `syllabus_view`, the same counts as
`longevity coverage`. It uses the running quiz's cards if there is one (as Stats does).
"""

import streamlit as st

from longevity_trainer.blocks.card_bank import load_cards
from longevity_trainer.blocks.topic_map import load_topic_map, syllabus_view
from quizkit.blocks.web_launch import safe

st.title("📚 Syllabus")
bank = getattr(st.session_state.get("quiz"), "bank", None)
try:
    chapters = syllabus_view(
        bank if bank is not None else load_cards(), load_topic_map()
    )
except (OSError, ValueError) as err:
    st.error(safe(f"can't read the cards or the topic map: {err}"))
    st.stop()
rows = [row for chapter in chapters for row in chapter.rows]
core = [row for row in rows if row.priority == "core"]
st.caption(
    safe(
        f"{sum(r.covered for r in rows)} of {len(rows)} sub-topics covered "
        f"(core {sum(r.covered for r in core)} of {len(core)}). "
        "Covered = a what card and a how card."
    )
)
for chapter in chapters:
    nn = "??" if chapter.number is None else f"{chapter.number:02d}"
    done = " ✓" if chapter.covered == chapter.total else ""
    label = f"{nn} {chapter.name}: {chapter.covered} of {chapter.total}{done}"
    with st.expander(safe(label)):
        for row in chapter.rows:
            parts = [row.name, row.priority, f"{row.cards} cards"]
            end = " ✓" if row.covered else f" ({row.gap})"
            st.text(" · ".join(p for p in parts if p) + end)
