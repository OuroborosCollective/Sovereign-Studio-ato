#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

SOURCE_DIR="${1:-}"
ROOT="/opt/sovereign-legacy-mcp"
TARGET="$ROOT/sovereign-toolchain"
COMMON_SOURCE="$(dirname "$SOURCE_DIR")/sovereign-legacy-mcp-common"
COMMON_TARGET="$ROOT/sovereign-legacy-mcp-common"
UNIT_SOURCE="$SOURCE_DIR/deploy/sovereign-toolchain.service"
UNIT_TARGET="/etc/systemd/system/sovereign-toolchain.service"
EVIDENCE_UNIT_SOURCE="$SOURCE_DIR/deploy/sovereign-toolchain-n8n-evidence.service"
EVIDENCE_UNIT_TARGET="/etc/systemd/system/sovereign-toolchain-n8n-evidence.service"
ENV_TARGET="/etc/sovereign-toolchain/runtime.env"
EVIDENCE_ENV_TARGET="/etc/sovereign-toolchain/evidence-runtime.env"
N8N_EVIDENCE_KEY_TARGET="/etc/sovereign-toolchain/n8n-evidence.key"
SERVICE="sovereign-toolchain.service"
EVIDENCE_SERVICE="sovereign-toolchain-n8n-evidence.service"
KEY_SOURCE="/opt/secure/sovereign-github-app/private-key.pem"
BACKUP_ROOT="$ROOT/.installer-backups"
PRIMARY_REPOSITORY="OuroborosCollective/Sovereign-Studio-ato"
AURION_REPOSITORY="OuroborosCollective/Echoes_of_Aurion"
EXPECTED_REVISION="${SOVEREIGN_TOOLCHAIN_EXPECTED_REVISION:-}"
REVISION_MARKER_NAME=".sovereign-source-revision"
MUTATION_STARTED=0
ROLLBACK_COMPLETED=0
INSTALL_COMMITTED=0

fail() {
  local reason="$1"
  local rollback_state="not-required"
  local exit_code=1
  if [[ "$MUTATION_STARTED" == "1" && "$INSTALL_COMMITTED" != "1" ]]; then
    trap - ERR HUP INT TERM
    if rollback; then
      rollback_state="verified"
    else
      rollback_state="failed"
      exit_code=70
    fi
  fi
  printf 'SOVEREIGN_TOOLCHAIN_INSTALL_FAILURE stage=%s reason_sha256=%s rollback=%s\n' \
    "${STAGE:-unknown}" "$(printf '%s' "$reason" | sha256sum | awk '{print $1}')" "$rollback_state" >&2
  exit "$exit_code"
}

on_unhandled_error() {
  local line="${1:-0}"
  trap - ERR
  [[ "$line" =~ ^[0-9]+$ ]] || line=0
  fail "unhandled command failure line=$line"
}
trap 'on_unhandled_error "$LINENO"' ERR

classify_uv_sync_failure() {
  local log_file="$1"
  if grep -Eqi '(unexpected argument|unrecognized option|unknown option|invalid option|found argument).*(--no-install-project|--no-dev|--locked)' "$log_file"; then
    printf 'CLI_COMPATIBILITY\n'
  elif grep -Eqi '(uv\.lock|lock ?file).*(needs? to be updated|out of date|not up[- ]to[- ]date)|locked.*(would|cannot|can.t).*update' "$log_file"; then
    printf 'LOCK_DRIFT\n'
  elif grep -Eqi '(no space left on device|disk quota|quota exceeded|filesystem full|out of disk space)' "$log_file"; then
    printf 'STORAGE\n'
  elif grep -Eqi '(permission denied|operation not permitted|access denied|read-only file system|read only file system)' "$log_file"; then
    printf 'PERMISSION\n'
  elif grep -Eqi '(failed to build|build backend|build-system|build system|pep[ -]?517|hatchling|failed to prepare metadata|failed to build wheel)' "$log_file"; then
    printf 'BUILD_SYSTEM\n'
  elif grep -Eqi '(cache).*(corrupt|invalid|failed|error)|failed to (extract|unpack)|input/output error|i/o error|checksum mismatch|hash mismatch' "$log_file"; then
    printf 'CACHE_IO\n'
  elif grep -Eqi '(no solution found|unsatisfiable|could not resolve|resolution failed|no matching distribution|package.*not found|not found in.*registry)' "$log_file"; then
    printf 'RESOLUTION\n'
  elif grep -Eqi '(python).*(not found|not available|unsupported|requires|requirement)|failed to (find|locate|download).*python' "$log_file"; then
    printf 'PYTHON\n'
  elif grep -Eqi '(timed? out|timeout|temporary failure|connection (refused|reset|aborted)|name or service not known|dns|tls|certificate|failed to (download|fetch)|request error|connect error|network|failed to query.*registry)' "$log_file"; then
    printf 'NETWORK\n'
  else
    printf 'OTHER\n'
  fi
}

