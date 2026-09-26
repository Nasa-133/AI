# Sintetik ERP ma’lumotlari

Test va demo uchun deterministik ERP eksporti generatori. Faqat Python 3.12 stdlib;
pul hisoblari faqat `Decimal` bilan.

```bash
python tools/synthetic_data/generate.py --seed 42 --rows 19000 --out fixtures/synthetic/demo
python tools/synthetic_data/generate.py --golden --out fixtures/synthetic/golden
uv run --no-project --with pytest pytest tools/synthetic_data/tests -q
```

Bir xil `--seed` va `--rows` byte-darajada bir xil fayllarni beradi. Generator oqim bilan
yozadi: 1 million satrgacha xotirada hammasini saqlamaydi (200 ming satr ≈ 3.5 s).

## To‘plamlar

| Papka | Mazmuni |
|---|---|
| `fixtures/synthetic/golden/` | Qo‘lda tekshiriladigan bir necha satr: TZ A01, A02, A07 |
| `fixtures/synthetic/demo/` | seed 42, 19 000 sotuv satri, 2025-09-01 … 2026-08-31, 5 filial, 150 mahsulot, ~800 mijoz |

## Fayllar

Ustun nomlari vendor ERP eksportiga o‘xshaydi (canonical emas); mapping ingestion’da bajariladi.
Sanalar `+05:00` offset bilan (Asia/Tashkent), pul qiymatlari 2 xonali, QQSsiz summalar.

| Fayl | Mazmuni |
|---|---|
| `sotuvlar.csv` | Sotuv satrlari: `Hujjat ID` (satr ID), `Hujjat №`, `Sana`, filial, mahsulot, mijoz, `Miqdor`, `Narx`, `Summa` = Miqdor × Narx, `Chegirma`, `QQS` (12%), `Tannarx` (bo‘sh bo‘lishi mumkin), `Valyuta`, `Holat` |
| `qaytarishlar.csv` | Qaytarishlar: `Asl hujjat ID` (bo‘sh bo‘lishi mumkin), `Summa` musbat, `Tannarx` doim to‘ldirilgan |
| `ombor_harakatlari.csv` | Ishorali `Miqdor`; `Turi`: kirim, sotuv (filial × mahsulot × kun bo‘yicha jamlangan, 23:00), qaytarish, ko‘chirish_kirim/chiqim, tuzatish |
| `debitorlik.csv` | Tasdiqlangan hujjatlar bo‘yicha qarz: `Summa` QQS bilan, `To‘langan`, `To‘lov muddati` |
| `expected.json` | Fayllardagi satrlardan hisoblangan kutilgan natijalar va senariy kalitlari |

## Hisoblash qoidalari (ingestion ham shularga amal qiladi)

- Faqat `Holat = tasdiqlangan` hisobga olinadi; `qoralama` va `bekor qilingan` e’tiborsiz (karantin emas).
- **Karantin** (`sotuvlar.csv`): bir xil `Hujjat ID` bir necha marta kelsa — barcha nusxalari;
  `Sana` offset’li ISO 8601 emas; `Miqdor` ≤ 0. Karantindagi satrlar hech qaysi agregatga,
  ombor harakatiga, qaytarish yoki debitorlikka kirmaydi.
- Oy — `Sana`ning Toshkent vaqtidagi oyi. Qaytarish o‘z sanasi va filiali bo‘yicha.
- Sof tushum = Σ Summa − Σ Chegirma − Σ qaytarish Summa.
- Tannarx = Σ sotuv Tannarx − Σ qaytarish Tannarx. Bo‘sh sotuv `Tannarx` 0 deb olinmaydi:
  yig‘indiga qo‘shilmaydi va `cogs_missing_rows`da sanaladi (yalpi foyda shu satrlar uchun oshib
  ko‘rinadi — UI buni cheklov sifatida ko‘rsatishi kerak).
- Yalpi foyda = sof tushum − tannarx; marja = foyda / sof tushum × 100, ROUND_HALF_UP,
  2 xona; sof tushum 0 bo‘lsa `null`.
- Valyutalar hech qachon qo‘shilmaydi: `expected.json`da `sales.<valyuta>` alohida.
- Debitorlik: qoldiq = Summa − To‘langan; `To‘lov muddati` < `as_of` va qoldiq > 0 — muddati o‘tgan.
- Ombor qoldig‘i = Σ Miqdor; sekin aylanadigan — oxirgi `sotuv` harakatidan `as_of`gacha ≥ 60 kun
  yoki umuman sotilmagan.

## Demo senariylari (`expected.json` → `scenarios`)

| Kalit | TZ | Mazmuni |
|---|---|---|
| `branch_opened` | A02 | Namangan 2026-03 da ochiladi; 2026-02 da savdo yo‘q |
| `profit_drop` | A06 | 2026-06 da umumiy foyda pasayadi, pasayishning >50% Samarqand aksiyasidan |
| `negative_gross_profit` | A07 | Buxoro 2026-04 likvidatsiya: yalpi foyda manfiy |
| `currencies` | A03 | ~2% satr USD (Toshkentdagi import mijozlari) |
| `quarantine_expected` | — | Dublikat (qayta ko‘rib chiqilgan qiymat), noto‘g‘ri sana, manfiy miqdor ID’lari |
| `missing_cost` | — | Tasdiqlangan satrlarning ~2% ida `Tannarx` yo‘q |
| `slow_moving_designed` | — | 12 mahsulot 2026-05-15 dan keyin sotilmaydi |
| `negative_stock` | anomaliya | Bitta mahsulot qoldig‘i to‘ldirilmaydi va manfiyga tushadi |
| `overdue_receivables_documents` | — | Kechikib to‘lovchi mijozlar sabab muddati o‘tgan qarzlar |

Golden to‘plam: A01 — Toshkent 2026-01: yalpi 1000, chegirma 50, qaytarish 100 (qaytarish
tannarxi 0.00), tannarx 500 → sof tushum 850, yalpi foyda 350, marja 41.18%. A02 — Namangan
2026-02 sof tushum 100, oldingi oyda savdo yo‘q. A07 — Buxoro yalpi foydasi 2026-03 da −100,
2026-04 da −50.
