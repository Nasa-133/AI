#!/usr/bin/env bash
# Integratsiya testlari uchun alohida bazalar (*_test): ishlayotgan `make stack` bilan to‘qnashmaydi
# (stek worker’lari test run’larini olib ketmaydi). Idempotent; rollar init skriptidagilar.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PSQL=(docker compose -f "$ROOT/infra/compose/docker-compose.yml" exec -T postgres psql -v ON_ERROR_STOP=1 -U postgres -q)

create() {
  local db=$1 owner=$2 app=$3
  if ! "${PSQL[@]}" -tAc "SELECT 1 FROM pg_database WHERE datname = '$db'" | grep -q 1; then
    "${PSQL[@]}" -c "CREATE DATABASE $db OWNER $owner"
  fi
  "${PSQL[@]}" -c "REVOKE ALL ON DATABASE $db FROM PUBLIC" \
               -c "GRANT CONNECT ON DATABASE $db TO $owner, $app" -c "GRANT TEMP ON DATABASE $db TO $app"
  "${PSQL[@]}" -d "$db" -c "REVOKE ALL ON SCHEMA public FROM PUBLIC" \
               -c "GRANT USAGE, CREATE ON SCHEMA public TO $owner"
}

create business_test business_owner business_app
create ai_runtime_test ai_owner ai_app
create integration_runtime_test integration_owner integration_app
"${PSQL[@]}" -d business_test -c "CREATE EXTENSION IF NOT EXISTS vector" -c "CREATE EXTENSION IF NOT EXISTS pg_trgm"

cd "$ROOT/services/business" && BUSINESS_MIGRATIONS_DATABASE_URL=postgresql+asyncpg://business_owner:business_owner_dev@localhost:55432/business_test uv run alembic upgrade head >/dev/null
cd "$ROOT/services/ai_runtime" && AI_MIGRATIONS_DATABASE_URL=postgresql+asyncpg://ai_owner:ai_owner_dev@localhost:55432/ai_runtime_test uv run alembic upgrade head >/dev/null
cd "$ROOT/services/integration_runtime" && INTEGRATION_MIGRATIONS_DATABASE_URL=postgresql+asyncpg://integration_owner:integration_owner_dev@localhost:55432/integration_runtime_test uv run alembic upgrade head >/dev/null
echo "Test bazalari tayyor: business_test, ai_runtime_test, integration_runtime_test"
