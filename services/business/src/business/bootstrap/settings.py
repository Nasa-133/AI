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
