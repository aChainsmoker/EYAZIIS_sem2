import logging

from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

_model = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        try:
            _model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu", local_files_only=True)
            logger.info("Loaded embedding model from local cache")
        except Exception:
            _model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
            logger.info("Downloaded embedding model (first run)")
    return _model


def encode(text: str) -> list[float]:
    model = _get_model()
    vec = model.encode([text])[0]
    return [float(x) for x in vec]