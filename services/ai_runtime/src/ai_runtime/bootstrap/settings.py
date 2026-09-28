from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_", env_file=".env", extra="ignore")

    environment: str = "local"
    database_url: str = "postgresql+asyncpg://ai_app:ai_app_dev@localhost:55432/ai_runtime"
    migrations_database_url: str = (
        "postgresql+asyncpg://ai_owner:ai_owner_dev@localhost:55432/ai_runtime"
    )
    amqp_url: str = "amqp://abo:abo_dev@localhost:5672/"
    business_tools_url: str = "http://localhost:8000"
    business_tools_token: str = ""
    model_provider: Literal["fake", "openai"] = "fake"
    # TZ 10 nomlari (OPENAI_*) va servis prefiksli nomlar (AI_OPENAI_*) ikkalasi ham qabul qilinadi.
    openai_api_key: str = Field(
        default="", validation_alias=AliasChoices("OPENAI_API_KEY", "AI_OPENAI_API_KEY"))
    # Model nomlari kodga tikilmaydi (TZ 10): deployment konfiguratsiyasidan.
    openai_model_main: str = Field(
        default="", validation_alias=AliasChoices("OPENAI_MODEL_MAIN", "AI_OPENAI_MODEL_MAIN"))
    openai_model_fast: str = Field(
        default="", validation_alias=AliasChoices("OPENAI_MODEL_FAST", "AI_OPENAI_MODEL_FAST"))
    # Embedding: `hash` — lokal deterministik (kalitsiz), `openai` — OPENAI_MODEL_EMBEDDING.
    embedding_provider: Literal["hash", "openai"] = "hash"
    openai_model_embedding: str = Field(
        default="", validation_alias=AliasChoices("OPENAI_EMBEDDING_MODEL",
                                                  "OPENAI_MODEL_EMBEDDING",
                                                  "AI_OPENAI_MODEL_EMBEDDING"))
    embedding_dimensions: int | None = None
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "us-east-1"
    vectors_bucket: str = "abo-ai"
    max_tool_calls: int = 20
    lease_seconds: int = 60
    runner_concurrency: int = 4
