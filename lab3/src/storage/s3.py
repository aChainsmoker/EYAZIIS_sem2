import hashlib
import logging
import os
import time

import boto3
from botocore.exceptions import ClientError

from src.config import MINIO_ACCESS_KEY, MINIO_BUCKET, MINIO_ENDPOINT, MINIO_SECRET_KEY, MINIO_SECURE

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


def wait_ready(timeout: float = 120) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            _get_client().list_buckets()
            return
        except Exception as exc:
            logger.warning("MinIO is not ready: %s", exc)
            time.sleep(1)
    raise RuntimeError(f"MinIO is unavailable at {MINIO_ENDPOINT}")


def _digest(path: str) -> str:
    return hashlib.sha256(os.path.abspath(os.path.normpath(path)).encode()).hexdigest()


def original_key(path: str) -> str:
    return f"originals/{_digest(path)}{os.path.splitext(path)[1].lower()}"


def summary_key(path: str) -> str:
    return f"summaries/{_digest(path)}.txt"


def summary_pdf_key(path: str) -> str:
    return f"summaries/{_digest(path)}.pdf"


def put_bytes(key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
    _get_client().put_object(Bucket=MINIO_BUCKET, Key=key, Body=data, ContentType=content_type)


def put_text(key: str, text: str) -> None:
    put_bytes(key, text.encode("utf-8"), "text/plain; charset=utf-8")


def get_text(key: str) -> str:
    response = _get_client().get_object(Bucket=MINIO_BUCKET, Key=key)
    return response["Body"].read().decode("utf-8")


def delete_object(key: str) -> None:
    try:
        _get_client().delete_object(Bucket=MINIO_BUCKET, Key=key)
    except ClientError as exc:
        logger.warning("Cannot delete S3 object %s: %s", key, exc)


def presigned_url(key: str, expires_in: int = 3600) -> str:
    return _get_client().generate_presigned_url(
        "get_object", Params={"Bucket": MINIO_BUCKET, "Key": key}, ExpiresIn=expires_in
    )
