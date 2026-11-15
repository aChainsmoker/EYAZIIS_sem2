import re

from src.nlp.resources import language_tools


def token_spans(text: str, language: str):
    if language not in {"ru", "en"}:
        raise ValueError("Поддерживаются языки ru/en.")
    alphabet = r"[а-яё]+" if language == "ru" else r"[a-z]+"
    return list(re.finditer(alphabet, text, re.IGNORECASE))


def preprocess_with_positions(text: str, language: str = "en") -> tuple[list[str], dict[str, list[int]]]:
    stopwords, normalize = language_tools(language)
    lemmas, positions = [], {}
    for position, match in enumerate(token_spans(text, language)):
        token = match.group().lower()
        if token in stopwords or len(token) <= 1:
            continue
        lemma = normalize(token)
        lemmas.append(lemma)
        positions.setdefault(lemma, []).append(position)
    return lemmas, positions


def preprocess(text: str, language: str = "en") -> list[str]:
    return preprocess_with_positions(text, language)[0]
