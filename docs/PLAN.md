# AI Business Office — qurish rejasi

Manba: `AI_Business_Office_TZ.md` v1.3. Reja TZ’ning 21-bo‘limidagi ketma-ketlikni ish paketlariga, qabul testlariga va bog‘liqliklarga aylantiradi. Har bosqich oxirida ishlaydigan foydalanuvchi oqimi, testlar va ma’lum cheklovlar topshiriladi; placeholder tayyor deb hisoblanmaydi.

## 1. Texnologik qarorlar (P0)

| Soha | Tanlov | Sabab |
|---|---|---|
| Python | 3.12, `uv` (har servisda o‘z `pyproject.toml` va `uv.lock`) | Tez, deterministik lockfile |
| HTTP | FastAPI + Pydantic v2 | TZ talabi |
| DB | PostgreSQL 16 + pgvector; SQLAlchemy 2 (async, asyncpg); Alembic | RLS, vektor va FTS bitta joyda |
| Broker | RabbitMQ (aio-pika), versionli JSON xabarlar | TZ 13.8; Celery servislar orasida ishlatilmaydi |
| Worker | O‘z consumer’imiz (aio-pika) + outbox relay | Kontrakt Python funksiya nomiga bog‘lanmaydi |
| Storage | S3-mos (lokalda SeaweedFS) | Immutable batch va fayllar |
| Cache | Redis | Rate limit, kesh; source of truth emas |
| Auth | Argon2id (`argon2-cffi`), TOTP (`pyotp`), server-side sessiya + httpOnly cookie | TZ 3-bo‘lim |
| Sifat | ruff, mypy (strict domain/application), pytest, import-linter | 13.15 gate’lari |
| Frontend | Next.js + TypeScript, `openapi-typescript` generated client, TanStack Query, ECharts | TZ 13.2 |
| LLM | OpenAI Responses API — faqat AI Runtime’da, `ModelProvider` port + `FakeProvider` | ADR 008 |
| Lokal muhit | Docker Compose (`infra/compose`) | 4 servis + platforma |
| CI | GitHub Actions: har servis alohida job | 13.15 |

## 2. Bosqichlar

Taxminiy muddat 3–4 kishilik jamoa uchun (2 backend, 1 frontend, 0.5 DevOps/QA). Bitta dasturchi + LLM bilan ~2 barobar uzoqroq.

### Bosqich 0 — Poydevor (2–3 hafta)

Maqsad: chegaralari CI’da tekshiriladigan bo‘sh, lekin ishlaydigan skelet.

| # | Ish paketi | Natija |
|---|---|---|
| 0.1 | Monorepo, `infra/compose` (Postgres+pgvector, RabbitMQ, Redis, MinIO), 3 ta logical DB va alohida credential | `make up` bilan platforma ko‘tariladi |
| 0.2 | Business Core, AI Runtime, Integration Runtime skeletlari: hexagonal qatlamlar, bootstrap, health/readiness | Har servis alohida ishga tushadi va testlanadi |
| 0.3 | Arxitektura testlari: import-linter (domain → framework taqiqi, kontekstlar orasidagi private import taqiqi, servislar orasidagi import taqiqi) | Qoidani buzgan PR CI’da yiqiladi |
| 0.4 | Identity & Access: tenant, user, membership, rol; onboarding, login/logout, sessiya, `/me`, korxona almashtirish; MFA | TZ 3-bo‘lim auth talablari |
| 0.5 | Tenant izolyatsiyasi: RLS (FORCE), transaction-local `app.tenant_id`, owner bo‘lmagan app role | S01 testining DB qismi |
| 0.6 | Kontraktlar: event envelope, command/event JSON Schema, OpenAPI eksport va baseline diff | `contracts/` CI’da tekshiriladi |
| 0.7 | Outbox/inbox kutubxonasi har runtime uchun (umumiy kod emas — har servisda o‘z implementatsiyasi yoki faqat transport tiplari) | Relay, dedup, retry, DLQ testlari |
| 0.8 | Sintetik ma’lumot generatori (savdo, qaytarish, ombor, qarzdorlik; 1 mln tranzaksiyagacha) | Keyingi bosqichlar uchun fixture |
| 0.9 | CI: lint, type, test, arch, contract, secret scan | Yashil pipeline |

