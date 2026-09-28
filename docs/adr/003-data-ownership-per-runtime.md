# ADR 003 — Har runtime o‘z ma’lumotining egasi

Holat: qabul qilindi · Sana: 2026-09-26

## Kontekst

Umumiy baza va umumiy ORM modellari runtime’larni yashirin bog‘laydi: bir servis migratsiyasi
boshqasini buzadi, credential sizib chiqsa hamma ma’lumot ochiladi. TZ 13.7, 13.12 har runtime
DB credential’i o‘z hududidan tashqariga chiqmasligini talab qiladi. Multi-tenant ma’lumot RLS
bilan majburiy ajratilishi kerak.

## Qaror

- Har runtime — alohida logical database (`business`, `ai_runtime`, `integration_runtime`), o‘z
  owner (migratsiya) va app (ish vaqti) roli. App roli superuser/BYPASSRLS/owner emas.
- Tenant jadvallarida `FORCE ROW LEVEL SECURITY`; tenant konteksti tranzaksiya darajasida
  (`set_config(..., true)`), pool’dan sizib chiqmaydi.
- Runtime’lar bir-birining bazasini o‘qimaydi; ma’lumot faqat command/event va object storage’dagi
  batch orqali o‘tadi (ADR 004, 012).

## Muqobillar

- **Bitta DB, alohida sxemalar.** Oddiyroq backup, lekin bitta credential bilan hammasiga yo‘l;
  runtime chegarasi faqat konventsiya bilan. Rad etildi.
- **Tenant uchun alohida DB.** Kuchli izolyatsiya, lekin yuzlab tenantda migratsiya va ulanish
  hovuzi boshqaruvi og‘ir. P2 da yirik mijozlar uchun qayta ko‘riladi.

## Trade-off

Runtime’lararo hisobot uchun ma’lumot nusxalanadi (canonical batch); backup uch baza bo‘yicha.
RLS’dan ikki asosli istisno bor (sessiya qidiruvi, outbox relay) — test ro‘yxatida.

## Oqibat va tekshiruv

- `services/business/tests/integration/test_data_ownership.py`: credential boshqa bazaga kira
  olmaydi, app roli imtiyozsiz, har tenant jadvalida FORCE RLS (istisnolar sababi bilan).
- `test_tenant_isolation.py`, eval S01 (`tools/eval/run_eval.py`): begona tenant ID’si
  HTTP/Tool API/qidiruv/SSE orqali hech narsa ochmaydi.
- Alohida test bazalari (`scripts/test-dbs.sh`), migratsiya aylanishi (`scripts/migration-check.sh`).
