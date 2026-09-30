import logging
import math
import re
from collections import Counter
from dataclasses import dataclass

import nltk
from src.config import get_ranking_weights
from nltk.corpus import stopwords
from nltk.stem import SnowballStemmer, WordNetLemmatizer
from nltk.tokenize import word_tokenize

logger = logging.getLogger(__name__)

def _ensure_nltk_resource(resource: str, lookup_path: str) -> None:
    try:
        nltk.data.find(lookup_path)
    except LookupError:
        logger.info("Downloading NLTK resource: %s", resource)
        nltk.download(resource, quiet=True)


_ensure_nltk_resource("stopwords", "corpora/stopwords")
_ensure_nltk_resource("wordnet", "corpora/wordnet")

_STOPWORDS = {
    "en": set(stopwords.words("english")),
    "es": set(stopwords.words("spanish")),
}
_LEMMATIZER = WordNetLemmatizer()
_STEMMERS = {
    "en": SnowballStemmer("english"),
    "es": SnowballStemmer("spanish"),
}


@dataclass(frozen=True)
class SentenceInfo:
    text: str
    document_start: int
    paragraph_start: int
    paragraph_length: int


def detect_language(text: str) -> str:
    from langdetect import DetectorFactory, detect

    DetectorFactory.seed = 0
    detected = detect(text[:10000])
    return "es" if detected.startswith("es") else "en"


def _tokens(text: str, language: str) -> list[str]:
    tokens = word_tokenize(text.lower(), preserve_line=True)
    language_stopwords = _STOPWORDS.get(language, _STOPWORDS["en"])
    result = []
    for token in tokens:
        if not token.isalpha() or len(token) <= 2 or token in language_stopwords:
            continue
        if language == "en":
            result.append(_LEMMATIZER.lemmatize(token))
        else:
            result.append(_STEMMERS[language].stem(token))
    return result


def _split_sentences(text: str) -> list[SentenceInfo]:
    """Split text while retaining document and paragraph character positions."""
    result: list[SentenceInfo] = []
    paragraph_pattern = re.compile(r".+?(?:(?:\r?\n){2,}|\Z)", flags=re.S)
    paragraphs = list(paragraph_pattern.finditer(text))
    if not paragraphs:
        paragraphs = [re.match(r".*", text, flags=re.S)]

    for paragraph_match in paragraphs:
        paragraph_text = paragraph_match.group(0)
        paragraph_start = paragraph_match.start()
        paragraph_length = max(len(paragraph_text.strip()), 1)
        for sentence_match in re.finditer(r"[^.!?]+(?:[.!?]+|$)", paragraph_text, flags=re.S):
            sentence = re.sub(r"\s+", " ", sentence_match.group(0)).strip()
            if len(sentence) < 20:
                continue
            result.append(
                SentenceInfo(
                    text=sentence,
                    document_start=paragraph_start + sentence_match.start(),
                    paragraph_start=sentence_match.start(),
                    paragraph_length=paragraph_length,
                )
            )

    if not result and text.strip():
        result.append(SentenceInfo(text=text.strip(), document_start=0, paragraph_start=0, paragraph_length=max(len(text), 1)))
    return result


def collection_document_frequency(texts: list[tuple[str, str]]) -> dict[str, int]:
    """Return df(t) for the complete input collection.

    The argument contains (text, language) pairs. Each document contributes
    at most one occurrence to df(t), as required by the assignment formula.
    """
    frequencies: Counter[str] = Counter()
    for text, language in texts:
        frequencies.update(set(_tokens(text, language)))
    return dict(frequencies)


def _term_weights(
    document_tokens: list[str],
    collection_document_count: int,
    document_frequency: dict[str, int],
) -> dict[str, float]:
    tf_document = Counter(document_tokens)
    max_tf = max(tf_document.values(), default=1)
    total_documents = max(collection_document_count, 1)
    weights: dict[str, float] = {}
    for term, frequency in tf_document.items():
        df = max(document_frequency.get(term, 1), 1)
        weights[term] = 0.5 * (1.0 + frequency / max_tf) * math.log(total_documents / df)
    return weights


def _normalize_scores(scores: dict[object, float]) -> dict[object, float]:
    maximum = max(scores.values(), default=0.0)
    if maximum <= 0:
        return {key: 0.0 for key in scores}
    return {key: value / maximum for key, value in scores.items()}


