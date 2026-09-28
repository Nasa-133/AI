# Zaxira va tiklash

Maqsad (TZ 19): **RPO 24 soat**, **RTO 4 soat**. Mashq: `./scripts/restore-drill.sh`
(hisobot `docs/reports/restore-<sana>.md`).

## Nima zaxiralanadi

| Qism | Usul | Chastota (pilot) |
|---|---|---|
| `business`, `ai_runtime`, `integration_runtime` bazalari | `pg_dump -Fc` (production: WAL arxivi + PITR) | kunlik to‘liq |
| S3: `abo-business` (yuklangan fayl, hujjat versiyalari), `abo-integration` (kanonik batch), `abo-ai` (vektor fayllari) | obyekt nusxasi + SHA-256 manifest (production: bucket versioning + replikatsiya) | kunlik |
| Broker | zaxiralanmaydi — holat outbox’da (qayta yuboriladi) | — |
| Redis | zaxiralanmaydi (rate limit hisoblagichlari) | — |

Backup saqlash muddati — 30 kun (TZ 17); o‘chirilgan tenant ma’lumoti backup’dan muddat
tugagach yo‘qoladi.

## Tiklash (hodisa paytida)

1. **Tashxis**: qaysi runtime/bazasi zarar ko‘rgan; oxirgi yaxshi zaxira vaqti (RPO hisobi).
2. Runtime’larni to‘xtatish (yozuvlar to‘xtashi uchun): API → worker’lar.
3. Bazani tiklash:
   ```bash
   docker compose ... exec -T postgres psql -U postgres -c "CREATE DATABASE business_new OWNER business_owner"
   docker compose ... exec -T postgres pg_restore -U postgres -d business_new --no-owner --role=business_owner < business.dump
   ```
   Keyin nomlarni almashtirish (`ALTER DATABASE ... RENAME`) yoki ulanish satrini yangilash.
4. S3: `uv run python tools/ops/s3_snapshot.py restore --src <dir> --suffix ""` (asl nomlarga).
5. `uv run alembic upgrade head` (zaxira eski versiyada bo‘lsa).
6. Runtime’larni ishga tushirish; **replay**: zaxira nuqtasidan keyingi outbox eventlari
   ([replay.md](replay.md)) — consumer’lar dedup qiladi.
7. Tekshiruv: jadval qatorlari (`restore-drill.sh` dagi `counts`), bitta tenant’da dashboard va
   hujjat ochilishi, audit jurnalida tiklash qaydi.

## Mashq

```bash
./scripts/restore-drill.sh   # ishlayotgan tizimga tegmaydi: *_restore bazalar, “-restore” bucket’lar
```

Mashq har chorakda va har katta migratsiyadan oldin. Natija (RTO, jadval/obyekt mosligi)
`docs/reports/` ga yoziladi.
