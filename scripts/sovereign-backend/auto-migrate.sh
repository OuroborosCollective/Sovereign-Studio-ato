#!/usr/bin/env bash
set -euo pipefail

: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"

POSTGRES_HOST="${POSTGRES_HOST:-db}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-postgres}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
MIGRATION_DIR="${MIGRATION_DIR:-/app/migrations}"
export PGPASSWORD="${POSTGRES_PASSWORD}"

psql_base=(
  psql
  -v ON_ERROR_STOP=1
  -h "${POSTGRES_HOST}"
  -p "${POSTGRES_PORT}"
  -U "${POSTGRES_USER}"
  -d "${POSTGRES_DB}"
)

if [[ ! -d "${MIGRATION_DIR}" ]]; then
  echo "Migration directory not found: ${MIGRATION_DIR}" >&2
  exit 1
fi

mapfile -t migrations < <(find "${MIGRATION_DIR}" -maxdepth 1 -type f -name '*.sql' -print | sort)
if (( ${#migrations[@]} == 0 )); then
  echo "No SQL migrations found in ${MIGRATION_DIR}" >&2
  exit 1
fi

for migration in "${migrations[@]}"; do
  echo "Applying migration: $(basename "${migration}")"
  "${psql_base[@]}" -f "${migration}"
done

ADMIN_API_KEY="${ADMIN_API_KEY:-}"
if [[ -n "${ADMIN_API_KEY}" ]]; then
  key_hash="$(printf '%s' "${ADMIN_API_KEY}" | sha256sum | awk '{print $1}')"
  "${psql_base[@]}" -v key_hash="${key_hash}" <<'SQL'
INSERT INTO admin_api_keys (admin_id, key_hash, label)
SELECT id, :'key_hash', 'Bootstrap Admin Key'
FROM admin_users
WHERE role IN ('admin', 'superadmin')
ORDER BY CASE WHEN role = 'superadmin' THEN 0 ELSE 1 END, id
LIMIT 1
ON CONFLICT (key_hash) DO NOTHING;
SQL

  key_count="$("${psql_base[@]}" -Atc "SELECT COUNT(*) FROM admin_api_keys WHERE key_hash = '${key_hash}'")"
  if [[ "${key_count}" != "1" ]]; then
    echo "ADMIN_API_KEY is configured, but no matching bootstrap key could be persisted." >&2
    exit 1
  fi
fi

echo "Database migrations completed successfully."
