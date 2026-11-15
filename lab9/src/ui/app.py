import streamlit as st

from src.language import LANGUAGES
from src.ui.navigation import PAGE_FILES, PAGE_TITLES
from src.ui.state import initialize, refresh_selection


def main():
    st.set_page_config(page_title="Помощник по документам", layout="wide")
    initialize()
    refresh_selection()
    pages = [
        st.Page(path, title=PAGE_TITLES[name], url_path=name, default=name == "chat")
        for name, path in PAGE_FILES.items()
    ]
    page = st.navigation(pages)
    with st.sidebar:
        st.selectbox("Язык", list(LANGUAGES), key="voice_language")
    page.run()
