# Deploy

## Tartib

1. **CI yashil**: lint, tip, arxitektura chegaralari, kontrakt diff (breaking yo‘q yoki yangi
   major versiya), unit + integratsiya, `make migration-check`, secret scan.
2. **Image’lar**: har runtime alohida (`services/*/Dockerfile`, repo ildizidan build,
   `uv sync --frozen`). Web: `apps/web` (`next build`).
3. **Migratsiya** (har runtime o‘z owner roli bilan, app roli bilan emas):
   ```bash
   BUSINESS_MIGRATIONS_DATABASE_URL=... uv run alembic upgrade head   # services/business
   AI_MIGRATIONS_DATABASE_URL=...        uv run alembic upgrade head   # services/ai_runtime
   INTEGRATION_MIGRATIONS_DATABASE_URL=... uv run alembic upgrade head # services/integration_runtime
   ```
   Migratsiyalar oldinga mos (expand → contract): eski kod yangi sxemada ishlay oladi.
4. **Runtime’lar ketma-ketligi**: consumer’lar avval (Business worker, AI worker, Integration
   worker), keyin producer’lar (Business API), oxirida Web. Kontraktlar N/N−1 mos.
5. **Tekshiruv**: `/health/ready` (API, AI API), SSE ulanishi, bitta test tenant’da chat savoli
   va dashboard ochilishi; broker’da `*.dlq` navbatlari o‘smayapti.

## Orqaga qaytarish

- Kod: oldingi image tag’ga qaytish (runtime’lar mustaqil).
- Migratsiya: `alembic downgrade <revision>` — faqat migratsiyada destructive bo‘lmasa; destructive
  o‘zgarish PR’da alohida belgilanadi va zaxiradan tiklash rejasi bilan chiqariladi
  ([backup-restore.md](backup-restore.md)).
- Broker xabarlari: yangi versiyadan chiqqan, eski consumer tushunmaydigan (yangi major) xabarlar
  DLQ’ga tushadi — qaytarilgach [replay.md](replay.md) bo‘yicha qayta yuboriladi.

## Secret’lar

| Secret | Qayerda | Kim ishlatadi |
|---|---|---|
| `BUSINESS_DATA_ENCRYPTION_KEY` (Fernet) | secret manager | Business (MFA sirlari, psevdonim vault’i) |
| `BUSINESS_TOOLS_SERVICE_TOKEN` = `AI_BUSINESS_TOOLS_TOKEN` | secret manager | Core ↔ AI |
| `BUSINESS_CAPABILITY_SIGNING_KEY` | secret manager | faqat Business |
| `OPENAI_API_KEY` | secret manager | faqat AI Runtime |
| ERP credential’lari | secret manager | faqat Integration Runtime |
| DB rollari (owner/app) | secret manager | har runtime faqat o‘ziniki |

Almashtirish tartibi: [incidents.md → Kalit almashtirish](incidents.md#kalit-almashtirish).
