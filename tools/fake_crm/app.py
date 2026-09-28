"""Soxta CRM REST API — savdo voronkasi (bitimlar) uchun, sintetik ma’lumot.

Ishga tushirish (repo ildizidan):
    make fake-crm                       # yoki make stack (ERP bilan birga)
    cd services/integration_runtime && uv run python ../../tools/fake_crm/app.py --port 8071

Shartnoma soxta ERP bilan bir xil (docs/INTEGRATION_GUIDE.md, 4.2): Bearer kalit, `data` +
`next_cursor`, izchil `as_of`. Resurs: GET /api/v1/deals. Kalit: fake-crm-dev-key.
"""

import argparse
import os
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:  # skript sifatida ishga tushirilganda
    sys.path.insert(0, str(TOOLS))

from fake_erp.app import create_rest_app  # noqa: E402

from fake_crm.crm import RESOURCES, CrmData  # noqa: E402

DEMO_DIR = TOOLS.parent / "fixtures/synthetic/demo"


def create_app(*, data: CrmData | None = None, api_key: str | None = None,
               clock: Callable[[], datetime] | None = None, fail_rate: float = 0.0) -> FastAPI:
    crm = data or CrmData.load(DEMO_DIR)
    return create_rest_app(
        title="Soxta CRM (demo)", system="CRM", resources=RESOURCES, records=crm.records,
        api_key=api_key or os.environ.get("FAKE_CRM_API_KEY", "fake-crm-dev-key"),
        clock=clock, fail_rate=fail_rate)


def main() -> None:
    parser = argparse.ArgumentParser(description="Soxta CRM REST API (demo)")
    parser.add_argument("--port", type=int, default=int(os.environ.get("FAKE_CRM_PORT", "8071")))
    parser.add_argument("--fail-rate", type=float,
                        default=float(os.environ.get("FAKE_CRM_FAIL_RATE", "0")))
    args = parser.parse_args()
    uvicorn.run(create_app(fail_rate=args.fail_rate), host="127.0.0.1", port=args.port,
                log_level="info")


if __name__ == "__main__":
    main()
