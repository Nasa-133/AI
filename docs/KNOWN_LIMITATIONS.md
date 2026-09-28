# Ma’lum cheklovlar (P0 qabul holati)

Bosqichlarda aniqlangan va ongli qoldirilgan cheklovlar. Har biri uchun: ta’sir va reja.
Yuridik/biznes qarorlari (TZ 24) alohida bo‘limda.

## Pilot oldidan hal qilinishi shart

| # | Cheklov | Ta’sir | Reja |
|---|---|---|---|
| 1 | Real OpenAI bilan eval va yuklama hali o‘tkazilmagan (fake provayder bilan o‘tgan) | Model sifati, narxi va kechikishi tasdiqlanmagan | `make eval-openai` (kalit kerak); natija `docs/reports/eval-*-openai.md` |
| 2 | Hosting hududi va OpenAI’ga yuboriladigan ma’lumot bo‘yicha yuridik xulosa yo‘q (TZ 18) | Pilot blocker | Yurist xulosasi; kerak bo‘lsa mahalliy hosting/model (ADR 010 triggerlari) |
| 3 | Email kanali yo‘q (`BUSINESS_NOTIFIER=log`) | Taklif/parol tiklash havolasi faqat logda | Email provayderi tanlovi va adapter |

## Funksional

| Cheklov | Izoh |
|---|---|
| OCR yo‘q | Skaner PDF “OCR kerak” deb belgilanadi (D03) |
| PDF tahriri DOCX sifatida saqlanadi | Asl PDF maketi saqlanmaydi |
| XLSX import yo‘q | CSV (UTF-8) — aniq 415 xabari bilan |
| Haqiqiy ERP’ga ulanish sinalmagan | `erp_api` REST connector va soxta ERP tayyor ([INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md)); faqat to‘liq sinxron, inkremental — P1 |
| Ombor qoldig‘i metrikalari yo‘q | Harakatlar yuklanadi, katalogda qoldiq/aylanma metrikasi — P1 |
| Agent profillari (ism sozlash, doimiy UUID) | Standart ismlar |
| `awaiting_approval` holati | Mapping’da bor, tasdiq talab qiladigan qadam yo‘q |
| Tasodifiy “ofis hayoti” animatsiyalari | Ongli yo‘q — harakat faqat backend holatiga bog‘langan |
| Dataset chip’i chatda | Hujjat chip’i bor; dataset — P1 |
| Katta eksport fon vazifasi | Widget CSV ≤ 5000 satr, sinxron |
| Tenant ma’lumotini to‘liq o‘chirish API’si | Runbook bo‘yicha qo‘lda (docs/runbooks/incidents.md) |

## Xavfsizlik va maxfiylik

| Cheklov | Izoh |
|---|---|
| Psevdonimlash naqsh va ustun nomlariga asoslangan | Erkin matndagi ism-familiya aniqlanmaydi |
| Audit yozuvi amaldan keyin alohida tranzaksiyada | Crash oynasida yozuv yo‘qolishi mumkin (amal saqlanadi) |
| Capability token AI bazasida ochiq matnda | Qisqa muddatli (≤10 daq), faqat AI DB’da |
| `BUSINESS_DATA_ENCRYPTION_KEY` almashtirish migratsiyasi yo‘q | Runbook’da vaqtinchalik tartib |
| NetworkPolicy namunaviy | FQDN egress allowlist klaster gateway’ida sozlanadi |
| Rate limit Redis’siz o‘chiq | Production’da Redis majburiy |

## Operatsion

| Cheklov | Izoh |
|---|---|
| Budjet embedding sarfini hisobga olmaydi | Faqat agent run tokenlari; narx bitta model uchun |
| AI bucket’idagi vaqtinchalik vektor fayllari o‘chirilmaydi | S3 lifecycle qoidasi (infra) |
| Distributed tracing (OpenTelemetry) yo‘q | `traceparent` envelope’da uzatiladi, `trace_id` API javobida; eksport — P1 |
| Yuklama testi bitta mashinada (har servis 1 jarayon) | Production o‘lchami va gorizontal masshtab alohida o‘lchanadi |
| Integratsiya: “Yuklandi” sync tugaganda; analitikaga tayyorlik biroz keyin | 1 mln satrda ~30–40 s farq (docs/reports/load-*.md) |
| Agentlar koridorda bir-biridan qochadi, lekin personaj rasmi katakdan kattaroq | Yonma-yon o‘tishda biroz ustma-ust tushishi mumkin |

## Keyin aniqlanadigan qarorlar (TZ 24)

Birinchi mijoz sohasi, ERP nomi/versiyasi, hosting hududi va yuridik xulosa, saqlash muddatlari,
bir vaqtdagi foydalanuvchilar soni, mijozning metrika lug‘ati, OpenAI model/budjet tanlovi va
tenant/oy xarajat taxmini, jamoa va muddatlar, SaaS tarif va billing modeli.
