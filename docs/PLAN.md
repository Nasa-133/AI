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

### Bosqich 2 — Web ilova: ✅ yakunlandi

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

Bosqich 2 yakunida qo‘shildi:
- A’zolar: ro‘yxat, taklif (Owner/Admin qoidalari), rolni o‘zgartirish, chiqarish; taklifni qabul
  qilish sahifasi; parolni tiklash (so‘rov va yangi parol) sahifalari.
- Dashboard: tahrir (nom, widget nomi/turi/tartibi, o‘chirish) → yangi versiya; versiyalar ro‘yxati;
  ulashish (butun korxona yoki tanlangan a’zolar, ACL backend’da); yangilash (oxirgi snapshot);
  widget bo‘yicha CSV eksport (UTF-8 BOM, formula injection neytrallangan).
- Mavzu: tizim / yorug‘ / qorong‘i, birinchi chizishdan oldin qo‘llanadi (miltillash yo‘q).
- Brauzer testlari: 4 ta ssenariy (asosiy oqim, drill-down, a’zolar va parol, dashboard amallari),
  2 marta ketma-ket barqaror.

Keyingi bosqichlarga o‘tgan ishlar:
- Chat’dagi hujjat “chip”i — Bosqich 3 da qo‘shildi; dataset chip’i — P1.
- Ofis sahnasi va jonli agent holatlari — Bosqich 4.
- Email orqali haqiqiy yuborish (hozir `notifier=log` faqat lokal) — provayder tanlovi kerak.
- Katta eksport uchun fon vazifasi (hozir widget natijasi ≤5000 satr, sinxron).
- Integratsiya testlari lokal stek bilan bir bazani ishlatadi: stek ishlab tursa AI worker test
  run’ini olib ketishi mumkin (beqarorlik). Testlar uchun alohida bazalar — Bosqich 5.

### Bosqich 3 — Hujjatlar: ✅ yakunlandi (FakeProvider bilan; OpenAI tekshiruvi — Bosqich 6)

| Ish paketi | Holat | Izoh |
|---|---|---|
| 3.1 Yuklash va parse | ✅ | DOCX/PDF/TXT, 25 MB limit, tuzilma skaneri, alohida jarayonda parse (timeout, rlimit), skaner PDF → `needs_ocr` |
| 3.2 Bo‘lim/parcha, qidiruv | ✅ | Locator’lar (¶, sahifa, jadval katagi), o‘zbekcha normalizator + FTS prefiks, pgvector, RRF; ACL qidiruvdan oldin |
| 3.3 Embedding | ✅ | `GenerateEmbeddings` → AI Runtime (`ai_runtime.embeddings`) → vektorlar `abo-ai` bucket’da → `EmbeddingsGenerated`; so‘rov vektori `POST /internal/v1/embed` (servis tokeni, 2 s); AI uzilsa matnli rejim va ogohlantirish |
| 3.4 Tahrir | ✅ | `replace_text` patch, DOCX run darajasida, draft versiya, bo‘lim diff’i, promote (409 VERSION_CONFLICT) |
| 3.5 Tool API va agent | ✅ | `search_documents`, `read_document_section`, `compare_document_versions`, `create_document_draft`; Dilnoza (hujjat yordamchisi), koordinator va moliya — faqat o‘qish |
| 3.6 Web | ✅ | Hujjatlar sahifasi (yuklash, holatlar, qidiruv, versiyalar, matn, farq, joriy qilish, yuklab olish, ulashish, o‘chirish); chat’da hujjat chip’i; draft havolasi |

Qabul testlari:
- Integratsiya (Postgres + S3): D01–D05, S03, ACL, chip → `context_refs`, pgvector saqlash va qidiruv.
- Unit: FakeProvider hujjat rejasi — D01 (iqtibos, versiya, locator), D02 (“Hujjatda topilmadi”),
  D06 (hujjat ichidagi buyruq bajarilmaydi), tahrir → draft, noaniq joy → aniqlashtiruvchi savol.
- To‘liq stek (`make e2e`): yuklash → parse → embedding → gibrid qidiruv → iqtibosli javob → AI draft
  → diff → promote.
- Brauzer (Playwright): hujjat oqimi va mobil kenglik (375 px) — 5/5 ssenariy o‘tadi.

