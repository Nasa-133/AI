"""Connector’lar: faqat manbani o‘qiydi (normallashtirish Sync Engine’da)."""

import asyncio
import csv
import os
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

from ..ports.connector import (
    ConnectorManifest,
    DiscoveredSource,
    InvalidSource,
    RawRow,
    SourceHandle,
)
from ..ports.storage import ObjectStorage

SAMPLE_ROWS = 5
_ENTITIES = ("sales.order_line", "sales.return", "inventory.movement", "finance.receivable")


def _read_header_and_samples(path: Path, name: str, delimiter: str,
                             encoding: str) -> DiscoveredSource:
    try:
        with path.open(encoding=encoding, newline="") as f:
            reader = csv.reader(f, delimiter=delimiter)
            header = next(reader, None)
            if not header:
                raise InvalidSource(f"{name}: sarlavha satri yo‘q")
            samples: list[list[str | None]] = [
                list(row) for _, row in zip(range(SAMPLE_ROWS), reader, strict=False)
            ]
    except (UnicodeDecodeError, csv.Error) as exc:
        raise InvalidSource(f"{name}: CSV o‘qilmadi ({exc})") from exc
    return DiscoveredSource(name, [c.strip() for c in header], samples)


async def _iter_csv(path: Path, delimiter: str, encoding: str) -> AsyncIterator[tuple[int, RawRow]]:
    try:
        with path.open(encoding=encoding, newline="") as f:
            reader = csv.DictReader(f, delimiter=delimiter)
            if reader.fieldnames is not None:
                reader.fieldnames = [c.strip() for c in reader.fieldnames]
            for number, row in enumerate(reader, start=2):
                yield number, {k: v for k, v in row.items() if k is not None}
                if number % 5000 == 0:
                    await asyncio.sleep(0)  # event loop’ni band qilmaslik
    except (UnicodeDecodeError, csv.Error) as exc:
        raise InvalidSource(f"CSV o‘qilmadi: {exc}") from exc


class FileImportConnector:
    """Foydalanuvchi yuklagan CSV (UTF-8, sarlavhali). Fayl S3’dan vaqtinchalik diskka olinadi."""

    manifest = ConnectorManifest(
        connector_id="file_import", version="1.0.0", display_name="CSV fayl importi",
        supported_entities=_ENTITIES, capabilities=("full-sync",), is_demo=False,
        requires_object_ref=True,
    )

    def __init__(self, storage: ObjectStorage, work_dir: Path | None = None) -> None:
        self._storage = storage
        self._work_dir = work_dir

    async def _local_copy(self, source: SourceHandle) -> Path:
        if source.object_ref is None:
            raise InvalidSource("Fayl ko‘rsatilmagan")
        fd, name = tempfile.mkstemp(suffix=".csv", dir=self._work_dir)
        os.close(fd)
        path = Path(name)
        await self._storage.download_to(source.object_ref, path)
        return path

    async def discover_schema(self, source: SourceHandle) -> list[DiscoveredSource]:
        path = await self._local_copy(source)
        try:
            name = Path(source.object_ref.key).name if source.object_ref else "fayl"
            return [_read_header_and_samples(path, name, source.config.delimiter,
                                             source.config.encoding)]
        finally:
            path.unlink(missing_ok=True)

    async def read_rows(self, source: SourceHandle,
                        entity: str) -> AsyncIterator[tuple[int, RawRow]]:
        path = await self._local_copy(source)
        try:
            async for item in _iter_csv(path, source.config.delimiter, source.config.encoding):
                yield item
        finally:
            path.unlink(missing_ok=True)


_DEMO_FILES = {
    "sales.order_line": "sotuvlar.csv",
    "sales.return": "qaytarishlar.csv",
    "inventory.movement": "ombor_harakatlari.csv",
    "finance.receivable": "debitorlik.csv",
}


class DemoErpConnector:
    """DEMO: sintetik ERP eksporti (fixtures/synthetic/demo). Haqiqiy ERP ulanishi EMAS."""

    manifest = ConnectorManifest(
        connector_id="demo_erp", version="1.0.0", display_name="Demo ERP (sintetik ma’lumot)",
        supported_entities=_ENTITIES, capabilities=("full-sync",), is_demo=True,
        requires_object_ref=False,
    )

    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir

    async def discover_schema(self, source: SourceHandle) -> list[DiscoveredSource]:
        found = []
        for name in _DEMO_FILES.values():
            path = self._dir / name
            if not path.exists():
                raise InvalidSource(f"Demo ma’lumot topilmadi: {path}")
            found.append(_read_header_and_samples(path, name, ",", "utf-8"))
        return found

    async def read_rows(self, source: SourceHandle,
                        entity: str) -> AsyncIterator[tuple[int, RawRow]]:
        path = self._dir / _DEMO_FILES[entity]
        async for item in _iter_csv(path, ",", "utf-8"):
            yield item
