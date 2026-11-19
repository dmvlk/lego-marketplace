from decimal import Decimal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://lego:lego_password@localhost:5432/payment_db"
    jwt_secret: str = "replace-with-a-long-random-secret"
    jwt_algorithm: str = "HS256"
    deals_service_url: str = "http://localhost:8003"
    service_token: str = "replace-with-a-long-random-service-token"
    payment_webhook_secret: str = "replace-with-a-long-random-payment-webhook-secret"
    platform_fee_percent: Decimal = Field(default=Decimal("5"), ge=0, lt=100)
    payment_currency: str = Field(default="RUB", min_length=3, max_length=3)


settings = Settings()
