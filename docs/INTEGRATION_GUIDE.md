# Tashqi tizim (ERP) bilan integratsiya — yo‘riqnoma

Bu hujjat AI Business Office’ni korxonaning hisob tizimiga (ERP, 1C, savdo/ombor dasturi) ulash
uchun. Ikki o‘quvchi uchun yozilgan:

- **Joriy qiluvchi / administrator** — 1–5, 8–9-bo‘limlar: nima kerak, qanday ulanadi, qanday
  tekshiriladi.
- **Dasturchi** — 4, 6, 7-bo‘limlar: API shartnomasi, yangi connector yozish, soxta ERP bilan sinash.

Hozir lokal/demo muhitda **soxta ERP** (`tools/fake_erp`) ishlaydi. U haqiqiy ERP kabi REST API
beradi va AI agentlar shu orqali ishlaydi. Haqiqiy ERP ulanganda faqat URL va kalit o‘zgaradi.

---

## 1. Qanday ishlaydi

```
ERP ──(o‘qish, faqat read-only kalit)──► Integration Runtime ──► kanonik batch (S3)
                                          connector + mapping         │ SourceBatchReady
                                                                      ▼
AI agentlar ◄── Tool API (deterministik hisob) ◄── Business Core: tasdiqlangan snapshot
```

Qoidalar:

1. ERP bilan faqat **Integration Runtime** gaplashadi. ERP manzili va kaliti faqat uning
   muhitida saqlanadi. Business Core, AI Runtime va brauzer ERP’ni ko‘rmaydi.
2. Ma’lumot faqat **o‘qiladi**. ERP’ga hech narsa yozilmaydi.
3. ERP maydonlari **kanonik modelga** (4-bo‘lim) mapping orqali o‘giriladi. Mapping’ni odam
   tasdiqlaydi; tasdiqlanmagan mapping ishlatilmaydi.
4. Har sinxron — to‘liq **snapshot**. Yangi snapshot faqat to‘liq va muvaffaqiyatli o‘qilganda
   e’lon qilinadi. Sinxron yarim yo‘lda uzilsa, oxirgi to‘liq snapshot bilan ishlash davom etadi
   (qabul mezoni A05).
5. **Bir nechta manba** (masalan, ikki filialning alohida ERP’lari yoki ERP + CSV) qo‘shib
   hisoblanadi. **Bitta bazani ikki marta ulash mumkin emas**: bir xil tizim yoki bir xil fayl
   shu obyekt uchun qayta ulanmaydi (ulashda rad etiladi). Boshqa yo‘l bilan ulansa ham, yangi
   manbaning yozuvlari yarmidan ko‘pi boshqa faol manbada bo‘lsa, u **“takroriy baza”** deb
   belgilanadi va hisobga olinmaydi. Qaysi biri ishlatilishini Integratsiyalar sahifasida
   **“Shu manbani ishlatish”** bilan tanlaysiz (masalan, eski CSV o‘rniga ERP).
6. Noto‘g‘ri satrlar (sana buzilgan, miqdor ≤ 0, takroriy ID) **karantinga** tushadi. Ular
   yashirilmaydi: sinxron natijasida soni va misollari ko‘rsatiladi.
7. AI raqamni o‘zi o‘ylab topmaydi. U faqat snapshot ustidagi deterministik so‘rov natijasini
   aytadi va manbani (snapshot, query ID) ko‘rsatadi.

---

## 2. Ulash usulini tanlash

| Usul | Qachon | Connector | Holat |
|---|---|---|---|
| **REST API** (tavsiya) | ERP’da API bor yoki ERP dasturchisi 4-bo‘limdagi shartnomaga mos endpoint qila oladi | `erp_api` | ✅ tayyor |
| **CSV eksport** | Tez boshlash; ERP’dan qo‘lda yoki jadval bo‘yicha eksport | `file_import` | ✅ tayyor |
| **ERP’ning o‘z API’si** (1C OData, SAP va h.k.) | API bor, lekin shakli boshqa, ERP tomonini o‘zgartirib bo‘lmaydi | yangi connector (6-bo‘lim) | ishlab chiqiladi |
| **DB view** (read-only) | API yo‘q, faqat bazaga kirish mumkin | yangi connector | P1 |

