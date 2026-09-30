from __future__ import annotations

import csv
import logging
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nltk.tokenize import word_tokenize

from src.indexer.file_handler import FileHandler
from src.nlp.cleaner import clean_text, release_model as release_cleaner_model
from src.nlp.summarizer import collection_document_frequency, detect_language, summarize
from tests.performance_timer import PerformanceTimer


INPUT_DIR = ROOT / "data" / "input"
RESULTS_DIR = ROOT / "tests" / "results"
RESULTS_FILE = RESULTS_DIR / "benchmark_results.csv"


def _prepare_collection(paths: list[Path]) -> list[tuple[str, str]]:
    prepared = []
    handler = FileHandler()
    for path in paths:
        text = handler.extract_text(str(path)) or ""
        cleaned = clean_text(text)
        if cleaned.strip():
            prepared.append((cleaned, detect_language(cleaned)))
    release_cleaner_model()
    return prepared


def run_benchmark() -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    paths = sorted(
        path
        for path in INPUT_DIR.rglob("*")
        if path.is_file() and path.suffix.lower() in FileHandler.SUPPORTED_EXTENSIONS
    )
    if not paths:
        raise RuntimeError(f"No supported files found in {INPUT_DIR}")

    prepared_collection = _prepare_collection(paths)
    document_frequency = collection_document_frequency(prepared_collection)
    collection_size = len(prepared_collection)
    rows: list[dict[str, object]] = []
    cumulative_seconds = 0.0
    cumulative_tokens = 0

    for path in paths:
        timer = PerformanceTimer(path.name).start()
        raw_text = FileHandler().extract_text(str(path)) or ""
        extraction = timer.lap("extraction")
        language = detect_language(raw_text)
        token_count = len(word_tokenize(raw_text))
        language_detection = timer.lap("language detection")
        cleaned_text = clean_text(raw_text)
        cleaning = timer.lap("cleaning")
        summary, keywords = summarize(
            cleaned_text,
            language,
            collection_document_count=collection_size,
            document_frequency=document_frequency,
        )
        summarization = timer.lap("summarization")
        total_seconds = timer.stop()
        cumulative_seconds += total_seconds
        cumulative_tokens += token_count
        rows.append(
            {
                "file_name": path.name,
                "file_path": str(path.relative_to(ROOT)),
                "language": language,
                "token_count": token_count,
                "summary_sentence_count": len(summary),
                "keyword_count": len(keywords),
                "cumulative_token_count": cumulative_tokens,
                "extraction_seconds": extraction["interval_seconds"],
                "cleaning_seconds": cleaning["interval_seconds"],
                "language_detection_seconds": language_detection["interval_seconds"],
                "summarization_seconds": summarization["interval_seconds"],
                "total_seconds": total_seconds,
                "cumulative_seconds": cumulative_seconds,
            }
        )

    with RESULTS_FILE.open("w", newline="", encoding="utf-8") as results_file:
        writer = csv.DictWriter(results_file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return RESULTS_FILE


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    results_file = run_benchmark()
    print(f"Benchmark results: {results_file}")
