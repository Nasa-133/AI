from decimal import Decimal
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
    # Har agent uchun korxona bo‘yicha parallel vazifalar limiti (TZ 4); to‘lsa — navbat.
    agent_parallel_limit: int = Field(default=3, ge=1, le=20)
    # AI budjeti standartlari (TZ 19; korxona egasi Sozlamalarda o‘zgartiradi). USD.
    budget_monthly_limit: Decimal | None = Decimal("50")
    budget_daily_limit: Decimal | None = None
    budget_task_reservation: Decimal = Decimal("0.05")
    # Fon ishlari va saqlash muddatlari (TZ 17; mahsulot defaultlari, mijoz talabi bilan o‘zgaradi).
    maintenance_interval_seconds: int = Field(default=60, ge=5)
    # I03: import/sync shuncha vaqt siljimasa dashboardlar “eskirgan” deb belgilanadi.
    data_stale_after_seconds: int = Field(default=300, ge=1)
    retention_conversation_days: int = Field(default=90, ge=1)
    retention_draft_days: int = Field(default=90, ge=1)
    retention_audit_days: int = Field(default=365, ge=30)