Qabul: 13.15 gate 1, 2, 10; S01 (DB darajasi); login oqimi end-to-end.

### Bosqich 1 — Analitika vertikal kesimi (3–4 hafta)

Maqsad: CSV → tasdiqlangan metrika → chat savoli → deterministik hisob → manbali javob → dashboard.

| # | Ish paketi |
|---|---|
| 1.1 | `POST /uploads` (purpose=`dataset_import`), MinIO, hajm/MIME tekshiruvi |
| 1.2 | Integration Runtime: Sync Engine, Connector Protocol, `file_import` va `demo_erp` connectorlari, canonical `sales.*`, `inventory.*`, `finance.receivable` v1 |
| 1.3 | Core Analytics ingestion: `SourceBatchReady` → validatsiya, dedup, karantin → `DatasetSnapshot` → `DatasetSnapshotPublished` |
| 1.4 | Semantik qatlam: metrika lug‘ati (7.1), mapping tasdiqlash API, query builder (parametrli SQL), Decimal/timezone qoidalari |
| 1.5 | Tool API: `list_available_metrics`, `run_metric_query`, `compare_periods`, `explain_contributions`, `create_dashboard`; delegated capability |
| 1.6 | AI Runtime: `RunAgent` consumer, tool loop, `FakeProvider` (deterministik), OpenAI adapteri, strict schema’lar, checkpoint |
| 1.7 | Workspace: conversation/message/task/TaskStep, `202 task_id`, SSE (persistent sequence, `Last-Event-ID`) |
| 1.8 | Dashboards: `DashboardSpec` validatsiyasi, saqlash, versiya, preview, CSV eksport |

Qabul: A01–A07, A04 (chat va dashboard bir xil raqam), I01, I02, I04, T02, T04.

### Bosqich 2 — Web ilova (Bosqich 1 bilan parallel, 3–4 hafta)

| # | Ish paketi |
|---|---|
| 2.1 | Next.js skeleti, generated API client, auth sahifalari, korxona almashtirish |
| 2.2 | Layout: chap navigatsiya, markaz, o‘ng chat; mobil variant |
| 2.3 | Chat: `@agent`, fayl biriktirish, context chip, vazifa kartasi, SSE, xato holatlari |
| 2.4 | Dashboard doskasi, tanlash oynasi, tafsilot oynasi, drill-down, breadcrumb, view-state |
| 2.5 | Mapping tasdiqlash ekrani va import holati |

Qabul: U02–U07.

### Bosqich 3 — Hujjatlar (3 hafta)

Upload (purpose=`document`) → skaner → parse (PDF/DOCX/TXT) → chunk → `GenerateEmbeddings` → pgvector + o‘zbekcha FTS normalizatori → `search_documents`/`read_document_section` → DOCX patch/draft/diff/promote (409).

Qabul: D01–D06, S03.

### Bosqich 4 — Virtual ofis (2 hafta)

Ofis sahnasi (DOM/SVG), agent kartalari, holat mapping’i (6-bo‘lim), parallel limit va navbat, reduced-motion, klaviatura.

Qabul: T01, U01.

### Bosqich 5 — Ishonchlilik va boshqaruv (2–3 hafta)

Retry/backoff, cancel (`CancelAgentRun`), budget rezervi va limitlar, o‘chirish lifecycle’i, audit, psevdonimlash filtri, failure/degradation testlari, network policy.

Qabul: T03, T05, I03, I05, I06, S02; 13.15 gate 5–8.

### Bosqich 6 — P0 qabul (1–2 hafta)

Real OpenAI tekshiruvi, eval to‘plami (40/20/10/10), load test, restore/replay mashqi, runbook’lar, ADR 001–012, ma’lum cheklovlar ro‘yxati.

Qabul: 20-bo‘lim to‘liq; 13.15 barcha gate’lar.

### Keyin — P1

Birinchi haqiqiy ERP adapteri, reconciliation, OCR, XLSX tahriri, SSO, pilot yuklama. Oldindan shart: yuridik xulosa va hosting hududi (TZ 18, 24).

## 3. Kritik yo‘l va parallel ishlar

