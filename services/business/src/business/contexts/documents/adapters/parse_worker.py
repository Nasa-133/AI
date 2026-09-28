"""Alohida jarayon kirish nuqtasi: `python -m ...parse_worker <format> <yo‘l>` → stdout’ga JSON.

Asosiy worker bu jarayonni timeout bilan ishga tushiradi; yiqilish yoki osilib qolish asosiy
jarayonga ta’sir qilmaydi.
"""

import json
import sys
from pathlib import Path

from .parsing import PARSERS, InvalidDocument


def main() -> None:
    fmt, path = sys.argv[1], Path(sys.argv[2])
    try:
        result = {"ok": True, **PARSERS[fmt](path)}
    except InvalidDocument as exc:
        result = {"ok": False, "error": str(exc)}
    sys.stdout.write(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
