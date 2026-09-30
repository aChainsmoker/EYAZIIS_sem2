import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.db import repository as repo
from src.config import get_ranking_weights, save_ranking_weights
from src.indexer.watcher import refresh_catalog
from src.storage import s3
from src.ui.help_texts import HELP_TEXT


st.set_page_config(page_title="Автоматическое реферирование", layout="wide")


def initialize() -> None:
    if "db_initialized" not in st.session_state:
        s3.wait_ready()
        repo.init_db()
        refresh_catalog()
        st.session_state.db_initialized = True


@st.fragment(run_every="3s")
def catalog_page() -> None:
    st.title("Каталог документов")

    default_sentence_weight, default_textrank_weight = get_ranking_weights()
    controls = st.columns(2)
    with controls[0]:
        sentence_weight = st.slider(
            "Коэффициент Sentence Extraction",
            min_value=0.0,
            max_value=1.0,
            value=default_sentence_weight,
            step=0.05,
            key="sentence_extraction_weight",
        )
    with controls[1]:
        textrank_weight = st.slider(
            "Коэффициент TextRank",
            min_value=0.0,
            max_value=1.0,
            value=default_textrank_weight,
            step=0.05,
            key="textrank_weight",
        )

    st.caption(f"Сумма коэффициентов: {sentence_weight + textrank_weight:.2f}")
    if st.button("Обновить данные", type="primary"):
        if abs(sentence_weight + textrank_weight - 1.0) > 1e-6:
            st.error("Сумма коэффициентов должна быть равна 1.00")
        else:
            with st.spinner("Перегенерация рефератов..."):
                save_ranking_weights(sentence_weight, textrank_weight)
                processed, removed = refresh_catalog(
                    sentence_extraction_weight=sentence_weight,
                    textrank_weight=textrank_weight,
                    force_reprocess=True,
                )
            st.session_state.pop("catalog_cache", None)
            st.success(f"Данные обновлены. Обработано: {processed}, удалено: {removed}")

    documents = repo.get_all_documents()
    if not documents:
        st.info("Обработанных документов пока нет.")
        return

    for document in documents:
        with st.expander(document.title, expanded=False):
            stamp = document.updated_at.isoformat() if document.updated_at else ""
            cache = st.session_state.setdefault("catalog_cache", {})
            cached = cache.get(document.id)
            if cached and cached["stamp"] == stamp:
                original_url = cached["original_url"]
                summary_url = cached["summary_url"]
                summary_text = cached["summary_text"]
                summary_error = cached["summary_error"]
            else:
                original_url = s3.presigned_url(document.source_s3_key)
                summary_url = s3.presigned_url(document.summary_s3_key)
                summary_error = None
                try:
                    summary_text = s3.get_text(s3.summary_key(document.file_path))
                except Exception as exc:
                    summary_text = ""
                    summary_error = str(exc)
                cache[document.id] = {
                    "stamp": stamp,
                    "original_url": original_url,
                    "summary_url": summary_url,
                    "summary_text": summary_text,
                    "summary_error": summary_error,
                }

            st.markdown(f"Ссылка на файл: [{original_url}]({original_url})")
            st.markdown("#### Реферат")
            if summary_error:
                st.error(f"Не удалось получить реферат из S3: {summary_error}")
            else:
                st.markdown(summary_text.replace("\n", "  \n"))
            st.markdown(f"Ссылка на реферат: [{summary_url}]({summary_url})")


def help_page() -> None:
    st.title("Помощь")
    st.markdown(HELP_TEXT)


initialize()

page = st.navigation(
    {
        "Навигация": [
            st.Page(catalog_page, title="Каталог текстов", url_path="catalog", default=True),
            st.Page(help_page, title="Помощь", url_path="help"),
        ]
    }
)
page.run()
