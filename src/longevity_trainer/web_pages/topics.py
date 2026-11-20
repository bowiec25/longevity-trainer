"""The web Topics page: what's in each quiz topic, at a glance.

Read-only (user, 2026-11-20: "a brief summary of whats in each chapter topic I can
select", not completion counts). One folding section per topic you can pick in the quiz
(an area): a one-line summary, then the sub-topics in it. From `topic_map.topic_guide`.
"""

import streamlit as st

from longevity_trainer.blocks.topic_map import load_topic_map, topic_guide
from quizkit.blocks.web_launch import safe

st.title("📚 What's in each topic")
try:
    guide = topic_guide(load_topic_map())
except (OSError, ValueError) as err:
    st.error(safe(f"can't read the topic map: {err}"))
    st.stop()
st.caption("Each quiz topic, in the Quiz page's order, and what sits under it.")
for area in guide:
    with st.expander(safe(area.area)):
        if area.summary:
            st.markdown(safe(area.summary))
        for name in area.topics:
            st.text(f"• {name}")
