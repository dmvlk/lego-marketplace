import boto3
from botocore.client import Config

from app.config import settings


client = boto3.client(
    "s3",
    endpoint_url=settings.s3_endpoint_url,
    region_name=settings.s3_region,
    aws_access_key_id=settings.s3_access_key,
    aws_secret_access_key=settings.s3_secret_key,
    config=Config(s3={"addressing_style": "path"}),
)


def ensure_bucket() -> None:
    try:
        client.head_bucket(Bucket=settings.s3_bucket)
    except client.exceptions.ClientError as error:
        code = error.response.get("Error", {}).get("Code")
        if code not in {"404", "NoSuchBucket", "NotFound"}:
            raise
        client.create_bucket(Bucket=settings.s3_bucket)


def upload_image(key: str, data: bytes, content_type: str) -> None:
    client.put_object(
        Bucket=settings.s3_bucket,
        Key=key,
        Body=data,
        ContentType=content_type,
    )


def get_image(key: str):
    return client.get_object(Bucket=settings.s3_bucket, Key=key)


def delete_image(key: str) -> None:
    client.delete_object(Bucket=settings.s3_bucket, Key=key)
