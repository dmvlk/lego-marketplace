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
