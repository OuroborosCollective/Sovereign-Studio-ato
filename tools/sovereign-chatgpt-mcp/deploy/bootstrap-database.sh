#!/usr/bin/env bash
set -Eeuo pipefail

MCP_ENV_FILE="${MCP_ENV_FILE:-/opt/sovereign-chatgpt-tools/.env}"
BACKEND_ENV_FILE="${SOVEREIGN_BACKEND_ENV_FILE:-/opt/sovereign-backend/.env}"
BACKEND_CONTAINER="${SOVEREIGN_BACKEND_CONTAINER:-sovereign-backend}"
READER_USER="sovereign_mcp_reader"
PREVIEW_USER="sovereign_mcp_preview"
PREVIEW_DB="sovereign_migration_preview"
PSQL_BIN="/usr/bin/psql"
CREATEDB_BIN="/usr/bin/createdb"

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
docker exec "$BACKEND_CONTAINER" "$PSQL_BIN" --version >/dev/null 2>&1 || fail "psql is missing in backend container"
docker exec "$BACKEND_CONTAINER" "$CREATEDB_BIN" --version >/dev/null 2>&1 || fail "createdb is missing in backend container"

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

psql_admin_db() {
  local database="$1"
  shift
  docker exec \
    -e PGPASSWORD="$ADMIN_PASSWORD" \
    "$BACKEND_CONTAINER" \
    "$PSQL_BIN" -v ON_ERROR_STOP=1 -h "$ADMIN_HOST" -p "$ADMIN_PORT" -U "$ADMIN_USER" -d "$database" "$@"
}

psql_admin_db_stdin() {
  local database="$1"
  shift
  docker exec -i \
    -e PGPASSWORD="$ADMIN_PASSWORD" \
    "$BACKEND_CONTAINER" \
    "$PSQL_BIN" -v ON_ERROR_STOP=1 -h "$ADMIN_HOST" -p "$ADMIN_PORT" -U "$ADMIN_USER" -d "$database" "$@"
}

psql_admin() {
  psql_admin_db "$ADMIN_DB" "$@"
}

psql_admin_stdin() {
  psql_admin_db_stdin "$ADMIN_DB" "$@"
}

database_owner_can_manage_public_schema() {
  local database="$1"
  psql_admin_db "$database" -tAc \
    "SELECT CASE WHEN pg_get_userbyid(d.datdba) = current_user OR r.rolsuper THEN 1 ELSE 0 END
       FROM pg_database AS d
       JOIN pg_roles AS r ON r.rolname = current_user
      WHERE d.datname = current_database();"
}

foreign_public_object_owners() {
  local database="$1"
  local expected_owner="$2"
  psql_admin_db "$database" -tAc \
    "SELECT COALESCE(string_agg(owner_name, ', ' ORDER BY owner_name), '')
       FROM (
         SELECT DISTINCT pg_get_userbyid(c.relowner) AS owner_name
           FROM pg_class AS c
           JOIN pg_namespace AS n ON n.oid = c.relnamespace
          WHERE n.nspname = 'public'
            AND c.relkind IN ('r','p','v','m','S','f')
            AND pg_get_userbyid(c.relowner) <> '$expected_owner'
       ) AS foreign_owners;"
}

if [[ "$(psql_admin -tAc "SELECT 1 FROM pg_roles WHERE rolname='$READER_USER'")" != "1" ]]; then
  printf "CREATE ROLE %s LOGIN PASSWORD :'role_password';\n" "$READER_USER" \
    | psql_admin_stdin -v role_password="$READER_PASSWORD"
else
  printf "ALTER ROLE %s LOGIN PASSWORD :'role_password';\n" "$READER_USER" \
    | psql_admin_stdin -v role_password="$READER_PASSWORD"
fi

if [[ "$(psql_admin -tAc "SELECT 1 FROM pg_roles WHERE rolname='$PREVIEW_USER'")" != "1" ]]; then
  printf "CREATE ROLE %s LOGIN PASSWORD :'role_password';\n" "$PREVIEW_USER" \
    | psql_admin_stdin -v role_password="$PREVIEW_PASSWORD"
else
  printf "ALTER ROLE %s LOGIN PASSWORD :'role_password';\n" "$PREVIEW_USER" \
    | psql_admin_stdin -v role_password="$PREVIEW_PASSWORD"
fi

PRODUCTION_FOREIGN_OWNERS="$(foreign_public_object_owners "$ADMIN_DB" "$ADMIN_USER")"
[[ -z "$PRODUCTION_FOREIGN_OWNERS" ]] \
  || fail "production public objects are not owned by $ADMIN_USER: $PRODUCTION_FOREIGN_OWNERS"
[[ "$(database_owner_can_manage_public_schema "$ADMIN_DB")" == "1" ]] \
  || fail "$ADMIN_USER is neither database owner nor superuser for $ADMIN_DB"

