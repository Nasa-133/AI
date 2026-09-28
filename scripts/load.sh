#!/usr/bin/env bash
# Pilot yuklama testi (TZ 19): alohida stek (API 8050, AI 8051) + tools/load/loadtest.py.
#   make load  (LOAD_ROWS, LOAD_SECONDS, EVAL_MODE=openai — ixtiyoriy)
# `make stack` to‘xtatilgan bo‘lsin (worker’lar umumiy broker navbatlaridan ish oladi).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOGS="$ROOT/.load-logs"; rm -rf "$LOGS"; mkdir -p "$LOGS"
PORT=8050 AI_PORT=8051
MODE="${EVAL_MODE:-fake}"
export E2E_BASE_URL="http://localhost:$PORT" EVAL_API_LOG="$LOGS/api.log"
export BUSINESS_TOOLS_SERVICE_TOKEN="load-tools-token-$(python3 -c 'import secrets;print(secrets.token_hex(16))')"
export BUSINESS_CAPABILITY_SIGNING_KEY="load-signing-key-$(python3 -c 'import secrets;print(secrets.token_hex(16))')"
export BUSINESS_DATABASE_URL=postgresql+asyncpg://business_app:business_app_dev@localhost:55432/business
export BUSINESS_DATA_ENCRYPTION_KEY="$(cd "$ROOT/services/business" && uv run python -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())')"
export BUSINESS_COOKIE_SECURE=false BUSINESS_NOTIFIER=log BUSINESS_AI_RUNTIME_URL="http://localhost:$AI_PORT"
export BUSINESS_AMQP_URL=amqp://abo:abo_dev@localhost:5672/ BUSINESS_S3_ACCESS_KEY=abo BUSINESS_S3_SECRET_KEY=abo_dev_password
export AI_BUSINESS_TOOLS_URL="http://localhost:$PORT" AI_BUSINESS_TOOLS_TOKEN="$BUSINESS_TOOLS_SERVICE_TOKEN"
export AI_MODEL_PROVIDER="$MODE" AI_S3_ACCESS_KEY=abo AI_S3_SECRET_KEY=abo_dev_password
if [ "$MODE" = "openai" ]; then
  : "${OPENAI_API_KEY:?OPENAI_API_KEY kerak (real OpenAI eval)}"
  : "${OPENAI_MODEL_MAIN:?OPENAI_MODEL_MAIN kerak}"
  export AI_EMBEDDING_PROVIDER=openai
fi
export INTEGRATION_DATABASE_URL=postgresql+asyncpg://integration_app:integration_app_dev@localhost:55432/integration_runtime
export INTEGRATION_AMQP_URL=amqp://abo:abo_dev@localhost:5672/ INTEGRATION_S3_ACCESS_KEY=abo INTEGRATION_S3_SECRET_KEY=abo_dev_password

PIDS=()
cleanup() { for p in "${PIDS[@]}"; do kill -TERM "$p" 2>/dev/null || true; done; wait 2>/dev/null || true; }
trap cleanup EXIT INT TERM
make -C "$ROOT" migrate >/dev/null
(cd "$ROOT/services/business" && exec uv run uvicorn business.bootstrap.app:create_app --factory --port "$PORT" >"$LOGS/api.log" 2>&1) & PIDS+=($!)
(cd "$ROOT/services/business" && exec uv run python -m business.entrypoints.worker >"$LOGS/business-worker.log" 2>&1) & PIDS+=($!)
(cd "$ROOT/services/integration_runtime" && exec uv run python -m integration_runtime.bootstrap.worker >"$LOGS/integration-worker.log" 2>&1) & PIDS+=($!)
(cd "$ROOT/services/ai_runtime" && exec uv run python -m ai_runtime.bootstrap.worker >"$LOGS/ai-worker.log" 2>&1) & PIDS+=($!)
(cd "$ROOT/services/ai_runtime" && exec uv run uvicorn ai_runtime.bootstrap.app:create_app --factory --port "$AI_PORT" >"$LOGS/ai-api.log" 2>&1) & PIDS+=($!)
for _ in $(seq 1 60); do curl -sf "http://localhost:$PORT/health/ready" >/dev/null && break; sleep 0.5; done
sleep 2
cd "$ROOT/services/business"
DATA="${LOAD_DATA:-$ROOT/.load-data}"
if [ ! -f "$DATA/sotuvlar.csv" ]; then
  echo "1 mln satr generatsiya qilinmoqda → $DATA"
  python3 "$ROOT/tools/synthetic_data/generate.py" --seed 7 --rows "${LOAD_ROWS:-1000000}" --out "$DATA" >/dev/null
fi
uv run python "$ROOT/tools/load/loadtest.py" --data "$DATA" --seconds "${LOAD_SECONDS:-180}" \
  || { echo "--- loglar: $LOGS"; exit 1; }
