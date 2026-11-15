import math

from src.config import CONFIG
from src.db import repository as repo
from src.documents import load_document_text
from src.errors import CommandError, DocumentTextError
from src.nlp.cleaner import clean_text
from src.summary.algorithm import collection_document_frequency, summarize
from src.summary.pdf import build_text_pdf


def summarize_document(document, *, weights: tuple[float, float] | None = None) -> dict:
    language = document.source_language
    settings = CONFIG.get("summary", {})
    sentence_count = int(settings.get("sentence_count", 10))
    if weights is None:
        weights = (
            float(settings.get("sentence_extraction_weight", 0.7)),
            float(settings.get("textrank_weight", 0.3)),
        )
    extraction_weight, textrank_weight = weights
    if sentence_count < 1:
        raise ValueError("Проверьте число предложений реферата в TOML.")
    if (not all(math.isfinite(weight) and 0 <= weight <= 1 for weight in weights)
            or abs(extraction_weight + textrank_weight - 1) > 1e-6):
        raise CommandError("Коэффициенты реферирования должны быть от 0 до 1, их сумма должна равняться 1.")
    target = clean_text(load_document_text(document))
    if not target:
        raise DocumentTextError("После очистки в документе не осталось текста.")
    collection = [(target, language)]
    for other in repo.all_documents():
        if other.id == document.id or other.source_language != language:
            continue
        try:
            text = clean_text(load_document_text(other))
        except DocumentTextError:
            # Пустые документы и PDF без текста не входят в коллекцию №3.
            continue
        if text:
            collection.append((text, language))
    frequencies = collection_document_frequency(collection)
    sentences, keyword_scores = summarize(
        target, language, sentence_count=sentence_count,
        collection_document_count=len(collection), document_frequency=frequencies,
        sentence_extraction_weight=extraction_weight, textrank_weight=textrank_weight,
    )
    keywords = [term for term, _ in keyword_scores[:15]]
    text = "\n".join([
        f"Документ: {document.title}",
        f"Исходный язык: {'русский' if language == 'ru' else 'английский'}", "",
        "Классический реферат:",
        *[f"{index}. {sentence}" for index, sentence in enumerate(sentences, 1)],
        "", "Ключевые слова:", *[f"- {word}" for word in keywords],
    ])
    return dict(title=document.title, source_language=language, sentences=sentences,
                keywords=keywords, text=text, pdf=build_text_pdf(text),
                mime_type="application/pdf", filename=f"{document.title}_summary.pdf",
                parameters={"sentence_count": sentence_count,
                            "sentence_extraction_weight": extraction_weight,
                            "textrank_weight": textrank_weight})
