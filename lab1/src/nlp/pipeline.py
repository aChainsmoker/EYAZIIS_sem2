import re
import nltk
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
from nltk.tokenize import word_tokenize

for _resource in ("punkt_tab", "stopwords", "wordnet"):
    nltk.download(_resource)

_lemmatizer = WordNetLemmatizer()
_stop_words = set(stopwords.words("english"))


def preprocess(text: str) -> list[str]:
    text = text.lower()
    text = re.sub(r"[^a-z\s]", " ", text)
    tokens = word_tokenize(text)
    tokens = [t for t in tokens if t not in _stop_words and len(t) > 1]
    lemmas = [_lemmatizer.lemmatize(t) for t in tokens]
    return lemmas


def preprocess_with_positions(text: str) -> tuple[list[str], dict[str, list[int]]]:
    text = text.lower()
    text = re.sub(r"[^a-z\s]", " ", text)
    tokens = word_tokenize(text)
    filtered = [(i, t) for i, t in enumerate(tokens) if t not in _stop_words and len(t) > 1]
    lemmas = []
    positions: dict[str, list[int]] = {}
    for idx, token in filtered:
        lemma = _lemmatizer.lemmatize(token)
        lemmas.append(lemma)
        positions.setdefault(lemma, []).append(idx)
    return lemmas, positions