**Eng oson yo‘l:** ERP tomonida 4-bo‘limdagi 4 ta endpoint’ni chiqaradigan yupqa qatlam
(masalan, 1C HTTP-servis yoki kichik proksi) yasash. Bizning tomonda kod o‘zgarmaydi — faqat
sozlama o‘zgaradi.

---

## 3. Joriy qilishdan oldin: ERP egasidan olinadigan narsalar

| # | Nima | Nega |
|---|---|---|
| 1 | API manzili (test va production) | Avval test muhitida sinaladi |
| 2 | **Faqat o‘qish** huquqli API kaliti (alohida texnik foydalanuvchi) | Kalit sizsa ham ERP’ga yozib bo‘lmasin |
| 3 | Qaysi obyektlar beriladi: savdo satrlari, qaytarishlar, ombor harakatlari, debitorlik | 4-bo‘lim |
| 4 | Hujjat holatlari ro‘yxati (masalan: provedeno / chernovik / otmenen) | Faqat “tasdiqlangan” satrlar hisobga olinadi |
| 5 | Summalar QQS bilanmi yoki QQSsiz, chegirma summadan ayrilganmi | Metrika sozlamalari (sof tushum to‘g‘ri chiqishi uchun) |
| 6 | Valyutalar va vaqt zonasi | Turli valyutalar hech qachon qo‘shilmaydi |
| 7 | Tarix chuqurligi (masalan, 2 yil) va kunlik hajm | Birinchi sinxron vaqti, sahifa hajmi |
| 8 | Chaqiruv limiti (rate limit) va texnik ishlar oynasi | Avtomatik sinxron oralig‘i |
| 9 | Nazorat hisoboti: bir oy uchun ERP’dagi savdo summasi | Ulangandan keyin raqamlarni solishtirish |
| 10 | Tarmoq: serverimiz IP’si ERP’ga ruxsat etilganmi | Egress allowlist (`docs/runbooks/deploy.md`) |

Yuridik tomoni: ma’lumot qayerda saqlanishi va OpenAI’ga nima yuborilishi bo‘yicha xulosa kerak
(`docs/KNOWN_LIMITATIONS.md`, TZ 18). Shaxsga oid maydonlar psevdonimlanadi (`docs/PERMISSIONS.md`).

---

## 4. Ma’lumot talablari va namunaviy ERP API shartnomasi

### 4.1. Obyektlar va majburiy maydonlar (kanonik model)

To‘liq sxemalar: `contracts/canonical/*.v1.json`. Pul va miqdor **satr** ko‘rinishidagi o‘nlik son
(`"2070000.00"`), float emas. Sana-vaqt — ISO 8601, vaqt zonasi bilan (`2026-09-28T10:05:00+05:00`).

**Savdo satri** (`sales.order_line`) — har hujjatning har mahsulot qatori alohida:

| Maydon | Majburiy | Ma’nosi |
|---|---|---|
| source_id | ✅ | Satrning ERP’dagi o‘zgarmas ID’si (takrorlanmaydi) |
| source_revision | — | O‘zgarish belgisi (masalan, `updated_at`) |
| document_number | ✅ | Hujjat raqami |
| occurred_at | ✅ | Hujjat sanasi-vaqti (zona bilan) |
| branch_code, branch_name | ✅ | Filial |
| product_code, product_name | ✅ | Mahsulot |
| customer_code | ✅ | Mijoz kodi |
| customer_name | — | Mijoz nomi (psevdonimlanadi) |
| quantity, unit_price, gross_amount | ✅ | Miqdor, narx, summa (chegirmagacha) |
| discount_amount | ✅ | Chegirma (bo‘lmasa `0`) |
| vat_amount | ✅ | QQS summasi |
| currency | ✅ | ISO 4217 (`UZS`, `USD`) |
| status | ✅ | Holat → `confirmed` / `draft` / `cancelled` (mapping’da xaritalanadi) |
| cost_amount | — | Tannarx (bo‘lmasa foyda hisobida alohida ko‘rsatiladi) |

**Qaytarish** (`sales.return`): source_id, original_order_source_id (bo‘lsa), occurred_at,
branch_code, product_code, customer_code, quantity, amount, vat_amount, currency, status, cost_amount.

**Ombor harakati** (`inventory.movement`): source_id, occurred_at, warehouse_code, branch_code,
product_code, quantity_delta (kirim +, chiqim −), movement_type (`receipt`, `sale`, `return`,
`transfer_in`, `transfer_out`, `adjustment`), unit_cost, currency.

