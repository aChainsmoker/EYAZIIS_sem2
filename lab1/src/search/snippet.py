from nltk.stem import WordNetLemmatizer

_lemmatizer = WordNetLemmatizer()


def _lemmatize_word(word: str) -> str:
    return _lemmatizer.lemmatize(word.strip(".,!?;:\"'()[]").lower())


def generate_snippet(text: str, positions: list[int], query_terms: list[str], window: int = 15) -> str:
    words = text.split()
    if not positions or not words:
        snippet_words = words[:window * 2]
    else:
        best_pos = min(positions)
        start = max(0, best_pos - window)
        end = min(len(words), best_pos + window)
        snippet_words = words[start:end]

    query_set = set(query_terms)
    highlighted = []
    for w in snippet_words:
        if _lemmatize_word(w) in query_set:
            highlighted.append(f"<mark>{w}</mark>")
        else:
            highlighted.append(w)
    snippet = " ".join(highlighted)
    if positions and words:
        best_pos = min(positions)
        if best_pos > window:
            snippet = "... " + snippet
        if best_pos + window < len(words):
            snippet = snippet + " ..."
    return snippet