bounded_uv_version() {
  local version
  version="$(uv --version 2>/dev/null | sed -nE 's/^uv ([0-9]+\.[0-9]+\.[0-9]+).*$/\1/p' | head -n 1)"
  if [[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    printf '%s\n' "$version"
  else
    printf 'unknown\n'
  fi
}

STAGE=preflight
[[ -n "$SOURCE_DIR" && -d "$SOURCE_DIR" && ! -L "$SOURCE_DIR" ]] || fail "source directory invalid"
[[ "$EXPECTED_REVISION" =~ ^[0-9a-f]{40}$ ]] || fail "expected revision must be a full commit SHA"
SOURCE_REPOSITORY_ROOT="$(git -C "$SOURCE_DIR" rev-parse --show-toplevel 2>/dev/null || true)"
SOURCE_IN_WORK_TREE="$(git -C "$SOURCE_DIR" rev-parse --is-inside-work-tree 2>/dev/null || true)"
[[ -n "$SOURCE_REPOSITORY_ROOT" && -d "$SOURCE_REPOSITORY_ROOT" && "$SOURCE_IN_WORK_TREE" == "true" ]] \
  || fail "source is not a full Git repository checkout"
[[ "$(realpath -- "$SOURCE_DIR")" == "$(realpath -- "$SOURCE_REPOSITORY_ROOT/tools/sovereign-toolchain")" ]] || fail "source directory is not the revision-bound toolchain path"
command -v uv >/dev/null 2>&1 || fail "uv is required for the locked runtime build"
command -v tar >/dev/null 2>&1 || fail "tar is required for revision materialization"
SOURCE_REVISION="$(git -C "$SOURCE_DIR" rev-parse HEAD 2>/dev/null || true)"
[[ "$SOURCE_REVISION" == "$EXPECTED_REVISION" ]] || fail "source revision differs from expected revision"
TRACKED_INSTALL_DIRTY="$(
  git -C "$SOURCE_REPOSITORY_ROOT" status \
    --porcelain \
    --untracked-files=no \
    -- \
    tools/sovereign-toolchain \
    tools/sovereign-legacy-mcp-common
)"
[[ -z "$TRACKED_INSTALL_DIRTY" ]] || fail "revision-bound toolchain source has tracked modifications"
[[ -f "$SOURCE_DIR/pyproject.toml" && -f "$SOURCE_DIR/uv.lock" ]] || fail "locked toolchain source incomplete"
[[ -f "$UNIT_SOURCE" && ! -L "$UNIT_SOURCE" ]] || fail "full service unit source invalid"
[[ -f "$EVIDENCE_UNIT_SOURCE" && ! -L "$EVIDENCE_UNIT_SOURCE" ]] || fail "evidence service unit source invalid"
[[ -d "$COMMON_SOURCE" && -f "$COMMON_SOURCE/github_app_auth.py" ]] || fail "common adapter source invalid"
[[ -f "$KEY_SOURCE" && ! -L "$KEY_SOURCE" ]] || fail "GitHub App private key source invalid"
KEY_UID="$(stat -c %u "$KEY_SOURCE")"
KEY_MODE="$(stat -c %a "$KEY_SOURCE")"
[[ "$KEY_UID" == "0" ]] || fail "GitHub App private key owner is invalid"
[[ "$KEY_MODE" == "600" || "$KEY_MODE" == "640" ]] || fail "GitHub App private key mode is invalid"
! grep -Eq '(^|[^A-Za-z0-9_])(GITHUB_TOKEN|GH_TOKEN|GITHUB_PAT)=' "$UNIT_SOURCE" || fail "full service unit has persistent token source"
! grep -Eq '(^|[^A-Za-z0-9_])(GITHUB_TOKEN|GH_TOKEN|GITHUB_PAT)=' "$EVIDENCE_UNIT_SOURCE" || fail "evidence service unit has persistent token source"
grep -Fq -- '--host 127.0.0.1 --port 8001' "$UNIT_SOURCE" || fail "full service unit is not loopback bound"
grep -Fq -- '--host 0.0.0.0 --port 8002' "$EVIDENCE_UNIT_SOURCE" || fail "evidence service listener contract is invalid"
grep -Fxq 'DynamicUser=yes' "$EVIDENCE_UNIT_SOURCE" || fail "evidence service is not dynamically unprivileged"
grep -Fxq 'ProtectSystem=strict' "$EVIDENCE_UNIT_SOURCE" || fail "evidence service filesystem is not read-only"
! grep -Eq '^User=root$|^ReadWritePaths=' "$EVIDENCE_UNIT_SOURCE" || fail "evidence service has a privileged filesystem contract"

STAGE=stage
install -d -m 0755 -o root -g root "$ROOT"
install -d -m 0700 -o root -g root "$BACKUP_ROOT" /etc/sovereign-toolchain
TEMP="$(mktemp -d "$ROOT/.toolchain-stage.XXXXXX")"
cleanup_stage() { rm -rf "$TEMP"; }
trap cleanup_stage EXIT
install -d -m 0700 -o root -g root "$TEMP/sovereign-toolchain" "$TEMP/sovereign-legacy-mcp-common" "$TEMP/archive"
git -C "$SOURCE_REPOSITORY_ROOT" archive --format=tar "$EXPECTED_REVISION" tools/sovereign-toolchain \
  | tar -xf - -C "$TEMP/archive"
git -C "$SOURCE_REPOSITORY_ROOT" archive --format=tar "$EXPECTED_REVISION" tools/sovereign-legacy-mcp-common \
  | tar -xf - -C "$TEMP/archive"
cp -a "$TEMP/archive/tools/sovereign-toolchain/." "$TEMP/sovereign-toolchain/"
cp -a "$TEMP/archive/tools/sovereign-legacy-mcp-common/." "$TEMP/sovereign-legacy-mcp-common/"
UNIT_SOURCE="$TEMP/sovereign-toolchain/deploy/sovereign-toolchain.service"
EVIDENCE_UNIT_SOURCE="$TEMP/sovereign-toolchain/deploy/sovereign-toolchain-n8n-evidence.service"
printf '%s\n' "$EXPECTED_REVISION" > "$TEMP/sovereign-toolchain/$REVISION_MARKER_NAME"
chmod 0644 "$TEMP/sovereign-toolchain/$REVISION_MARKER_NAME"
rm -rf "$TEMP/sovereign-toolchain/.venv"
(
  cd "$TEMP/sovereign-toolchain"
  UV_SYNC_LOG="$TEMP/uv-sync.log"
  UV_CACHE_DIR="$TEMP/uv-cache"
  install -d -m 0700 -o root -g root "$UV_CACHE_DIR"
  if ! env -u UV_FROZEN -u UV_LOCKED UV_CACHE_DIR="$UV_CACHE_DIR" uv sync --locked --no-dev --no-install-project >"$UV_SYNC_LOG" 2>&1; then
    UV_FAILURE_FAMILY="$(classify_uv_sync_failure "$UV_SYNC_LOG")"
    UV_VERSION="$(bounded_uv_version)"
    UV_OUTPUT_SHA256="$(sha256sum "$UV_SYNC_LOG" | awk '{print $1}')"
    printf 'SOVEREIGN_TOOLCHAIN_UV_DIAGNOSTIC family=%s uv_version=%s output_sha256=%s\n' \
      "$UV_FAILURE_FAMILY" "$UV_VERSION" "$UV_OUTPUT_SHA256" >&2
    rm -f "$UV_SYNC_LOG"
    fail "uv sync failed family=$UV_FAILURE_FAMILY uv_version=$UV_VERSION output_sha256=$UV_OUTPUT_SHA256"
  fi
  rm -f "$UV_SYNC_LOG"
  rm -rf "$UV_CACHE_DIR"
  unset UV_SYNC_LOG UV_CACHE_DIR UV_FAILURE_FAMILY UV_VERSION UV_OUTPUT_SHA256
  PYTHONPATH="$TEMP/sovereign-toolchain/src:$TEMP/sovereign-legacy-mcp-common" \
    .venv/bin/python -c 'import sovereign_toolchain.n8n_evidence_app, uvicorn'
)
chown -R root:root "$TEMP/sovereign-toolchain" "$TEMP/sovereign-legacy-mcp-common"
chmod -R u=rwX,go=rX "$TEMP/sovereign-toolchain" "$TEMP/sovereign-legacy-mcp-common"

STAGE=metadata
METADATA_READER="$TEMP/sovereign-toolchain/deploy/read-broker-github-app-metadata.sh"
[[ -f "$METADATA_READER" && ! -L "$METADATA_READER" ]] || fail "broker metadata reader source invalid"
# Read only required literal App metadata. Never execute broker.env as shell code.
"$METADATA_READER" /opt/sovereign-chatgpt-tools/broker.env > "$TEMP/evidence-runtime.env"
SOVEREIGN_MCP_REPOSITORY="$(awk -F= '$1 == "SOVEREIGN_MCP_REPOSITORY" { print $2 }' "$TEMP/evidence-runtime.env")"
[[ "$SOVEREIGN_MCP_REPOSITORY" == "$PRIMARY_REPOSITORY" ]] || fail "unexpected primary repository metadata"

TOOLCHAIN_API_ENV_NAME="TOOLCHAIN_$(printf '%s%s' 'API' '_KEY')"
TOOLCHAIN_API_KEY_VALUE=""
if [[ -e "$ENV_TARGET" ]]; then
  [[ -f "$ENV_TARGET" && ! -L "$ENV_TARGET" ]] || fail "existing runtime environment invalid"
  TOOLCHAIN_KEY_COUNT="$(grep -c "^$TOOLCHAIN_API_ENV_NAME=" "$ENV_TARGET" || true)"
  [[ "$TOOLCHAIN_KEY_COUNT" =~ ^[0-9]+$ ]] || fail "existing toolchain API key count invalid"
  if [[ "$TOOLCHAIN_KEY_COUNT" == "1" ]]; then
    TOOLCHAIN_API_KEY_VALUE="$(awk -F= -v name="$TOOLCHAIN_API_ENV_NAME" '$1 == name { print substr($0, index($0, "=") + 1) }' "$ENV_TARGET")"
  elif [[ "$TOOLCHAIN_KEY_COUNT" != "0" ]]; then
    fail "existing toolchain API key cardinality invalid"
  fi
fi
if [[ -z "$TOOLCHAIN_API_KEY_VALUE" ]]; then
  command -v openssl >/dev/null 2>&1 || fail "openssl is required to create toolchain API key"
  TOOLCHAIN_API_KEY_VALUE="$(openssl rand -hex 32)"
fi
[[ "$TOOLCHAIN_API_KEY_VALUE" =~ ^[0-9a-f]{64}$ ]] || fail "toolchain API key format invalid"

N8N_EVIDENCE_ENV_NAME="N8N_EVIDENCE_$(printf '%s%s' 'API' '_KEY')"
N8N_EVIDENCE_KEY_VALUE=""
if [[ -e "$ENV_TARGET" ]]; then
  [[ -f "$ENV_TARGET" && ! -L "$ENV_TARGET" ]] || fail "existing runtime environment invalid"
  EXISTING_KEY_COUNT="$(grep -c "^$N8N_EVIDENCE_ENV_NAME=" "$ENV_TARGET" || true)"
  [[ "$EXISTING_KEY_COUNT" =~ ^[0-9]+$ ]] || fail "existing n8n evidence key count invalid"
  if [[ "$EXISTING_KEY_COUNT" == "1" ]]; then
    N8N_EVIDENCE_KEY_VALUE="$(awk -F= -v name="$N8N_EVIDENCE_ENV_NAME" '$1 == name { print substr($0, index($0, "=") + 1) }' "$ENV_TARGET")"
  elif [[ "$EXISTING_KEY_COUNT" != "0" ]]; then
    fail "existing n8n evidence key cardinality invalid"
  fi
fi

N8N_EVIDENCE_KEY_FILE_VALUE=""
if [[ -e "$N8N_EVIDENCE_KEY_TARGET" ]]; then
  [[ -f "$N8N_EVIDENCE_KEY_TARGET" && ! -L "$N8N_EVIDENCE_KEY_TARGET" ]] || fail "existing n8n evidence key file invalid"
  [[ "$(stat -c %u "$N8N_EVIDENCE_KEY_TARGET")" == "0" ]] || fail "existing n8n evidence key file owner invalid"
  [[ "$(stat -c %a "$N8N_EVIDENCE_KEY_TARGET")" == "600" ]] || fail "existing n8n evidence key file mode invalid"
  N8N_EVIDENCE_KEY_FILE_VALUE="$(<"$N8N_EVIDENCE_KEY_TARGET")"
  [[ "$N8N_EVIDENCE_KEY_FILE_VALUE" =~ ^[0-9a-f]{64}$ ]] || fail "existing n8n evidence key file format invalid"
fi
if [[ -n "$N8N_EVIDENCE_KEY_VALUE" && -n "$N8N_EVIDENCE_KEY_FILE_VALUE" && "$N8N_EVIDENCE_KEY_VALUE" != "$N8N_EVIDENCE_KEY_FILE_VALUE" ]]; then
  fail "n8n evidence key sources disagree"
fi
N8N_EVIDENCE_KEY_VALUE="${N8N_EVIDENCE_KEY_VALUE:-$N8N_EVIDENCE_KEY_FILE_VALUE}"
if [[ -z "$N8N_EVIDENCE_KEY_VALUE" ]]; then
  command -v openssl >/dev/null 2>&1 || fail "openssl is required to create n8n evidence key"
  N8N_EVIDENCE_KEY_VALUE="$(openssl rand -hex 32)"
fi
[[ "$N8N_EVIDENCE_KEY_VALUE" =~ ^[0-9a-f]{64}$ ]] || fail "n8n evidence key format invalid"

printf 'ALLOWED_REPOS=%s,%s\nGITHUB_TIMEOUT_SECONDS=60\n' \
  "$PRIMARY_REPOSITORY" "$AURION_REPOSITORY" >> "$TEMP/evidence-runtime.env"
cp "$TEMP/evidence-runtime.env" "$TEMP/runtime.env"
printf 'SOVEREIGN_TOOLCHAIN_GITHUB_READ_ONLY=1\n' >> "$TEMP/evidence-runtime.env"
printf '%s=%s\n' "$TOOLCHAIN_API_ENV_NAME" "$TOOLCHAIN_API_KEY_VALUE" >> "$TEMP/runtime.env"
printf '%s\n' "$N8N_EVIDENCE_KEY_VALUE" > "$TEMP/n8n-evidence.key"
chmod 0600 "$TEMP/runtime.env" "$TEMP/evidence-runtime.env" "$TEMP/n8n-evidence.key"
! grep -Eq '^(GITHUB_TOKEN|GH_TOKEN|GITHUB_PAT)=' "$TEMP/runtime.env" || fail "runtime environment has persistent GitHub token"
! grep -Eq "^$TOOLCHAIN_API_ENV_NAME=|^$N8N_EVIDENCE_ENV_NAME=" "$TEMP/evidence-runtime.env" || fail "evidence runtime environment contains a cross-boundary secret"

STAGE=activate
STAMP="$(date -u +%Y%m%dT%H%M%SZ).$$"
UNIT_BACKUP="$BACKUP_ROOT/sovereign-toolchain.service.$STAMP"
EVIDENCE_UNIT_BACKUP="$BACKUP_ROOT/sovereign-toolchain-n8n-evidence.service.$STAMP"
TARGET_BACKUP="$BACKUP_ROOT/sovereign-toolchain.$STAMP"
COMMON_BACKUP="$BACKUP_ROOT/sovereign-legacy-mcp-common.$STAMP"
ENV_BACKUP="$BACKUP_ROOT/runtime.env.$STAMP"
EVIDENCE_ENV_BACKUP="$BACKUP_ROOT/evidence-runtime.env.$STAMP"
N8N_KEY_BACKUP="$BACKUP_ROOT/n8n-evidence.key.$STAMP"
ROLLBACK_MANIFEST="$BACKUP_ROOT/last-install.json"
ROLLBACK_HELPER="$BACKUP_ROOT/rollback-last-install.py"
ROLLBACK_HELPER_SOURCE="$TEMP/sovereign-toolchain/deploy/rollback-last-install.py"
[[ -f "$ROLLBACK_HELPER_SOURCE" && ! -L "$ROLLBACK_HELPER_SOURCE" ]] || fail "rollback helper source invalid"

atomic_install() {
  local mode="$1"
  local source="$2"
  local target="$3"
  local temporary
  temporary="$(dirname "$target")/.$(basename "$target").new.$STAMP"
  install -m "$mode" -o root -g root "$source" "$temporary"
  mv -fT "$temporary" "$target"
}

atomic_install 0500 "$ROLLBACK_HELPER_SOURCE" "$ROLLBACK_HELPER"
ROLLBACK_PREPARE_LOG="$(mktemp)"
if ! python3 "$ROLLBACK_HELPER" prepare \
  --expected-installed-revision "$EXPECTED_REVISION" \
  --stamp "$STAMP" >"$ROLLBACK_PREPARE_LOG" 2>&1; then
  ROLLBACK_PREPARE_DIAGNOSTIC="$(
    grep -E '^SOVEREIGN_TOOLCHAIN_ROLLBACK_FAILURE operation=prepare reason_sha256=[0-9a-f]{64}$' \
      "$ROLLBACK_PREPARE_LOG" | head -n 1 | tr -d '\r\n' | cut -c1-256 || true
  )"
  ROLLBACK_PREPARE_OUTPUT_SHA256="$(sha256sum "$ROLLBACK_PREPARE_LOG" | awk '{print $1}')"
  rm -f "$ROLLBACK_PREPARE_LOG"
  if [[ -n "$ROLLBACK_PREPARE_DIAGNOSTIC" ]]; then
    fail "rollback prepare failed: $ROLLBACK_PREPARE_DIAGNOSTIC output_sha256=$ROLLBACK_PREPARE_OUTPUT_SHA256"
  fi
  fail "rollback prepare failed: output_sha256=$ROLLBACK_PREPARE_OUTPUT_SHA256"
