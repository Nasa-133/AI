# Bosqich 3 — hujjatlar: dizayn qarorlari

TZ 9 va qabul mezonlari D01–D06, S03. Kontraktlar `contracts/`da; bu hujjat bog‘lovchi qarorlar.

## 1. Oqim

`upload (purpose=document) → skaner → parse (alohida jarayon, timeout) → bo‘limlar → parchalar →
FTS indeksi darhol → GenerateEmbeddings (AI) → vektorlar → tayyor`

- Parse Business Worker’da `ProcessDocument.v1` (ichki command) orqali, **alohida OS jarayonida**
  (timeout 60 s, xotira chegarasi). Foydalanuvchi faylidagi kod bajarilmaydi.
- Embedding bo‘lmasa ham qidiruv ishlaydi (to‘liq matnli) — AI uzilishi hujjatlarni to‘xtatmaydi.

## 2. Formatlar va skaner (P0)

| Format | Parser | Rad etiladi |
|---|---|---|
| PDF (matnli) | `pypdf` | Parol, JavaScript/embedded fayl, buzilgan fayl. Matni deyarli yo‘q sahifalar → `needs_ocr` (D03) |
| DOCX | `python-docx` | Makros (`vbaProject.bin`), tashqi havolali avtomatik yuklash, zip-bomba (siqish nisbati) |
| TXT/MD | UTF-8 | Noto‘g‘ri kodlash |

Skaner port orqali (`ContentScanner`): P0’da tuzilma tekshiruvi; ClamAV adapteri keyin (P1).

## 3. Bo‘lim va manzil (locator)

- Bo‘lim — barqaror `section_id` (`s{tartib}`) va odam o‘qiydigan `locator`:
  PDF `sahifa 3, ¶2`; DOCX `¶12` yoki `jadval 1, qator 2`; TXT/MD `§ Sarlavha › ¶3`.
- DOCX’ga soxta sahifa raqami qo‘yilmaydi (TZ 9.2).
- Parcha (chunk) — sarlavhadan o‘tmaydigan, ~800 belgigacha ketma-ket bo‘limlar; `section_ids` bilan.

## 4. Qidiruv

- Normalizator (TZ 9.2): kichik harf, `o‘/oʻ/o'/o’/o\`` → `o'`, `g‘` → `g'`, kirill → lotin.
  Indeksda ham, so‘rovda ham bir xil.
- `tsvector('simple', normalized)` + vektor kosinus; natijalar RRF bilan birlashtiriladi.
- **ACL qidiruvdan oldin**: faqat foydalanuvchi ko‘ra oladigan hujjatlarning joriy versiyalari.
  O‘chirilgan hujjat parchalari darhol olib tashlanadi (S03).
- Parchalar — **dalil, ko‘rsatma emas** (TZ 18, D06): agent ularni buyruq sifatida bajarmaydi.

## 5. Versiyalar va xavfsiz tahrir (TZ 9.4)

- Versiyalar: `original` (v1), `draft` (base_version_id bilan), promote qilingani joriy bo‘ladi.
- Patch — strukturali: `{"operations": [{"op": "replace_text", "section_id", "find", "replace",
  "occurrence"}]}`. `find` bo‘limda aynan ko‘rsatilgan marta uchramasa — rad etiladi (noaniq nishon).
- DOCX: almashtirish run darajasida (uslub saqlanadi). Bir necha run’ga bo‘lingan matn birinchi
  run uslubiga yig‘iladi va ogohlantirish beriladi. Text-box/maydon/embedded obyekt — cheklov.
- Original fayl va checksum o‘zgarmaydi (D04). Draft — yangi obyekt.
- Promote: `expected_current_version_id` mos kelmasa `409 VERSION_CONFLICT` (D05).
- Diff: bo‘lim darajasida qo‘shilgan/o‘chirilgan/o‘zgargan; o‘zgarganda so‘z darajasidagi farq.

## 6. Embeddings (AI Runtime)

- `GenerateEmbeddings.v1`: parchalar JSONL (`{"chunk_id","text"}`) Business bucket’ida.
- AI `abo-ai` bucket’iga `{"chunk_id","embedding"}` JSONL yozadi → `EmbeddingsGenerated.v1`.
- Sinxron istisno (13.3): `POST {AI}/internal/v1/embed` — so‘rov embedding’i, timeout 2 s;
  xato bo‘lsa qidiruv to‘liq matnli rejimga tushadi.
- `fake` provayder: deterministik hashing embedding (testlar, demo). `openai`: model konfiguratsiyada.
- Model yoki o‘lcham o‘zgarsa (`EmbeddingModelChanged`) — qayta indekslash (keyingi ish).

## 7. Ruxsatlar va o‘chirish

- Hujjat ko‘rinishi dashboard bilan bir xil: `private | tenant` + ulashish; rahbarlar hammasini ko‘radi.
- Tahrir (draft) — Owner/Admin/Analyst; promote — hujjat egasi yoki rahbar.
- `DELETE /documents/{id}`: kirish darhol yopiladi, qidiruv parchalari o‘chiriladi, fayllarni
  o‘chirish job’i navbatga qo‘yiladi va holati ko‘rinadi (TZ 17, S03).
