#!/usr/bin/env bash
set -Eeuo pipefail

MCP_ENV_FILE="${MCP_ENV_FILE:-/opt/sovereign-chatgpt-tools/.env}"
BACKEND_ENV_FILE="${SOVEREIGN_BACKEND_ENV_FILE:-/opt/sovereign-backend/.env}"
BACKEND_CONTAINER="${SOVEREIGN_BACKEND_CONTAINER:-sovereign-backend}"
READER_USER="sovereign_mcp_reader"
PREVIEW_USER="sovereign_mcp_preview"
PREVIEW_DB="sovereign_migration_preview"

fail() {
  printf 'database bootstrap blocked: %s\n' "$*" >&2
  exit 1
}

read_value() {
  local file="$1"
  local key="$2"
  sed -n "s/^${key}=//p" "$file" | tail -n 1
}

set_value() {
  local file="$1"
  local key="$2"
  local value="$3"
  python3 - "$file" "$key" "$value" <<'PY'
from pathlib import Path
import os
import sys

path = Path(sys.argv[1])
key = sys.argv[2]
value = sys.argv[3]
lines = path.read_text("utf-8").splitlines() if path.exists() else []
replaced = False
out = []
for line in lines:
    if line.startswith(key + "="):
        out.append(f"{key}={value}")
        replaced = True
    else:
        out.append(line)
if not replaced:
    out.append(f"{key}={value}")
temporary = path.with_suffix(path.suffix + ".tmp")
temporary.write_text("\n".join(out) + "\n", "utf-8")
os.chmod(temporary, 0o600)
temporary.replace(path)
PY
}

[[ "${EUID:-$(id -u)}" -eq 0 ]] || fail "run as root"
[[ -f "$MCP_ENV_FILE" ]] || fail "MCP environment file is missing"
[[ -f "$BACKEND_ENV_FILE" ]] || fail "backend environment file is missing"
docker inspect "$BACKEND_CONTAINER" >/dev/null 2>&1 || fail "backend container is not running"
docker exec "$BACKEND_CONTAINER" command -v psql >/dev/null 2>&1 || fail "psql is missing in backend container"
docker exec "$BACKEND_CONTAINER" command -v createdb >/dev/null 2>&1 || fail "createdb is missing in backend container"

ADMIN_HOST="$(read_value "$BACKEND_ENV_FILE" POSTGRES_HOST)"
ADMIN_PORT="$(read_value "$BACKEND_ENV_FILE" POSTGRES_PORT)"
ADMIN_DB="$(read_value "$BACKEND_ENV_FILE" POSTGRES_DB)"
ADMIN_USER="$(read_value "$BACKEND_ENV_FILE" POSTGRES_USER)"
ADMIN_PASSWORD="$(read_value "$BACKEND_ENV_FILE" POSTGRES_PASSWORD)"
ADMIN_HOST="${ADMIN_HOST:-db}"
ADMIN_PORT="${ADMIN_PORT:-5432}"
ADMIN_DB="${ADMIN_DB:-postgres}"

[[ "$ADMIN_HOST" =~ ^[A-Za-z0-9_.-]+$ ]] || fail "invalid POSTGRES_HOST"
[[ "$ADMIN_PORT" =~ ^[0-9]+$ ]] || fail "invalid POSTGRES_PORT"
[[ "$ADMIN_DB" =~ ^[A-Za-z0-9_]+$ ]] || fail "invalid POSTGRES_DB"
[[ "$ADMIN_USER" =~ ^[A-Za-z0-9_]+$ ]] || fail "invalid POSTGRES_USER"
[[ -n "$ADMIN_PASSWORD" ]] || fail "POSTGRES_PASSWORD is empty"

READER_PASSWORD="$(read_value "$MCP_ENV_FILE" POSTGRES_PASSWORD)"
PREVIEW_PASSWORD="$(read_value "$MCP_ENV_FILE" SOVEREIGN_MCP_PREVIEW_POSTGRES_PASSWORD)"
READER_PASSWORD="${READER_PASSWORD:-$(openssl rand -hex 32)}"
PREVIEW_PASSWORD="${PREVIEW_PASSWORD:-$(openssl rand -hex 32)}"

