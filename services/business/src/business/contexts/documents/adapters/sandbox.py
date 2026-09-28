"""Parserni alohida OS jarayonida timeout va xotira chegarasi bilan ishga tushirish (TZ 9.2, 18)."""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from .parsing import InvalidDocument

PARSE_TIMEOUT_SECONDS = 60
MEMORY_LIMIT_BYTES = 1024 * 1024 * 1024
_LIMIT = (
    "import resource,runpy,sys\n"
    f"try: resource.setrlimit(resource.RLIMIT_AS, ({MEMORY_LIMIT_BYTES}, {MEMORY_LIMIT_BYTES}))\n"
    "except (ValueError, OSError): pass\n"  # macOS RLIMIT_AS’ni qo‘llamaydi; Linux’da ishlaydi
    "sys.argv = sys.argv[1:]\n"
    "runpy.run_module('business.contexts.documents.adapters.parse_worker', run_name='__main__')\n"
)


class ParserTimeout(Exception):
    pass


async def parse_isolated(fmt: str, path: Path, *,
                         limit_seconds: float = PARSE_TIMEOUT_SECONDS) -> dict[str, Any]:
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-c", _LIMIT, "parse_worker", fmt, str(path),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=limit_seconds)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise ParserTimeout(f"Faylni o‘qish {int(limit_seconds)} soniyadan oshdi.") from None
    if proc.returncode != 0:
        raise InvalidDocument("Faylni o‘qishda parser yiqildi (fayl buzilgan bo‘lishi mumkin).")
    result: dict[str, Any] = json.loads(out)
    if not result["ok"]:
        raise InvalidDocument(result["error"])
    return result
