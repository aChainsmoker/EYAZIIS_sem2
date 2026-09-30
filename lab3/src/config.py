import json
import os


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.abspath(os.environ.get("DATA_DIR", os.path.join(BASE_DIR, "data", "input")))

DB_URL = os.environ.get(
    "DB_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5454/eyaziis_sem2_lab3",
)

MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", os.environ.get("MINIO_USER", "minioadmin"))
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", os.environ.get("MINIO_PASSWORD", "minioadmin"))
MINIO_SECURE = os.environ.get("MINIO_SECURE", "false").lower() == "true"
MINIO_BUCKET = os.environ.get("MINIO_BUCKET", "eyaziis-lab3")

SUMMARY_SENTENCE_COUNT = int(os.environ.get("SUMMARY_SENTENCE_COUNT", "10"))
DEFAULT_SENTENCE_EXTRACTION_WEIGHT = 0.7
DEFAULT_TEXTRANK_WEIGHT = 0.3
RANKING_CONFIG_PATH = os.path.join(BASE_DIR, "data", "ranking_config.json")
CLEANER_ENABLED = os.environ.get("CLEANER_ENABLED", "true").lower() == "true"
CLEANER_MODEL_NAME = os.environ.get("CLEANER_MODEL_NAME", "Qwen/Qwen2.5-1.5B-Instruct")
CLEANER_MAX_INPUT_TOKENS = int(os.environ.get("CLEANER_MAX_INPUT_TOKENS", "4096"))
CLEANER_MAX_NEW_TOKENS = int(os.environ.get("CLEANER_MAX_NEW_TOKENS", "2048"))


def get_ranking_weights() -> tuple[float, float]:
    try:
        with open(RANKING_CONFIG_PATH, encoding="utf-8") as config_file:
            config = json.load(config_file)
        sentence_weight = float(config["sentence_extraction_weight"])
        textrank_weight = float(config["textrank_weight"])
        if abs(sentence_weight + textrank_weight - 1.0) > 1e-6:
            raise ValueError("ranking weights must sum to 1")
        return sentence_weight, textrank_weight
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return DEFAULT_SENTENCE_EXTRACTION_WEIGHT, DEFAULT_TEXTRANK_WEIGHT


def save_ranking_weights(sentence_weight: float, textrank_weight: float) -> None:
    if not 0 <= sentence_weight <= 1 or not 0 <= textrank_weight <= 1:
        raise ValueError("ranking weights must be between 0 and 1")
    os.makedirs(os.path.dirname(RANKING_CONFIG_PATH), exist_ok=True)
    with open(RANKING_CONFIG_PATH, "w", encoding="utf-8") as config_file:
        json.dump(
            {
                "sentence_extraction_weight": sentence_weight,
                "textrank_weight": textrank_weight,
            },
            config_file,
            indent=2,
        )
