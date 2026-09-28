from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BUSINESS_", env_file=".env", extra="ignore")

    database_url: str
    data_encryption_key: str = Field(min_length=44)
    session_ttl_hours: int = 12
    cookie_secure: bool = True
    environment: str = "local"
    # Bo‘sh bo‘lsa rate limit o‘chiq (faqat testlar uchun).
    redis_url: str = ""
    amqp_url: str = "amqp://abo:abo_dev@localhost:5672/"
    web_base_url: str = "http://localhost:3000"
    # `log` — faqat lokal: havola logga yoziladi. Production email adapteri keyin qo‘shiladi.
    notifier: Literal["log", "disabled"] = "disabled"
    # AI Runtime → Tool API servis tokeni va capability imzo kaliti (secret manager’dan).
    tools_service_token: str = Field(min_length=32)
    capability_signing_key: str = Field(min_length=32)
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "us-east-1"
    uploads_bucket: str = "abo-business"
    # AI Runtime ichki API’si (query embedding). Bo‘sh bo‘lsa qidiruv faqat matnli.
    ai_runtime_url: str = ""
