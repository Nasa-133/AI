# Ruxsatlar (TZ 3, 12, 13.4, 13.12)

Majburiy tekshiruv **Business Core**da (HTTP entrypoint, application, Governance siyosati va DB
RLS). AI Runtime’dagi rol ro‘yxati faqat modelga qaysi vositalar ko‘rsatilishini belgilaydi —
vakolat manbai emas. Kod: `contexts/governance/domain/tool_policy.py`, `domain/access.py`
(hujjat, dashboard), `entrypoints/http/*`.

## Foydalanuvchi rollari

| Amal | Owner | Admin | Analyst | Viewer |
|---|---|---|---|---|
| A’zolarni taklif qilish, rol o‘zgartirish | ✅ (hammasi) | ✅ (Analyst/Viewer) | ✗ | ✗ |
| Metrika sozlamalarini tasdiqlash | ✅ | ✅ | ✗ | ✗ |
| Integratsiyalar (yuklash, mapping, sync) | ✅ | ✅ | ✗ | ✗ |
| Chatda analitik so‘rov / agent topshirig‘i | ✅ | ✅ | ✅ | faqat hujjat o‘qish |
| Erkin analitik query (`/analytics/queries`) | ✅ | ✅ | ✅ | ✗ |
| Dashboard ko‘rish | ruxsatli | ruxsatli | ruxsatli | ulashilgan |
| Dashboard tahrir / ulashish | egasi yoki Owner/Admin | ✅ | o‘zinikini | ✗ |
| Hujjat yuklash | ✅ | ✅ | ✅ | ✗ |
| Hujjat o‘qish / qidirish | ACL bo‘yicha | ACL bo‘yicha | ACL bo‘yicha | ACL bo‘yicha |
| Hujjat draft yaratish | ACL + rol | ACL + rol | ACL + rol | ✗ |
| Hujjat versiyasini joriy qilish / o‘chirish / ulashish | egasi yoki Owner/Admin | ✅ | egasi | ✗ |
| AI budjeti limitini o‘zgartirish | ✅ | ✗ (ko‘radi) | ✗ (ko‘radi) | ✗ (ko‘radi) |
| Maxfiylik (psevdonimlash) sozlamasi | ✅ | ✗ (ko‘radi) | ✗ (ko‘radi) | ✗ (ko‘radi) |
| Audit jurnalini ko‘rish | ✅ | ✅ | ✗ | ✗ |

Hujjat ACL: egasi har doim; `tenant` ko‘rinishida barcha a’zolar; `private` — egasi va
ulashilgan a’zolar; Owner/Admin hammasini ko‘radi. Qidiruv ACL’ni **qidiruvdan oldin** qo‘llaydi.

## Agent vositalari (agent roli ∩ foydalanuvchi roli)

| Agent | Analitika o‘qish | Dashboard yaratish | Hujjat o‘qish | Hujjat draft |
|---|---|---|---|---|
| Bosh yordamchi (coordinator) | ✅ | ✅ | ✅ | ✗ |
| Ali — savdo | ✅ | ✅ | ✗ | ✗ |
| Madina — moliya | ✅ | ✅ | ✅ | ✗ |
| Sardor — ombor | ✅ | ✅ | ✗ | ✗ |
| Dilnoza — hujjatlar | ✗ | ✗ | ✅ | ✅ |

Agent vakolati topshiriq bergan foydalanuvchidan oshmaydi: Viewer topshirig‘ida faqat hujjat
o‘qish. Har Tool API chaqirig‘ida: servis tokeni → capability imzosi va muddati → a’zolik va
**joriy** rol DB’dan → siyosat → argumentlar schema’si → idempotentlik (`task_id` +
`tool_call_id`). Rol vazifa davomida olib tashlansa, keyingi chaqiriq rad etiladi.

## Tekshiruv

`tests/integration/test_tool_api.py`, `test_members_http.py`, `test_documents.py` (ACL),
`test_audit.py`, `test_budget.py`, `test_privacy.py`; eval S-01…S-10 (`tools/eval/run_eval.py`).
