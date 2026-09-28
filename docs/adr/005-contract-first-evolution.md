# ADR 005 — Contract-first evolyutsiya

Holat: qabul qilindi · Sana: 2026-09-26

## Kontekst

Uch runtime va Web mustaqil deploy qilinadi (ADR 002). Kontrakt faqat kodda bo‘lsa, bir tomonning
o‘zgarishi ikkinchisini runtime’da buzadi. TZ 13.11 breaking o‘zgarishni CI’da to‘xtatishni va
N/N−1 moslikni talab qiladi.

## Qaror

- `contracts/` — yagona manba: command/event payload’lari, envelope, tool args/result, kanonik
  entity’lar (JSON Schema 2020-12, yopiq obyektlar, barcha maydon `required`, null aniq), HTTP
  OpenAPI baseline.
- Servislar kontraktni Python tipi sifatida emas, schema sifatida bo‘lishadi; AI Runtime tool
  schema’larining nusxasi paket ichida (image mustaqil), mosligi test bilan tekshiriladi.
- Web tiplari OpenAPI’dan generatsiya (`openapi-typescript`), CI’da farq bo‘lsa yiqiladi.
- Breaking o‘zgarish — yangi major versiya (`.v2`), eski versiya bir release davomida qo‘llanadi.

## Muqobillar

- **Protobuf/gRPC.** Kuchli tiplash, lekin brauzer va SSE uchun qo‘shimcha gateway; jamoa uchun
  yangi vosita. P0 da rad etildi.
- **Umumiy Python paketi bilan DTO’lar.** Deploy’larni kod darajasida bog‘laydi (TZ 13.6 taqiq).

## Trade-off

Schema’lar va fixture’larni qo‘lda yuritish kerak; har yangi maydon uchun kontrakt + fixture +
generatsiya. Evaziga producer/consumer mos kelmasligi PR’da ko‘rinadi.

## Oqibat va tekshiruv

- `tests/contracts/test_event_schemas.py` (fixture’lar schema’ga mos), `test_openapi_diff.py`
  (breaking diff), `services/business/tests/contract/test_openapi_baseline.py`,
  `services/ai_runtime/tests/unit/test_tool_catalog.py` (paket nusxasi = kontrakt),
  CI `web` job’idagi `api:types` farqi.
