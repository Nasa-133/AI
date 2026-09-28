# P0 qabul matritsasi (TZ 20, 13.15)

Har mezon uchun **avtomatik dalil** (test yoki skript) va uni ishga tushirish yo‘li.
Holat: ✅ — avtomatik test bilan tasdiqlangan; ⚠️ — qisman / shart bilan (izohda);
⏳ — tashqi shart kutilmoqda.

Ishga tushirish:

| Buyruq | Nima tekshiradi |
|---|---|
| `make check` | lint, mypy, import-linter, unit + integratsiya (real Postgres/RabbitMQ/S3/Redis), kontrakt, web |
| `make e2e` | `tests/system` — real jarayonlar (API, 3 worker) bilan to‘liq oqim |
| `make degradation` | I03, I05, broker restart (gate 5/7) |
| `cd apps/web && npx playwright test` | UI oqimlari (brauzerda) |
| `make eval` / `make eval-openai` | release eval to‘plami (fake / real OpenAI) |
| `make load`, `./scripts/restore-drill.sh`, `make migration-check` | yuklama, tiklash, migratsiya |

Oxirgi natijalar (2026-09-28): `make check` — Business 179, AI 74, Integration 28,
messaging 18, repo 236, web 37; `make e2e` 3/3; `make degradation` 5/5; Playwright 11/11;
eval (fake) barcha toifalar 100%; yuklama — TZ 19 maqsadlari bajarildi; restore RTO 57 s.

## TZ 20 — ssenariylar

### Analitika

| ID | Holat | Dalil |
|---|---|---|
| A01 | ✅ | `services/business/tests/integration/test_analytics.py::test_a01_golden_numbers` (850 / 350 / 41.18%), `tests/unit/analytics/test_metrics.py::test_a01_*`; eval: 42 raqamli holat |
| A02 | ✅ | `test_analytics.py::test_a02_a07_growth_rules`, `test_metrics.py::test_a02_growth_from_zero_is_absolute_only` |
| A03 | ✅ | `test_analytics.py::test_a03_partial_month_and_mixed_currencies` — valyuta bo‘yicha ajratish (qo‘shilmaydi), “Davr hali tugamagan” izohi; noma’lum metrika — bitta aniqlashtiruvchi savol (`ai_runtime .../test_planner.py::test_unknown_metric_asks_one_question`) |
| A04 | ✅ | `test_analytics.py::test_a04_snapshot_versioning_keeps_old_answers`; dashboard widget chat natijasining `query_spec_id` siga bog‘lanadi (`test_dashboards_http.py`), `tests/system/test_vertical_slice.py::test_csv_to_answer_to_dashboard` |
| A05 | ✅ | Integration: `services/integration_runtime/tests/integration/test_sync_interrupted.py` (uzilgan sync → `SyncRunFailed`, batch e’lon qilinmaydi, run “failed” ko‘rinadi); Core: `test_analytics.py::test_a05_failed_ingestion_keeps_previous_snapshot` |
| A06 | ✅ | `test_analytics.py::test_a06_contributions`, `test_metrics.py::test_a06_*`; javobda “hisobiy hissa sababni isbotlamaydi” izohi |
| A07 | ✅ | `test_analytics.py::test_a02_a07_growth_rules`, `test_metrics.py::test_a07_growth_from_negative_is_absolute_only` |

### Hujjatlar

| ID | Holat | Dalil |
|---|---|---|
| D01 | ✅ | `test_documents.py::test_d01_d02_search_and_sources`, `ai_runtime .../test_fake_documents.py::test_d01_answer_quotes_source_with_version_and_locator`; eval: 15/15 |
| D02 | ✅ | `test_fake_documents.py::test_d02_not_found_does_not_invent_answer`; eval: javobsiz 5/5 |
| D03 | ✅ | `test_documents.py::test_d03_scanned_pdf_and_rejected_files` — “OCR kerak”, “o‘rganildi” deyilmaydi |
| D04 | ✅ | `test_documents.py::test_d04_d05_draft_diff_promote_conflict`, `test_d04_*` (DOCX uslubi, faqat tanlangan band); eval: 11/11 |
| D05 | ✅ | `test_documents.py::test_d04_d05_draft_diff_promote_conflict` — `VERSION_CONFLICT`, yashirin overwrite yo‘q |
| D06 | ✅ | `test_fake_documents.py::test_d06_instructions_inside_document_are_not_followed`; eval adversarial 10/10 |