def _pagerank(graph: dict[object, dict[object, float]], iterations: int = 30) -> dict[object, float]:
    if not graph:
        return {}
    nodes = list(graph)
    count = len(nodes)
    ranks = {node: 1.0 / count for node in nodes}
    damping = 0.85

    for _ in range(iterations):
        next_ranks = {node: (1.0 - damping) / count for node in nodes}
        for source, neighbours in graph.items():
            total_weight = sum(neighbours.values())
            if total_weight <= 0:
                share = damping * ranks[source] / count
                for node in nodes:
                    next_ranks[node] += share
                continue
            for target, edge_weight in neighbours.items():
                next_ranks[target] += damping * ranks[source] * edge_weight / total_weight
        ranks = next_ranks
    return ranks


def _sentence_textrank(sentence_tokens: list[list[str]]) -> dict[int, float]:
    graph: dict[int, dict[int, float]] = {index: {} for index in range(len(sentence_tokens))}
    token_sets = [set(tokens) for tokens in sentence_tokens]
    for left in range(len(token_sets)):
        for right in range(left + 1, len(token_sets)):
            union = token_sets[left] | token_sets[right]
            if not union:
                continue
            similarity = len(token_sets[left] & token_sets[right]) / len(union)
            if similarity > 0:
                graph[left][right] = similarity
                graph[right][left] = similarity
    return _pagerank(graph)


def _word_textrank(tokens: list[str], window: int = 2) -> dict[str, float]:
    graph: dict[str, dict[str, float]] = {token: {} for token in set(tokens)}
    for index, source in enumerate(tokens):
        for target in tokens[index + 1 : index + window + 1]:
            if source == target:
                continue
            graph[source][target] = graph[source].get(target, 0.0) + 1.0
            graph[target][source] = graph[target].get(source, 0.0) + 1.0
    return _pagerank(graph)


def summarize(
    text: str,
    language: str,
    sentence_count: int = 10,
    collection_document_count: int = 1,
    document_frequency: dict[str, int] | None = None,
    sentence_extraction_weight: float | None = None,
    textrank_weight: float | None = None,
) -> tuple[list[str], list[tuple[str, float]]]:
    """Build a summary using sentence extraction combined with weighted TextRank."""
    sentence_infos = _split_sentences(text)
    if not sentence_infos:
        return [], []

    if sentence_extraction_weight is None or textrank_weight is None:
        sentence_extraction_weight, textrank_weight = get_ranking_weights()

    document_frequency = document_frequency or collection_document_frequency([(text, language)])
    document_tokens = _tokens(text, language)
    term_weights = _term_weights(document_tokens, collection_document_count, document_frequency)
    document_length = max(len(text), 1)
    sentence_tokens_list = [_tokens(sentence.text, language) for sentence in sentence_infos]
    sentence_textrank_scores = _sentence_textrank(sentence_tokens_list)
    sentence_scores: list[tuple[int, float]] = []
    keyword_scores: Counter[str] = Counter()

    for index, sentence_info in enumerate(sentence_infos):
        sentence_tokens = sentence_tokens_list[index]
        tf_sentence = Counter(sentence_tokens)
        modified_tfidf_score = 0.0
        for term, frequency in tf_sentence.items():
            contribution = frequency * term_weights.get(term, 0.0)
            modified_tfidf_score += contribution
            keyword_scores[term] += contribution

        pos_document = 1.0 - (sentence_info.document_start / document_length)
        pos_paragraph = 1.0 - (sentence_info.paragraph_start / sentence_info.paragraph_length)
        sentence_score = max(pos_document, 0.0) * max(pos_paragraph, 0.0) * modified_tfidf_score
        sentence_scores.append((index, sentence_score))

    normalized_sentence_scores = _normalize_scores(dict(sentence_scores))
    normalized_sentence_textrank = _normalize_scores(sentence_textrank_scores)
    combined_sentence_scores = [
        (
            index,
            sentence_extraction_weight * normalized_sentence_scores.get(index, 0.0)
            + textrank_weight * normalized_sentence_textrank.get(index, 0.0),
        )
        for index, _ in sentence_scores
    ]

    selected_indexes = {
        index for index, _ in sorted(combined_sentence_scores, key=lambda item: item[1], reverse=True)[:sentence_count]
    }
    selected_sentences = [info.text for index, info in enumerate(sentence_infos) if index in selected_indexes]
    keyword_textrank_scores = _word_textrank(document_tokens)
    normalized_keyword_scores = _normalize_scores(dict(keyword_scores))
    normalized_keyword_textrank = _normalize_scores(keyword_textrank_scores)
    combined_keyword_scores = {
        term: sentence_extraction_weight * normalized_keyword_scores.get(term, 0.0)
        + textrank_weight * normalized_keyword_textrank.get(term, 0.0)
        for term in keyword_scores
    }
    keywords = sorted(combined_keyword_scores.items(), key=lambda item: item[1], reverse=True)[:20]
    return selected_sentences, [(term, float(score)) for term, score in keywords]