fi
rm -f "$ROLLBACK_PREPARE_LOG"
unset ROLLBACK_PREPARE_LOG ROLLBACK_PREPARE_DIAGNOSTIC ROLLBACK_PREPARE_OUTPUT_SHA256

rollback() {
  [[ "$ROLLBACK_COMPLETED" != "1" ]] || return 0
  if python3 "$ROLLBACK_HELPER" rollback \
    --expected-installed-revision "$EXPECTED_REVISION" >/dev/null; then
    ROLLBACK_COMPLETED=1
    return 0
  fi
  return 1
}
on_activation_error() {
  trap - ERR
  fail "activation command failed"
}
on_activation_signal() {
  local signal_name="$1"
  trap - ERR HUP INT TERM
  fail "activation interrupted by $signal_name"
}

MUTATION_STARTED=1
trap on_activation_error ERR
trap 'on_activation_signal HUP' HUP
trap 'on_activation_signal INT' INT
trap 'on_activation_signal TERM' TERM

# Stop both consumers before the first live tree/config mutation. Missing services
# are acceptable on first install, but a surviving process is not.
systemctl stop "$EVIDENCE_SERVICE" "$SERVICE" >/dev/null 2>&1 || :
! systemctl is-active --quiet "$SERVICE" || fail "full service did not stop before cutover"
! systemctl is-active --quiet "$EVIDENCE_SERVICE" || fail "evidence service did not stop before cutover"

