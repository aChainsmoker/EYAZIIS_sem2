import boto3
from botocore.exceptions import BotoCoreError, ClientError
from src.config import CONFIG
from src.errors import StorageUnavailableError

settings = CONFIG["s3"]
client = boto3.client("s3", endpoint_url=settings["endpoint"], aws_access_key_id=settings["access_key"], aws_secret_access_key=settings["secret_key"])
bucket = settings["bucket"]

def initialize():
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError as exc:
        if str(exc.response["Error"]["Code"]) not in {"404", "NoSuchBucket"}:
            raise
        client.create_bucket(Bucket=bucket)

def put(key, data):
    try:
        client.put_object(Bucket=bucket, Key=key, Body=data)
    except (BotoCoreError, ClientError) as exc:
        raise StorageUnavailableError("Не удалось сохранить оригинал в S3.") from exc


def get_bytes(key: str) -> bytes:
    try:
        response = client.get_object(Bucket=bucket, Key=key)
        body = response["Body"]
        try:
            return body.read()
        finally:
            body.close()
    except (BotoCoreError, ClientError, OSError) as exc:
        raise StorageUnavailableError("Не удалось получить оригинал из S3. Проверьте доступность хранилища.") from exc

def delete(key):
    try:
        client.delete_object(Bucket=bucket, Key=key)
    except (BotoCoreError, ClientError) as exc:
        raise StorageUnavailableError("Не удалось удалить оригинал из S3.") from exc

def url(key):
    return client.generate_presigned_url("get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=3600)
