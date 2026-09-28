# ADR 002 — Modular Business Core + alohida AI va Integration runtime’lar

Holat: qabul qilindi · Sana: 2026-09-26

## Kontekst

Uch xil yuk profili bor: tranzaksion biznes API (past kechikish), AI agent run’lari (uzoq, tashqi
provayderga bog‘liq, qimmat) va ERP integratsiyasi (tashqi tizimlar, katta batch’lar). TZ 13.1
xatolar izolyatsiyasi va mustaqil deploy’ni talab qiladi, lekin P0 jamoasi kichik.

## Qaror

Uchta mustaqil deploy qilinadigan runtime:
- **Business Core** — modular monolit (API + worker), barcha biznes qoidalari va ma’lumot egasi;
- **AI Runtime** — agent runner, model provayderi, embedding;
- **Integration Runtime** — connector’lar, sync engine.
Har biri o‘z lockfile’i, Dockerfile’i, bazasi va migratsiyasiga ega.

## Muqobillar

- **Bitta monolit.** Eng oddiy, lekin OpenAI yoki ERP muammosi butun tizimni (dashboard, chat)
  sekinlashtiradi; secret’lar (OpenAI, ERP) bitta jarayonda. Rad etildi.
- **Har bounded context mikroservis.** 7+ servis, taqsimlangan tranzaksiyalar — P0 uchun ortiqcha.

## Trade-off

Uch runtime orasida kontrakt boshqaruvi (ADR 005) va broker (ADR 004) kerak; lokal ishga
tushirish murakkabroq (`scripts/dev.sh`). Evaziga AI yoki Integration o‘chsa ham Core ishlaydi.

## Oqibat va tekshiruv

- Degradatsiya: `scripts/degradation.sh` (I03, I05, broker restart) — AI yoki Integration
  o‘chiq bo‘lganda dashboard, chat va hujjatlar ishlaydi.
- Har servis alohida build: `services/*/Dockerfile`, CI `service` matritsasi.
- Qayta ko‘rish: Core ichida bir context yuki boshqalardan keskin ajralsa (masalan, hujjat parse)
  — alohida runtime’ga chiqarish.