if [[ -d "$TARGET" ]]; then
  mv "$TARGET" "$TARGET_BACKUP"
fi
if [[ -d "$COMMON_TARGET" ]]; then
  mv "$COMMON_TARGET" "$COMMON_BACKUP"
fi
mv "$TEMP/sovereign-toolchain" "$TARGET"
mv "$TEMP/sovereign-legacy-mcp-common" "$COMMON_TARGET"
chmod -R u=rwX,go=rX "$TARGET" "$COMMON_TARGET"

# The staged tree now lives at TARGET. Rebind unit sources before reading them;
# otherwise atomic_install would dereference the already-moved TEMP paths.
UNIT_SOURCE="$TARGET/deploy/sovereign-toolchain.service"
EVIDENCE_UNIT_SOURCE="$TARGET/deploy/sovereign-toolchain-n8n-evidence.service"
atomic_install 0644 "$UNIT_SOURCE" "$UNIT_TARGET"
atomic_install 0644 "$EVIDENCE_UNIT_SOURCE" "$EVIDENCE_UNIT_TARGET"
atomic_install 0600 "$TEMP/runtime.env" "$ENV_TARGET"
atomic_install 0600 "$TEMP/evidence-runtime.env" "$EVIDENCE_ENV_TARGET"
atomic_install 0600 "$TEMP/n8n-evidence.key" "$N8N_EVIDENCE_KEY_TARGET"

