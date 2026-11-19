from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://lego:lego_password@localhost:5432/catalog_db"
    jwt_secret: str = "replace-with-a-long-random-secret"
    jwt_algorithm: str = "HS256"
    s3_endpoint_url: str = "http://localhost:4566"
    s3_bucket: str = "lego-marketplace-images"
    s3_region: str = "us-east-1"
    s3_access_key: str = "test"
    s3_secret_key: str = "test"
    max_image_size_bytes: int = 5 * 1024 * 1024


settings = Settings()
