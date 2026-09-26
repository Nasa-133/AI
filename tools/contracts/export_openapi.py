"""Servisning OpenAPI spetsifikatsiyasini deterministik JSON sifatida chiqaradi.

Servisning o‘z virtual muhitida ishga tushiriladi (DB kerak emas):

    cd services/business && uv run python ../../tools/contracts/export_openapi.py business \
        > ../../contracts/http/business.openapi.json
"""

import json
import sys
from typing import Any

DUMMY_DATABASE_URL = "postgresql+asyncpg://x:x@localhost:1/x"


def build_openapi(service: str) -> dict[str, Any]:
    if service == "business":
        from business.bootstrap.app import create_app
        from business.bootstrap.settings import Settings
        from cryptography.fernet import Fernet

        settings = Settings(
            database_url=DUMMY_DATABASE_URL,
            data_encryption_key=Fernet.generate_key().decode(),
            cookie_secure=True,
            environment="contract",
        )
        spec: dict[str, Any] = create_app(settings).openapi()
        return spec
    if service == "ai_runtime":
        from ai_runtime.bootstrap.app import create_app as create_ai_app

        return create_ai_app().openapi()
    if service == "integration_runtime":
        from integration_runtime.bootstrap.app import create_app as create_int_app

        return create_int_app().openapi()
    raise SystemExit(f"Noma’lum servis: {service}")


def render(spec: dict[str, Any]) -> str:
    return json.dumps(spec, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Foydalanish: export_openapi.py <business|ai_runtime|integration_runtime>",
              file=sys.stderr)
        return 2
    sys.stdout.write(render(build_openapi(argv[1])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
