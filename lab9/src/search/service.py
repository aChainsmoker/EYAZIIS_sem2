from src.config import CONFIG
from src.db import repository as repo
from src.documents import load_document_text, require_document
from src.search.pipeline import preprocess
from src.search.snippet import generate_snippet


def search(
    query: str, document_id: int, *, k1: float | None = None,
    b: float | None = None, limit: int | None = None,
) -> list[dict]:
    document = require_document(document_id)
    language = document.source_language
    settings = CONFIG.get("search", {})
    k1 = settings.get("k1", 1.2) if k1 is None else k1
    b = settings.get("b", 0.75) if b is None else b
    limit = settings.get("limit", 20) if limit is None else limit
    if not 0 <= k1 <= 3 or not 0 <= b <= 1.5 or limit < 1:
        raise ValueError("Недопустимые параметры поиска.")
    terms = preprocess(query, language)
    if not terms:
        return []
    entries = repo.search_entries(terms, document_id, language)
    if not entries:
        return []
    indexed_document = entries[0]["document"]
    score = 0.0
    positions = []
    for entry in entries:
        denominator = entry["tf"] + k1 * (
            1 - b + b * entry["doc_length"] / entry["average_length"]
        )
        if denominator:
            score += entry["idf"] * entry["tf"] * (k1 + 1) / denominator
        positions.extend(entry["positions"])
    positions = sorted(set(positions))
    return [dict(
        doc_id=indexed_document.id, title=indexed_document.title,
        file_path=indexed_document.file_path, source_s3_key=indexed_document.source_s3_key,
        score=round(score, 4), positions=positions, doc_length=entries[0]["doc_length"],
        snippet=generate_snippet(
            load_document_text(indexed_document), positions, terms, language=language,
        ),
    )]
