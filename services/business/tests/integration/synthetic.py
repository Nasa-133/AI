"""Test yordamchisi: sintetik ERP CSV → canonical record (Integration mapping’ining nusxasi)."""

import csv
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
STATUS = {"tasdiqlangan": "confirmed", "qoralama": "draft", "bekor qilingan": "cancelled"}


def order_lines(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        return [{
            "source_id": r["Hujjat ID"], "source_revision": None, "document_number": r["Hujjat №"],
            "occurred_at": r["Sana"], "branch_code": r["Filial kodi"], "branch_name": r["Filial"],
            "product_code": r["Mahsulot kodi"], "product_name": r["Mahsulot"],
            "customer_code": r["Mijoz kodi"], "customer_name": r["Mijoz"] or None,
            "quantity": r["Miqdor"], "unit_price": r["Narx"], "gross_amount": r["Summa"],
            "discount_amount": r["Chegirma"], "discount_already_deducted": False,
            "vat_amount": r["QQS"], "amount_includes_vat": False, "currency": r["Valyuta"],
            "status": STATUS[r["Holat"]], "cost_amount": r["Tannarx"] or None,
        } for r in csv.DictReader(f)]


def returns(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        return [{
            "source_id": r["Qaytarish ID"], "source_revision": None,
            "original_order_source_id": r["Asl hujjat ID"] or None, "occurred_at": r["Sana"],
            "branch_code": r["Filial kodi"], "product_code": r["Mahsulot kodi"],
            "customer_code": r["Mijoz kodi"], "quantity": r["Miqdor"], "amount": r["Summa"],
            "vat_amount": r["QQS"], "amount_includes_vat": False, "currency": r["Valyuta"],
            "cost_amount": r["Tannarx"] or None, "status": STATUS[r["Holat"]],
        } for r in csv.DictReader(f)]


def jsonl(records: list[dict[str, Any]]) -> list[bytes]:
    return [json.dumps(r, ensure_ascii=False).encode() for r in records]
