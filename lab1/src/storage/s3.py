import hashlib
import logging
import os
import time

import boto3
from botocore.exceptions import ClientError

from src.config import (
    MINIO_ENDPOINT,
    MINIO_ACCESS_KEY,
    MINIO_SECRET_KEY,
    MINIO_SECURE,
    MINIO_BUCKET,
)

logger = logging.getLogger(__name__)

_client = None
_bucket_ready = False


def _get_client():
    global _client, _bucket_ready
    if _client is None:
        scheme = "https" if MINIO_SECURE else "http"
        _client = boto3.client(
            "s3",
            endpoint_url=f"{scheme}://{MINIO_ENDPOINT}",
            aws_access_key_id=MINIO_ACCESS_KEY,
            aws_secret_access_key=MINIO_SECRET_KEY,
        )
    if not _bucket_ready:
        try:
            _client.head_bucket(Bucket=MINIO_BUCKET)
        except ClientError:
            _client.create_bucket(Bucket=MINIO_BUCKET)
        _bucket_ready = True
    return _client


def wait_ready(timeout: float = 60.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            _get_client().list_buckets()
            return
        except Exception as e:
            logger.warning(f"MinIO not ready yet: {e}")
            time.sleep(1.0)
    raise RuntimeError(f"MinIO is not reachable after {timeout}s at {MINIO_ENDPOINT}")


def object_key(file_path: str) -> str:
    normalized = os.path.abspath(os.path.normpath(file_path))
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"docs/{digest}.txt"


def original_key(file_path: str) -> str:
    normalized = os.path.abspath(os.path.normpath(file_path))
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    ext = os.path.splitext(normalized)[1].lower() or ".txt"
    return f"originals/{digest}{ext}"


def _content_type(key: str) -> str:
    ext = os.path.splitext(key)[1].lower()
    content_types = {
        ".txt": "text/plain",
        ".pdf": "application/pdf",
        ".rtf": "text/rtf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    return content_types.get(ext, "application/octet-stream")


def put_text(key: str, text: str):
    _get_client().put_object(Bucket=MINIO_BUCKET, Key=key, Body=text.encode("utf-8"))


def put_bytes(key: str, data: bytes):
    _get_client().put_object(Bucket=MINIO_BUCKET, Key=key, Body=data, ContentType=_content_type(key))


def get_text(key: str) -> str:
    response = _get_client().get_object(Bucket=MINIO_BUCKET, Key=key)
    return response["Body"].read().decode("utf-8")


def delete_object(key: str):
    try:
        _get_client().delete_object(Bucket=MINIO_BUCKET, Key=key)
    except ClientError as e:
        logger.warning(f"Cannot delete S3 object {key}: {e}")


def presigned_url(key: str, expires_in: int = 3600) -> str:
    return _get_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": MINIO_BUCKET, "Key": key},
        ExpiresIn=expires_in,
    )