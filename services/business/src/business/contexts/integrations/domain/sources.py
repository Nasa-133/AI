"""Data source proyeksiyasi (Core tomoni): holatlar va yuklash qoidalari (TZ 9.1, 16)."""

import re
from enum import StrEnum

from business.kernel.errors import BusinessError, ValidationFailed

MAX_DATASET_IMPORT_BYTES = 500 * 1024 * 1024
MAX_DOCUMENT_BYTES = 25 * 1024 * 1024
# connector_id → fayl talab qiladimi
CONNECTORS = {"file_import": True, "demo_erp": False, "erp_api": False, "crm_api": False}
# Tashqi tizimdan o‘zi o‘qiladigan connector’lar: davriy avtomatik sinxron (fon ishi).
AUTO_SYNC_CONNECTORS = ("erp_api", "crm_api")


class SourceStatus(StrEnum):
    DISCOVERING = "discovering"
    AWAITING_MAPPING = "awaiting_mapping"
    CONFIGURING = "configuring"
    READY = "ready"
    SYNCING = "syncing"
    SYNCED = "synced"
    FAILED = "failed"


class UnsupportedFile(BusinessError):
    code = "UNSUPPORTED_MEDIA_TYPE"


class SourceNotReady(BusinessError):
    code = "SOURCE_NOT_READY"


class AlreadyConnected(BusinessError):
    """Bitta bazani ikki marta ulash mumkin emas — raqamlar ikki marta sanalardi."""

    code = "ALREADY_CONNECTED"


class InvalidSource(ValidationFailed):
    pass


_SAFE_NAME = re.compile(r"[^\w.\- ]", re.UNICODE)


def check_upload(filename: str, purpose: str) -> tuple[str, int]:
    """Fayl nomi xavfsiz ko‘rinishga keltiriladi; maqsadga mos kengaytma va limit qaytadi."""
    name = _SAFE_NAME.sub("_", filename.strip().split("/")[-1].split("\\")[-1])[:200] or "fayl"
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if purpose == "dataset_import":
        if ext == "xlsx":
            raise UnsupportedFile("XLSX import hali qo‘llanmaydi (P1). Faylni CSV (UTF-8) "
                                  "sifatida saqlab yuklang.")
        if ext != "csv":
            raise UnsupportedFile("Analitik import uchun CSV fayl yuklang.")
        return name, MAX_DATASET_IMPORT_BYTES
    if purpose == "document":
        if ext not in {"pdf", "docx", "txt", "md"}:
            raise UnsupportedFile("Hujjat uchun PDF, DOCX, TXT yoki MD yuklang.")
        return name, MAX_DOCUMENT_BYTES
    raise InvalidSource("purpose: document yoki dataset_import.")


def requires_file(connector_id: str) -> bool:
    if connector_id not in CONNECTORS:
        raise InvalidSource(f"Noma’lum connector: {connector_id}")
    return CONNECTORS[connector_id]
