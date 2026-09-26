# AI Business Office

Korxona rahbarlari uchun ERP/CRM ma’lumotlari va hujjatlar asosida ishlaydigan AI analitika platformasi.

- Talablar: [`AI_Business_Office_TZ.md`](AI_Business_Office_TZ.md) (v1.3)
- Qurish rejasi va holat: [`docs/PLAN.md`](docs/PLAN.md)

## Tuzilma

| Yo‘l | Mas’uliyat |
|---|---|
| `services/business/` | Business Core — haqiqat manbai (API + Worker), DDD kontekstlari |
| `services/ai_runtime/` | Model chaqirig‘i, agent tool loop, embeddings |
| `services/integration_runtime/` | Connector’lar, sync engine, canonical batch |
| `contracts/` | Versionli HTTP/event/tool/canonical kontraktlar |
| `infra/compose/` | Lokal platforma |
| `tests/architecture/`, `tests/contracts/` | Servislararo chegara va kontrakt testlari |

Aloqa qoidalari: TZ 13.3 (hub-and-spoke, spoke ↔ spoke aloqasi yo‘q).

## Ishga tushirish

Talablar: Docker, [uv](https://docs.astral.sh/uv/), Python 3.12.

```bash
cp .env.example .env
# BUSINESS_DATA_ENCRYPTION_KEY ni to‘ldiring:
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

make up        # Postgres (3 ta alohida DB), RabbitMQ, Redis, S3 ombori (SeaweedFS)
make sync      # har servis dependency’lari
make migrate   # Business schema + RLS
make dev       # http://localhost:8000/api/docs
make check     # lint + type + arxitektura + barcha testlar
```

Postgres hostda `55432` portida (lokal 5432 bilan to‘qnashmasligi uchun).
