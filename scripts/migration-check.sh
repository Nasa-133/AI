#!/usr/bin/env bash
# 13.15 gate 8: toza bazada upgrade → to‘liq downgrade → qayta upgrade (har uch runtime).
# Destructive rollback yashirilmaydi: downgrade ishlamasa skript yiqiladi.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PSQL=(docker compose -f "$ROOT/infra/compose/docker-compose.yml" exec -T postgres psql -v ON_ERROR_STOP=1 -U postgres -q)

check() {
  local service=$1 db=$2 owner=$3 app=$4 env=$5 ext=${6:-}
  "${PSQL[@]}" -c "SET client_min_messages = warning" -c "DROP DATABASE IF EXISTS $db" -c "CREATE DATABASE $db OWNER $owner" \
               -c "GRANT CONNECT ON DATABASE $db TO $app"
  if [ -n "$ext" ]; then
    "${PSQL[@]}" -d "$db" -c "CREATE EXTENSION IF NOT EXISTS vector" -c "CREATE EXTENSION IF NOT EXISTS pg_trgm"
  fi
  local url="postgresql+asyncpg://$owner:${owner}_dev@localhost:55432/$db"
  (cd "$ROOT/services/$service" && export "$env=$url" \
    && uv run alembic upgrade head >/dev/null \
    && uv run alembic downgrade base >/dev/null \
    && uv run alembic upgrade head >/dev/null \
    && echo "  $service: upgrade → downgrade base → upgrade: OK ($(uv run alembic current 2>/dev/null | tail -1))")
  "${PSQL[@]}" -c "DROP DATABASE $db"
}

echo "Migratsiya tekshiruvi (toza bazalar):"
check business business_migcheck business_owner business_app BUSINESS_MIGRATIONS_DATABASE_URL ext
check ai_runtime ai_runtime_migcheck ai_owner ai_app AI_MIGRATIONS_DATABASE_URL
check integration_runtime integration_runtime_migcheck integration_owner integration_app INTEGRATION_MIGRATIONS_DATABASE_URL
