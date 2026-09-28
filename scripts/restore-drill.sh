#!/usr/bin/env bash
# Zaxira → tiklash mashqi (TZ 19: RPO 24 soat, RTO 4 soat maqsad; 13.15 gate 9).
#   1) uch baza pg_dump (custom format) + jadval qatorlari soni; S3 bucket’lar + SHA-256 manifest
#   2) alohida *_restore bazalariga pg_restore, S3 “-restore” bucket’lariga yuklash
#   3) tekshiruv: har jadval qatorlari soni teng, har obyekt checksum’i teng; RTO o‘lchanadi
# Ishlayotgan tizimga tegmaydi (faqat o‘qish va *_restore nusxalar).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STAMP="$(date +%Y%m%d-%H%M%S)"
DIR="$ROOT/.backups/$STAMP"; mkdir -p "$DIR"
PG=(docker compose -f "$ROOT/infra/compose/docker-compose.yml" exec -T postgres)
DBS=("business:business_owner" "ai_runtime:ai_owner" "integration_runtime:integration_owner")
REPORT="$ROOT/docs/reports/restore-$(date +%Y-%m-%d).md"

counts() {  # db → "jadval|qatorlar" — bitta so‘rov, aniq COUNT (superuser: RLS’siz)
  "${PG[@]}" psql -v ON_ERROR_STOP=1 -U postgres -d "$1" -tA -F'|' -c "
    SELECT table_schema||'.'||table_name,
           (xpath('/row/c/text()', query_to_xml(format('SELECT count(*) AS c FROM %I.%I',
             table_schema, table_name), false, true, '')))[1]::text::bigint
    FROM information_schema.tables
    WHERE table_type = 'BASE TABLE' AND table_schema NOT IN ('pg_catalog', 'information_schema')
    ORDER BY 1" </dev/null
}

t0=$(date +%s)
echo "== 1) Zaxira → $DIR"
for entry in "${DBS[@]}"; do
  db=${entry%%:*}
  "${PG[@]}" pg_dump -U postgres -Fc "$db" > "$DIR/$db.dump" </dev/null
  counts "$db" > "$DIR/$db.counts"
  echo "  $db: $(du -h "$DIR/$db.dump" | cut -f1), $(wc -l < "$DIR/$db.counts" | tr -d ' ') jadval"
done
(cd "$ROOT/services/business" && uv run python "$ROOT/tools/ops/s3_snapshot.py" backup --out "$DIR/s3" abo-business abo-integration abo-ai)
t1=$(date +%s)

echo "== 2) Tiklash (*_restore)"
for entry in "${DBS[@]}"; do
  db=${entry%%:*}; owner=${entry##*:}
  "${PG[@]}" psql -v ON_ERROR_STOP=1 -U postgres -q -c "SET client_min_messages = warning" \
    -c "DROP DATABASE IF EXISTS ${db}_restore" -c "CREATE DATABASE ${db}_restore OWNER $owner" </dev/null
  # Superuser sifatida, asl egalar va extension’lar bilan (pgvector). Xato — mashq yiqiladi.
  "${PG[@]}" pg_restore -U postgres -d "${db}_restore" --exit-on-error < "$DIR/$db.dump"
done
(cd "$ROOT/services/business" && uv run python "$ROOT/tools/ops/s3_snapshot.py" restore --src "$DIR/s3")
t2=$(date +%s)

echo "== 3) Tekshiruv"
fail=0
for entry in "${DBS[@]}"; do
  db=${entry%%:*}
  counts "${db}_restore" > "$DIR/$db.restore.counts"
  if diff -q "$DIR/$db.counts" "$DIR/$db.restore.counts" >/dev/null; then
    echo "  $db: qatorlar soni teng ($(awk -F'|' '{s+=$2} END {print s}' "$DIR/$db.counts") qator)"
  else
    echo "  $db: FARQ BOR"; diff "$DIR/$db.counts" "$DIR/$db.restore.counts" | head; fail=1
  fi
done
s3_result=$(cd "$ROOT/services/business" && uv run python "$ROOT/tools/ops/s3_snapshot.py" verify --src "$DIR/s3") || fail=1
echo "  S3: $s3_result"
t3=$(date +%s)

{
  echo "# Zaxira va tiklash mashqi — $(date +%Y-%m-%d)"
  echo
  echo "| Bosqich | Vaqt, s |"; echo "|---|---|"
  echo "| Zaxira (3 baza + S3) | $((t1 - t0)) |"
  echo "| Tiklash (pg_restore + S3) | $((t2 - t1)) |"
  echo "| Tekshiruv | $((t3 - t2)) |"
  echo "| **RTO (tiklash + tekshiruv)** | **$((t3 - t1))** (maqsad ≤ 14400) |"
  echo
  for entry in "${DBS[@]}"; do db=${entry%%:*}
    echo "- $db: $(wc -l < "$DIR/$db.counts" | tr -d ' ') jadval, $(awk -F'|' '{s+=$2} END {print s}' "$DIR/$db.counts") qator — tiklangan nusxada teng"; done
  echo "- S3: $s3_result"
  echo
  echo "RPO: zaxira jadvali bilan belgilanadi — kunlik \`pg_dump\` + S3 nusxa → RPO ≤ 24 soat (TZ 19)."
  echo "Kichikroq RPO uchun production’da Postgres WAL arxivi (PITR) va bucket versioning tavsiya etiladi."
  echo
  echo "Natija: $([ $fail = 0 ] && echo '✅ tiklangan nusxa asl bilan mos' || echo '❌ farq bor')"
} > "$REPORT"
echo "Hisobot: $REPORT"
if [ "${KEEP_RESTORE:-0}" != "1" ]; then  # mashq nusxalari tozalanadi (KEEP_RESTORE=1 — qoldirish)
  for entry in "${DBS[@]}"; do
    "${PG[@]}" psql -U postgres -q -c "DROP DATABASE IF EXISTS ${entry%%:*}_restore" </dev/null
  done
fi
exit $fail
