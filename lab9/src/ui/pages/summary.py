import streamlit as st

from src.bot.models import Command
from src.bot.service import execute
from src.ui.components import render_result, selected_document_panel
from src.ui.state import apply_prefill, save_result


def save_weights():
    st.session_state.summary_weights = (
        st.session_state.summary_sentence_extraction_weight,
        st.session_state.summary_textrank_weight,
    )


st.title("Реферирование")
document = selected_document_panel()
if document is None:
    st.stop()

apply_prefill("summary")
weights = st.session_state.summary_weights
st.session_state.setdefault("summary_sentence_extraction_weight", weights[0])
st.session_state.setdefault("summary_textrank_weight", weights[1])
left, right = st.columns(2)
with left:
    sentence_weight = st.slider(
        "Коэффициент Sentence Extraction",
        min_value=0.0, max_value=1.0, step=0.05,
        key="summary_sentence_extraction_weight", on_change=save_weights,
    )
with right:
    textrank_weight = st.slider(
        "Коэффициент TextRank",
        min_value=0.0, max_value=1.0, step=0.05,
        key="summary_textrank_weight", on_change=save_weights,
    )

st.caption(f"Сумма коэффициентов — {sentence_weight + textrank_weight:.2f}")
if st.button("Составить реферат", type="primary"):
    if abs(sentence_weight + textrank_weight - 1) > 1e-6:
        st.error("Сумма коэффициентов должна быть равна 1.00")
    else:
        with st.spinner("Составляю реферат и PDF..."):
            result = execute(
                Command("summary"), document["id"],
                summary_weights=(sentence_weight, textrank_weight),
            )
        save_result(result, expected_document=document)
        st.rerun()

render_result("summary")
