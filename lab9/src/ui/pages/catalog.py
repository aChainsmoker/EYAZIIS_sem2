import logging

import streamlit as st

from src.language import LANGUAGE_NAMES
from src.ui.components import load_catalog

logger = logging.getLogger(__name__)
st.title("Каталог документов")


@st.fragment(run_every="3s")
def catalog():
    documents = load_catalog()
    if documents is None:
        return
    if not documents:
        st.info("В каталоге пока нет документов.")
        return
    st.caption(f"Всего документов: {len(documents)}")
    for document in documents:
        with st.expander(document.title):
            st.write(f"Язык — {LANGUAGE_NAMES.get(document.source_language, 'не определён')}")
            try:
                from src.storage import s3
                st.link_button("Скачать оригинал", s3.url(document.source_s3_key))
            except Exception:
                logger.exception("Cannot create original download link")
                st.warning("Не удалось получить ссылку на оригинал.")


catalog()
