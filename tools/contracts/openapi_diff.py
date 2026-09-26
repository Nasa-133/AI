"""OpenAPI breaking-change tekshiruvchisi (TZ 13.11). Faqat stdlib.

    python openapi_diff.py BASELINE.json CURRENT.json

Breaking topilsa exit 1. Har topilma alohida qatorda: `BREAKING: ...` yoki `NON_BREAKING: ...`.

Qoidalar (klient nuqtai nazaridan):
  Operatsiyalar
    - path yoki operatsiya o‘chirilgan                       → BREAKING
    - avval bo‘lgan 2xx javob statusi o‘chirilgan            → BREAKING
    - yangi path/operatsiya/status                           → NON_BREAKING
  Parametrlar (in + name bo‘yicha)
    - parametr o‘chirilgan                                   → BREAKING
    - ixtiyoriy parametr majburiy bo‘lgan                    → BREAKING
    - yangi majburiy parametr                                → BREAKING
    - yangi ixtiyoriy parametr                               → NON_BREAKING
  Request body (so‘rov yo‘nalishi)
    - body avval yo‘q edi, endi majburiy                     → BREAKING
    - media type o‘chirilgan                                 → BREAKING
    - yangi majburiy maydon / ixtiyoriy maydon majburiy bo‘ldi → BREAKING
    - maydon o‘chirilgan, yangi ixtiyoriy maydon             → NON_BREAKING
    - enum qiymati o‘chirilgan                               → BREAKING (eski klient uni yuboradi)
    - enum qiymati qo‘shilgan                                → NON_BREAKING
  Javob (2xx, javob yo‘nalishi)
    - maydon o‘chirilgan yoki majburiy maydon ixtiyoriy bo‘ldi → BREAKING
    - yangi maydon                                           → NON_BREAKING
    - enum qiymati qo‘shilgan                                → BREAKING (qat’iy klient noma’lum
      qiymatni qabul qilmaydi; qo‘shish uchun yangi major versiya yoki kelishuv kerak)
    - enum qiymati o‘chirilgan                               → NON_BREAKING
  Turlar
    - so‘rovda tur kengaygan (masalan string → string|null)  → NON_BREAKING
    - javobda tur torayganda (string|null → string)          → NON_BREAKING
    - boshqa har qanday tur o‘zgarishi                       → BREAKING
  Qolgan farqlar (description, title va h.k.)                → NON_BREAKING
"""

import json
import sys
from dataclasses import dataclass, field
from typing import Any

Schema = dict[str, Any]
HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")
REQUEST = "request"
RESPONSE = "response"


@dataclass
class Report:
    breaking: list[str] = field(default_factory=list)
    non_breaking: list[str] = field(default_factory=list)

    def lines(self) -> list[str]:
        return [f"BREAKING: {m}" for m in self.breaking] + [
            f"NON_BREAKING: {m}" for m in self.non_breaking
        ]


class _Resolver:
    def __init__(self, spec: Schema) -> None:
        self.spec = spec

    def resolve(self, node: Any) -> tuple[Any, str | None]:
        """Lokal `$ref`ni ochadi. (tugun, ref nomi) qaytaradi."""
        ref_name = None
        seen: set[str] = set()
        while isinstance(node, dict) and "$ref" in node:
            ref = node["$ref"]
            if not isinstance(ref, str) or not ref.startswith("#/") or ref in seen:
                break
            seen.add(ref)
            ref_name = ref
            target: Any = self.spec
            for part in ref[2:].split("/"):
                target = target.get(part.replace("~1", "/").replace("~0", "~"), {})
            node = target
        return node, ref_name


def _types(schema: Any, resolver: _Resolver) -> frozenset[str]:
    schema, _ = resolver.resolve(schema)
    if not isinstance(schema, dict):
        return frozenset()
    found: set[str] = set()
    declared = schema.get("type")
    if isinstance(declared, str):
        found.add(declared)
    elif isinstance(declared, list):
        found.update(t for t in declared if isinstance(t, str))
    if schema.get("nullable") is True:
        found.add("null")
    for key in ("anyOf", "oneOf"):
        for member in schema.get(key, []):
            found |= _types(member, resolver)
    return frozenset(found)


def _unwrap_optional(schema: Any, resolver: _Resolver) -> Any:
    """`anyOf: [X, {type: null}]` → X (Pydantic Optional)."""
    schema, _ = resolver.resolve(schema)
    if isinstance(schema, dict):
        for key in ("anyOf", "oneOf"):
            members = schema.get(key)
            if isinstance(members, list):
                non_null = [m for m in members if _types(m, resolver) != frozenset({"null"})]
                if len(non_null) == 1:
                    return resolver.resolve(non_null[0])[0]
    return schema