**Debitorlik** (`finance.receivable`): source_id, customer_code, customer_name, document_number,
issued_on, due_on (sana), amount, paid_amount, currency, branch_code. Qoldiq = amount − paid_amount.

Ikkita mapping sozlamasi (tasdiqlash oynasida doimiy qiymat sifatida beriladi):
`discount_already_deducted` (chegirma summadan ayrilganmi) va `amount_includes_vat` (summa QQS
bilanmi). Noto‘g‘ri tanlansa, sof tushum ikki marta ayriladi yoki ortiqcha chiqadi.

### 4.2. REST API shartnomasi (`erp_api` connector kutadigan shakl)

Soxta ERP aynan shu shartnomani bajaradi, shuning uchun uni namuna sifatida ishlatish mumkin
(7-bo‘lim).

**Autentifikatsiya:** har so‘rovda `Authorization: Bearer <kalit>`.

**Endpoint’lar** (hammasi `GET`):

| Endpoint | Obyekt |
|---|---|
| `/api/v1/sales-invoice-lines` | savdo satrlari |
| `/api/v1/sales-returns` | qaytarishlar |
| `/api/v1/stock-movements` | ombor harakatlari |
| `/api/v1/receivables` | debitorlik |
| `/api/v1/health` | holat (kalitsiz) |

**Parametrlar:**

| Parametr | Ma’nosi |
|---|---|
| `limit` | Sahifa hajmi (1–1000; connector standart 500 so‘raydi) |
| `cursor` | Oldingi javobdagi `next_cursor`; bo‘lmasa birinchi sahifa |
| `updated_since` | ISO vaqt: faqat shundan keyin o‘zgarganlar (inkremental — P1, hozir connector to‘liq o‘qiydi) |

**Javob** (`200 OK`, `application/json`):

```json
{
  "data": [
    {"line_id": "S26092800801", "invoice_no": "SV-260928-008",
     "posted_at": "2026-09-28T10:05:00+05:00", "branch_code": "FAR", "branch_name": "Farg‘ona",
     "item_code": "P127", "item_name": "Shampun 5 li", "customer_code": "M0426",
     "customer_name": "Sharq Trade MChJ", "qty": "1", "price": "162600.00",
     "amount": "162600.00", "discount": "4878.00", "vat": "18926.64", "cost": "136584.00",
     "currency": "UZS", "state": "posted", "updated_at": "2026-09-28T10:05:00+05:00"}
  ],
  "next_cursor": "eyJvIjogNTAwLCAidCI6IC4uLn0",
  "as_of": "2026-09-28T05:12:35+00:00",
  "total": 20411
}
```

**Majburiy xatti-harakatlar** (ular bo‘lmasa raqamlar noto‘g‘ri yoki beqaror bo‘ladi):

1. **Barqaror tartib va izchil kursor.** Kursor sinxron boshlangan paytdagi holatni (`as_of`)
   saqlasin. Sahifalash davomida yangi hujjat qo‘shilsa ham sahifalar siljimasin: satr
   tushib qolmasin va takrorlanmasin.
2. **O‘zgarmas ID.** `line_id` / `return_id` / … hujjat tahrirlanganda o‘zgarmasin. O‘chirilgan
   yoki bekor qilingan hujjat `state: cancelled` bilan qaytsin yoki ro‘yxatdan chiqsin (to‘liq
   snapshot — ro‘yxatda yo‘q satr o‘chirilgan hisoblanadi).
3. **Pul — satr.** `"2070000.00"`. JSON son kelsa ham connector uni satrga o‘giradi, lekin
   float yaxlitlash xatosi xavfi bor.
4. **Vaqt zonasi bilan sana.** `2026-09-28T10:05:00+05:00`. Zonasiz vaqt noaniq.
5. **Xato kodlari:**

| Kod | Ma’nosi | Connector nima qiladi |
|---|---|---|
| 401 / 403 | Kalit noto‘g‘ri yoki ruxsat yo‘q | Darhol to‘xtaydi (qayta urinmaydi), “kalitni tekshiring” xabari |
| 404 | Endpoint yo‘q | To‘xtaydi |
| 429 | Limit | `Retry-After` bo‘yicha kutib, sahifani 3 marta qayta so‘raydi |
| 5xx, timeout, tarmoq | Vaqtincha nosozlik | 3 marta qayta so‘raydi; bo‘lmasa sinxron “xato” bo‘ladi va keyingi siklda qayta uriniladi |

