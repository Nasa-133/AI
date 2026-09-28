"""Pilot yuklama testi (TZ 19): 20 faol foydalanuvchi, 5 parallel analitik vazifa, 1 mln tranzaksiya.

O‘lchanadi (P50/P95/max) va TZ 19 maqsadlari bilan solishtiriladi:
  - oddiy API task qabul qilish          P95 ≤ 1 s
  - tayyor snapshotdagi KPI query         P95 ≤ 3 s
  - backend eventidan UI (SSE) holatiga   P95 ≤ 2 s
  - oddiy AI analitik javob               P95 ≤ 30 s (provayder rejimi hisobotda)
  - 10 MB matnli DOCX indekslash          ≤ 120 s
Natija: docs/reports/load-<sana>.{json,md}. scripts/load.sh ishga tushiradi.
"""

import argparse
import asyncio
import json
import os
import random
import statistics
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pyotp

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))
from run_eval import MONTHS, Api, import_csv, register, until  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
TARGETS = {"task_accept": 1.0, "kpi_query": 3.0, "event_to_client": 2.0, "ai_answer": 30.0,
           "docx_10mb_index": 120.0}
LABELS = {"task_accept": "Task qabul qilish (POST xabar)", "kpi_query": "KPI query (1 mln satr)",
          "event_to_client": "Backend eventi → mijoz (SSE)", "ai_answer": "AI javobi (to‘liq)",
          "docx_10mb_index": "10 MB DOCX indekslash", "office": "Ofis holati (GET /office)",
          "dashboards": "Dashboardlar ro‘yxati",
          "ingest_1m": "1 mln satr: yuklashdan so‘rovga tayyor bo‘lguncha"}


@dataclass
class Metrics:
    samples: dict[str, list[float]] = field(default_factory=dict)
    errors: dict[str, int] = field(default_factory=dict)

    def add(self, name: str, seconds: float) -> None:
        self.samples.setdefault(name, []).append(seconds)

    def error(self, name: str) -> None:
        self.errors[name] = self.errors.get(name, 0) + 1


def pct(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, round(p / 100 * len(ordered)) - 1))]


async def invite_user(owner: Api, log: Path) -> Api:
    email = f"load-{uuid4().hex[:8]}@demo.uz"
    (await owner.post("/api/v1/invitations", json={"email": email, "role": "analyst"})
     ).raise_for_status()

    async def token() -> str | None:
        for line in reversed(log.read_text(errors="ignore").splitlines()):
            if email in line and "token=" in line:
                return line.rsplit("token=", 1)[1].strip()
        return None

    t = await until(token, "taklif havolasi", 10)
    c = httpx.AsyncClient(timeout=120)
    user = Api(owner.base, c)
    (await c.post(f"{owner.base}/api/v1/invitations/accept", json={
        "token": t, "password": "correct-horse-battery"})).raise_for_status()
    secret = (await user.post("/api/v1/auth/mfa/enroll")).json()["secret"]
    (await user.post("/api/v1/auth/mfa/verify", json={"code": pyotp.TOTP(secret).now()})
     ).raise_for_status()
    return user


async def browse_loop(user: Api, m: Metrics, stop: float) -> None:
    """Oddiy foydalanuvchi: KPI so‘rovlari, ofis va dashboardlar (LLM chaqirilmaydi)."""
    rnd = random.Random(id(user))
    while time.monotonic() < stop:
        month = rnd.choice(MONTHS)
        y, mo = map(int, month.split("-"))
        dims = rnd.choice([[], ["branch"], ["product"], ["month"]])
        body = {"metric_ids": rnd.sample(["net_sales", "gross_profit", "gross_margin",
                                          "discounts", "returns"], 2),
                "date_range": {"from": f"{month}-01", "to": f"{month}-28"} if dims != ["month"]
                else {"from": "2025-09-01", "to": "2026-08-31"},
                "dimensions": dims, "currency": "UZS", "limit": 50}
        for name, call in [("kpi_query",
                            lambda body=body: user.post("/api/v1/analytics/queries", json=body)),
                           ("office", lambda: user.get("/api/v1/office")),
                           ("dashboards", lambda: user.get("/api/v1/dashboards"))]:
            t0 = time.monotonic()
            try:
                r = await call()
                r.raise_for_status()
                m.add(name, time.monotonic() - t0)
            except Exception:
                m.error(name)
        await asyncio.sleep(rnd.uniform(0.5, 1.5))


