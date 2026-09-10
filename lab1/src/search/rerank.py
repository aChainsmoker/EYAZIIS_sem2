import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from src.db import repository as repo
from src.search.bm25 import bm25_search
from src.search.embeddings import _get_model, encode
from src.storage.reader import get_document_text


def rerank(query: str, bm25_results: list[dict], k1: float = 1.2, b: float = 0.75, top_n: int = 20) -> list[dict]:
    if not bm25_results:
        return []

    model = _get_model()

    query_embedding = encode(query)

    doc_ids = [r["doc_id"] for r in bm25_results]
    embeddings_map = repo.get_document_embeddings(doc_ids)

    doc_embeddings = []
    missing = []
    for r in bm25_results:
        emb = embeddings_map.get(r["doc_id"])
        if emb is not None:
            doc_embeddings.append(emb)
        else:
            missing.append(r)

    if missing:
        missing_texts = []
        for r in missing:
            text = get_document_text(r["doc_id"])
            missing_texts.append(text if text else "")
        missing_embeddings = model.encode(missing_texts)
        for i, r in enumerate(missing):
            doc_embeddings.append(missing_embeddings[i].tolist())
            repo.update_document_embedding(r["doc_id"], [float(x) for x in missing_embeddings[i]])

    doc_embeddings = np.array(doc_embeddings)
    similarities = cosine_similarity([query_embedding], doc_embeddings)[0]

    for i, r in enumerate(bm25_results):
        r["cosine_score"] = round(float(similarities[i]), 4)
        r["final_score"] = round(r["score"] * r["cosine_score"], 4)

    reranked = sorted(bm25_results, key=lambda x: x["final_score"], reverse=True)[:top_n]
    return reranked


def search_with_rerank(query: str, k1: float = 1.2, b: float = 0.75, bm25_limit: int = 100, top_n: int = 20) -> list[dict]:
    bm25_results = bm25_search(query, k1=k1, b=b, limit=bm25_limit)
    return rerank(query, bm25_results, k1=k1, b=b, top_n=top_n)