```
0.1 → 0.2 → 0.3 ─┬→ 0.4 → 0.5 ─┬→ 1.1 → 1.3 → 1.4 → 1.5 → 1.6 → 1.7 → 1.8 → 6
                 └→ 0.6 → 0.7 ─┘        1.2 ↗                        ↘ 3 → 5 ↗
                                  2.1 → 2.2 → 2.3 → 2.4 → 4 ────────────────↗
```

Frontend 0.6 dagi OpenAPI baseline tayyor bo‘lgach mock server bilan parallel boshlaydi.

## 4. Xavflar

| Xavf | Chora |
|---|---|
| Arxitektura infratuzilmasi analitikadan vaqt oladi | Bosqich 0 qat’iy cheklangan; N/N−1 va canary keyinga |
| O‘zbek tilida qidiruv/embedding sifati past | Bosqich 3 boshida kichik eval to‘plami |
| OpenAI mavjudligi/narxi | `FakeProvider` bilan to‘liq ishlash, model konfiguratsiyada |
| Yuridik lokalizatsiya | Pilotdan oldin yurist xulosasi; psevdonimlash Bosqich 5 da |
| LLM kod yozuvchi skelet qoldiradi | Har bosqich qabul testlari bilan yopiladi |

## 5. Holat

### Bosqich 0 — Poydevor: ✅ yakunlandi

| Ish paketi | Holat | Izoh |
|---|---|---|
| 0.1 Monorepo va platforma | ✅ | 3 ta logical DB, alohida owner/app rollari; Postgres hostda 55432 |
| 0.2 Servis skeletlari | ✅ | Business Core to‘liq; AI va Integration health + qatlamlar (Bosqich 1 da to‘ldiriladi) |
| 0.3 Arxitektura testlari | ✅ | import-linter + `tests/architecture`; buzilish CI’ni yiqitishi qo‘lda tekshirildi |
| 0.4 Identity va auth | ✅ | Onboarding, login, lockout, MFA (TOTP, replay himoyasi), sessiya, CSRF, korxona almashtirish, takliflar, a’zolar va rollar, parol tiklash, Redis rate limit |
| 0.5 Tenant izolyatsiyasi (RLS) | ✅ | FORCE RLS (tenants, memberships, invitations), app roli superuser/BYPASSRLS emas, kontekst sizmasligi testlangan |
| 0.6 Kontraktlar | ✅ | Envelope, 4 command, 5 event, 4 canonical + batch manifest; OpenAPI baseline va breaking-change tekshiruvi |
| 0.7 Outbox/inbox | ✅ | `packages/abo_messaging` (ADR 004), Business migratsiyasi va worker; retry/DLQ haqiqiy RabbitMQ bilan testlangan |
| 0.8 Sintetik ma’lumotlar | ✅ | `tools/synthetic_data`, golden (A01/A02/A07) va demo (19 ming satr, 12 oy, barcha ssenariylar) |
| 0.9 CI | 🟡 | Workflow yozilgan, lokal `make check` yashil; GitHub’da remote yo‘qligi sababli ishga tushirilmagan |

Ma’lum cheklovlar:
- Production email adapteri yo‘q: `notifier=log` faqat lokal, boshqa muhitda taklif/parol havolasi yuborilmaydi (provayder tanlovi kerak).
- Rate limit Redis ishlamasa o‘chadi (fail-open); login uchun DB lockout baribir ishlaydi.
- Takliflar commitdan keyin yuboriladi; yuborish xatosi logga yoziladi, qayta yuborish endpointi hali yo‘q.

### Bosqich 1 — Analitika vertikal kesimi: 🟡 asosiy oqim ishlaydi

`make e2e` — API va 3 worker alohida jarayon sifatida: CSV yuklash → mapping tasdiqlash → sync →
ingestion → chat savoli → AI (FakeProvider) → Tool API → hisob → manbali javob → dashboard.
Barqaror (3/3), ~9 soniya.