async def task_loop(user: Api, m: Metrics, stop: float, agent: str) -> None:
    """Analitik vazifa: qabul vaqti, SSE eventlarining kechikishi va to‘liq javob vaqti."""
    conv = (await user.post("/api/v1/conversations", json={"title": "Yuklama"})).json()["id"]
    rnd = random.Random(agent)
    while time.monotonic() < stop:
        month = rnd.choice(MONTHS)
        y, mo = map(int, month.split("-"))
        t0 = time.monotonic()
        try:
            r = await user.post(f"/api/v1/conversations/{conv}/messages", headers={
                "Idempotency-Key": str(uuid4())}, json={
                "content": f"{agent}, {y}-yil {mo}-oy sof savdosi qancha?"})
            r.raise_for_status()
        except Exception:
            m.error("task_accept")
            continue
        m.add("task_accept", time.monotonic() - t0)
        task = r.json()["task_id"]
        try:
            async with user.c.stream("GET", f"{user.base}/api/v1/tasks/{task}/events",
                                     timeout=120) as stream:
                event = None
                async for line in stream.aiter_lines():
                    if line.startswith("event: "):
                        event = line.removeprefix("event: ")
                    elif line.startswith("data: "):
                        payload = json.loads(line.removeprefix("data: "))
                        created = datetime.fromisoformat(payload["created_at"])
                        m.add("event_to_client",
                              max(0.0, (datetime.now(UTC) - created).total_seconds()))
                        if event == "task.completed":
                            m.add("ai_answer", time.monotonic() - t0)
                            if payload["status"] == "failed":
                                m.error("ai_answer")
                            break
        except Exception:
            m.error("ai_answer")


def make_big_docx(path: Path, megabytes: int = 10) -> Path:
    """Tabiiy matnga yaqin siqilish (katta lug‘at) bilan ~`megabytes` MB DOCX.

    Kam so‘zli takror matn juda yaxshi siqiladi va “10 MB” fayl ichida yuz megabaytlab matn
    bo‘lib qoladi — bu real hujjat emas. Shuning uchun lug‘at katta, fayl bir marta saqlanadi.
    """
    import docx

    rnd = random.Random(1)
    letters = "abdefghijklmnopqrstuvxyzoʻgʻshch"
    vocab = ["".join(rnd.choice(letters) for _ in range(rnd.randint(3, 11))) for _ in range(20000)]
    vocab += "shartnoma to‘lov muddat tovar yetkazib kafolat sifat nizom band tomonlar".split()

    def build(paragraphs: int) -> None:
        d = docx.Document()
        for i in range(paragraphs):
            if i % 20 == 0:
                d.add_heading(f"{i // 20 + 1}. Bo‘lim", level=2)
            d.add_paragraph(" ".join(rnd.choice(vocab) for _ in range(70)) + ".")
        d.save(str(path))

    paragraphs = 2000
    build(paragraphs)  # o‘lchov: paragraf boshiga bayt
    per_paragraph = path.stat().st_size / paragraphs
    build(int(megabytes * 1024 * 1024 / per_paragraph))
    return path


async def docx_index(owner: Api, m: Metrics, tmp: Path) -> float:
    """10 MB DOCX: hajm matndan (rasm emas) — parse + bo‘lim + parcha + embedding so‘rovi."""
    path = make_big_docx(tmp / "katta_hujjat.docx")
    t0 = time.monotonic()
    with path.open("rb") as f:
        doc = (await owner.post("/api/v1/documents", files={"file": (path.name, f)})).json()

    async def ready() -> bool:
        v = (await owner.get(f"/api/v1/documents/{doc['id']}")).json()["versions"][0]
        if v["parse_status"] == "failed":
            raise RuntimeError(v["parse_error"])
        return v["parse_status"] == "ready"

    await until(ready, "10 MB DOCX", 300)
    elapsed = time.monotonic() - t0
    m.add("docx_10mb_index", elapsed)
    return path.stat().st_size / 1024 / 1024


