#!/usr/bin/env bash
# Bosqich 1 vertikal kesimini haqiqiy jarayonlar bilan tekshiradi: API + 3 worker + platforma.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOGS="$ROOT/.e2e-logs"; mkdir -p "$LOGS"
PORT="${E2E_PORT:-8020}"  # make stack 8010’ni band qilishi mumkin
export E2E_BASE_URL="http://localhost:$PORT"
TOKEN="e2e-tools-token-$(python3 -c 'import secrets;print(secrets.token_hex(16))')"
export BUSINESS_DATABASE_URL=postgresql+asyncpg://business_app:business_app_dev@localhost:55432/business
export BUSINESS_DATA_ENCRYPTION_KEY="$(cd "$ROOT/services/business" && uv run python -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())')"
export BUSINESS_COOKIE_SECURE=false BUSINESS_TOOLS_SERVICE_TOKEN="$TOKEN"
export BUSINESS_CAPABILITY_SIGNING_KEY="e2e-signing-key-$(python3 -c 'import secrets;print(secrets.token_hex(16))')"
export BUSINESS_AMQP_URL=amqp://abo:abo_dev@localhost:5672/ BUSINESS_S3_ACCESS_KEY=abo BUSINESS_S3_SECRET_KEY=abo_dev_password
export AI_BUSINESS_TOOLS_URL="http://localhost:$PORT" AI_BUSINESS_TOOLS_TOKEN="$TOKEN" AI_MODEL_PROVIDER=fake
export INTEGRATION_DATABASE_URL=postgresql+asyncpg://integration_app:integration_app_dev@localhost:55432/integration_runtime
export INTEGRATION_AMQP_URL=amqp://abo:abo_dev@localhost:5672/ INTEGRATION_S3_ACCESS_KEY=abo INTEGRATION_S3_SECRET_KEY=abo_dev_password

PIDS=()
cleanup() { for p in "${PIDS[@]}"; do kill -TERM "$p" 2>/dev/null || true; done; wait 2>/dev/null || true; }
trap cleanup EXIT

make -C "$ROOT" migrate >/dev/null
(cd "$ROOT/services/business" && exec uv run uvicorn business.bootstrap.app:create_app --factory --port "$PORT" >"$LOGS/api.log" 2>&1) & PIDS+=($!)
(cd "$ROOT/services/business" && exec uv run python -m business.entrypoints.worker >"$LOGS/business-worker.log" 2>&1) & PIDS+=($!)
(cd "$ROOT/services/integration_runtime" && exec uv run python -m integration_runtime.bootstrap.worker >"$LOGS/integration-worker.log" 2>&1) & PIDS+=($!)
(cd "$ROOT/services/ai_runtime" && exec uv run python -m ai_runtime.bootstrap.worker >"$LOGS/ai-worker.log" 2>&1) & PIDS+=($!)

for _ in $(seq 1 60); do curl -sf "http://localhost:$PORT/health/ready" >/dev/null && break; sleep 0.5; done
sleep 2  # consumer’lar navbatlarni e’lon qilishi uchun
cd "$ROOT/services/business"
if ! uv run pytest -q -p no:cacheprovider -o asyncio_mode=auto -o asyncio_default_test_loop_scope=session -o markers=system "$ROOT/tests/system" --rootdir "$ROOT/tests/system"; then
  echo "--- loglar: $LOGS"; tail -n 40 "$LOGS"/*.log; exit 1
fi
