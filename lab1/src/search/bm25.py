import json
import math
from collections import defaultdict

from src.nlp.pipeline import preprocess
from src.db import repository as repo
from src.db.models import InvertedIndex, Term


def bm25_search(query: str, k1: float = 1.2, b: float = 0.75, limit: int = 100) -> list[dict]:
    query_terms = preprocess(query)
    if not query_terms:
        return []

    terms = repo.get_terms_for_query(query_terms)
    if not terms:
        return []

    stats = repo.get_collection_stats()
    if not stats:
        return []

    total_docs, avg_dl = stats

    scores: dict[int, float] = defaultdict(float)
    term_data: dict[int, list[tuple[InvertedIndex, Term]]] = defaultdict(list)

    term_by_id = {t.id: t for t in terms}
    entries = repo.get_entries_for_terms(list(term_by_id.keys()))
    for entry in entries:
        term_data[entry.doc_id].append((entry, term_by_id[entry.term_id]))

    docs_map = repo.get_documents_by_ids(list(term_data.keys()))
    for doc_id, entries in term_data.items():
        doc = docs_map.get(doc_id)
        if not doc:
            continue
        dl = doc.doc_length
        score = 0.0
        for entry, term in entries:
            tf = entry.tf
            idf = term.idf
            numerator = tf * (k1 + 1)
            denominator = tf + k1 * (1 - b + b * (dl / avg_dl))
            score += idf * (numerator / denominator)
        scores[doc_id] = score

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:limit]
    results = []
    for doc_id, score in ranked:
        doc = docs_map.get(doc_id)
        if doc:
            all_positions = []
            for entry, _ in term_data[doc_id]:
                all_positions.extend(json.loads(entry.positions))
            results.append({
                "doc_id": doc.id,
                "title": doc.title,
                "file_path": doc.file_path,
                "s3_key": doc.s3_key,
                "s3_original_key": doc.s3_original_key,
                "score": round(score, 4),
                "doc_length": doc.doc_length,
                "positions": sorted(set(all_positions)),
            })
    return results