Topilib tuzatilgan xatolar: app roli `vector` turini ko‘rmasligi (public sxemaga USAGE, 0010
migratsiyasi) — embedding saqlash va vektor qidiruv ishlamas edi; AI draftdan keyin hujjat
versiyalari yangilanmasligi; chat markdown’ida iqtibos va kursiv yo‘qligi.

Ma’lum cheklovlar:
- `hash` embedding — lokal/demo uchun (kalitsiz); sifatli semantik qidiruv uchun
  `AI_EMBEDDING_PROVIDER=openai` va `OPENAI_EMBEDDING_MODEL` (Bosqich 6 da tekshiriladi).
  Provayder almashtirilsa eski vektorlar o‘lcham bo‘yicha e’tiborsiz qoladi; qayta indekslash buyrug‘i — P1.
- OCR yo‘q (skaner PDF faqat belgilanadi) — P1.
- PDF tahriri draftda DOCX sifatida saqlanadi (asl PDF maketi saqlanmaydi).
- O‘zbek tilidagi qidiruv eval to‘plami — Bosqich 6 eval bilan.

### Bosqich 4 — Virtual ofis: ✅ yakunlandi

| Ish paketi | Holat | Izoh |
|---|---|---|
| 4.1 Agent navbati | ✅ | Har agent uchun korxona bo‘yicha parallel limit (`BUSINESS_AGENT_PARALLEL_LIMIT`, standart 3); to‘lsa — shu agent navbati, o‘rni ko‘rsatiladi, boshqa mutaxassislikka o‘tkazilmaydi; advisory lock bilan poygasiz; slot bo‘shaganda keyingisi yuboriladi; navbatdagi vazifani bekor qilish — AI’ga hech narsa yuborilmaydi |
| 4.2 Holat mapping’i | ✅ | TZ 6 jadvali domen funksiyasi sifatida: step turi AI bosqichidan (read/retrieve/compute/analyze/draft), ustuvorlik, yakuniy holat 30 s dan so‘ng `idle`, aniqlashtirish → `awaiting_input` (javob berilguncha) |
| 4.3 API | ✅ | `GET /api/v1/office` (agent holati, joriy ishlar / limit, navbat, joriy vazifa; boshqa foydalanuvchi vazifasi matni yashirin), `GET /api/v1/tasks`; SSE’da `task.queued` |
| 4.4 Ofis sahnasi | ✅ | DOM/SVG: 5 ta stol, personaj, holat belgisi; strelkalar/Home/End, Enter — agent kartasi (non-modal, Escape va fokus qaytishi); `prefers-reduced-motion`; “Ro‘yxat” ko‘rinishi — sahnasiz muqobil (U01) |
| 4.5 Agent kartasi va Vazifalar | ✅ | Faol vazifalar, bosqich, navbatdagi o‘rin, to‘xtatish, “Chatga yozish” (agent tanlanadi, fokus), suhbatni ochish; Vazifalar sahifasi |

Qabul testlari:
- Unit: holat mapping jadvali, ustuvorlik, 30 s qoida, aniqlashtirish.
- Integratsiya: T01 (limit 1 → o‘rinlar 1, 2; boshqa agent darhol; slot bo‘shaganda navbat siljiydi),
  T05 (navbatdagini bekor qilish), ofis holati progress eventidan, `awaiting_input`.
- To‘liq stek: uchta parallel so‘rov → bittasi ishlaydi, ikkitasi navbatda → hammasi yakunlanadi.
- Brauzer: ofis holati, klaviatura, karta, “Chatga yozish”, ro‘yxat ko‘rinishi (saqlanadi),
  Vazifalar, mobil kenglik; aniqlashtirish → “Javobingizni kutmoqda”, reduced-motion’da animatsiya
  yo‘q (odatiy rejimda borligi ham tekshiriladi). Jami 7/7.

Topilib tuzatilgan xatolar: navbatdagi bir nechta vazifadan eng oxirgisi “joriy” deb ko‘rsatilishi
(endi AI’ga yuborilgan va eng eskisi); vosita xatosi matnida ikki nuqta.

Ma’lum cheklovlar:
- Agent profillari (ism sozlash, doimiy UUID) — P1; hozir standart ismlar.
- `awaiting_approval` holati mapping’da bor, lekin tasdiq talab qiladigan qadam hali yo‘q.
- Ofis holati 2 s polling bilan yangilanadi (backend holatidan); tenant SSE kanali — P1.
- Osilib qolgan (15 daqiqadan oshgan) vazifa slotni band qilmaydi; uni avtomatik `failed` qilish — Bosqich 5.
