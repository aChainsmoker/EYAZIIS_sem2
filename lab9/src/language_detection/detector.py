import json
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def _profiles() -> dict[str, dict[str, float]]:
    with Path(__file__).with_name("profiles.json").open(encoding="utf-8") as stream:
        profiles = json.load(stream)
    normalized = {}
    for language in ("ru", "en"):
        weights = profiles[language]
        total = sum(weights.values())
        normalized[language] = {word: weight / total for word, weight in weights.items()}
    return normalized


def detect_language(text: str) -> str:
    counts = Counter(re.findall(r"[^\W\d_]+", text.casefold()))
    scores = {
        language: sum(profile.get(word, 0.0) * count for word, count in counts.items())
        for language, profile in _profiles().items()
    }
    if scores["ru"] == scores["en"]:
        return "unknown"
    return max(scores, key=scores.get)