ERP’da maydon nomlari boshqacha bo‘lsa (masalan, `DocNumber`, `Sklad`), shartnomani o‘zgartirish
shart emas: mapping oynasida ustunlar qo‘lda ulanadi. Faqat endpoint yo‘llari, `data` /
`next_cursor` shakli va Bearer autentifikatsiyasi mos bo‘lishi kerak. Ular ham mos kelmasa —
6-bo‘lim.

---

## 5. Bosqichma-bosqich ulash

### 5.1. Sozlama (server, Integration Runtime muhiti)

```bash
INTEGRATION_ERP_API_URL=https://erp.korxona.uz        # lokal: http://localhost:8070 (soxta ERP)
INTEGRATION_ERP_API_KEY=<read-only kalit>              # secret manager’da; kodga/logga yozilmaydi
INTEGRATION_ERP_API_PAGE_SIZE=500                      # ixtiyoriy
```

`INTEGRATION_ERP_API_URL` bo‘sh bo‘lsa, `erp_api` connector yoqilmaydi. Sozlamadan keyin Integration
worker qayta ishga tushiriladi.

Business muhitida avtomatik sinxron oralig‘i:

```bash
BUSINESS_ERP_AUTO_SYNC_SECONDS=900    # standart 15 daqiqa; 0 — faqat qo‘lda
```

### 5.2. Ilovada (Owner yoki Admin)

1. **Sozlamalar → Hisob qoidalari (metrika sozlamalari)**: QQS va chegirma qoidasini tasdiqlash. Tasdiqlanmaguncha
   moliyaviy xulosa chiqmaydi.
2. **Integratsiyalar → “ERP ulash (API)”**. To‘rtta manba yaratiladi: ERP: Sotuvlar,
   Qaytarishlar, Ombor harakatlari, Debitorlik. Har biri ERP’dan ustunlar va namunaviy satrlarni
   o‘qiydi (“Manba o‘qilmoqda”).
3. Har manbada **mapping’ni tekshirib tasdiqlash**:
   - ustunlar kanonik maydonlarga ulangan bo‘ladi (soxta ERP va shartnomaga mos ERP uchun 100%
     moslik);
   - **holat qiymatlari** (masalan, `posted` → `confirmed`) va ombor uchun **harakat turlari**
     tekshiriladi. Xaritaga kirmagan qiymatli satr karantinga tushadi;
   - majburiy maydon ulanmagan bo‘lsa, tugma bosilmaydi.
4. **“Sinxronlash”**. Holat: Sinxronlanmoqda → Yuklandi. Rad etilgan satrlar bo‘lsa, soni va
   misoli ko‘rsatiladi.
5. Keyingi sinxronlar avtomatik (5.1). Xato bo‘lsa, manba “Xato” holatida ko‘rinadi. ERP tiklangach
   keyingi siklda o‘zi qayta urinadi yoki “Qayta sinxronlash” tugmasi bosiladi.

### 5.3. Tekshirish (majburiy — ishga tushirishdan oldin)

1. Chatda: “Ali, 2026 avgust oyidagi sof savdo qancha?”. Javobni ERP’ning shu oy hisoboti bilan
   solishtiring (3-bo‘lim, 9-band). Farq bo‘lsa, odatda sabab: QQS/chegirma sozlamasi, holat
   xaritasi yoki bekor qilingan hujjatlar.
2. “Filiallar bo‘yicha” va “mahsulotlar bo‘yicha” kesimlar ERP bilan mos.
3. Debitorlik: “Madina, avgust oxiridagi debitorlik qoldig‘i qancha?”.
4. Karantindagi satrlar sababi tushunarli (ERP egasi bilan kelishilgan).
5. Filial bo‘yicha ruxsatlar kerak bo‘lsa: **Sozlamalar → A’zolar → Filiallar** (S02).

---

## 6. Yangi connector yozish (dasturchi uchun)

ERP API’si 4.2-shartnomaga keltirilmasa, Integration Runtime’da yangi connector yoziladi.
Core, AI va Web kodi o‘zgarmaydi (qabul mezoni I01). Bunga faqat 5-qadamdagi bir qator istisno.

