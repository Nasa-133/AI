# ADR 010 — Hosting, broker, storage va model tanlovi

Holat: qabul qilindi (P0) · Sana: 2026-09-28

## Kontekst

P0 pilot: ~20 faol foydalanuvchi, 5 parallel analitik vazifa, 1 mln tranzaksiya (TZ 19).
Shaxsiy ma’lumotlarni lokalizatsiya talabi (TZ 18) hosting hududini yuridik xulosaga bog‘laydi.

## Qaror

| Qism | Tanlov | Sabab |
|---|---|---|
| Ma’lumotlar bazasi | PostgreSQL 16 + pgvector | RLS, FTS, vektor qidiruv bitta tizimda |
| Broker | RabbitMQ (topic exchange, retry/DLQ navbatlari) | Publisher confirm, TTL retry, oddiy operatsiya |
| Obyekt ombori | S3-mos (lokal: SeaweedFS) | Vendor’ga bog‘lanmagan API; lokal MinIO image yo‘q edi |
| Kesh/rate limit | Redis | Oddiy, keng tarqalgan |
| Model | OpenAI Responses API (model nomi konfiguratsiyada) | Tool calling, strict schema; provayder porti ortida (ADR 008) |
| Deploy | Konteyner (Docker/Kubernetes), har runtime alohida | Mustaqil masshtablash, NetworkPolicy |

## Muqobillar

- **Kafka** — katta oqimlar uchun kuchli, lekin P0 hajmida operatsion narxi yuqori.
- **Managed vektor DB (Pinecone va h.k.)** — ma’lumot tashqariga chiqadi, ACL ikki joyda.
- **Mahalliy/ochiq model (self-hosted)** — lokalizatsiya uchun qulay, lekin GPU narxi va sifat;
  yuridik xulosa talab qilsa qayta ko‘riladi (provayder porti tayyor).

## Operatsion xarajat (taxmin, pilot)

Uch baza bitta Postgres klasterida (alohida DB/rol), bitta RabbitMQ, bitta S3 bucket to‘plami.
Model xarajati tenant budjeti bilan cheklanadi (standart oylik 50 USD, 80% ogohlantirish).

## Qayta ko‘rish triggerlari

- Hosting hududi bo‘yicha yuridik xulosa (pilot blocker, TZ 18) — O‘zbekistondagi hosting/model.
- Broker navbatlarida doimiy kechikish > 5 s yoki kuniga > 1 mln xabar — Kafka/Redpanda.
- Vektor qidiruv P95 > 1 s yoki > 10 mln parcha — alohida indeks (HNSW sozlash yoki tashqi DB).
- Model narxi tenant budjetidan doimiy oshsa — kichikroq model/routing.

## Oqibat va tekshiruv

`docs/reports/load-*.md` (yuklama), `infra/compose/docker-compose.yml`,
`infra/k8s/network-policies.yaml`.