for protected_file in "$ENV_TARGET" "$EVIDENCE_ENV_TARGET" "$N8N_EVIDENCE_KEY_TARGET"; do
  [[ -f "$protected_file" && ! -L "$protected_file" ]] || fail "activated protected file invalid"
  [[ "$(stat -c %u "$protected_file")" == "0" ]] || fail "activated protected file owner invalid"
  [[ "$(stat -c %a "$protected_file")" == "600" ]] || fail "activated protected file mode invalid"
done
cmp -s "$TEMP/runtime.env" "$ENV_TARGET" || fail "activated runtime environment mismatch"
cmp -s "$TEMP/evidence-runtime.env" "$EVIDENCE_ENV_TARGET" || fail "activated evidence environment mismatch"
cmp -s "$TEMP/n8n-evidence.key" "$N8N_EVIDENCE_KEY_TARGET" || fail "activated n8n evidence key mismatch"
[[ "$(grep -c "^$TOOLCHAIN_API_ENV_NAME=" "$ENV_TARGET" || true)" == "1" ]] || fail "activated toolchain API key cardinality invalid"
[[ "$(grep -c "^$TOOLCHAIN_API_ENV_NAME=" "$EVIDENCE_ENV_TARGET" || true)" == "0" ]] || fail "toolchain API key crossed into evidence environment"
[[ "$(grep -c '^SOVEREIGN_TOOLCHAIN_GITHUB_READ_ONLY=1$' "$EVIDENCE_ENV_TARGET" || true)" == "1" ]] || fail "evidence read-only GitHub token mode missing"
[[ "$(grep -c '^SOVEREIGN_TOOLCHAIN_GITHUB_READ_ONLY=' "$ENV_TARGET" || true)" == "0" ]] || fail "read-only token mode crossed into full runtime"

