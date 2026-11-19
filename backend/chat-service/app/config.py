from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://lego:lego_password@localhost:5432/chat_db"
    jwt_secret: str = "replace-with-a-long-random-secret"
    jwt_algorithm: str = "HS256"
    catalog_service_url: str = "http://localhost:8002"
    service_token: str = "replace-with-a-long-random-service-token"


settings = Settings()
