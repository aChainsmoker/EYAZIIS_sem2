"""Поиск документов каталога и единое извлечение текста из оригиналов."""

import codecs
import hashlib
import ntpath

from src.errors import (
    AmbiguousDocumentError, DocumentNotFoundError, DocumentNotReadyError,
    DocumentTextError, LanguageDetectionError,
)

SUPPORTED_EXTENSIONS = {".txt", ".pdf", ".docx", ".rtf"}


def extract_text(data: bytes, filename: str) -> str:
    extension = ntpath.splitext(filename)[1].lower()
    try:
        if extension == ".txt":
            encoding = "utf-16" if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)) else "utf-8-sig"
            text = data.decode(encoding)
        elif extension == ".pdf":
            import fitz
            with fitz.open(stream=data, filetype="pdf") as document:
                text = "\n".join(page.get_text() for page in document)
        elif extension == ".docx":
            from io import BytesIO
            from docx import Document
            document = Document(BytesIO(data))
            parts = [paragraph.text for paragraph in document.paragraphs]
            parts.extend("\t".join(cell.text for cell in row.cells)
                         for table in document.tables for row in table.rows)
            text = "\n".join(parts)
        elif extension == ".rtf":
            from striprtf.striprtf import rtf_to_text
            text = rtf_to_text(data.decode("latin-1"))
        else:
            raise DocumentTextError("Поддерживаются только TXT, PDF, DOCX и RTF.")
    except DocumentTextError:
        raise
    except Exception as exc:
        raise DocumentTextError(f"Не удалось прочитать текст файла «{ntpath.basename(filename)}».") from exc
    if not text.strip():
        raise DocumentTextError("Документ пуст или не содержит текстового слоя. OCR не поддерживается.")
    return text


def describe(document) -> dict:
    return {"id": document.id, "title": document.title, "file_path": document.file_path,
            "source_language": document.source_language, "file_hash": document.file_hash}


def require_document(document_id: int):
    from src.db import repository as repo
    if not isinstance(document_id, int) or isinstance(document_id, bool):
        raise DocumentNotFoundError("Сначала выберите документ на странице чата.")
    document = repo.get_document(document_id)
    if document is None:
        raise DocumentNotFoundError("Выбранный документ удалён. Выберите другой файл в чате.")
    if not repo.is_index_current(document):
        raise DocumentNotReadyError("Документ ожидает обновления индекса. Запустите индексатор и дождитесь обработки файла.")
    if document.source_language not in {"ru", "en"}:
        raise LanguageDetectionError("Не удалось определить язык документа методом частотных слов.")
    return document


def ensure_document_unchanged(document):
    from src.db import repository as repo
    latest = repo.get_document(document.id)
    if latest is None or (latest.file_hash, latest.source_language) != (document.file_hash, document.source_language):
        raise DocumentNotReadyError("Документ изменился во время обработки. Повторите команду для обновлённого файла.")


def resolve_document(reference: str):
    from src.db import repository as repo
    documents = repo.all_documents()
    reference = reference.strip()
    normalized_path = ntpath.normcase(ntpath.normpath(reference))
    path_matches = [doc for doc in documents
                    if ntpath.normcase(ntpath.normpath(doc.file_path)) == normalized_path]
    if len(path_matches) == 1:
        return path_matches[0]
    query = reference.casefold()
    exact = [doc for doc in documents if query in {doc.title.casefold(), ntpath.basename(doc.file_path).casefold()}]
    # Whisper может добавить точку в конце произнесённого названия.
    if not exact and reference.endswith((".", "!", "?")):
        query = query.rstrip(".!?").strip()
        exact = [doc for doc in documents if query in {doc.title.casefold(), ntpath.basename(doc.file_path).casefold()}]
    matches = exact or [doc for doc in documents if query and (
        query in doc.title.casefold() or query in ntpath.basename(doc.file_path).casefold()
    )]
    if not matches:
        raise DocumentNotFoundError(f"Документ «{reference}» не найден.")
    if len(matches) > 1:
        raise AmbiguousDocumentError(
            "Найдено несколько документов. Повторите полную команду с нужным путём.",
            candidates=[describe(doc) for doc in matches],
        )
    return matches[0]


def load_document_text(document) -> str:
    from src.storage import s3
    data = s3.get_bytes(document.source_s3_key)
    if hashlib.sha256(data).hexdigest() != document.file_hash:
        raise DocumentTextError("Оригинал обновляется. Повторите запрос после завершения индексации.")
    return extract_text(data, document.file_path)
