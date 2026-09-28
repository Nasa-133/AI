# Lokal ishga tushirish

## Talablar

- Docker (Compose v2), Python 3.12 va [uv](https://docs.astral.sh/uv/), Node.js 22+ va npm.
- Bo‘sh portlar: 55432 (Postgres), 5672 (RabbitMQ), 6379 (Redis), 9000 (S3), 8010/8011 (API),
  3010 (web).

## Birinchi marta

```bash
make up          # Postgres (pgvector), RabbitMQ, Redis, S3 (SeaweedFS)
make sync        # har servis uchun uv sync (lockfile bo‘yicha)
make migrate     # uch baza migratsiyasi
(cd apps/web && npm ci)
```

## Butun stek

```bash
make stack       # API :8010, AI embed :8011, 3 worker, web http://localhost:3010, soxta ERP :8070
```

Loglar: `.dev-logs/`. Taklif va parol tiklash havolalari lokalda API logiga yoziladi
(`BUSINESS_NOTIFIER=log`). Ro‘yxatdan o‘tish: http://localhost:3010/register → MFA → Sozlamalar
(hisob qoidalarini tasdiqlash) → Integratsiyalar → **“ERP ulash (API)”** (soxta ERP; mapping’larni
tasdiqlab sinxronlang) yoki `fixtures/synthetic/demo/*.csv` ni yuklang. ERP ulash va haqiqiy
tizimga o‘tish: [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md).

**Test korxona (ERP + CRM + dashboardlar) bir buyruqda.** `make stack` ishlab turganda:

```bash
cd services/business && uv run python ../../tools/demo/setup_test_company.py \
    --email <sizning email> --dashboards
```

Akkauntingizga alohida “Test korxona” qo‘shiladi (asosiy korxona o‘zgarmaydi; tepadagi menyudan
almashtiriladi). Hisob qoidalari tasdiqlanadi, soxta ERP (4 obyekt) va soxta CRM (bitimlar)
ulanib sinxronlanadi. `--dashboards` bilan 4 ta tahlil dashboardi (Rahbar paneli, Savdo va foyda,
CRM voronkasi, Debitorlik) “Asosiy xulosalar” matni bilan yaratiladi. Qayta ishga tushirilsa
dashboardlar oxirgi ma’lumot bilan yangi versiya bo‘ladi. Har qadam auditda “demo-sozlash” belgisi
bilan.

Sintetik ma’lumot: `make synthetic` (19 000 satr); golden to‘plam `fixtures/synthetic/golden`.

## OpenAI bilan

`.env.example` ga qarang. Fake provayder standart; real model uchun:

```bash
export AI_MODEL_PROVIDER=openai OPENAI_API_KEY=... OPENAI_MODEL_MAIN=... \
       AI_EMBEDDING_PROVIDER=openai OPENAI_EMBEDDING_MODEL=...
make stack
```

Narx (budjet uchun): `AI_PRICE_INPUT_PER_1M`, `AI_PRICE_OUTPUT_PER_1M` (USD).

## Tekshiruvlar

| Buyruq | Nima |
|---|---|
| `make check` | lint, tip, arxitektura chegaralari, unit + integratsiya (alohida `*_test` bazalarida), web |
| `make e2e` | to‘liq stek: CSV → chat → dashboard; hujjatlar; agent navbati |
| `make e2e-ui` | Playwright (avval `make stack`) |
| `make eval` / `make eval-openai` | release eval (TZ 20), hisobot `docs/reports/` |
| `make load` | pilot yuklama: 1 mln satr, 20 foydalanuvchi, 5 parallel vazifa |
| `make degradation` | AI / Integration / broker o‘chiq holatlar |
| `make migration-check` | toza bazada upgrade → downgrade → upgrade |
| `./scripts/restore-drill.sh` | zaxira → tiklash → tekshiruv, RTO o‘lchovi |

`make e2e`, `make eval`, `make load`, `make degradation` o‘z portlarida alohida stek ishga
tushiradi; `make stack` ishlab tursa uni avval to‘xtating (worker’lar bir broker navbatini bo‘lishadi).
