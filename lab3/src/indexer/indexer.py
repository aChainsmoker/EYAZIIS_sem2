import logging

from src.db import repository as repo
from src.indexer.watcher import refresh_catalog, start_watcher
from src.storage import s3

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def run() -> None:
    s3.wait_ready()
    repo.init_db()
    processed, removed = refresh_catalog()
    logging.info("Initial scan completed: processed=%s, removed=%s", processed, removed)
    observer = start_watcher()
    try:
        while observer.is_alive():
            observer.join(timeout=1.0)
    except KeyboardInterrupt:
        logging.info("Stopping file watcher")
        observer.stop()
    observer.join()
    logging.info("File watcher stopped")


if __name__ == "__main__":
    run()
