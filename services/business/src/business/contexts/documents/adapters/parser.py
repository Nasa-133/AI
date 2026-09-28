"""Parser porti: skaner + alohida jarayondagi parse; adapter xatolari DocumentUnreadable’ga."""

from pathlib import Path
from typing import Any

from ..ports.store import DocumentUnreadable
from . import scanner
from .parsing import InvalidDocument
from .sandbox import ParserTimeout, parse_isolated


class IsolatedParser:
    def detect_format(self, filename: str) -> str:
        try:
            return scanner.detect_format(filename)
        except InvalidDocument as exc:
            raise DocumentUnreadable(str(exc)) from exc

    def scan(self, path: Path, fmt: str) -> None:
        try:
            scanner.scan(path, fmt)
        except InvalidDocument as exc:
            raise DocumentUnreadable(str(exc)) from exc

    async def parse(self, fmt: str, path: Path) -> dict[str, Any]:
        try:
            return await parse_isolated(fmt, path)
        except (InvalidDocument, ParserTimeout) as exc:
            raise DocumentUnreadable(str(exc)) from exc
