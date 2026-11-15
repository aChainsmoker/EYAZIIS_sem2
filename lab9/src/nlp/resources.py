from functools import lru_cache

from src.errors import ResourceUnavailableError


@lru_cache(maxsize=2)
def language_tools(language: str):
    from nltk.corpus import stopwords
    from nltk.stem import SnowballStemmer, WordNetLemmatizer
    if language not in {"ru", "en"}:
        raise ValueError("Поддерживаются языки ru/en.")
    try:
        if language == "ru":
            words = set(stopwords.words("russian"))
            normalize = SnowballStemmer("russian").stem
        else:
            words = set(stopwords.words("english"))
            lemmatizer = WordNetLemmatizer()
            lemmatizer.lemmatize("documents")
            normalize = lemmatizer.lemmatize
    except LookupError as exc:
        raise ResourceUnavailableError(
            "Установите данные NLTK: python -m nltk.downloader stopwords wordnet punkt_tab"
        ) from exc
    return words, normalize