class _Comparer:
    def __init__(self, base: Schema, cur: Schema) -> None:
        self.base = _Resolver(base)
        self.cur = _Resolver(cur)
        self.report = Report()
        self._seen: set[tuple[str, str, str]] = set()

    def schema(self, b: Any, c: Any, where: str, direction: str) -> None:
        b, b_ref = self.base.resolve(b)
        c, c_ref = self.cur.resolve(c)
        if b_ref and c_ref:
            key = (b_ref, c_ref, direction)
            if key in self._seen:
                return
            self._seen.add(key)
        if not isinstance(b, dict) or not isinstance(c, dict):
            return

        bt, ct = _types(b, self.base), _types(c, self.cur)
        if bt and ct and bt != ct:
            safe = ct > bt if direction == REQUEST else ct < bt
            target = self.report.non_breaking if safe else self.report.breaking
            target.append(f"{where}: tur {sorted(bt)} → {sorted(ct)} ({direction})")

        self._enum(b, c, where, direction)

        b_obj, c_obj = _unwrap_optional(b, self.base), _unwrap_optional(c, self.cur)
        if b_obj is not b or c_obj is not c:
            self.schema(b_obj, c_obj, where, direction)
            return

        self._properties(b, c, where, direction)
        if "items" in b and "items" in c:
            self.schema(b["items"], c["items"], f"{where}[]", direction)

    def _enum(self, b: Schema, c: Schema, where: str, direction: str) -> None:
        if "enum" not in b and "enum" not in c:
            return
        if "enum" not in c:
            # Cheklov olib tashlandi: so‘rovda xavfsiz, javobda yangi qiymatlar kelishi mumkin.
            target = self.report.non_breaking if direction == REQUEST else self.report.breaking
            target.append(f"{where}: enum cheklovi olib tashlandi ({direction})")
            return
        if "enum" not in b:
            target = self.report.breaking if direction == REQUEST else self.report.non_breaking
            target.append(f"{where}: enum cheklovi qo‘shildi ({direction})")
            return
        be, ce = set(map(json.dumps, b["enum"])), set(map(json.dumps, c["enum"]))
        removed, added = sorted(be - ce), sorted(ce - be)
        if direction == REQUEST:
            if removed:
                self.report.breaking.append(f"{where}: so‘rov enum qiymati o‘chirildi {removed}")
            if added:
                self.report.non_breaking.append(f"{where}: so‘rov enum qiymati qo‘shildi {added}")
        else:
            if added:
                self.report.breaking.append(f"{where}: javob enum qiymati qo‘shildi {added}")
            if removed:
                self.report.non_breaking.append(
                    f"{where}: javob enum qiymati o‘chirildi {removed}"
                )

    def _properties(self, b: Schema, c: Schema, where: str, direction: str) -> None:
        bp, cp = b.get("properties", {}), c.get("properties", {})
        if not bp and not cp:
            return
        br, cr = set(b.get("required", [])), set(c.get("required", []))
        for name in sorted(set(bp) - set(cp)):
            msg = f"{where}.{name}: maydon o‘chirildi ({direction})"
            target = self.report.breaking if direction == RESPONSE else self.report.non_breaking
            target.append(msg)
        for name in sorted(set(cp) - set(bp)):
            if direction == REQUEST and name in cr:
                self.report.breaking.append(f"{where}.{name}: yangi majburiy so‘rov maydoni")
            else:
                self.report.non_breaking.append(f"{where}.{name}: yangi maydon ({direction})")
        for name in sorted(set(bp) & set(cp)):
            if direction == REQUEST and name in cr and name not in br:
                self.report.breaking.append(f"{where}.{name}: so‘rov maydoni majburiy bo‘ldi")
            if direction == RESPONSE and name in br and name not in cr:
                self.report.breaking.append(f"{where}.{name}: javob maydoni endi majburiy emas")
            self.schema(bp[name], cp[name], f"{where}.{name}", direction)

    def parameters(self, b_op: Schema, c_op: Schema, where: str) -> None:
        def index(op: Schema, resolver: _Resolver) -> dict[tuple[str, str], Schema]:
            result = {}
            for raw in op.get("parameters", []):
                param, _ = resolver.resolve(raw)
                result[(param.get("in", ""), param.get("name", ""))] = param
            return result

        bps, cps = index(b_op, self.base), index(c_op, self.cur)
        for key in sorted(set(bps) - set(cps)):
            self.report.breaking.append(f"{where}: parametr o‘chirildi {key[0]}:{key[1]}")
        for key in sorted(set(cps) - set(bps)):
            if cps[key].get("required"):
                self.report.breaking.append(f"{where}: yangi majburiy parametr {key[0]}:{key[1]}")
            else:
                self.report.non_breaking.append(f"{where}: yangi parametr {key[0]}:{key[1]}")
        for key in sorted(set(bps) & set(cps)):
            label = f"{where} param {key[0]}:{key[1]}"
            if cps[key].get("required") and not bps[key].get("required"):
                self.report.breaking.append(f"{label}: majburiy bo‘ldi")
            self.schema(bps[key].get("schema"), cps[key].get("schema"), label, REQUEST)

    def request_body(self, b_op: Schema, c_op: Schema, where: str) -> None:
        b_body, _ = self.base.resolve(b_op.get("requestBody"))
        c_body, _ = self.cur.resolve(c_op.get("requestBody"))
        if not c_body:
            if b_body:
                self.report.non_breaking.append(f"{where}: request body olib tashlandi")
            return
        if not b_body:
            target = self.report.breaking if c_body.get("required") else self.report.non_breaking
            target.append(f"{where}: request body qo‘shildi")
            return
        if c_body.get("required") and not b_body.get("required"):
            self.report.breaking.append(f"{where}: request body majburiy bo‘ldi")
        b_content, c_content = b_body.get("content", {}), c_body.get("content", {})
        for media in sorted(set(b_content) - set(c_content)):
            self.report.breaking.append(f"{where}: request media type o‘chirildi {media}")
        for media in sorted(set(b_content) & set(c_content)):
            self.schema(b_content[media].get("schema"), c_content[media].get("schema"),
                        f"{where} body", REQUEST)

    def responses(self, b_op: Schema, c_op: Schema, where: str) -> None:
        b_resp, c_resp = b_op.get("responses", {}), c_op.get("responses", {})
        for status in sorted(set(b_resp) - set(c_resp)):
            target = self.report.breaking if status.startswith("2") else self.report.non_breaking
            target.append(f"{where}: {status} javobi o‘chirildi")
        for status in sorted(set(c_resp) - set(b_resp)):
            self.report.non_breaking.append(f"{where}: {status} javobi qo‘shildi")
        for status in sorted(set(b_resp) & set(c_resp)):
            if not status.startswith("2"):
                continue
            b_r, _ = self.base.resolve(b_resp[status])
            c_r, _ = self.cur.resolve(c_resp[status])
            b_content, c_content = b_r.get("content", {}), c_r.get("content", {})
            for media in sorted(set(b_content) - set(c_content)):
                self.report.breaking.append(
                    f"{where} {status}: javob media type o‘chirildi {media}"
                )
            for media in sorted(set(b_content) & set(c_content)):
                self.schema(b_content[media].get("schema"), c_content[media].get("schema"),
                            f"{where} {status}", RESPONSE)


