from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO = Path(__file__).resolve().parents[5]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="INTEGRATION_", env_file=".env", extra="ignore")

    environment: str = "local"
    # Credential’lar faqat muhitdan (.env); kodda standart parol yo‘q.
    database_url: str
    amqp_url: str
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str
    s3_secret_key: str
    s3_region: str = "us-east-1"
    canonical_bucket: str = "abo-integration"
    # DEMO connector ma’lumotlari (sintetik). Productionda demo_erp o‘chiq bo‘ladi.
    demo_data_dir: Path = _REPO / "fixtures/synthetic/demo"
    enable_demo_connector: bool = True
    # ERP REST API connector (`erp_api`). URL bo‘sh bo‘lsa connector yoqilmaydi.
    # Lokal/demo: tools/fake_erp (make fake-erp) — http://localhost:8070.
    erp_api_url: str = ""
    erp_api_key: SecretStr = SecretStr("")
    erp_api_page_size: int = 500
    worker_id: str = "integration-worker"


class HttpSettings(BaseSettings):
    """Ichki health API’si uchun: credential talab qilmaydi."""

    model_config = SettingsConfigDict(env_prefix="INTEGRATION_", env_file=".env", extra="ignore")

    environment: str = "local"