1. **Port**: `services/integration_runtime/src/integration_runtime/ports/connector.py`.
   - `manifest`: `connector_id` (`[a-z][a-z0-9_]+`), versiya, qo‘llanadigan obyektlar.
   - `discover_schema(source)`: har obyekt uchun ustunlar va ≤20 namunaviy satr.
   - `read_rows(source, entity)`: `(tartib raqami, {ustun: xom satr | None})` oqimi. Tip
     o‘girish, validatsiya va karantin connector’da **qilinmaydi** — bu Sync Engine’ning ishi.
   - Xatolar: vaqtincha nosozlik — `SourceUnavailable` (runner qayta uriniladi); kalit yoki
     format xatosi — `InvalidSource` (qayta urinilmaydi).
2. **Namuna**: `adapters/erp_api.py` (REST, kursor, retry, `Retry-After`).
3. **Mapping shabloni** (ixtiyoriy, lekin tavsiya etiladi): `domain/templates.py`. Shablon
   bo‘lsa, tasdiqlash oynasida ustunlar avtomatik ulanadi. Noma’lum ustun hech qachon taxmin
   qilinmaydi.
4. **Ro‘yxatga olish**: `bootstrap/settings.py` (URL/kalit — `SecretStr`), `bootstrap/worker.py`.
5. **Business’da bir qator**: `contexts/integrations/domain/sources.py` — `CONNECTORS` (fayl
   kerakmi) va kerak bo‘lsa `AUTO_SYNC_CONNECTORS`; `entrypoints/http/integrations.py` — `Literal`;
   `make openapi` va `npm run api:types`; UI tugmasi (`app/(app)/integrations/page.tsx`).
6. **Testlar** (majburiy):
   - `tests/unit/test_connector_conformance.py` — connector’ni ro‘yxatga qo‘shish: manifest,
     discovery, xom satrlar, Sync Engine’dan kanonik sxemaga mos batch;
   - xatolar: noto‘g‘ri kalit, uzilish, 429, izchil sahifalash — namuna `tests/unit/test_erp_api.py`;
   - tizim testi: `tests/system/test_erp.py` (ulash → mapping → sinxron → agent javobi).
7. **Tekshiruv**: `make check`, `make e2e`.

---

## 7. Soxta ERP (lokal va demo)

`tools/fake_erp` — 4.2-shartnomani bajaradigan REST API (FastAPI). Ma’lumot sintetik, haqiqiy
korxona ma’lumoti emas.

- **Tarix**: 2025-09-01 — 2026-08-31 (demo to‘plam: ~19 ming savdo satri, 750 qaytarish, 18,6 ming
  ombor harakati, 2,1 ming debitorlik).
- **“Jonli” qism**: 2026-09-01 dan bugungacha har kun uchun yangi hujjatlar deterministik
  generatsiya qilinadi (kuniga ~18 hujjat, ish kunlari ko‘proq). Faqat vaqti kelganlari ko‘rinadi.
  Shuning uchun bir necha daqiqadan keyin qayta sinxronda yangi savdolar paydo bo‘ladi. Har yangi
  savdoga ombor chiqimi, ~2% qaytarish va ~30% nasiya (debitorlik) qo‘shiladi.
- Tarixda karantin holatlari ataylab bor (buzilgan sana, takroriy ID, miqdor 0) — ular sinxron
  natijasida ko‘rinadi.

**Ishga tushirish:**

```bash
make stack        # API + worker’lar + web + soxta ERP (http://localhost:8070) birga
# yoki alohida:
make fake-erp
```

Kalit: `fake-erp-dev-key` (`FAKE_ERP_API_KEY` bilan o‘zgartiriladi; `make stack` Integration
Runtime’ga o‘zi uzatadi).

**Qo‘lda tekshirish:**

```bash
curl -s localhost:8070/api/v1/health
curl -s -H "Authorization: Bearer fake-erp-dev-key" \
  "localhost:8070/api/v1/sales-invoice-lines?limit=2" | python3 -m json.tool
curl -s -H "Authorization: Bearer fake-erp-dev-key" localhost:8070/admin/stats
```

**Nosozlikni simulyatsiya qilish** (degradatsiya va A05 mashqi uchun):

