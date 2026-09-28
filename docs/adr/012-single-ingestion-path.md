# ADR 012 — Yagona ingestion yo‘li va kanonik model

Holat: qabul qilindi · Sana: 2026-09-26

## Kontekst

CSV import va ERP sinxronlash ikki xil yo‘l bo‘lsa, validatsiya, karantin va snapshot qoidalari
ajralib ketadi: bir xil ma’lumot turli raqam beradi. TZ I02 bir xil zanjirni talab qiladi.

## Qaror

Har manba (CSV fayl, demo ERP, kelajakdagi ERP) bitta zanjirdan o‘tadi:

1. Connector → xom satrlar (ADR 006);
2. Sync Engine → tasdiqlangan mapping bo‘yicha normallashtirish, rad etish hisoboti, kanonik JSONL
   batch (object storage, checksum);
3. `SourceBatchReady` → Business Analytics ingestion: karantin, deduplikatsiya (bir batch ikki marta
   kelsa snapshot bir marta — I04), versiyalangan snapshot, `DatasetSnapshotPublished`.

CSV yuklash ham `file_import` connector sifatida xuddi shu yo‘ldan boradi.

## Muqobillar

- **CSV to‘g‘ridan-to‘g‘ri Business’ga.** Tezroq demo, lekin ikkinchi validatsiya yo‘li. Rad etildi.
- **ERP’dan to‘g‘ridan-to‘g‘ri Business DB’ga yozish.** Runtime chegarasini buzadi (ADR 003).

## Trade-off

Kichik CSV ham broker va object storage orqali o‘tadi (bir necha soniya kechikish). Evaziga I02
kafolatlanadi va bitta joyda sinaladi.

## Oqibat va tekshiruv

- `test_connector_conformance.py::test_i02_csv_and_demo_erp_give_identical_canonical_batch`.
- Business: `tests/integration/test_analytics.py` (I04 takroriy batch), `scripts/e2e.sh` (CSV →
  mapping → sync → snapshot → chat).
