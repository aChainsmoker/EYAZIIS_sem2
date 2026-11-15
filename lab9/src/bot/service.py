"""Прикладной API действий над явно выбранным документом."""

import logging

from src.bot.models import BotResult, Command
from src.bot.parser import parse_command
from src.errors import BotError, CommandError, DatabaseUnavailableError

logger = logging.getLogger(__name__)
_ACTIONS = {"search", "summary", "translation", "speech"}


def _failure(error: BotError, action=None) -> BotResult:
    return BotResult(False, action, None, str(error), error.details, error.code)


def execute(
    command: Command, document_id: int | None, *,
    summary_weights: tuple[float, float] | None = None,
) -> BotResult:
    action = command.action if isinstance(command, Command) else None
    try:
        if action not in _ACTIONS:
            raise CommandError("Укажите одно из четырёх действий.")
        if action == "search" and not command.argument.strip():
            raise CommandError("Укажите поисковый запрос.")
        if action != "search" and command.argument:
            raise CommandError("Действие применяется к документу, выбранному в чате.")
        if action == "translation" and command.target_language not in {"ru", "en"}:
            raise CommandError("Укажите целевой язык перевода, русский или английский.")
        from src.documents import describe, ensure_document_unchanged, load_document_text, require_document
        document = require_document(document_id)
        if action == "search":
            from src.config import CONFIG
            from src.search.service import search
            settings = CONFIG.get("search", {})
            parameters = {
                "k1": float(settings.get("k1", 1.2)),
                "b": float(settings.get("b", 0.75)),
                "limit": int(settings.get("limit", 20)),
            }
            results = search(command.argument, document.id, **parameters)
            data = {"query": command.argument, "results": results, "parameters": parameters}
            message = "Совпадения найдены." if results else "В выбранном документе ничего не найдено."
        elif action == "summary":
            from src.summary.service import summarize_document
            data = summarize_document(document, weights=summary_weights)
            message = "Реферат готов."
        elif action == "translation":
            from src.translation.service import translate
            source, target = document.source_language, command.target_language
            translated = translate(load_document_text(document), source, target)
            data = {"text": translated, "source_language": source, "target_language": target}
            if source == target:
                message = "Документ уже на выбранном языке. Показан оригинальный текст."
            else:
                message = "Перевод готов."
        else:
            from src.tts.service import synthesize_document
            data = synthesize_document(load_document_text(document), document.title, document.source_language)
            message = "Аудиозапись готова."
        ensure_document_unchanged(document)
        return BotResult(True, action, action, message, {"document": describe(document), **data})
    except BotError as error:
        return _failure(error, action)
    except Exception as error:
        from sqlalchemy.exc import SQLAlchemyError
        if isinstance(error, SQLAlchemyError):
            logger.exception("Database operation failed")
            return _failure(DatabaseUnavailableError("База данных недоступна. Проверьте запуск PostgreSQL и индексатора."), action)
        logger.exception("Bot operation failed")
        return _failure(BotError("Не удалось выполнить действие. Проверьте зависимости и настройки сервиса."), action)


def handle_message(
    text: str, document_id: int | None, *, summary_weights: tuple[float, float] | None = None,
) -> BotResult:
    try:
        command = parse_command(text)
    except CommandError as error:
        return _failure(error)
    return execute(command, document_id, summary_weights=summary_weights)


def handle_audio(
    audio_bytes: bytes, language: str, document_id: int | None, *,
    summary_weights: tuple[float, float] | None = None,
) -> BotResult:
    try:
        from src.speech import transcribe_audio
        text = transcribe_audio(audio_bytes, language)
    except BotError as error:
        return _failure(error)
    except Exception:
        logger.exception("Audio recognition failed")
        from src.errors import RecognitionError
        return _failure(RecognitionError("Не удалось подготовить распознавание речи. Проверьте Whisper и FFmpeg."))
    result = handle_message(text, document_id, summary_weights=summary_weights)
    return BotResult(
        result.success, result.action, result.page, result.message,
        {"recognized_text": text, **result.data}, result.error_code,
    )