def write_report(m: Metrics, meta: dict[str, Any], out: Path) -> tuple[Path, bool]:
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    rows, ok_all = [], True
    for name, values in m.samples.items():
        p50, p95, mx = statistics.median(values), pct(values, 95), max(values)
        target = TARGETS.get(name)
        ok = target is None or p95 <= target
        ok_all &= ok
        rows.append((name, len(values), p50, p95, mx, target, ok, m.errors.get(name, 0)))
    (out / f"load-{stamp}.json").write_text(json.dumps(
        {"meta": meta, "samples": {k: sorted(v) for k, v in m.samples.items()},
         "errors": m.errors}, ensure_ascii=False, indent=1))
    lines = [f"# Yuklama testi — {stamp}", ""]
    lines += [f"- {k}: {v}" for k, v in meta.items()]
    lines += ["", "| O‘lchov | Soni | P50, s | P95, s | Max, s | Maqsad (P95) | Xato | Natija |",
              "|---|---|---|---|---|---|---|---|"]
    for name, n, p50, p95, mx, target, ok, errs in rows:
        lines.append(f"| {LABELS.get(name, name)} | {n} | {p50:.3f} | {p95:.3f} | {mx:.3f} | "
                     f"{'—' if target is None else f'≤ {target:g}'} | {errs} | "
                     f"{'✅' if ok else '❌'} |")
    total_errors = sum(m.errors.values())
    lines += ["", f"Xatolar jami: {total_errors}",
              f"**Umumiy: {'✅ maqsadlar bajarildi' if ok_all and not total_errors else '❌'}**"]
    path = out / f"load-{stamp}.md"
    path.write_text("\n".join(lines) + "\n")
    return path, ok_all and not total_errors


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=os.environ.get("E2E_BASE_URL", "http://localhost:8050"))
    parser.add_argument("--data", required=True, help="generate.py chiqishi (1 mln satr)")
    parser.add_argument("--users", type=int, default=20)
    parser.add_argument("--tasks", type=int, default=5)
    parser.add_argument("--seconds", type=int, default=180)
    parser.add_argument("--out", default=str(ROOT / "docs/reports"))
    args = parser.parse_args()
    log = Path(os.environ["EVAL_API_LOG"])
    m = Metrics()
    owner, _ = await register(args.base, "Yuklama MChJ")
    data = Path(args.data)
    rows = sum(1 for _ in (data / "sotuvlar.csv").open()) - 1
    print(f"Import: {rows} savdo satri…", flush=True)
    t0 = time.monotonic()
    await import_csv(owner, data / "sotuvlar.csv")
    await import_csv(owner, data / "qaytarishlar.csv")
    synced = time.monotonic() - t0
    # “Yuklandi” — Integration sync tugagani; ma’lumot so‘rov uchun tayyorligi (Business ingestion)
    # alohida: to‘liq yil sof savdosi generator hisobi bilan aniq teng bo‘lguncha kutiladi.
    expected = json.loads((data / "expected.json").read_text())["sales"]["UZS"]
    want = sum((Decimal(v["total"]["net_sales"]) for v in expected.values()), Decimal("0"))

    async def ingested() -> bool:
        r = await owner.post("/api/v1/analytics/queries", json={
            "metric_ids": ["net_sales"], "date_range": {"from": "2025-09-01", "to": "2026-08-31"},
            "currency": "UZS"})
        rows = r.json().get("data", {}).get("rows") if r.status_code == 200 else None
        return bool(rows) and Decimal(rows[0][0]) == want

    try:
        await until(ingested, "1 mln satr analitikaga tayyor", 1800)
        m.add("ingest_1m", time.monotonic() - t0)
    except TimeoutError:
        m.error("ingest_1m")
    print(f"  sync: {synced:.0f} s, so‘rovga tayyor: {time.monotonic() - t0:.0f} s", flush=True)
    users = [owner] + [await invite_user(owner, log) for _ in range(args.users - 1)]
    print(f"{len(users)} foydalanuvchi, {args.tasks} parallel vazifa, {args.seconds} s…",
          flush=True)
    stop = time.monotonic() + args.seconds
    agents = ["Ali", "Madina", "Ali", "Madina", "Ali"]
    await asyncio.gather(
        *(task_loop(u, m, stop, agents[i % len(agents)]) for i, u in enumerate(users[:args.tasks])),
        *(browse_loop(u, m, stop) for u in users[args.tasks:]))
    print("10 MB DOCX indekslash…", flush=True)
    size = 0.0
    with tempfile.TemporaryDirectory() as tmp:
        try:
            size = await docx_index(owner, m, Path(tmp))
        except Exception as exc:  # hisobot baribir yoziladi
            m.error("docx_10mb_index")
            print(f"  DOCX: {exc}", flush=True)
    meta = {"Stek": args.base, "Savdo satrlari": rows, "Foydalanuvchilar": len(users),
            "Parallel vazifalar": args.tasks, "Davomiyligi, s": args.seconds,
            "AI provayder": os.environ.get("AI_MODEL_PROVIDER", "fake"),
            "DOCX hajmi, MB": f"{size:.1f}",
            "Muhit": "lokal (bitta mashina, har servis 1 jarayon)"}
    path, ok = write_report(m, meta, Path(args.out))
    print(path.read_text())
    for u in users:
        await u.c.aclose()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