psql_admin() {
  docker exec \
    -e PGPASSWORD="$ADMIN_PASSWORD" \
    "$BACKEND_CONTAINER" \
    psql -v ON_ERROR_STOP=1 -h "$ADMIN_HOST" -p "$ADMIN_PORT" -U "$ADMIN_USER" -d "$ADMIN_DB" "$@"
}

if [[ "$(psql_admin -tAc "SELECT 1 FROM pg_roles WHERE rolname='$READER_USER'")" != "1" ]]; then
  psql_admin -c "CREATE ROLE $READER_USER LOGIN PASSWORD '$READER_PASSWORD'"
else
  psql_admin -c "ALTER ROLE $READER_USER LOGIN PASSWORD '$READER_PASSWORD'"
fi

if [[ "$(psql_admin -tAc "SELECT 1 FROM pg_roles WHERE rolname='$PREVIEW_USER'")" != "1" ]]; then
  psql_admin -c "CREATE ROLE $PREVIEW_USER LOGIN PASSWORD '$PREVIEW_PASSWORD'"
else
  psql_admin -c "ALTER ROLE $PREVIEW_USER LOGIN PASSWORD '$PREVIEW_PASSWORD'"
fi

psql_admin -c "GRANT CONNECT ON DATABASE $ADMIN_DB TO $READER_USER"
docker exec \
  -e PGPASSWORD="$ADMIN_PASSWORD" \
  "$BACKEND_CONTAINER" \
  psql -v ON_ERROR_STOP=1 -h "$ADMIN_HOST" -p "$ADMIN_PORT" -U "$ADMIN_USER" -d "$ADMIN_DB" \
  -c "GRANT USAGE ON SCHEMA public TO $READER_USER" \
  -c "GRANT SELECT ON ALL TABLES IN SCHEMA public TO $READER_USER" \
  -c "GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO $READER_USER" \
  -c "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO $READER_USER" \
  -c "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON SEQUENCES TO $READER_USER"

if [[ "$(psql_admin -tAc "SELECT 1 FROM pg_database WHERE datname='$PREVIEW_DB'")" != "1" ]]; then
  docker exec \
    -e PGPASSWORD="$ADMIN_PASSWORD" \
    "$BACKEND_CONTAINER" \
    createdb -h "$ADMIN_HOST" -p "$ADMIN_PORT" -U "$ADMIN_USER" -O "$PREVIEW_USER" "$PREVIEW_DB"
fi

set_value "$MCP_ENV_FILE" POSTGRES_HOST "$ADMIN_HOST"
set_value "$MCP_ENV_FILE" POSTGRES_PORT "$ADMIN_PORT"
set_value "$MCP_ENV_FILE" POSTGRES_DB "$ADMIN_DB"
set_value "$MCP_ENV_FILE" POSTGRES_USER "$READER_USER"
set_value "$MCP_ENV_FILE" POSTGRES_PASSWORD "$READER_PASSWORD"
set_value "$MCP_ENV_FILE" SOVEREIGN_MCP_PREVIEW_POSTGRES_HOST "$ADMIN_HOST"
set_value "$MCP_ENV_FILE" SOVEREIGN_MCP_PREVIEW_POSTGRES_PORT "$ADMIN_PORT"
set_value "$MCP_ENV_FILE" SOVEREIGN_MCP_PREVIEW_POSTGRES_DB "$PREVIEW_DB"
set_value "$MCP_ENV_FILE" SOVEREIGN_MCP_PREVIEW_POSTGRES_USER "$PREVIEW_USER"
set_value "$MCP_ENV_FILE" SOVEREIGN_MCP_PREVIEW_POSTGRES_PASSWORD "$PREVIEW_PASSWORD"
chmod 0600 "$MCP_ENV_FILE"

printf '{"ok":true,"reader":"%s","production_database":"%s","preview_owner":"%s","preview_database":"%s"}\n' \
  "$READER_USER" "$ADMIN_DB" "$PREVIEW_USER" "$PREVIEW_DB"