```bash
# 60 soniya texnik ishlar (503) — sinxron “Xato”, oxirgi snapshot bilan ishlash davom etadi
curl -s -X POST -H "Authorization: Bearer fake-erp-dev-key" "localhost:8070/admin/outage?seconds=60"
# tasodifiy 429 (30% so‘rov) — connector qayta urinib yutadi
FAKE_ERP_FAIL_RATE=0.3 make fake-erp
```

**AI bilan ishlatish:** Integratsiyalar → “ERP ulash (API)” → mapping’larni tasdiqlash →
sinxron. Keyin chatda: “Ali, 2026 sentabr oyidagi savdoni filiallar bo‘yicha ko‘rsat”,
“Madina, avgust oxiridagi debitorlik qoldig‘i qancha?”. Ma’lumot 15 daqiqada avtomatik yangilanadi.

---

## 8. Muammolar va yechimlar

| Ko‘rinish | Sabab | Nima qilish |
|---|---|---|
| “ERP kaliti noto‘g‘ri yoki ruxsat yo‘q” | 401/403 | Kalitni va texnik foydalanuvchi huquqini tekshirish, worker’ni qayta ishga tushirish |
| “ERP javob bermayapti (HTTP 503)” / “aloqa yo‘q” | ERP texnik ishlarda yoki tarmoq | ERP holati; tarmoq allowlist. Tiklangach o‘zi qayta sinxronlanadi |
| Manba uzoq “o‘qilmoqda” / “Kutilmoqda” | Integration worker ishlamayapti | Worker logi (`.dev-logs/integration-worker.log`) |
| “N ta satr o‘qilmadi” | Karantin: sana, miqdor, takroriy ID, xaritada yo‘q holat | Misollarni ERP egasiga berish; holat xaritasini to‘ldirish (yangi mapping versiyasi) |
| Raqam ERP hisobotidan farq qiladi | QQS/chegirma sozlamasi, holat xaritasi | Hisob qoidalari va mapping’dagi `discount_already_deducted`, `amount_includes_vat` |
| Dashboard’da “Eskirgan” | Sinxron uzoq vaqt yakunlanmadi | Integratsiyalar sahifasidagi manba holati |
| “Filialga ruxsat yo‘q” | Foydalanuvchiga filial doirasi berilgan (S02) | Sozlamalar → A’zolar |

Chuqurroq: `docs/runbooks/incidents.md` (“Integration Runtime ishlamayapti”),
`docs/runbooks/replay.md` (yo‘qolgan xabarlarni qayta yuborish).

---

## 9. Xavfsizlik bo‘yicha qisqacha

- Kalit **faqat o‘qish** huquqli va alohida texnik foydalanuvchiga tegishli. Muddatli
  almashtirish tartibi — `docs/runbooks/incidents.md#kalit-almashtirish`.
- Kalit faqat Integration Runtime muhitida (`INTEGRATION_ERP_API_KEY`, `SecretStr`). Log,
  event, Core va AI’ga chiqmaydi.
- Tarmoq: Integration Runtime’dan faqat ERP manziliga egress (`infra/k8s/network-policies.yaml`).
  ERP tomonida esa faqat bizning IP’dan kirish.
- Shaxsga oid maydonlar (mijoz nomi, telefon va h.k.) AI’ga yuborilishdan oldin psevdonimlanadi.

## 10. Hozirgi cheklovlar

- Faqat to‘liq sinxron. `updated_since` bilan inkremental sinxron — P1 (API shartnomada bor).
- Bitta manba — bitta obyekt. ERP 4 ta manba sifatida ulanadi (“ERP ulash” tugmasi hammasini
  yaratadi), har birining mapping’i alohida tasdiqlanadi.
- Takroriy baza yozuv ID’lari (source_id) bo‘yicha aniqlanadi: ikki tizim bir hujjatga turli ID
  bersa, takror sezilmaydi — bunday holatda manbalardan birini qo‘lda o‘chirib qo‘ying.
- Ombor harakatlari yuklanadi, lekin qoldiq/aylanma metrikalari katalogda hali yo‘q — ombor
  qoldig‘i bo‘yicha savollarga hozircha raqamli javob berilmaydi (P1).
- ERP’ga yozish (hujjat yaratish) — rejada yo‘q (faqat o‘qish).
