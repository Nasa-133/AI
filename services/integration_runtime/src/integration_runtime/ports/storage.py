from pathlib import Path
from typing import Protocol

from .connector import ObjectRef


class ObjectStorage(Protocol):
    async def download_to(self, ref: ObjectRef, path: Path) -> None: ...
    async def upload(self, *, bucket: str, key: str, path: Path, content_type: str) -> None: ...