| Ish paketi | Holat | Izoh |
|---|---|---|
| 1.1 Yuklash | ✅ | CSV → S3, SHA-256, limitlar; XLSX — aniq 415 xabari bilan (P1) |
| 1.2 Integration Runtime | ✅ | Connector SDK, lease’li sync, `file_import`, `demo_erp` (demo deb belgilangan) |
| 1.3 Ingestion | ✅ | Karantin, versiyali snapshot, idempotent batch |
| 1.4 Semantik qatlam | ✅ | 10 metrika, taqqoslash, hissa; valyutalar qo‘shilmaydi; A01/A02/A04/A06/A07 testlangan |
| 1.5 Tool API | ✅ | Servis tokeni, capability, joriy rol, siyosat, schema, idempotentlik |
| 1.6 AI Runtime | ✅ | FakeProvider bilan ishlaydi; OpenAI adapteri real kalit bilan tekshirilmagan |
| 1.7 Workspace | ✅ | Chat, task, RunAgent, SSE (Last-Event-ID), bekor qilish |
| 1.8 Dashboards | 🟡 | Tool orqali yaratish, doska va tafsilot; foydalanuvchi tahriri/versiyalash/ulashish/CSV eksport — hali yo‘q |

Qolgan ishlar va ma’lum cheklovlar:
- OpenAI bilan real tekshiruv (kalit kerak).
- Dashboard tahriri, ulashish, CSV eksport (TZ 8.2).
- FakeProvider: dashboard nomi xabar matnidan olinadi; jadval sarlavhasida metrika ID’si.
- Dashboard kartochkasi preview’i faqat saqlangan natijadan; “yangilash” (refresh) yo‘q.
- Budjet rezervi faqat identifikator (limit qo‘llanmaydi) — Bosqich 5.
- Ingestion batch’ni xotirada ushlaydi (~200 ming satrgacha mos); katta batch — SQL staging, P1.
- Web ilova (Bosqich 2) boshlanmagan; Node.js o‘rnatilmagan.

### Bosqich 2 — Web ilova: ✅ asosiy ekranlar tayyor

`make stack` — API + 3 worker + web (http://localhost:3010). `make e2e-ui` — Playwright.

| Ish paketi | Holat | Izoh |
|---|---|---|
| 2.1 Skelet, API client, auth | ✅ | Next.js 16, OpenAPI’dan tiplar, CSRF, ro‘yxatdan o‘tish, login, MFA (QR), korxona almashtirish |
| 2.2 Layout | ✅ | Chap menyu, markaz, doimiy chat; mobil: bitta panel + pastki navigatsiya (toshish yo‘q) |
| 2.3 Chat | ✅ | @agent, SSE task kartasi (bosqich + vaqt, soxta foiz yo‘q), bekor qilish, xavfsiz markdown, xato holatlari |
| 2.4 Dashboardlar | ✅ | Doska, tanlash oynasi, ilova ichidagi oyna, drill-down (oy → filial → mahsulot), breadcrumb, sessiyada tiklanish, Escape va fokus qaytishi |
| 2.5 Integratsiya ekrani | ✅ | CSV yuklash, eng mos entity, mapping tahriri, holat qiymatlari, sinxronlash holati |

Brauzer testlari (Playwright, haqiqiy stek): U02, U03, U05, U06, U07 va to‘liq oqim — o‘tadi (3/3).

UI tekshiruvida topilib tuzatilgan xatolar: birinchi xabarda suhbat ID yo‘qolishi; yangi dashboard
doskada ko‘rinmasligi; bir fayl uchun 4 ta mapping muharriri; mapping jadvalida siqilgan
tanlovlar; mobil ekranda gorizontal toshish va Sozlamalarga yo‘l yo‘qligi; FakeProvider’da oylar
oralig‘i, dashboard nomi, jadval sarlavhalari va debitorlik metrika ID’si.

Qolgan ishlar:
- Chat’dagi faol hujjat/dataset “chip”i — hujjatlar bilan (Bosqich 3).
- A’zolarni boshqarish ekrani (API tayyor, UI yo‘q), parolni tiklash sahifalari.
- Dashboard tahriri, ulashish, CSV eksport (backend ham hali yo‘q).
- Ofis sahnasi va jonli agent holatlari — Bosqich 4.
- Tungi rejim ranglari brauzer sozlamasi bo‘yicha; qo‘lda almashtirgich yo‘q.
