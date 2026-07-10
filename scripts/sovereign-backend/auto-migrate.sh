#!/usr/bin/env bash
set -euo pipefail
export PGPASSWORD="${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
for migration in /app/migrations/*.sql; do
  [ -f "$migration" ] || continue
  echo "Applying migration: $(basename "$migration")"
  psql -v ON_ERROR_STOP=1     -h "${POSTGRES_HOST:-db}"     -p "${POSTGRES_PORT:-5432}"     -U "${POSTGRES_USER:-postgres}"     -d "${POSTGRES_DB:-postgres}"     -f "$migration"
done
