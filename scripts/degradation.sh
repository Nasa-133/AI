#!/usr/bin/env bash
# Degradatsiya ssenariylari (TZ I03, I05, gate 5/7) haqiqiy jarayonlar bilan:
#   1) AI o‘chiq → qidiruv matnli, vazifa navbatda (soxta javob yo‘q), dashboardlar ishlaydi
#   2) AI yoqiladi → vazifa bir marta bajariladi, embedding keladi
#   3) Integration o‘chiq → import kutilmoqda, dashboard “eskirgan”, chat/hujjat ishlaydi
#   4) Broker to‘xtatiladi → vazifa saqlanadi va ko‘rinadi; 5) broker qaytadi → vazifa bajariladi
# `make stack` to‘xtatilgan bo‘lsin (uning worker’lari shu navbatlardan ish oladi).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOGS="$ROOT/.degradation-logs"; mkdir -p "$LOGS"
PORT=8030 AI_PORT=8031
COMPOSE=(docker compose -f "$ROOT/infra/compose/docker-compose.yml")
export E2E_BASE_URL="http://localhost:$PORT" DEGRADATION_STATE="$LOGS/state.json"
TOKEN="deg-tools-token-$(python3 -c 'import secrets;print(secrets.token_hex(16))')"
export BUSINESS_DATABASE_URL=postgresql+asyncpg://business_app:business_app_dev@localhost:55432/business
export BUSINESS_DATA_ENCRYPTION_KEY="$(cd "$ROOT/services/business" && uv run python -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())')"
export BUSINESS_COOKIE_SECURE=false BUSINESS_TOOLS_SERVICE_TOKEN="$TOKEN" BUSINESS_DATA_STALE_AFTER_SECONDS=4
export BUSINESS_CAPABILITY_SIGNING_KEY="deg-signing-key-$(python3 -c 'import secrets;print(secrets.token_hex(16))')"
export BUSINESS_AMQP_URL=amqp://abo:abo_dev@localhost:5672/ BUSINESS_S3_ACCESS_KEY=abo BUSINESS_S3_SECRET_KEY=abo_dev_password
export BUSINESS_AI_RUNTIME_URL="http://localhost:$AI_PORT"
export AI_BUSINESS_TOOLS_URL="http://localhost:$PORT" AI_BUSINESS_TOOLS_TOKEN="$TOKEN" AI_MODEL_PROVIDER=fake
export AI_S3_ACCESS_KEY=abo AI_S3_SECRET_KEY=abo_dev_password
export INTEGRATION_DATABASE_URL=postgresql+asyncpg://integration_app:integration_app_dev@localhost:55432/integration_runtime
export INTEGRATION_AMQP_URL=amqp://abo:abo_dev@localhost:5672/ INTEGRATION_S3_ACCESS_KEY=abo INTEGRATION_S3_SECRET_KEY=abo_dev_password

PIDDIR="$LOGS/pids"; rm -rf "$PIDDIR"; mkdir -p "$PIDDIR"  # bash 3.2 (macOS) — assotsiativ massivsiz
start() {  # nom, katalog, buyruq...
  local name=$1 dir=$2; shift 2
  (cd "$ROOT/services/$dir" && exec "$@" >"$LOGS/$name.log" 2>&1) &
  echo $! >"$PIDDIR/$name"
}
stop() {
  local pid; pid=$(cat "$PIDDIR/$1" 2>/dev/null || true)
  [ -n "$pid" ] && { kill -TERM "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true; }
  rm -f "$PIDDIR/$1"
}
cleanup() {
  for f in "$PIDDIR"/*; do [ -e "$f" ] && stop "$(basename "$f")"; done
  "${COMPOSE[@]}" start rabbitmq >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM
phase() {
  echo "== $1"
  (cd "$ROOT/services/business" && DEGRADATION_PHASE=$1 uv run pytest -q -p no:cacheprovider \
     -o asyncio_mode=auto -o asyncio_default_test_loop_scope=session -o markers=system \
     "$ROOT/tests/system/test_degradation.py" --rootdir "$ROOT/tests/system" 2>&1 | tail -3) \
    || { echo "--- loglar: $LOGS"; tail -n 30 "$LOGS"/*.log; exit 1; }
}

make -C "$ROOT" migrate >/dev/null
start api business uv run uvicorn business.bootstrap.app:create_app --factory --port "$PORT"
start business-worker business uv run python -m business.entrypoints.worker
start integration-worker integration_runtime uv run python -m integration_runtime.bootstrap.worker
for _ in $(seq 1 60); do curl -sf "http://localhost:$PORT/health/ready" >/dev/null && break; sleep 0.5; done
sleep 2

phase ai_down
start ai-worker ai_runtime uv run python -m ai_runtime.bootstrap.worker
start ai-api ai_runtime uv run uvicorn ai_runtime.bootstrap.app:create_app --factory --port "$AI_PORT"
phase ai_up
stop integration-worker
phase integration_down
"${COMPOSE[@]}" stop rabbitmq >/dev/null 2>&1
phase broker_down
"${COMPOSE[@]}" start rabbitmq >/dev/null 2>&1
"${COMPOSE[@]}" up -d --wait rabbitmq >/dev/null 2>&1
phase broker_up
echo "Degradatsiya ssenariylari: hammasi o‘tdi"
