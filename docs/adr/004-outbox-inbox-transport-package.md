# ADR 004 — Outbox/inbox, at-least-once va transport paketi

Holat: qabul qilindi · Sana: 2026-09-27

## Kontekst

TZ 13.8 har producer’dan domain o‘zgarishi va xabarni bitta lokal tranzaksiyada saqlashni (transactional outbox), consumer’dan esa `event_id + consumer` bo‘yicha deduplikatsiyani talab qiladi. Uchta runtime’ning hammasi xabar yuboradi va qabul qiladi.

TZ 13.6 umumiy paketni faqat “schema-generated transport tiplari va kichik kuzatuv utilitalari” bilan cheklaydi; umumiy ORM, biznes servisi va ulkan `common` paketi taqiqlangan.

## Qaror

1. Yetkazish **at-least-once**. Exactly-once va’da qilinmaydi.
2. Mexanika `packages/abo_messaging` transport paketida: envelope, `enqueue`, `OutboxRelay` (`FOR UPDATE SKIP LOCKED`, publisher confirm, backoff, `failed_at`), `InboxProcessor` (dedup + handler + inbox bitta tranzaksiyada) va RabbitMQ topologiyasi (topic exchange `abo`, har consumer uchun asosiy, `.retry` (TTL) va `.dlq` navbat).
3. Paketda **biznes mantiqi, domain modeli va umumiy jadval yo‘q**. Har servis `messaging.outbox`/`messaging.inbox` jadvallarini **o‘z bazasida, o‘z migratsiyasida** yaratadi. Servislar orasidagi kontrakt — `contracts/` dagi JSON schema’lar, Python tiplari emas.
4. Handler qayta ishlashi, inbox belgisi va (kerak bo‘lsa) keyingi outbox xabari bitta tranzaksiyada — shuning uchun duplicate yoki qisman bajarilish bo‘lmaydi.
5. Xatolar: `InvalidEnvelope`, noma’lum `event_type`/major versiya va `PermanentError` — darhol DLQ; boshqa xatolar — cheklangan retry, keyin DLQ.
6. Vaqt hisobi (backoff, purge) DB soatida: host va konteyner soati farqi natijaga ta’sir qilmaydi.

## Muqobil

- **Har servisda alohida nusxa.** Kodni bog‘lamaydi, lekin bir xil nozik mexanikani (skip locked, confirm, dedup) uch joyda qo‘llab-quvvatlash kerak bo‘ladi va xatolar bir joyda tuzatilib, boshqasida qoladi. Rad etildi.
- **Celery.** Servislararo kontrakt Python task nomiga bog‘lanadi (TZ 13.8 taqiqlaydi). Rad etildi.
- **Debezium/CDC.** Operatsion murakkablik P0 uchun ortiqcha. P2 da qayta ko‘riladi.

## Oqibat va tekshiruv

- Paket servis kodini import qilmaydi; domain/application/ports qatlamlari paketni import qilmaydi — `tests/architecture/test_boundaries.py` va import-linter tekshiradi.
- Paket o‘zgarishi har servisning image’iga build vaqtida kiradi; runtime deploy mustaqilligi saqlanadi, chunki simdagi format — versionli envelope.
- Failure testlari: `packages/abo_messaging/tests/test_outbox_inbox.py` (rollback, confirm’siz qayta yuborish, max attempts, parallel relay, duplicate, handler rollback, DLQ) va `test_rabbit_e2e.py` (haqiqiy broker bilan retry va DLQ).
- Qayta ko‘rish triggeri: paketga biznes tushunchasi qo‘shish ehtiyoji paydo bo‘lsa — bu ADR buzilgan hisoblanadi va yangi qaror kerak.