def compare(baseline: Schema, current: Schema) -> Report:
    comparer = _Comparer(baseline, current)
    report = comparer.report
    b_paths, c_paths = baseline.get("paths", {}), current.get("paths", {})
    for path in sorted(set(b_paths) | set(c_paths)):
        b_item, c_item = b_paths.get(path, {}), c_paths.get(path, {})
        for method in HTTP_METHODS:
            b_op, c_op = b_item.get(method), c_item.get(method)
            where = f"{method.upper()} {path}"
            if b_op is not None and c_op is None:
                report.breaking.append(f"{where}: operatsiya o‘chirildi")
            elif b_op is None and c_op is not None:
                report.non_breaking.append(f"{where}: yangi operatsiya")
            elif b_op is not None and c_op is not None:
                comparer.parameters(b_op, c_op, where)
                comparer.request_body(b_op, c_op, where)
                comparer.responses(b_op, c_op, where)
    if baseline != current and not report.breaking and not report.non_breaking:
        report.non_breaking.append("boshqa farqlar (description, title, metadata va h.k.)")
    return report


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("Foydalanish: openapi_diff.py BASELINE.json CURRENT.json", file=sys.stderr)
        return 2
    with open(argv[1], encoding="utf-8") as fb, open(argv[2], encoding="utf-8") as fc:
        report = compare(json.load(fb), json.load(fc))
    for line in report.lines():
        print(line)
    return 1 if report.breaking else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
