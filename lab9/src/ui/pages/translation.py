import streamlit as st

from src.bot.models import Command
from src.bot.service import execute
from src.language import LANGUAGE_NAMES
from src.ui.components import render_result, selected_document_panel
from src.ui.state import apply_prefill, current_result, save_result

st.title("Перевод документа")
document = selected_document_panel()
if document is None:
    st.stop()
apply_prefill("translation")
record = current_result("translation")
last_target = record["parameters"]["target_language"] if record else (
    "en" if document["source_language"] == "ru" else "ru"
)
st.session_state.setdefault("translation_target_language", last_target)
with st.form("translation_form"):
    target = st.selectbox(
        "Язык перевода", ["ru", "en"],
        format_func=lambda language: LANGUAGE_NAMES[language],
        key="translation_target_language",
    )
    submitted = st.form_submit_button("Перевести", type="primary")
if submitted:
    with st.spinner("Перевожу выбранный документ..."):
        result = execute(Command("translation", target_language=target), document["id"])
    save_result(result, expected_document=document)
    st.rerun()
render_result("translation")
