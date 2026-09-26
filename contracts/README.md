# Kontraktlar

Servislar orasidagi yagona kelishuv. Servislar bir-birining kodini import qilmaydi (TZ 13.3), faqat shu yerdagi schema’lar orqali gaplashadi.

## Papkalar

| Papka | Mazmuni |
|---|---|
| `http/` | Har servisning review qilingan OpenAPI baseline’i (`<servis>.openapi.json`) |
| `events/` | Event envelope (`envelope.v1.json`) va event payload schema’lari |
| `commands/` | Command payload schema’lari (`RunAgent`, `SyncSource`, …) |
| `canonical/` | Integration → Analytics canonical record’lari, domen bo‘yicha (`sales/`, `inventory/`, `finance/`) va batch manifest |
| `tools/` | (reja) tool argument/natija schema’lari |
| `*/fixtures/` | Har schema uchun `<nom>.valid.json` — testlar avtomatik tekshiradi |

## Qoidalar

- Fayl nomi: `<Nom>.v<major>.json`; `event_type` `<Nom>.v<major>` ko‘rinishida.
- JSON Schema draft 2020-12. Har obyekt `additionalProperties: false`; barcha maydonlar `required`, ixtiyoriy qiymat `null` bilan ifodalanadi.
- Pul va miqdor — Decimal **string** (`"1234.50"`), hech qachon JSON number emas. Valyuta — ISO 4217 (`UZS`). Vaqt — `date-time` (UTC), sana — `date`.
- Katta ma’lumot brokerda emas: object storage reference (`bucket`, `key`, `checksum_sha256`, `size_bytes`). Canonical record’lar JSON Lines faylida.
- Har yangi schema bilan birga fixture qo‘shiladi.

## Versiyalash (TZ 13.11)

- **Mos o‘zgarish** (yangi ixtiyoriy maydon, yangi endpoint) — joriy major’da.
- **Buzuvchi o‘zgarish** (maydonni o‘chirish, turini o‘zgartirish, required qo‘shish, ma’noni o‘zgartirish, javob enum’iga qiymat qo‘shish) — yangi major fayl (`.v2.json`) va migratsiya rejasi. Eski major consumer’lar ko‘chmaguncha saqlanadi.
- Consumer noma’lum ixtiyoriy maydonni e’tiborsiz qoldiradi; noma’lum major event DLQ’ga sabab bilan tushadi.

## OpenAPI baseline

`services/business/tests/contract/test_openapi_baseline.py` joriy API’ni baseline bilan solishtiradi: breaking o‘zgarishda va yangilanmagan baseline’da yiqiladi. API o‘zgarishi review qilingach baseline’ni qayta yarating:

```bash
cd services/business && uv run python ../../tools/contracts/export_openapi.py business > ../../contracts/http/business.openapi.json
```

Ikki spetsifikatsiyani qo‘lda solishtirish (breaking bo‘lsa exit 1):

```bash
python3 tools/contracts/openapi_diff.py eski.json yangi.json
```

Qoidalarning to‘liq ro‘yxati `tools/contracts/openapi_diff.py` boshida.
