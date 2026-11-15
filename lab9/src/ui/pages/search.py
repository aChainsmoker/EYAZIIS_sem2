import streamlit as st

from src.config import CONFIG
from src.ui.components import render_result, run_search, selected_document_panel
from src.ui.state import apply_prefill, current_result, save_result

st.title("Поиск в тексте")
document = selected_document_panel()
if document is None:
    st.stop()
apply_prefill("search")
settings = CONFIG.get("search", {})
record = current_result("search")
last_query = record["result"].data.get("query", "") if record else ""
last_parameters = record.get("parameters", {}) if record else {}
st.session_state.setdefault("search_query", last_query)
st.session_state.setdefault("search_k1", float(last_parameters.get("k1", settings.get("k1", 1.2))))
st.session_state.setdefault("search_b", float(last_parameters.get("b", settings.get("b", 0.75))))

with st.form("search_form"):
    query = st.text_input("Поисковый запрос", key="search_query")
    left, right = st.columns(2)
    with left:
        k1 = st.slider("Насыщение частоты термина (k1)", 0.0, 3.0, step=0.1, key="search_k1")
    with right:
        b = st.slider("Нормализация длины (b)", 0.0, 1.5, step=0.05, key="search_b")
    submitted = st.form_submit_button("Найти", type="primary")

if submitted:
    if not query.strip():
        st.warning("Введите поисковый запрос.")
    else:
        with st.spinner("Ищу в выбранном документе..."):
            result = run_search(query.strip(), document["id"], k1=k1, b=b)
        save_result(result, parameters={"k1": k1, "b": b}, expected_document=document)
        st.rerun()

render_result("search")
