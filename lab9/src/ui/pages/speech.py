import streamlit as st

from src.ui.components import render_result, run_document_action

st.title("Озвучка документа")
run_document_action("speech", "Озвучить", "Создаю аудиозапись...")
render_result("speech")