cat <<SQL | psql_admin_stdin
BEGIN;
GRANT CONNECT ON DATABASE $ADMIN_DB TO $READER_USER;
GRANT USAGE ON SCHEMA public TO $READER_USER;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO $READER_USER;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO $READER_USER;
ALTER DEFAULT PRIVILEGES FOR ROLE $ADMIN_USER IN SCHEMA public GRANT SELECT ON TABLES TO $READER_USER;
ALTER DEFAULT PRIVILEGES FOR ROLE $ADMIN_USER IN SCHEMA public GRANT SELECT ON SEQUENCES TO $READER_USER;
COMMIT;
SQL

if [[ "$(psql_admin -tAc "SELECT 1 FROM pg_database WHERE datname='$PREVIEW_DB'")" != "1" ]]; then
  docker exec \
    -e PGPASSWORD="$ADMIN_PASSWORD" \
    "$BACKEND_CONTAINER" \
    "$CREATEDB_BIN" -h "$ADMIN_HOST" -p "$ADMIN_PORT" -U "$ADMIN_USER" "$PREVIEW_DB"
fi

PREVIEW_FOREIGN_OWNERS="$(foreign_public_object_owners "$PREVIEW_DB" "$PREVIEW_USER")"
[[ -z "$PREVIEW_FOREIGN_OWNERS" ]] \
  || fail "preview public objects are not owned by $PREVIEW_USER: $PREVIEW_FOREIGN_OWNERS"
[[ "$(database_owner_can_manage_public_schema "$PREVIEW_DB")" == "1" ]] \
  || fail "$ADMIN_USER is neither database owner nor superuser for $PREVIEW_DB"

cat <<SQL | psql_admin_db_stdin "$PREVIEW_DB"
BEGIN;
GRANT CONNECT, TEMPORARY ON DATABASE $PREVIEW_DB TO $PREVIEW_USER;
GRANT USAGE, CREATE ON SCHEMA public TO $PREVIEW_USER;
COMMIT;
SQL

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

READER_CANARY="$(docker exec \
  -e PGPASSWORD="$READER_PASSWORD" \
  "$BACKEND_CONTAINER" \
  "$PSQL_BIN" -v ON_ERROR_STOP=1 -h "$ADMIN_HOST" -p "$ADMIN_PORT" -U "$READER_USER" -d "$ADMIN_DB" -tAc 'SELECT 1')"
[[ "$READER_CANARY" == "1" ]] || fail "production reader authentication canary failed"

READER_PRIVILEGE_CANARY="$(psql_admin -tAc \
  "SELECT CASE
      WHEN EXISTS (
        SELECT 1
          FROM pg_class AS c
          JOIN pg_namespace AS n ON n.oid = c.relnamespace
         WHERE n.nspname = 'public'
           AND CASE
             WHEN c.relkind IN ('r','p','v','m','f')
               THEN NOT has_table_privilege('$READER_USER', c.oid, 'SELECT')
             ELSE FALSE
           END
      ) OR EXISTS (
        SELECT 1
          FROM pg_class AS c
          JOIN pg_namespace AS n ON n.oid = c.relnamespace
         WHERE n.nspname = 'public'
           AND CASE
             WHEN c.relkind = 'S'
               THEN NOT has_sequence_privilege('$READER_USER', c.oid, 'SELECT')
             ELSE FALSE
           END
      )
      THEN 0 ELSE 1 END;")"
[[ "$READER_PRIVILEGE_CANARY" == "1" ]] || fail "production reader object privilege canary failed"

PREVIEW_OWNER_CANARY="$(psql_admin_db "$PREVIEW_DB" -tAc \
  "SELECT CASE WHEN EXISTS (
      SELECT 1
        FROM pg_class AS c
        JOIN pg_namespace AS n ON n.oid = c.relnamespace
       WHERE n.nspname = 'public'
         AND c.relkind IN ('r','p','v','m','S','f')
         AND pg_get_userbyid(c.relowner) <> '$PREVIEW_USER'
    ) THEN 0 ELSE 1 END;")"
[[ "$PREVIEW_OWNER_CANARY" == "1" ]] || fail "preview database object ownership canary failed"

printf '%s\n' \
  'BEGIN;' \
  'DROP TABLE IF EXISTS public.sovereign_mcp_preview_canary;' \
  'CREATE TABLE public.sovereign_mcp_preview_canary(id integer);' \
  'ROLLBACK;' \
  | docker exec -i \
      -e PGPASSWORD="$PREVIEW_PASSWORD" \
      "$BACKEND_CONTAINER" \
      "$PSQL_BIN" -v ON_ERROR_STOP=1 -h "$ADMIN_HOST" -p "$ADMIN_PORT" -U "$PREVIEW_USER" -d "$PREVIEW_DB" >/dev/null \
  || fail "preview database authentication or DDL canary failed"

printf '{"ok":true,"reader":"%s","production_database":"%s","reader_canary":true,"reader_object_privileges":true,"preview_user":"%s","preview_database":"%s","preview_owner_canary":true,"preview_canary":true}\n' \
  "$READER_USER" "$ADMIN_DB" "$PREVIEW_USER" "$PREVIEW_DB"