systemctl daemon-reload
systemctl enable "$SERVICE" "$EVIDENCE_SERVICE" >/dev/null
STAGE=runtime
[[ -x "$TARGET/.venv/bin/python" ]] || fail "final target runtime executable missing"
PYTHONPATH="$TARGET/src:$COMMON_TARGET" "$TARGET/.venv/bin/python" \
  -c 'import sovereign_toolchain.app, sovereign_toolchain.n8n_evidence_app, uvicorn'
systemctl restart "$SERVICE"
systemctl restart "$EVIDENCE_SERVICE"
systemctl is-enabled --quiet "$SERVICE" || fail "full service is not enabled"
systemctl is-enabled --quiet "$EVIDENCE_SERVICE" || fail "evidence service is not enabled"

STAGE=readback
for _ in $(seq 1 30); do
  if systemctl is-active --quiet "$SERVICE" &&
     systemctl is-active --quiet "$EVIDENCE_SERVICE" &&
     python3 - <<'PY'
import json
import urllib.request

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
with opener.open("http://127.0.0.1:8001/", timeout=3) as response:
    full = json.loads(response.read().decode("utf-8"))
assert full == {
    "ok": True,
    "name": "Sovereign Universal Toolchain",
    "rest": "/api/v1/manifest",
    "openapi": "/api/openapi.json",
    "mcp": "/mcp",
}
with opener.open("http://127.0.0.1:8002/healthz", timeout=3) as response:
    evidence = json.loads(response.read().decode("utf-8"))
assert evidence == {
    "ok": True,
    "service": "sovereign-n8n-ci-evidence",
    "capabilityContext": "sovereign.n8n-ci-evidence-capability.v1",
}
PY
  then
    break
  fi
  sleep 1
done
systemctl is-active --quiet "$SERVICE" || fail "full service health readback failed"
systemctl is-active --quiet "$EVIDENCE_SERVICE" || fail "evidence service health readback failed"

FULL_EXEC_START="$(systemctl show --property ExecStart --value "$SERVICE")"
EVIDENCE_EXEC_START="$(systemctl show --property ExecStart --value "$EVIDENCE_SERVICE")"
[[ "$FULL_EXEC_START" == *"--host 127.0.0.1 --port 8001"* ]] || fail "full app is not loopback bound"
[[ "$EVIDENCE_EXEC_START" == *"--host 0.0.0.0 --port 8002"* ]] || fail "evidence listener bind contract mismatch"
[[ "$(systemctl show --property DynamicUser --value "$EVIDENCE_SERVICE")" == "yes" ]] || fail "evidence DynamicUser readback failed"
[[ "$(systemctl show --property ProtectSystem --value "$EVIDENCE_SERVICE")" == "strict" ]] || fail "evidence ProtectSystem readback failed"
[[ -z "$(systemctl show --property ReadWritePaths --value "$EVIDENCE_SERVICE")" ]] || fail "evidence service has effective writable paths"
FULL_ENVIRONMENT_FILES="$(systemctl show --property EnvironmentFiles --value "$SERVICE")"
EVIDENCE_ENVIRONMENT_FILES="$(systemctl show --property EnvironmentFiles --value "$EVIDENCE_SERVICE")"
[[ "$FULL_ENVIRONMENT_FILES" == *"/etc/sovereign-toolchain/runtime.env"* && "$FULL_ENVIRONMENT_FILES" != *"evidence-runtime.env"* ]] || fail "full service environment-file boundary mismatch"
[[ "$EVIDENCE_ENVIRONMENT_FILES" == *"/etc/sovereign-toolchain/evidence-runtime.env"* && "$EVIDENCE_ENVIRONMENT_FILES" != *"/runtime.env"* ]] || fail "evidence service environment-file boundary mismatch"

python3 - <<'PY' || fail "listener socket boundary canary failed"
from pathlib import Path

def listeners(path: str, port: int) -> set[str]:
    result = set()
    for line in Path(path).read_text("ascii").splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 4 and fields[3] == "0A":
            address, encoded_port = fields[1].split(":")
            if int(encoded_port, 16) == port:
                result.add(address)
    return result

assert listeners("/proc/net/tcp", 8001) == {"0100007F"}
assert not listeners("/proc/net/tcp6", 8001)
assert listeners("/proc/net/tcp", 8002) == {"00000000"}
assert not listeners("/proc/net/tcp6", 8002)
PY

python3 - "$ENV_TARGET" "$N8N_EVIDENCE_KEY_TARGET" <<'PY' || fail "authenticated boundary canary failed"
from pathlib import Path
import hashlib
import hmac
import http.client
import json
import os
import re
import stat
import sys
import urllib.error
import urllib.request

def protected_text(path_text: str) -> str:
    path = Path(path_text)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        assert stat.S_ISREG(metadata.st_mode)
        assert metadata.st_uid == 0
        assert stat.S_IMODE(metadata.st_mode) == 0o600
        return os.read(descriptor, 65536).decode("utf-8")
    finally:
        os.close(descriptor)

