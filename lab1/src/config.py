import os
import tomli


def load_config() -> dict:
    secret_path = os.path.join(os.path.dirname(__file__), "..", "secrets", "secret.toml")
    if os.path.isfile(secret_path):
        with open(secret_path, "rb") as f:
            return tomli.load(f)
    return {}


_config = load_config()

try:
    _FALLBACK_DB_URL = _config["database"]["url"]
except (KeyError, TypeError):
    _FALLBACK_DB_URL = ""

try:
    _FALLBACK_MINIO = _config["minio"]
except (KeyError, TypeError):
    _FALLBACK_MINIO = {}


DB_URL = os.environ.get("DB_URL", _FALLBACK_DB_URL)
BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.environ.get(
    "DATA_DIR",
    os.path.abspath(os.path.normpath(os.path.join(BASE_DIR, "..", "data", "incoming"))),
)

MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", _FALLBACK_MINIO.get("endpoint", "localhost:9000"))
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", _FALLBACK_MINIO.get("access_key", ""))
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", _FALLBACK_MINIO.get("secret_key", ""))
MINIO_SECURE = os.environ.get("MINIO_SECURE", str(_FALLBACK_MINIO.get("secure", "false"))).lower() == "true"
MINIO_BUCKET = os.environ.get("MINIO_BUCKET", _FALLBACK_MINIO.get("bucket", "eyaziis-documents"))