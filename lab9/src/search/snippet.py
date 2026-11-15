import re
from html import escape

from src.nlp.resources import language_tools
from src.search.pipeline import token_spans


def generate_snippet(
    text: str, positions: list[int], query_terms: list[str],
    window: int = 15, language: str = "en",
) -> str:
    _, normalize = language_tools(language)
    spans = token_spans(text, language)
    if not spans:
        return escape(text[:300])
    best = min(positions) if positions else 0
    best = min(best, len(spans) - 1)
    start = max(0, best - window)
    end = min(len(spans), best + window + 1)
    query_set = set(query_terms)
    cursor = spans[start].start()
    parts = ["... "] if start else []
    for match in spans[start:end]:
        parts.append(escape(text[cursor:match.start()]))
        word = escape(match.group())
        if normalize(match.group().lower()) in query_set:
            word = f"<mark>{word}</mark>"
        parts.append(word)
        cursor = match.end()
    if end < len(spans):
        parts.append(" ...")
    else:
        parts.append(escape(text[cursor:]))
    return re.sub(r"\s+", " ", "".join(parts))
