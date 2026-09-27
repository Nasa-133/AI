from typing import Literal

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
    openai_api_key: str = ""
    # Model nomlari kodga tikilmaydi (TZ 10): deployment konfiguratsiyasidan.
    openai_model_main: str = ""
    openai_model_fast: str = ""
    max_tool_calls: int = 20
    lease_seconds: int = 60
    runner_concurrency: int = 4