runtime_lines = protected_text(sys.argv[1]).splitlines()
key_lines = [line.split("=", 1)[1] for line in runtime_lines if line.startswith("TOOLCHAIN_API_KEY=")]
assert len(key_lines) == 1 and re.fullmatch(r"[0-9a-f]{64}", key_lines[0])
toolchain_key = key_lines[0]
master = protected_text(sys.argv[2]).strip()
assert re.fullmatch(r"[0-9a-f]{64}", master)

context = "sovereign.n8n-ci-evidence-capability.v1"
full_origin = "http://127.0.0.1:8001"
evidence_origin = "http://127.0.0.1:8002"
evidence_url = evidence_origin + "/api/v1/n8n/ci-evidence"
sovereign = {
    "owner": "OuroborosCollective",
    "repo": "Sovereign-Studio-ato",
    "workflow_id": "sovereign-coordinated-release.yml",
    "branch": "main",
}
aurion = {
    "owner": "OuroborosCollective",
    "repo": "Echoes_of_Aurion",
    "workflow_id": 340269357,
    "branch": "main",
}

def capability(key: str, payload: dict) -> str:
    message = (
        context + "\n" + payload["owner"] + "/" + payload["repo"] + "\n"
        + str(payload["workflow_id"]) + "\n" + payload["branch"]
    ).encode("utf-8")
    return hmac.new(key.encode("utf-8"), message, hashlib.sha256).hexdigest()

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

def request(target: str, *, method: str = "GET", payload=None, headers=None, timeout=70):
    encoded = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request_headers = dict(headers or {})
    if encoded is not None:
        request_headers["Content-Type"] = "application/json"
    call = urllib.request.Request(target, data=encoded, headers=request_headers, method=method)
    try:
        with opener.open(call, timeout=timeout) as response:
            return response.status, response.read(), dict(response.headers)
    except urllib.error.HTTPError as error:
        body = error.read()
        return error.code, body, dict(error.headers)

tool_call = {"args": {"goal": "verify"}}
for headers in ({}, {"X-Toolchain-Key": "0" * 64}):
    assert request(
        full_origin + "/api/v1/tools/plan_sandbox_commands",
        method="POST",
        payload=tool_call,
        headers=headers,
    )[0] == 401
rest_status, rest_body, _ = request(
    full_origin + "/api/v1/tools/plan_sandbox_commands",
    method="POST",
    payload=tool_call,
    headers={"X-Toolchain-Key": toolchain_key},
)
assert rest_status == 200 and json.loads(rest_body)["ok"] is True

initialize = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "sovereign-installer-canary", "version": "1.0"},
    },
}
for path, headers in (
    ("/mcp", {}),
    ("/mcp/", {}),
    ("/mcp/anything", {}),
    ("/mcp", {"X-Toolchain-Key": "0" * 64}),
    ("/mcp/", {"X-Toolchain-Key": "0" * 64}),
    ("/mcp/anything", {"X-Toolchain-Key": "0" * 64}),
):
    assert request(
        full_origin + path,
        method="POST",
        payload=initialize,
        headers={
            **headers,
            "Accept": "application/json, text/event-stream",
        },
        timeout=5,
    )[0] == 401

encoded_initialize = json.dumps(initialize, separators=(",", ":")).encode("utf-8")
connection = http.client.HTTPConnection("127.0.0.1", 8001, timeout=5)
connection.putrequest("POST", "/mcp/")
connection.putheader("Content-Type", "application/json")
connection.putheader("Accept", "application/json, text/event-stream")
connection.putheader("Content-Length", str(len(encoded_initialize)))
connection.putheader("X-Toolchain-Key", toolchain_key)
connection.putheader("X-Toolchain-Key", toolchain_key)
connection.endheaders(encoded_initialize)
duplicate_response = connection.getresponse()
duplicate_response.read()
assert duplicate_response.status == 401
connection.close()

mcp_status, mcp_body, _ = request(
    full_origin + "/mcp/",
    method="POST",
    payload=initialize,
    headers={
        "X-Toolchain-Key": toolchain_key,
        "Accept": "application/json, text/event-stream",
    },
    timeout=10,
)
assert mcp_status == 200
assert b'"result"' in mcp_body and b'"serverInfo"' in mcp_body

sovereign_capability = capability(master, sovereign)
aurion_capability = capability(master, aurion)
wrong_master_capability = capability("0" * 64, sovereign)
for supplied in (None, "invalid", master, wrong_master_capability, aurion_capability):
    headers = {} if supplied is None else {"X-Sovereign-Evidence-Capability": supplied}
    assert request(evidence_url, method="POST", payload=sovereign, headers=headers)[0] == 401
assert request(
    evidence_url,
    method="POST",
    payload=aurion,
    headers={"X-Sovereign-Evidence-Capability": sovereign_capability},
)[0] == 401
assert request(
    evidence_url + "/",
    method="POST",
    payload=sovereign,
    headers={"X-Sovereign-Evidence-Capability": sovereign_capability},
)[0] == 404

oversized = dict(sovereign, padding="x" * 4096)
assert request(
    evidence_url,
    method="POST",
    payload=oversized,
    headers={"X-Sovereign-Evidence-Capability": sovereign_capability},
)[0] == 413
connection = http.client.HTTPConnection("127.0.0.1", 8002, timeout=5)
connection.request(
    "POST",
    "/api/v1/n8n/ci-evidence",
    body=iter((b"x" * 2048, b"y" * 2049)),
    headers={
        "Content-Type": "application/json",
        "X-Sovereign-Evidence-Capability": sovereign_capability,
    },
    encode_chunked=True,
)
chunked_response = connection.getresponse()
chunked_response.read()
assert chunked_response.status == 413
connection.close()

