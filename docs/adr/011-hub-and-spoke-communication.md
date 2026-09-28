# ADR 011 — Hub-and-spoke va aloqa matritsasi

Holat: qabul qilindi · Sana: 2026-09-26

## Kontekst

Uch runtime bir-biri bilan erkin gaplashsa, bog‘liqliklar grafi chigallashadi, xatolar zanjir
bo‘lib tarqaladi va xavfsizlik chegarasi yo‘qoladi. TZ 13.3 yopiq aloqa matritsasini talab qiladi.

## Qaror

- **Business Core — hub**; AI va Integration — spoke. Spoke ↔ spoke aloqasi yo‘q.
- Asinxron (broker): Core → AI (`RunAgent`, `CancelAgentRun`, `GenerateEmbeddings`),
  Core → Integration (`SyncSource`, `DiscoverSchema`, `ConfigureSource`), spoke’lardan eventlar.
- Sinxron chaqiruvlar ro‘yxati yopiq:
  1. AI → Core Tool API (servis tokeni + delegated capability, har chaqiriqda joriy rol);
  2. Core → AI `POST /internal/v1/embed` (2 s timeout, xatoda full-text qidiruv).
- Katta ma’lumot broker orqali emas, object storage’dagi batch havolasi (checksum bilan).
- Yangi sinxron endpoint yoki spoke ↔ spoke aloqa faqat yangi ADR bilan.

## Muqobillar

- **Service mesh bilan erkin REST.** Moslashuvchan, lekin matritsani majburlash konventsiyaga
  qoladi va sinxron zanjirlar kechikishni ko‘paytiradi.
- **Hammasi faqat broker orqali (Tool API ham).** To‘liq asinxron, lekin agent tool loop’ida
  har chaqiriq navbatdan o‘tadi — kechikish va murakkablik oshadi.

## Trade-off

Core markaziy nuqta — uning mavjudligi muhim (degradatsiya rejimlari bilan yumshatilgan).

## Oqibat va tekshiruv

- `tests/architecture/test_boundaries.py` — servislar bir-birining kodini import qilmaydi.
- Tarmoq: compose `networks` (Integration faqat `data` tarmog‘ida), `infra/k8s/network-policies.yaml`.
- Credential: `test_data_ownership.py` (I06). Degradatsiya: `scripts/degradation.sh`.