### Xavfsizlik

| ID | Holat | Dalil |
|---|---|---|
| S01 | ✅ | `test_identity_http.py::test_other_tenant_is_not_reachable`, `test_tenant_isolation.py`, `test_data_ownership.py::test_every_tenant_table_forces_rls`, Tool API (`test_tool_api.py::test_auth_and_policy`), hujjat qidiruvi (`test_documents.py`) |
| S02 | ✅ | `test_branch_scope.py::test_single_branch_user_sees_only_allowed_branch` — HTTP so‘rov, Tool API, taqqoslash/hissa, dashboard/eksport; “Faqat ruxsat etilgan filiallar: …” izohi; ruxsatsiz filial — `BRANCH_FORBIDDEN`. Unit: `tests/unit/analytics/test_branch_scope.py` |
| S03 | ✅ | `test_documents.py::test_acl_and_s03_delete`, `test_maintenance.py::test_retention_and_document_jobs` (cleanup job qayta urinadi) |

### Vazifalar

| ID | Holat | Dalil |
|---|---|---|
| T01 | ✅ | `test_agent_queue.py::test_t01_queue_per_agent_and_office_state`, `tests/system/test_vertical_slice.py::test_t01_agent_queue_drains_with_real_workers` |
| T02 | ✅ | `test_agent_queue.py::test_t02_sse_resumes_from_last_event_id_without_rerun`; web: `features/chat/taskStream.test.ts` |
| T03 | ✅ | `ai_runtime .../test_provider_failures.py` — cheklangan retry, `PROVIDER_UNAVAILABLE`, soxta javob yo‘q |
| T04 | ✅ | `test_agent_queue.py::test_t04_same_idempotency_key_creates_one_task`; artifact: `test_tool_api.py::test_create_dashboard_is_idempotent` |
| T05 | ✅ | `ai_runtime .../test_runner.py::test_cancel_before_next_step`, `test_run_state.py::test_cancel_only_before_final`; navbatdagi vazifa — `test_agent_queue.py::test_t01_*` |

### Integratsiya va degradatsiya

| ID | Holat | Dalil |
|---|---|---|
| I01 | ✅ | `integration_runtime .../test_connector_conformance.py` — 4 connector (fayl, demo ERP, ERP REST API — soxta ERP’ga qarshi, test-only sintetik API) bitta suite’dan; Core/AI domeni o‘zgarmagan. Tizim testi: `tests/system/test_erp.py` |
| I02 | ✅ | `test_connector_conformance.py::test_i02_csv_and_demo_erp_give_identical_canonical_batch` |
| I03 | ✅ | `tests/system/test_degradation.py::test_i03_integration_down_import_waits_dashboards_marked_stale`; UI “Eskirgan” belgisi |
| I04 | ✅ | `test_analytics.py::test_duplicate_batch_is_idempotent_and_quarantine`, `abo_messaging .../test_outbox_inbox.py::test_duplicate_delivery_is_processed_once` |
| I05 | ✅ | `test_degradation.py::test_i05_ai_down_search_falls_back_and_task_waits`, `test_i05_ai_recovers_task_runs_once_and_embeddings_arrive` |
| I06 | ✅ | `test_data_ownership.py::test_runtime_credential_cannot_open_foreign_database`, `test_app_role_is_not_privileged`; compose tarmoq segmentatsiyasi, `infra/k8s/network-policies.yaml` (klasterda — namunaviy) |

