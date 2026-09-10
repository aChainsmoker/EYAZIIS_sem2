import logging

from src.db import repository as repo
from src.storage import s3
from src.indexer.file_handler import FileHandler

logger = logging.getLogger(__name__)


def get_document_text(doc_id: int) -> str | None:
    doc = repo.get_document(doc_id)
    if not doc:
        return None
    if doc.s3_key:
        try:
            return s3.get_text(doc.s3_key)
        except Exception as e:
            logger.warning(f"Cannot read S3 object {doc.s3_key}: {e}")
    try:
        return FileHandler().extract_text(doc.file_path)
    except Exception as e:
        logger.warning(f"Cannot read {doc.file_path}: {e}")
        return None