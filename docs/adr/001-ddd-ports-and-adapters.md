# ADR 001 — DDD + Ports & Adapters (hexagonal)

Holat: qabul qilindi · Sana: 2026-09-26

## Kontekst

Biznes qoidalari (metrika hisobi, hujjat patch’i, vazifa holatlari, budjet) yillar davomida
o‘zgaradi, infratuzilma (FastAPI, Postgres, RabbitMQ, OpenAI) esa almashishi mumkin. TZ 13.1–13.5
domainni framework’dan mustaqil sinashni va kontekstlar orasida private importlarni taqiqlashni
talab qiladi.

## Qaror

Har servis va Business ichidagi har bounded context (`identity`, `analytics`, `dashboards`,
`documents`, `workspace`, `integrations`, `governance`) bir xil qatlamlarga bo‘linadi:
`domain` (sof Python) → `ports` (Protocol) → `application` (use-case) → `adapters` (SQL, S3,
HTTP, OpenAI) → `public` (boshqa kontekstlar uchun yagona kirish) → `entrypoints` (HTTP,
consumer, job) → `bootstrap` (composition root).

## Muqobillar

- **Klassik layered (controller → service → ORM model).** Tezroq boshlanadi, lekin ORM modeli
  domainga oqib kiradi va sof domen testlari yo‘qoladi. Rad etildi.
- **Har context — alohida mikroservis.** Operatsion narxi P0 uchun juda yuqori (ADR 002).

## Trade-off

Ko‘proq fayl va “wiring” kodi (`entrypoints/wiring.py`); yangi dasturchi uchun kirish chizig‘i
balandroq. Evaziga domain testlari DB/brokersiz millisekundlarda ishlaydi va adapter almashishi
domainga tegmaydi.

## Oqibat va tekshiruv

- import-linter (`services/*/pyproject.toml`, “Qatlamlar” va “Domain … framework’ga qaram emas”
  kontraktlari) va `tests/architecture/test_boundaries.py` CI’da yiqiladi.
- Sof domen testlari: `services/business/tests/unit/*/test_domain*.py`,
  `tests/unit/workspace/test_office.py`, `tests/unit/governance/test_pii.py`.
- Qayta ko‘rish triggeri: kontekstlar orasida `public`dan tashqari import zarurati tug‘ilsa.
