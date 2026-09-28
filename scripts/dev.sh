#!/usr/bin/env bash
# Lokal ishlab chiqish: API + 3 worker + web bitta buyruq bilan (make up oldindan kerak).
# Ctrl+C barcha jarayonlarni to‘xtatadi. Loglar: .dev-logs/
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOGS="$ROOT/.dev-logs"; mkdir -p "$LOGS"
PORT="${E2E_PORT:-8010}"
WEB_PORT="${WEB_PORT:-3010}"
TOKEN="e2e-tools-token-$(python3 -c 'import secrets;print(secrets.token_hex(16))')"
export BUSINESS_DATABASE_URL=postgresql+asyncpg://business_app:business_app_dev@localhost:55432/business
export BUSINESS_DATA_ENCRYPTION_KEY="$(cd "$ROOT/services/business" && uv run python -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())')"
export BUSINESS_COOKIE_SECURE=false BUSINESS_TOOLS_SERVICE_TOKEN="$TOKEN"
# Lokal: taklif/parol havolalari API logiga yoziladi (email kanali hali yo‘q).
export BUSINESS_NOTIFIER=log BUSINESS_WEB_BASE_URL="http://localhost:$WEB_PORT"
export BUSINESS_CAPABILITY_SIGNING_KEY="e2e-signing-key-$(python3 -c 'import secrets;print(secrets.token_hex(16))')"
export BUSINESS_AMQP_URL=amqp://abo:abo_dev@localhost:5672/ BUSINESS_S3_ACCESS_KEY=abo BUSINESS_S3_SECRET_KEY=abo_dev_password
export AI_BUSINESS_TOOLS_URL="http://localhost:$PORT" AI_BUSINESS_TOOLS_TOKEN="$TOKEN" AI_MODEL_PROVIDER=fake
# AI Runtime ichki HTTP (embed): Core qidiruv so‘rovini vektorlashtiradi (TZ 13.3).
AI_PORT="${AI_PORT:-8011}"
export BUSINESS_AI_RUNTIME_URL="http://localhost:$AI_PORT" AI_S3_ACCESS_KEY=abo AI_S3_SECRET_KEY=abo_dev_password
export INTEGRATION_DATABASE_URL=postgresql+asyncpg://integration_app:integration_app_dev@localhost:55432/integration_runtime
export INTEGRATION_AMQP_URL=amqp://abo:abo_dev@localhost:5672/ INTEGRATION_S3_ACCESS_KEY=abo INTEGRATION_S3_SECRET_KEY=abo_dev_password
# Soxta ERP (tools/fake_erp): erp_api connector shunga ulanadi. Haqiqiy ERP’da URL/kalit boshqa.
ERP_PORT="${FAKE_ERP_PORT:-8070}"
export FAKE_ERP_API_KEY="${FAKE_ERP_API_KEY:-fake-erp-dev-key}"
export INTEGRATION_ERP_API_URL="http://localhost:$ERP_PORT" INTEGRATION_ERP_API_KEY="$FAKE_ERP_API_KEY"
CRM_PORT="${FAKE_CRM_PORT:-8071}"
export FAKE_CRM_API_KEY="${FAKE_CRM_API_KEY:-fake-crm-dev-key}"
export INTEGRATION_CRM_API_URL="http://localhost:$CRM_PORT" INTEGRATION_CRM_API_KEY="$FAKE_CRM_API_KEY"
# Lokalda testlar ko‘plab sinov korxonalarini yaratadi — ularning ERP manbalari worker’ni band
# qilmasligi uchun avtomatik sinxron soatiga bir marta (production standarti: 15 daqiqa).
export BUSINESS_ERP_AUTO_SYNC_SECONDS="${BUSINESS_ERP_AUTO_SYNC_SECONDS:-3600}"

PIDS=()
cleanup() { for p in "${PIDS[@]}"; do kill -TERM "$p" 2>/dev/null || true; done; wait 2>/dev/null || true; }
trap cleanup EXIT INT TERM

make -C "$ROOT" migrate >/dev/null
(cd "$ROOT/services/business" && exec uv run uvicorn business.bootstrap.app:create_app --factory --port "$PORT" >"$LOGS/api.log" 2>&1) & PIDS+=($!)
(cd "$ROOT/services/business" && exec uv run python -m business.entrypoints.worker >"$LOGS/business-worker.log" 2>&1) & PIDS+=($!)
(cd "$ROOT/services/integration_runtime" && exec uv run python ../../tools/fake_erp/app.py --port "$ERP_PORT" >"$LOGS/fake-erp.log" 2>&1) & PIDS+=($!)
(cd "$ROOT/services/integration_runtime" && exec uv run python ../../tools/fake_crm/app.py --port "$CRM_PORT" >"$LOGS/fake-crm.log" 2>&1) & PIDS+=($!)
(cd "$ROOT/services/integration_runtime" && exec uv run python -m integration_runtime.bootstrap.worker >"$LOGS/integration-worker.log" 2>&1) & PIDS+=($!)
(cd "$ROOT/services/ai_runtime" && exec uv run python -m ai_runtime.bootstrap.worker >"$LOGS/ai-worker.log" 2>&1) & PIDS+=($!)
(cd "$ROOT/services/ai_runtime" && exec uv run uvicorn ai_runtime.bootstrap.app:create_app --factory --port "$AI_PORT" >"$LOGS/ai-api.log" 2>&1) & PIDS+=($!)
(cd "$ROOT/apps/web" && BUSINESS_API_URL="http://localhost:$PORT" exec npx next dev --port "$WEB_PORT" >"$LOGS/web.log" 2>&1) & PIDS+=($!)
echo "API: http://localhost:$PORT  ·  Web: http://localhost:$WEB_PORT  ·  Soxta ERP: http://localhost:$ERP_PORT  ·  Soxta CRM: http://localhost:$CRM_PORT  ·  loglar: $LOGS"
wait
