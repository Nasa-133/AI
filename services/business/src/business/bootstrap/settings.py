from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BUSINESS_", env_file=".env", extra="ignore")

    database_url: str
    data_encryption_key: str = Field(min_length=44)
    session_ttl_hours: int = 12
    cookie_secure: bool = True
    environment: str = "local"