unsupported = dict(sovereign, branch="develop")
assert request(
    evidence_url,
    method="POST",
    payload=unsupported,
    headers={"X-Sovereign-Evidence-Capability": capability(master, unsupported)},
)[0] == 403
for path in ("/", "/docs", "/redoc", "/openapi.json", "/mcp", "/api/v1/manifest"):
    assert request(evidence_origin + path)[0] == 404
assert request(
    evidence_origin + "/api/v1/tools/github_read_file",
    method="POST",
    payload={"args": {}},
)[0] == 404
assert request(
    full_origin + "/api/v1/n8n/ci-evidence",
    method="POST",
    payload=sovereign,
    headers={"X-Sovereign-Evidence-Capability": sovereign_capability},
)[0] == 404

for payload, header in (
    (sovereign, sovereign_capability),
    (aurion, aurion_capability),
):
    status, body, _ = request(
        evidence_url,
        method="POST",
        payload=payload,
        headers={"X-Sovereign-Evidence-Capability": header},
    )
    parsed = json.loads(body)
    assert status == 200 and parsed["ok"] is True
    assert parsed["tool"] == "github_actions_run_evidence"
    result = parsed["result"]
    assert result["repository"] == payload["owner"] + "/" + payload["repo"]
    assert result["workflowSelector"] == str(payload["workflow_id"])
    assert result["branch"] == payload["branch"]
PY

PID="$(systemctl show --property MainPID --value "$SERVICE")"
EVIDENCE_PID="$(systemctl show --property MainPID --value "$EVIDENCE_SERVICE")"
[[ "$PID" =~ ^[1-9][0-9]*$ ]] || fail "full service process missing"
[[ "$EVIDENCE_PID" =~ ^[1-9][0-9]*$ ]] || fail "evidence service process missing"
EVIDENCE_UID="$(awk '/^Uid:/ { print $2 }' "/proc/$EVIDENCE_PID/status")"
[[ "$EVIDENCE_UID" =~ ^[1-9][0-9]*$ ]] || fail "evidence service is not unprivileged"
for service_pid in "$PID" "$EVIDENCE_PID"; do
  if tr '\0' '\n' < "/proc/$service_pid/environ" | grep -qE '^(GITHUB_TOKEN|GH_TOKEN|GITHUB_PAT)='; then
    fail "persistent GitHub token inherited by service"
  fi
  if tr '\0' '\n' < "/proc/$service_pid/environ" | grep -q "^$N8N_EVIDENCE_ENV_NAME="; then
    fail "n8n evidence master key leaked into process environment"
  fi
done
[[ "$(tr '\0' '\n' < "/proc/$PID/environ" | grep -c "^$TOOLCHAIN_API_ENV_NAME=" || true)" == "1" ]] || fail "full process toolchain capability cardinality invalid"
[[ "$(tr '\0' '\n' < "/proc/$EVIDENCE_PID/environ" | grep -c "^$TOOLCHAIN_API_ENV_NAME=" || true)" == "0" ]] || fail "toolchain capability leaked into evidence process"
[[ "$(tr '\0' '\n' < "/proc/$PID/environ" | grep -c '^SOVEREIGN_TOOLCHAIN_GITHUB_READ_ONLY=' || true)" == "0" ]] || fail "full process inherited evidence read-only mode"
[[ "$(tr '\0' '\n' < "/proc/$EVIDENCE_PID/environ" | grep -c '^SOVEREIGN_TOOLCHAIN_GITHUB_READ_ONLY=1$' || true)" == "1" ]] || fail "evidence process read-only mode readback failed"

[[ -f "$TARGET/$REVISION_MARKER_NAME" && ! -L "$TARGET/$REVISION_MARKER_NAME" ]] || fail "installed revision marker missing"
INSTALLED_REVISION="$(tr -d '\r\n' < "$TARGET/$REVISION_MARKER_NAME")"
[[ "$INSTALLED_REVISION" == "$EXPECTED_REVISION" ]] || fail "installed revision readback mismatch"
python3 "$ROLLBACK_HELPER" commit \
  --expected-installed-revision "$EXPECTED_REVISION" >/dev/null || fail "rollback manifest commit verification failed"

INSTALL_COMMITTED=1
trap - ERR HUP INT TERM
unset N8N_EVIDENCE_KEY_VALUE N8N_EVIDENCE_KEY_FILE_VALUE TOOLCHAIN_API_KEY_VALUE
unset FULL_EXEC_START EVIDENCE_EXEC_START FULL_ENVIRONMENT_FILES EVIDENCE_ENVIRONMENT_FILES
printf '{"ok":true,"status":"SOVEREIGN_TOOLCHAIN_INSTALLED","revision":"%s","revisionVerified":true,"healthReadback":true,"fullAppLoopbackCanary":true,"fullMcpAuthCanary":true,"evidenceListenerMinimal":true,"n8nEvidenceAuthCanary":true,"n8nEvidenceLaneCapabilities":true,"evidenceGitHubReadOnly":true,"rollbackCapable":true,"rollbackManifestCommitted":true,"mutationPerformed":true,"secretValuesReturned":false}\n' "$INSTALLED_REVISION"
printf 'SOVEREIGN_TOOLCHAIN_INSTALL_OK services=%s,%s revision=%s token_free=true full_mcp_auth=true evidence_listener_minimal=true lane_auth_canary=true rollback_manifest=committed\n' "$SERVICE" "$EVIDENCE_SERVICE" "$INSTALLED_REVISION"
