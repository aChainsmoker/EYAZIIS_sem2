import os
import json
import logging
import math
import time
from collections import Counter
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from src.config import DATA_DIR
from src.nlp.pipeline import preprocess_with_positions
from src.search.embeddings import encode
from src.storage import s3
from src.storage.reader import get_document_text
from src.indexer.file_handler import FileHandler
from src.db import repository as repo

logger = logging.getLogger(__name__)


def index_file(file_path: str):
    file_path = os.path.abspath(os.path.normpath(file_path))
    if repo.get_document_by_path(file_path):
        logger.info(f"Already indexed: {file_path}")
        return

    text = FileHandler().extract_text(file_path)
    if text is None:
        logger.error(f"Cannot extract text from {file_path}")
        return
    logger.info(f"Extracting text: {file_path}")

    try:
        with open(file_path, "rb") as f:
            raw = f.read()
    except Exception as e:
        logger.error(f"Cannot read {file_path}: {e}")
        return

    key = s3.object_key(file_path)
    original_key = s3.original_key(file_path)
    try:
        s3.put_text(key, text)
        s3.put_bytes(original_key, raw)
    except Exception as e:
        logger.error(f"Cannot upload {file_path} to MinIO: {e}")
        return
    logger.info(f"Uploading to MinIO: {file_path}")
    logger.info("Preprocessing text...")

    lemmas, positions = preprocess_with_positions(text)
    doc_length = len(lemmas)
    if doc_length == 0:
        logger.warning(f"Empty document after preprocessing: {file_path}")
        return

    title = os.path.splitext(os.path.basename(file_path))[0]
    logger.info("Saving document to DB...")
    doc = repo.add_document(title=title, file_path=file_path, doc_length=doc_length, s3_key=key, s3_original_key=original_key)

    logger.info("Creating embeddings...")
    embedding = encode(text)
    repo.update_document_embedding(doc.id, embedding)

    tf_counter = Counter(lemmas)
    total_terms = len(lemmas)

    logger.info("Adding inverted index entries...")

    term_ids = repo.get_or_create_terms(list(tf_counter.keys()))
    rows = [
        (term_ids[lemma], count / total_terms, positions.get(lemma, []))
        for lemma, count in tf_counter.items()
    ]
    repo.add_inverted_entries(doc.id, rows)

    repo.recalculate_term_stats()

    logger.info(f"Document indexed successfully: {title} ({doc_length} tokens)")


def delete_document(file_path: str):
    path = os.path.abspath(os.path.normpath(file_path))
    doc = repo.get_document_by_path(path)
    if not doc:
        return
    repo.delete_document(path)
    if doc.s3_key:
        s3.delete_object(doc.s3_key)
    if doc.s3_original_key:
        s3.delete_object(doc.s3_original_key)
    logger.info(f"Document deleted successfully: {path}")


def _is_supported(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in FileHandler.SUPPORTED_EXTENSIONS


class FileEventHandler(FileSystemEventHandler):
    def __init__(self):
        self._last_modified: dict[str, float] = {}

    def on_created(self, event):
        if event.is_directory:
            return
        if _is_supported(event.src_path):
            logger.info(f"New file detected: {event.src_path}")
            index_file(event.src_path)

    def on_deleted(self, event):
        if event.is_directory:
            return
        if _is_supported(event.src_path):
            logger.info(f"File deleted: {event.src_path}")
            delete_document(event.src_path)

    def on_modified(self, event):
        if event.is_directory:
            return
        if not _is_supported(event.src_path):
            return
        path = os.path.abspath(os.path.normpath(event.src_path))
        now = time.time()
        if now - self._last_modified.get(path, 0.0) < 1.0:
            return
        self._last_modified[path] = now
        logger.info(f"File modified: {path}")
        if repo.get_document_by_path(path):
            delete_document(path)
        index_file(path)


def start_watcher():
    os.makedirs(DATA_DIR, exist_ok=True)
    observer = Observer()
    observer.schedule(FileEventHandler(), path=DATA_DIR, recursive=False)
    observer.start()
    logger.info(f"Watching {DATA_DIR} for supported documents")
    return observer


def index_existing_files():
    os.makedirs(DATA_DIR, exist_ok=True)
    for filename in os.listdir(DATA_DIR):
        if _is_supported(filename):
            file_path = os.path.join(DATA_DIR, filename)
            index_file(file_path)
    logger.info("Indexing existing files completed")


def sync_with_filesystem() -> int:
    removed = 0
    for doc in repo.get_all_documents():
        if not os.path.isfile(doc.file_path):
            delete_document(doc.file_path)
            removed += 1
    logger.info(f"Filesystem sync completed: removed {removed} document(s)")
    return removed


def backfill_embeddings():
    logger.info("Backfilling embeddings...")
    backfilled = 0
    for doc in repo.get_all_documents():
        if repo.get_document_embedding(doc.id) is None:
            text = get_document_text(doc.id)
            if not text:
                logger.error(f"Cannot read {doc.file_path}: no text available")
                continue
            repo.update_document_embedding(doc.id, encode(text))
            backfilled += 1
            logger.info(f"Embedding backfilled for: {doc.title}")
    logger.info(f"Embedding backfill completed: {backfilled} document(s)")
