#!/bin/bash
# Har runtime uchun alohida logical database, egasi (migratsiya) va app roli (RLS’ga bo‘ysunadi).
# Runtime’lar bir-birining bazasiga ulana olmaydi (TZ 13.7, 13.12).
set -euo pipefail

create_runtime_db() {
  local db=$1 owner=$2 owner_pw=$3 app=$4 app_pw=$5
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<SQL
CREATE ROLE ${owner} LOGIN PASSWORD '${owner_pw}' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
CREATE ROLE ${app} LOGIN PASSWORD '${app_pw}' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
CREATE DATABASE ${db} OWNER ${owner};
REVOKE ALL ON DATABASE ${db} FROM PUBLIC;
GRANT CONNECT ON DATABASE ${db} TO ${owner}, ${app};
SQL
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$db" <<SQL
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO ${owner};
SQL
}

create_runtime_db business business_owner "$BUSINESS_DB_OWNER_PASSWORD" business_app "$BUSINESS_DB_APP_PASSWORD"
create_runtime_db ai_runtime ai_owner "$AI_DB_OWNER_PASSWORD" ai_app "$AI_DB_APP_PASSWORD"
create_runtime_db integration_runtime integration_owner "$INTEGRATION_DB_OWNER_PASSWORD" integration_app "$INTEGRATION_DB_APP_PASSWORD"

# Extension’lar superuser talab qiladi.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname business <<SQL
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
SQL