### UI

| ID | Holat | Dalil |
|---|---|---|
| U01 | ✅ | Playwright `office.floor.spec.ts` “reduced-motion”; ofisdan tashqari yo‘l — “Ro‘yxat” ko‘rinishi, `/tasks` sahifasi, chat |
| U02 | ✅ | Playwright `office.spec.ts` — kartochka → dashboard oynasi (yangi tab yo‘q) |
| U03 | ✅ | Playwright `office.floor.spec.ts` (xarita holati saqlanadi), `office.spec.ts` |
| U04 | ✅ | `test_dashboards_http.py::test_u04_fifty_dashboards_listed_and_searchable_without_llm` (RunAgent yo‘q), `apps/web/src/features/dashboards/Picker.test.tsx` (50 ta, qidiruv, saralash, tanlash) |
| U05 | ✅ | Playwright `office.spec.ts` — chatda havola va doskada kartochka paydo bo‘ladi, oyna o‘zi ochilmaydi |
| U06 | ✅ | Playwright `drilldown.spec.ts`; ruxsatsiz kesim — S02 testi |
| U07 | ✅ | Playwright `drilldown.spec.ts` — sessiyada tiklanish va reset |

### Release eval to‘plami

| Talab | Holat | Dalil |
|---|---|---|
| ≥40 raqamli, 20 hujjat Q&A, 10 tahrir, 10 adversarial | ✅ fake | `docs/reports/eval-2026-09-28-fake.md`: 42 / 15+5 / 11 / 10, barchasi 100% |
| Real API integratsiyasi alohida | ⏳ | `make eval-openai` — `OPENAI_API_KEY` kerak. Kalitsiz hisobot “fake” deb belgilanadi, “real tekshirildi” deyilmaydi |

## 13.15 — kod darajasidagi gate’lar

| # | Gate | Holat | Dalil |
|---|---|---|---|
| 1 | Boundary | ✅ | import-linter (har servis, CI), `tests/architecture/test_boundaries.py` (servislar bir-birini import qilmaydi, context’lar faqat `public`, domain transport’siz) |
| 2 | Izolyatsiyalangan domain | ✅ | `services/*/tests/unit` — DB/broker/internetsiz |
| 3 | Contract | ✅ | `tests/contracts` (har schema + fixture), OpenAPI baseline diff (`test_openapi_baseline.py`), tool/event producer testlari. N/N−1 — birinchi production release’dan keyin |
| 4 | Adapter | ✅ | connector conformance (3 connector); fake/OpenAI provider bir port orqali (`test_provider_failures.py`, eval fake/openai) |
| 5 | Failure | ✅ | `test_outbox_inbox.py` (relay, dedup, parallel relay), `test_runs.py::test_stale_worker_cannot_commit_after_takeover`, `test_runner.py::test_resume_after_lost_lease_*`, `test_degradation.py::test_broker_restart_task_completes_once`, replay/DLQ testlari |
| 6 | Data ownership | ✅ | `test_data_ownership.py`, S01/S02 testlari, SSE va object download RLS orqali |
| 7 | Degradation | ✅ | `make degradation` (5/5) |
| 8 | Migration | ✅ | `make migration-check` (toza DB: upgrade → downgrade → upgrade), CI’da |
| 9 | Operatsion dalil | ⚠️ | yuklama `docs/reports/load-2026-09-28.md`, eval, restore `docs/reports/restore-2026-09-28.md`, replay testlari, `docs/runbooks/`. Tracing: `traceparent`/`trace_id` uzatiladi, OpenTelemetry eksport — P1 (`docs/KNOWN_LIMITATIONS.md`) |
| 10 | Kod sifati | ✅ | CI: ruff, mypy, eslint/tsc, pip-audit, npm audit, secret scan, har servis alohida image build |

Cheklovlar va ochiq qarorlar: [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md).
