import hashlib
import logging
import os
from pathlib import Path

from src.config import DATA_DIR, SUMMARY_SENTENCE_COUNT, get_ranking_weights
from src.db import repository as repo
from src.indexer.file_handler import FileHandler
from src.nlp.cleaner import clean_text, release_model as release_cleaner_model
from src.nlp.summarizer import collection_document_frequency, detect_language, summarize
from src.storage import s3
from src.storage.pdf_generator import build_text_pdf

logger = logging.getLogger(__name__)


def _file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _content_type(path: str) -> str:
    return {".pdf": "application/pdf", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".rtf": "text/rtf", ".txt": "text/plain"}.get(Path(path).suffix.lower(), "application/octet-stream")


def process_file(
    path: str,
    text: str | None = None,
    language: str | None = None,
    existing=None,
    collection_document_count: int = 1,
    document_frequency: dict[str, int] | None = None,
    sentence_extraction_weight: float | None = None,
    textrank_weight: float | None = None,
    force_reprocess: bool = False,
) -> None:
    path = os.path.abspath(os.path.normpath(path))
    raw = Path(path).read_bytes()
    digest = _file_hash(raw)
    if (
        existing
        and existing.file_hash == digest
        and not force_reprocess
    ):
        logger.info("Skipping unchanged document: %s", path)
        return

    logger.info("Extracting and cleaning text: %s", path)
    text = text or FileHandler().extract_text(path)
    if not text or not text.strip():
        logger.warning("Skipping empty or unreadable file: %s", path)
        return
    language = language or detect_language(text)
    source_sentences, keyword_scores = summarize(
        text,
        language,
        SUMMARY_SENTENCE_COUNT,
        collection_document_count=collection_document_count,
        document_frequency=document_frequency,
        sentence_extraction_weight=sentence_extraction_weight,
        textrank_weight=textrank_weight,
    )
    logger.info("Building summary in the original language: %s", path)
    source_keywords = [term for term, _ in keyword_scores[:15]]

    summary = "\n".join([
        f"Документ: {Path(path).name}",
        f"Исходный язык: {'испанский' if language == 'es' else 'английский'}",
        "",
        "Классический реферат:",
        *[f"{index}. {sentence}" for index, sentence in enumerate(source_sentences, 1)],
        "",
        "Ключевые слова:",
        *[f"- {keyword}" for keyword in source_keywords],
    ])
    original_key = s3.original_key(path)
    summary_text_key = s3.summary_key(path)
    abstract_key = s3.summary_pdf_key(path)
    logger.info("Uploading original and summary to S3: %s", path)
    s3.put_bytes(original_key, raw, _content_type(path))
    s3.put_text(summary_text_key, summary)
    s3.put_bytes(abstract_key, build_text_pdf(summary), "application/pdf")
    logger.info("Saving document metadata to PostgreSQL: %s", path)
    repo.save_document({
        "title": Path(path).stem,
        "file_path": path,
        "source_language": language,
        "file_hash": digest,
        "source_s3_key": original_key,
        "summary_s3_key": abstract_key,
        "summary_text": summary,
    }, existing=existing)
    logger.info("Processed %s", path)


def reconcile_input(
    sentence_extraction_weight: float | None = None,
    textrank_weight: float | None = None,
    force_reprocess: bool = False,
) -> tuple[int, int]:
    logger.info("Scanning input directory: %s", DATA_DIR)
    os.makedirs(DATA_DIR, exist_ok=True)
    paths = {
        os.path.abspath(str(path))
        for path in Path(DATA_DIR).rglob("*")
        if path.is_file() and path.suffix.lower() in FileHandler.SUPPORTED_EXTENSIONS
    }
    current = {document.file_path: document for document in repo.get_all_documents()}
    prepared: dict[str, tuple[str, str]] = {}
    for path in sorted(paths):
        try:
            text = FileHandler().extract_text(path)
            if text and text.strip():
                cleaned_text = clean_text(text)
                prepared[path] = (cleaned_text, detect_language(cleaned_text))
        except Exception:
            logger.exception("Cannot extract text from %s", path)

    release_cleaner_model()

    document_frequency = collection_document_frequency(list(prepared.values()))
    collection_document_count = len(prepared)
    if sentence_extraction_weight is None or textrank_weight is None:
        sentence_extraction_weight, textrank_weight = get_ranking_weights()
    logger.info("Prepared %s supported document(s) for processing", collection_document_count)
    processed = 0
    for path in sorted(paths):
        try:
            before = current.get(path)
            if path not in prepared:
                continue
            text, language = prepared[path]
            process_file(
                path,
                text=text,
                language=language,
                existing=before,
                collection_document_count=collection_document_count,
                document_frequency=document_frequency,
                sentence_extraction_weight=sentence_extraction_weight,
                textrank_weight=textrank_weight,
                force_reprocess=force_reprocess,
            )
            if before is None or before.file_hash != _file_hash(Path(path).read_bytes()):
                processed += 1
        except Exception:
            logger.exception("Cannot process %s", path)
    removed = 0
    for path, document in current.items():
        if path not in paths:
            logger.info("Removing missing document: %s", path)
            deleted = repo.delete_document(path, existing=document)
            if deleted:
                s3.delete_object(deleted.source_s3_key)
                s3.delete_object(deleted.summary_s3_key)
                text_summary_key = s3.summary_key(path)
                if text_summary_key != deleted.summary_s3_key:
                    s3.delete_object(text_summary_key)
                removed += 1
    return processed, removed
