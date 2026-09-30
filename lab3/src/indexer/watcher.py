import logging
import os
import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from src.config import DATA_DIR
from src.indexer.file_handler import FileHandler
from src.indexer.reconciler import reconcile_input

logger = logging.getLogger(__name__)

_refresh_lock = threading.Lock()
_state_lock = threading.Lock()
_refresh_pending = False
_refresh_worker_running = False


def refresh_catalog(
    sentence_extraction_weight: float | None = None,
    textrank_weight: float | None = None,
    force_reprocess: bool = False,
) -> tuple[int, int]:
    """Synchronously reconcile the input directory with DB and S3."""
    logger.info("Starting catalog refresh")
    with _refresh_lock:
        processed, removed = reconcile_input(
            sentence_extraction_weight=sentence_extraction_weight,
            textrank_weight=textrank_weight,
            force_reprocess=force_reprocess,
        )
    logger.info("Catalog refresh completed: processed=%s, removed=%s", processed, removed)
    return processed, removed


def _background_refresh_loop() -> None:
    global _refresh_pending, _refresh_worker_running
    while True:
        with _state_lock:
            if not _refresh_pending:
                _refresh_worker_running = False
                return
            _refresh_pending = False

        try:
            refresh_catalog()
        except Exception:
            logger.exception("Background catalog refresh failed")


def request_refresh(reason: str) -> None:
    """Queue a refresh without blocking watchdog's event thread."""
    global _refresh_pending, _refresh_worker_running
    with _state_lock:
        _refresh_pending = True
        if _refresh_worker_running:
            logger.info("Catalog refresh already running; queued another refresh (%s)", reason)
            return
        _refresh_worker_running = True
        worker = threading.Thread(target=_background_refresh_loop, name="catalog-refresh", daemon=True)
        worker.start()
    logger.info("Catalog refresh requested: %s", reason)


def _is_supported(path: str) -> bool:
    return Path(path).suffix.lower() in FileHandler.SUPPORTED_EXTENSIONS


class FileEventHandler(FileSystemEventHandler):
    def __init__(self) -> None:
        super().__init__()
        self._last_events: dict[str, float] = {}

    def _handle_event(self, path: str, event_name: str) -> None:
        if not _is_supported(path):
            return
        normalized = os.path.abspath(os.path.normpath(path))
        now = time.monotonic()
        if now - self._last_events.get(normalized, 0.0) < 1.0:
            return
        self._last_events[normalized] = now
        logger.info("%s file detected: %s", event_name, normalized)
        request_refresh(f"{event_name.lower()}: {normalized}")

    def on_created(self, event) -> None:
        if not event.is_directory:
            self._handle_event(event.src_path, "New")

    def on_modified(self, event) -> None:
        if not event.is_directory:
            self._handle_event(event.src_path, "Modified")

    def on_deleted(self, event) -> None:
        if not event.is_directory:
            self._handle_event(event.src_path, "Deleted")

    def on_moved(self, event) -> None:
        if event.is_directory:
            return
        self._handle_event(event.src_path, "Moved/deleted")
        self._handle_event(event.dest_path, "Moved/created")


def start_watcher() -> Observer:
    os.makedirs(DATA_DIR, exist_ok=True)
    observer = Observer()
    observer.schedule(FileEventHandler(), path=DATA_DIR, recursive=True)
    observer.start()
    logger.info("Watching %s recursively for supported documents", DATA_DIR)
    return observer
