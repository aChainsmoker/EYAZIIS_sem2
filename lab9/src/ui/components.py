import logging
from collections import Counter

import streamlit as st

from src.bot.models import BotResult, Command
from src.bot.service import execute
from src.config import CONFIG
from src.errors import BotError
from src.language import LANGUAGE_NAMES
from src.ui.navigation import PAGE_FILES
from src.ui.state import current_error, current_result, reconcile_catalog, save_result, select_document

logger = logging.getLogger(__name__)


def show_error(result: BotResult):
    st.error(result.message)


def load_catalog():
    try:
        from src.db import repository as repo
        documents = repo.all_documents()
        reconcile_catalog(documents)
        return documents
    except Exception:
        logger.exception("Cannot load catalog")
        st.error("Каталог недоступен. Запустите хранилища и индексатор, затем обновите страницу.")
        return None


def document_label(document) -> str:
    language = LANGUAGE_NAMES.get(document.source_language, "не определён")
    return f"{document.title} — {language}"


def _choose_document(documents):
    from src.documents import describe
    document = documents.get(st.session_state["_document_choice"])
    select_document(describe(document) if document else None)


def document_selector():
    documents = load_catalog()
    if documents is None:
        return
    if not documents:
        st.info("В каталоге пока нет документов.")
        return
    by_id = {document.id: document for document in documents}
    labels = {document.id: document_label(document) for document in documents}
    label_counts = Counter(labels.values())
    for document_id, label in labels.items():
        if label_counts[label] > 1:
            labels[document_id] = f"{label} (№{document_id})"
    selected_id = st.session_state.selected_document_id
    if selected_id not in by_id:
        select_document(None)
        selected_id = None
    st.session_state["_document_choice"] = selected_id
    st.selectbox(
        "Документ для работы", list(by_id), index=None, key="_document_choice",
        format_func=lambda item: labels[item],
        placeholder="Выберите документ",
        on_change=_choose_document, args=(by_id,),
    )


def selected_document_panel(*, show_selection_link: bool = True):
    document = st.session_state.selected_document
    if document is None:
        st.info("Сначала выберите документ на странице чата.")
        if show_selection_link:
            if st.button("Выбрать документ", type="primary"):
                st.switch_page(PAGE_FILES["chat"])
        return None
    st.subheader(document["title"])
    st.caption(f"Язык документа — {LANGUAGE_NAMES.get(document['source_language'], 'не определён')}")
    if document["source_language"] == "unknown":
        st.warning("Метод частотных слов не определил язык этого документа.")
    return document


def run_document_action(action: str, button_label: str, progress: str):
    document = selected_document_panel()
    if document is not None and st.button(button_label, type="primary"):
        with st.spinner(progress):
            result = execute(Command(action), document["id"])
        save_result(result, expected_document=document)
        st.rerun()


def render_result(action: str):
    error = current_error(action)
    if error:
        show_error(error)
    record = current_result(action)
    if not record:
        return
    result, record_id = record["result"], record["id"]
    if not result.success:
        show_error(result)
        return
    data = result.data
    if data.get("recognized_text"):
        st.caption("Распознанная команда")
        st.text(data["recognized_text"])
    if action == "search":
        _search_results(data)
    elif action == "summary":
        parameters = record["parameters"]
        extraction_weight = parameters["sentence_extraction_weight"]
        textrank_weight = parameters["textrank_weight"]
        current_weights = st.session_state.summary_weights
        if (abs(current_weights[0] - extraction_weight) > 1e-6
                or abs(current_weights[1] - textrank_weight) > 1e-6):
            st.info(
                f"Сохранённый реферат рассчитан с весами Sentence Extraction {extraction_weight:.2f} "
                f"и TextRank {textrank_weight:.2f}. Для применения выбранных коэффициентов "
                "нажмите «Составить реферат»."
            )
        st.text_area("Реферат", data["text"], height=450, disabled=True, key=f"summary_text_{record_id}")
        st.download_button(
            "Скачать реферат (PDF)", data=data["pdf"], file_name=data["filename"],
            mime=data["mime_type"], key=f"summary_download_{record_id}", on_click="ignore",
        )
    elif action == "translation":
        if data["source_language"] == data["target_language"]:
            st.info(result.message)
        st.text_area("Перевод", data["text"], height=450, disabled=True, key=f"translation_text_{record_id}")
    elif action == "speech":
        st.audio(data["audio"], format=data["mime_type"])
        st.download_button(
            "Скачать аудиофайл (WAV)", data=data["audio"], file_name=data["filename"],
            mime=data["mime_type"], key=f"speech_download_{record_id}", on_click="ignore",
        )


def _search_results(data: dict):
    st.write(f"Результаты по запросу «{data['query']}»")
    if not data["results"]:
        st.info("В выбранном документе ничего не найдено.")
        return
    for row in data["results"]:
        st.caption(f"BM25 — {row['score']:.4f}")
        st.markdown(row["snippet"], unsafe_allow_html=True)


def run_search(query: str, document_id: int, *, k1: float, b: float) -> BotResult:
    try:
        from src.documents import describe, ensure_document_unchanged, require_document
        from src.search.service import search
        document = require_document(document_id)
        parameters = {"k1": k1, "b": b, "limit": int(CONFIG.get("search", {}).get("limit", 20))}
        results = search(query, document_id, **parameters)
        ensure_document_unchanged(document)
        return BotResult(
            True, "search", "search", "Поиск завершён.",
            {"query": query, "results": results, "parameters": parameters, "document": describe(document)},
        )
    except BotError as error:
        return BotResult(False, "search", None, str(error), error.details, error.code)
    except Exception:
        logger.exception("Search failed")
        return BotResult(False, "search", None,
                         "Поиск недоступен. Проверьте запуск индексатора и хранилищ.")
