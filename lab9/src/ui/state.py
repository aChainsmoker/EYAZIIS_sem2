import logging
from uuid import uuid4

import streamlit as st

from src.bot.models import BotResult
from src.config import CONFIG

logger = logging.getLogger(__name__)
_ACTIONS = ("search", "summary", "translation", "speech")


def _default_summary_weights():
    settings = CONFIG.get("summary", {})
    return (
        float(settings.get("sentence_extraction_weight", 0.7)),
        float(settings.get("textrank_weight", 0.3)),
    )


def initialize():
    st.session_state.setdefault("bot_history", [])
    st.session_state.setdefault("bot_results", {})
    st.session_state.setdefault("bot_errors", {})
    st.session_state.setdefault("bot_prefill", {})
    st.session_state.setdefault("voice_input_version", 0)
    st.session_state.setdefault("selected_document_id", None)
    st.session_state.setdefault("selected_document", None)
    st.session_state.setdefault("selected_signature", None)
    st.session_state.setdefault("summary_weights", _default_summary_weights())
    if any(action in st.session_state.bot_results for action in _ACTIONS):
        _migrate_results()
        _restore_settings()


def _signature(document: dict | None):
    if document is None:
        return None
    return document["id"], document["file_hash"], document["source_language"]


def _result_parameters(result: BotResult, parameters: dict | None = None):
    if result.action == "search":
        settings = CONFIG.get("search", {})
        defaults = {
            "query": result.data["query"],
            "k1": float(settings.get("k1", 1.2)),
            "b": float(settings.get("b", 0.75)),
            "limit": int(settings.get("limit", 20)),
        }
    elif result.action == "summary":
        # Старые результаты не содержат весов, но их сохраняла сессия.
        extraction_weight, textrank_weight = st.session_state.summary_weights
        defaults = {
            "sentence_extraction_weight": extraction_weight,
            "textrank_weight": textrank_weight,
            "sentence_count": int(CONFIG.get("summary", {}).get("sentence_count", 10)),
        }
    elif result.action == "translation":
        defaults = {"target_language": result.data["target_language"]}
    else:
        defaults = {}
    return {**defaults, **(parameters or {}), **result.data.get("parameters", {})}


def _migrate_results():
    cache = st.session_state.bot_results
    for action in _ACTIONS:
        record = cache.pop(action, None)
        if not record or not record["result"].success:
            continue
        signature = record.get("document_signature") or _signature(record["result"].data.get("document"))
        if signature is None:
            continue
        migrated = {
            **record,
            "parameters": _result_parameters(record["result"], record.get("parameters")),
            "document_signature": signature,
        }
        cache.setdefault(signature[0], {}).setdefault(action, migrated)


def _prefill_values(action: str, record: dict | None):
    parameters = record["parameters"] if record else {}
    if action == "search":
        settings = CONFIG.get("search", {})
        return {
            "search_query": parameters.get("query", ""),
            "search_k1": float(parameters.get("k1", settings.get("k1", 1.2))),
            "search_b": float(parameters.get("b", settings.get("b", 0.75))),
        }
    if action == "summary":
        extraction_weight, textrank_weight = _default_summary_weights()
        return {
            "summary_sentence_extraction_weight": parameters.get("sentence_extraction_weight", extraction_weight),
            "summary_textrank_weight": parameters.get("textrank_weight", textrank_weight),
        }
    if action == "translation":
        document = st.session_state.selected_document
        source = document["source_language"] if document else None
        return {
            "translation_target_language": parameters.get("target_language", "en" if source == "ru" else "ru"),
        }
    return {}


def _restore_settings():
    records = st.session_state.bot_results.get(st.session_state.selected_document_id, {})
    st.session_state.bot_prefill = {
        action: _prefill_values(action, records.get(action))
        for action in ("search", "summary", "translation")
    }
    summary = st.session_state.bot_prefill["summary"]
    st.session_state.summary_weights = (
        summary["summary_sentence_extraction_weight"], summary["summary_textrank_weight"],
    )


def select_document(document: dict | None):
    signature = _signature(document)
    changed = signature != st.session_state.selected_signature
    if document is not None:
        records = st.session_state.bot_results.get(document["id"], {})
        if any(record["document_signature"] != signature for record in records.values()):
            st.session_state.bot_results.pop(document["id"], None)
            changed = True
    st.session_state.selected_signature = signature
    st.session_state.selected_document_id = document["id"] if document else None
    st.session_state.selected_document = document
    if changed:
        st.session_state.bot_errors = {}
        _restore_settings()
        st.session_state.voice_input_version += 1


def _refresh_document(document: dict | None):
    if document is None:
        st.session_state.bot_results.pop(st.session_state.selected_document_id, None)
        st.session_state.selection_notice = "Выбранный документ удалён. Выберите другой файл."
    elif _signature(document) != st.session_state.selected_signature:
        st.session_state.selection_notice = "Документ обновлён. Его предыдущие результаты сброшены."
    select_document(document)


def reconcile_catalog(documents):
    from src.documents import describe
    snapshots = {document.id: describe(document) for document in documents}
    cache = st.session_state.bot_results
    for document_id, records in list(cache.items()):
        signature = _signature(snapshots.get(document_id))
        if signature is None or any(record["document_signature"] != signature for record in records.values()):
            cache.pop(document_id)
    selected_id = st.session_state.selected_document_id
    if selected_id is not None:
        _refresh_document(snapshots.get(selected_id))


def refresh_selection():
    document_id = st.session_state.selected_document_id
    if document_id is None:
        return
    try:
        from src.db import repository as repo
        from src.documents import describe
        document = repo.get_document(document_id)
    except Exception:
        logger.exception("Cannot refresh selected document")
        st.session_state.selected_document = None
        st.session_state.selection_notice = "Каталог временно недоступен. Проверьте подключение к PostgreSQL."
        return
    _refresh_document(describe(document) if document else None)


def save_result(
    result: BotResult, *, prefill: bool = False, parameters: dict | None = None,
    expected_document: dict | None = None,
) -> str | None:
    if expected_document is not None and _signature(expected_document) != st.session_state.selected_signature:
        return None
    record_id = uuid4().hex
    document = result.data.get("document")
    if result.success and _signature(document) != st.session_state.selected_signature:
        return None
    if result.success and document:
        select_document(document)
    if not result.action or st.session_state.selected_document is None:
        return record_id
    record = {
        "id": record_id, "result": result,
        "document_signature": st.session_state.selected_signature,
    }
    if not result.success:
        st.session_state.bot_errors[result.action] = record
        return record_id
    record["parameters"] = _result_parameters(result, parameters)
    records = st.session_state.bot_results.setdefault(document["id"], {})
    records[result.action] = record
    st.session_state.bot_errors.pop(result.action, None)
    if prefill:
        st.session_state.bot_prefill[result.action] = _prefill_values(result.action, record)
    return record_id


def current_result(action: str):
    records = st.session_state.bot_results.get(st.session_state.selected_document_id, {})
    record = records.get(action)
    if not record or st.session_state.selected_document is None:
        return None
    if record.get("document_signature") != st.session_state.selected_signature:
        return None
    return record


def current_error(action: str):
    record = st.session_state.bot_errors.get(action)
    if not record or st.session_state.selected_document is None:
        return None
    if record["document_signature"] != st.session_state.selected_signature:
        return None
    return record["result"]


def apply_prefill(action: str):
    for key, value in st.session_state.bot_prefill.pop(action, {}).items():
        st.session_state[key] = value
