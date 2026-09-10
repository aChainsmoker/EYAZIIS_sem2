from src.db import repository as repo
from src.search.bm25 import bm25_search


def precision_at_k(retrieved: list[int], relevant_set: set[int], k: int) -> float:
    retrieved_k = retrieved[:k]
    if not retrieved_k:
        return 0.0
    hits = sum(1 for d in retrieved_k if d in relevant_set)
    return hits / len(retrieved_k)


def recall_at_k(retrieved: list[int], relevant_set: set[int], k: int) -> float:
    if not relevant_set:
        return 0.0
    retrieved_k = retrieved[:k]
    hits = sum(1 for d in retrieved_k if d in relevant_set)
    return hits / len(relevant_set)


def f1_at_k(p: float, r: float) -> float:
    if p + r == 0:
        return 0.0
    return 2 * p * r / (p + r)


def average_precision(retrieved: list[int], relevant_set: set[int]) -> float:
    if not relevant_set:
        return 0.0
    hits = 0
    sum_precisions = 0.0
    for i, doc_id in enumerate(retrieved):
        if doc_id in relevant_set:
            hits += 1
            sum_precisions += hits / (i + 1)
    return sum_precisions / len(relevant_set) if relevant_set else 0.0


def mean_average_precision(all_results: dict[int, tuple[list[int], set[int]]]) -> float:
    if not all_results:
        return 0.0
    total_ap = 0.0
    for query_id, (retrieved, relevant_set) in all_results.items():
        total_ap += average_precision(retrieved, relevant_set)
    return total_ap / len(all_results)


def interpolated_precision_recall(retrieved: list[int], relevant_set: set[int], total_relevant: int) -> list[tuple[float, float]]:
    if not relevant_set or total_relevant == 0:
        return [(0.0, 0.0)] * 11

    precisions = []
    recalls = []
    hits = 0
    for i, doc_id in enumerate(retrieved):
        if doc_id in relevant_set:
            hits += 1
            p = hits / (i + 1)
            r = hits / total_relevant
            precisions.append((r, p))

    if not precisions:
        return [(0.0, 0.0)] * 11

    levels = [i / 10.0 for i in range(11)]
    interpolated = []
    for level in levels:
        max_p = 0.0
        for r, p in precisions:
            if r >= level:
                max_p = max(max_p, p)
        interpolated.append((level, max_p))
    return interpolated


RETRIEVAL_LIMIT = 50


def generate_k_values(max_k: int) -> list[int]:
    if max_k <= 0:
        return []
    ks = []
    k = 5
    while k < max_k:
        ks.append(k)
        k *= 2
    if not ks:
        ks.append(max_k)
    elif ks[-1] != max_k:
        ks.append(max_k)
    return ks


def evaluate_from_db(k_values: list[int] = None) -> dict:
    if k_values is None:
        stats = repo.get_collection_stats()
        total_docs = stats[0] if stats else 0
        k_values = generate_k_values(total_docs) or [5]

    queries = repo.get_all_evaluation_queries()

    metrics = {
        "per_query": {},
        "avg": {},
        "pr_curves": {},
    }

    all_pr_curves = {k: [] for k in k_values}

    for eval_query in queries:
        query_id = eval_query.id
        query_text = eval_query.query_text

        judgments = repo.get_judgments(query_id)
        relevant_set = {doc_id for doc_id, rel in judgments.items() if rel}
        total_relevant = len(relevant_set)

        retrieved_docs = bm25_search(query_text, limit=RETRIEVAL_LIMIT)
        retrieved_ids = [d["doc_id"] for d in retrieved_docs]

        query_metrics = {"precision": {}, "recall": {}, "f1": {}}
        for k in k_values:
            p = precision_at_k(retrieved_ids, relevant_set, k)
            r = recall_at_k(retrieved_ids, relevant_set, k)
            query_metrics["precision"][k] = p
            query_metrics["recall"][k] = r
            query_metrics["f1"][k] = f1_at_k(p, r)

        query_metrics["map"] = average_precision(retrieved_ids, relevant_set)
        query_metrics["total_relevant"] = total_relevant
        metrics["per_query"][query_id] = query_metrics

        for k in k_values:
            pr_curve = interpolated_precision_recall(retrieved_ids[:k], relevant_set, total_relevant)
            all_pr_curves[k].append(pr_curve)

    avg_metrics = {"precision": {}, "recall": {}, "f1": {}}
    n_queries = len(metrics["per_query"])
    for k in k_values:
        avg_metrics["precision"][k] = sum(m["precision"][k] for m in metrics["per_query"].values()) / n_queries if n_queries else 0.0
        avg_metrics["recall"][k] = sum(m["recall"][k] for m in metrics["per_query"].values()) / n_queries if n_queries else 0.0
        avg_metrics["f1"][k] = sum(m["f1"][k] for m in metrics["per_query"].values()) / n_queries if n_queries else 0.0

    avg_metrics["map"] = sum(m["map"] for m in metrics["per_query"].values()) / n_queries if n_queries else 0.0
    metrics["avg"] = avg_metrics

    for k in k_values:
        curves = all_pr_curves[k]
        if curves:
            avg_curve = []
            for level_idx in range(11):
                avg_p = sum(curve[level_idx][1] for curve in curves) / len(curves)
                avg_curve.append((level_idx / 10.0, avg_p))
            metrics["pr_curves"][k] = avg_curve
        else:
            metrics["pr_curves"][k] = [(i / 10.0, 0.0) for i in range(11)]

    return metrics
