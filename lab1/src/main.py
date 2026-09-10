import sys
import os
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.db import repository as repo
from src.indexer.watcher import start_watcher, index_existing_files, backfill_embeddings, sync_with_filesystem
from src.storage import s3

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def main():
    s3.wait_ready(timeout=120.0)
    repo.init_db()
    index_existing_files()
    sync_with_filesystem()
    backfill_embeddings()
    observer = start_watcher()
    try:
        while True:
            pass
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()
