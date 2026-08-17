#!/usr/bin/env bash
set -Eeuo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_ROOT="/opt/sovereign-chatgpt-tools"
BIN_DIR="$INSTALL_ROOT/bin"
BROKER_DIR="$INSTALL_ROOT/broker"
COMPOSE_TEMPLATE_ROOT="$INSTALL_ROOT/templates"
PGBACKWEB_TEMPLATE_DIR="$COMPOSE_TEMPLATE_ROOT/pgbackweb-wq5r"
PGBACKWEB_TEMPLATE_SOURCE="$SOURCE_DIR/templates/pgbackweb-wq5r"
PATCHMON_TEMPLATE_DIR="$COMPOSE_TEMPLATE_ROOT/patchmon-sovereign"
PATCHMON_TEMPLATE_SOURCE="$SOURCE_DIR/templates/patchmon-sovereign"
PATCHMON_AGENT_ROOT="/opt/patchmon-sovereign/agent"
PATCHMON_AGENT_BIN_TARGET="$PATCHMON_AGENT_ROOT/bin/patchmon-agent"
PATCHMON_AGENT_CONFIG_TARGET="$PATCHMON_AGENT_ROOT/etc"
PATCHMON_AGENT_UNIT_TARGET="$PATCHMON_AGENT_ROOT/systemd/patchmon-agent.service"
PATCHMON_AGENT_BIN_LINK="/usr/local/bin/patchmon-agent"
PATCHMON_AGENT_CONFIG_LINK="/etc/patchmon"
PATCHMON_AGENT_UNIT_LINK="/etc/systemd/system/patchmon-agent.service"
CODE_SERVER_TEMPLATE_DIR="$COMPOSE_TEMPLATE_ROOT/code-server-46bq"
CODE_SERVER_TEMPLATE_SOURCE="$SOURCE_DIR/templates/code-server-46bq"
MILVUS_TEMPLATE_DIR="$COMPOSE_TEMPLATE_ROOT/milvus-sovereign"
MILVUS_TEMPLATE_SOURCE="$SOURCE_DIR/templates/milvus-sovereign"
FREELLMAPI_TEMPLATE_DIR="$COMPOSE_TEMPLATE_ROOT/sovereign-freellmapi"
FREELLMAPI_TEMPLATE_SOURCE="$SOURCE_DIR/templates/sovereign-freellmapi"
FREELLMPOOL_TEMPLATE_DIR="$COMPOSE_TEMPLATE_ROOT/sovereign-freellmpool"
FREELLMPOOL_TEMPLATE_SOURCE="$SOURCE_DIR/templates/sovereign-freellmpool"
DOCKER_AUTH_DIR="$INSTALL_ROOT/docker-auth"
WORKSPACE_DIR="$INSTALL_ROOT/workspaces"
COMMAND_QUEUE_DIR="$INSTALL_ROOT/command-queue"
RUNTIME_EVIDENCE_DIR="$INSTALL_ROOT/runtime-evidence"
MAINTENANCE_DIR="$INSTALL_ROOT/maintenance"
ANDROID_SDK_DIR="/opt/android-sdk"
OWNER_INPUT_HOST_ROOT="/opt/sovereign-owner-managed"
RETIRED_OWNER_GITHUB_PAT_FILE="$OWNER_INPUT_HOST_ROOT/github_pat.txt"
GITHUB_APP_SECRET_DIR="/opt/secure/sovereign-github-app"
GITHUB_APP_PRIVATE_KEY_FILE="$GITHUB_APP_SECRET_DIR/private-key.pem"
MCP_GITHUB_APP_PRIVATE_KEY_FILE="/run/secrets/sovereign-github-app-private-key.pem"
MCP_GITHUB_APP_INSTALLATION_ID="153170343"
BACKEND_WORKSPACE_HOST_ROOT="/opt/sovereign-agent-workspaces"
BACKEND_WORKSPACE_UID="10001"
BACKEND_WORKSPACE_GID="10001"
ENV_FILE="$INSTALL_ROOT/.env"
MANAGED_ENV="$INSTALL_ROOT/runtime.env"
BACKEND_MANAGED_ENV="$INSTALL_ROOT/backend-runtime.env"
GHCR_ENV="$INSTALL_ROOT/.ghcr.env"
TUNNEL_ENV="$INSTALL_ROOT/tunnel.env"
BROKER_ENV="$INSTALL_ROOT/broker.env"
BROKER_GOVERNANCE_MODE="$BROKER_DIR/sovereign-governance-mode.json"
BROKER_SERVICE="/etc/systemd/system/sovereign-chatgpt-broker.service"
COMMAND_WORKER_SERVICE="/etc/systemd/system/sovereign-chatgpt-command-worker.service"
SELF_UPDATE_SERVICE="/etc/systemd/system/sovereign-chatgpt-mcp-self-update.service"
SELF_UPDATE_BIN="$BIN_DIR/self-update-chatgpt-mcp"
RELEASE_RECONCILER_BIN="$BIN_DIR/reconcile-main-release"
RELEASE_READBACK_BIN="$BIN_DIR/run-coordinated-release-readback"
RELEASE_RECONCILER_SERVICE="/etc/systemd/system/sovereign-release-reconciler.service"
RELEASE_RECONCILER_TIMER="/etc/systemd/system/sovereign-release-reconciler.timer"
TUNNEL_SERVICE="/etc/systemd/system/sovereign-openai-tunnel.service"
MCP_UID="10001"
MCP_GID="10001"
MCP_HOST_PORT="8090"
NEURO_RUNTIME_STATE_HOST_DIR="$INSTALL_ROOT/tool-routing-state/neuro-runtime"
EXPECTED_MCP_TOOL_COUNT="250"
MCP_IMAGE_REPOSITORY="${SOVEREIGN_MCP_IMAGE_REPOSITORY:-ghcr.io/ouroboroscollective/sovereign-chatgpt-mcp}"
EXPECTED_REVISION="${SOVEREIGN_MCP_EXPECTED_REVISION:-}"
EXPECTED_MCP_DIGEST="${SOVEREIGN_MCP_EXPECTED_DIGEST:-}"
EXPECTED_CROSS_RUNTIME_PARITY="true"
MCP_IMAGE_PULL_ATTEMPTS="${SOVEREIGN_MCP_IMAGE_PULL_ATTEMPTS:-36}"
MCP_IMAGE_PULL_DELAY_SECONDS="${SOVEREIGN_MCP_IMAGE_PULL_DELAY_SECONDS:-10}"
BROKER_READY_ATTEMPTS="${SOVEREIGN_MCP_BROKER_READY_ATTEMPTS:-90}"
REQUIRE_TUNNEL="${SOVEREIGN_MCP_REQUIRE_TUNNEL:-0}"
TUNNEL_MODE="${SOVEREIGN_MCP_TUNNEL_MODE:-auto}"
ALLOW_FIRST_INSTALL_WITHOUT_PREDECESSOR="${SOVEREIGN_MCP_ALLOW_FIRST_INSTALL_WITHOUT_PREDECESSOR:-0}"
INSTALL_STAGE="initializing"
INSTALL_FAILURE_REASON=""
INSTALL_COMPLETED=0
ROLLBACK_ARMED=0
ROLLBACK_DIR=""
ROLLBACK_MANIFEST=""
PREVIOUS_MCP_IMAGE_DIGEST=""
PREVIOUS_MCP_REGISTRY_FILE=""
PREVIOUS_MCP_TOOL_SURFACE_CAPTURED=0
PREVIOUS_MCP_CONTAINER_PRESENT=0
PREVIOUS_MCP_REGISTRY_CAPTURE_MODE="attested-first-install-no-predecessor"

fail() {
  INSTALL_FAILURE_REASON="$*"
  exit 1
}

prepare_patchmon_agent_sandbox_paths() {
  install -d -m 0750 "$PATCHMON_AGENT_ROOT" "$PATCHMON_AGENT_ROOT/bin" "$PATCHMON_AGENT_ROOT/systemd"
  install -d -m 0700 "$PATCHMON_AGENT_CONFIG_TARGET"

  if [[ -L "$PATCHMON_AGENT_BIN_LINK" ]]; then
    [[ "$(readlink "$PATCHMON_AGENT_BIN_LINK")" == "$PATCHMON_AGENT_BIN_TARGET" ]] \
      || fail "PatchMon agent binary symlink points outside the managed root"
  elif [[ -e "$PATCHMON_AGENT_BIN_LINK" ]]; then
    [[ -f "$PATCHMON_AGENT_BIN_LINK" ]] \
      || fail "PatchMon agent binary path is neither a regular file nor the managed symlink"
  else
    ln -s "$PATCHMON_AGENT_BIN_TARGET" "$PATCHMON_AGENT_BIN_LINK"
  fi

  if [[ -L "$PATCHMON_AGENT_CONFIG_LINK" ]]; then
    [[ "$(readlink "$PATCHMON_AGENT_CONFIG_LINK")" == "$PATCHMON_AGENT_CONFIG_TARGET" ]] \
      || fail "PatchMon agent config symlink points outside the managed root"
  elif [[ -e "$PATCHMON_AGENT_CONFIG_LINK" ]]; then
    [[ -d "$PATCHMON_AGENT_CONFIG_LINK" ]] \
      || fail "PatchMon agent config path is neither a directory nor the managed symlink"
  else
    ln -s "$PATCHMON_AGENT_CONFIG_TARGET" "$PATCHMON_AGENT_CONFIG_LINK"
  fi

  if [[ -L "$PATCHMON_AGENT_UNIT_LINK" ]]; then
    [[ "$(readlink "$PATCHMON_AGENT_UNIT_LINK")" == "$PATCHMON_AGENT_UNIT_TARGET" ]] \
      || fail "PatchMon agent unit symlink points outside the managed root"
  elif [[ -e "$PATCHMON_AGENT_UNIT_LINK" ]]; then
    [[ -f "$PATCHMON_AGENT_UNIT_LINK" ]] \
      || fail "PatchMon agent unit path is neither a regular file nor the managed symlink"
  else
    ln -s "$PATCHMON_AGENT_UNIT_TARGET" "$PATCHMON_AGENT_UNIT_LINK"
  fi

  chown -R root:root "$PATCHMON_AGENT_ROOT"
  chmod 0750 "$PATCHMON_AGENT_ROOT" "$PATCHMON_AGENT_ROOT/bin" "$PATCHMON_AGENT_ROOT/systemd"
  chmod 0700 "$PATCHMON_AGENT_CONFIG_TARGET"
}

read_value() {
  local file="$1"
  local key="$2"
  sed -n "s/^${key}=//p" "$file" | tail -n 1
}

read_mcp_value() {
  local key="$1"
  if [[ -f "$MANAGED_ENV" ]] && grep -q "^${key}=" "$MANAGED_ENV"; then
    read_value "$MANAGED_ENV" "$key"
  else
    read_value "$ENV_FILE" "$key"
  fi
}

read_backend_value() {
  local key="$1"
  if [[ -f "$BACKEND_MANAGED_ENV" ]] && grep -q "^${key}=" "$BACKEND_MANAGED_ENV"; then
    read_value "$BACKEND_MANAGED_ENV" "$key"
  else
    read_value "$BACKEND_ENV_PATH" "$key"
  fi
}

prepare_mcp_github_app_secret() {
  local app_id encoded_key temporary_key
  INSTALL_STAGE="prepare_mcp_github_app_secret"
  app_id="$(read_backend_value GITHUB_APP_ID)"
  encoded_key="$(read_backend_value GITHUB_APP_PRIVATE_KEY)"
  [[ "$app_id" =~ ^[1-9][0-9]*$ ]] || fail "backend GitHub App ID is missing or invalid"
  [[ -n "$encoded_key" ]] || fail "backend GitHub App private key is missing"
  install -d -m 0750 -o root -g "$MCP_GID" "$GITHUB_APP_SECRET_DIR"
  temporary_key="$(mktemp "$GITHUB_APP_SECRET_DIR/.private-key.XXXXXX")" \
    || fail "could not create temporary GitHub App private key file"
  if ! printf '%s' "$encoded_key" | base64 --decode > "$temporary_key"; then
    rm -f "$temporary_key"
    fail "backend GitHub App private key is not valid base64"
  fi
  if ! grep -Eq '^-----BEGIN (RSA )?PRIVATE KEY-----$' "$temporary_key"; then
    rm -f "$temporary_key"
    fail "backend GitHub App private key has an invalid PEM header"
  fi
  chown root:"$MCP_GID" "$temporary_key" || { rm -f "$temporary_key"; fail "could not set GitHub App private key ownership"; }
  chmod 0640 "$temporary_key" || { rm -f "$temporary_key"; fail "could not set GitHub App private key mode"; }
  mv -f "$temporary_key" "$GITHUB_APP_PRIVATE_KEY_FILE" || { rm -f "$temporary_key"; fail "could not activate GitHub App private key"; }
  chown root:"$MCP_GID" "$GITHUB_APP_PRIVATE_KEY_FILE" || fail "could not verify GitHub App private key ownership"
  chmod 0640 "$GITHUB_APP_PRIVATE_KEY_FILE" || fail "could not verify GitHub App private key mode"
  set_value "$MANAGED_ENV" SOVEREIGN_MCP_GITHUB_APP_ID "$app_id"
  set_value "$MANAGED_ENV" SOVEREIGN_MCP_GITHUB_APP_INSTALLATION_ID "$MCP_GITHUB_APP_INSTALLATION_ID"
  set_value "$MANAGED_ENV" SOVEREIGN_MCP_GITHUB_APP_PRIVATE_KEY_FILE "$MCP_GITHUB_APP_PRIVATE_KEY_FILE"
  unset app_id encoded_key temporary_key
}

ensure_managed_env() {
  local file="$1"
  local label="${2:-${file##*/}}"
  local parent attrs=""
  local cleared_immutable=0
  local cleared_append_only=0
  INSTALL_STAGE="ensure_managed_environment:${label}"
  if [[ -e "$file" || -L "$file" ]]; then
    ensure_private_file_mode "$file" "$label"
    return 0
  fi
  parent="$(dirname -- "$file")"
  [[ -d "$parent" && ! -L "$parent" ]] \
    || fail "managed environment parent is not a regular directory: label=$label parent=$parent"
  if install -m 0600 /dev/null "$file"; then
    return 0
  fi
  attrs="$(lsattr -d -- "$parent" 2>/dev/null | awk '{print $1}' || true)"
  if [[ "$attrs" == *i* ]]; then
    chattr -i -- "$parent" \
      || fail "managed environment parent immutable-bit clear failed: label=$label parent=$parent"
    cleared_immutable=1
  fi
  if [[ "$attrs" == *a* ]]; then
    if ! chattr -a -- "$parent"; then
      [[ "$cleared_immutable" != "1" ]] || chattr +i -- "$parent" >/dev/null 2>&1 || true
      fail "managed environment parent append-only-bit clear failed: label=$label parent=$parent"
    fi
    cleared_append_only=1
  fi
  if [[ "$cleared_immutable" != "1" && "$cleared_append_only" != "1" ]]; then
    fail "managed environment creation failed without protected parent attributes: label=$label parent=$parent"
  fi
  if ! install -m 0600 /dev/null "$file"; then
    [[ "$cleared_append_only" != "1" ]] || chattr +a -- "$parent" >/dev/null 2>&1 || true
    [[ "$cleared_immutable" != "1" ]] || chattr +i -- "$parent" >/dev/null 2>&1 || true
    fail "managed environment creation failed after protected parent attribute clear: label=$label parent=$parent"
  fi
  if [[ "$cleared_append_only" == "1" ]]; then
    chattr +a -- "$parent" \
      || fail "managed environment parent append-only-bit restore failed: label=$label parent=$parent"
  fi
  if [[ "$cleared_immutable" == "1" ]]; then
    chattr +i -- "$parent" \
      || fail "managed environment parent immutable-bit restore failed: label=$label parent=$parent"
  fi
}

install_ci_runtime_readback_authorization() {
  local key_source="$SOURCE_DIR/deploy/ci-runtime-readback.pub"
  local root_ssh_dir="/root/.ssh"
  local authorized_keys="$root_ssh_dir/authorized_keys"
  local temporary=""
  INSTALL_STAGE="install_ci_runtime_readback_authorization"
  [[ -f "$key_source" && ! -L "$key_source" ]] \
    || fail "CI runtime readback public key is missing"
  [[ "$(awk 'NF {count += 1} END {print count + 0}' "$key_source")" == "1" ]] \
    || fail "CI runtime readback public key must contain exactly one line"
  ssh-keygen -lf "$key_source" >/dev/null \
    || fail "CI runtime readback public key is invalid"
  install -d -m 0700 -o root -g root "$root_ssh_dir"
  touch "$authorized_keys"
  chown root:root "$authorized_keys"
  chmod 0600 "$authorized_keys"
  prepare_managed_private_file_mutation "$authorized_keys" "root-authorized-keys"
  temporary="$(mktemp "$root_ssh_dir/.authorized_keys.XXXXXX")" \
    || { restore_managed_private_file_mutation_best_effort "$authorized_keys"; fail "CI runtime readback authorization temporary file creation failed"; }
  if ! {
    grep -Fv 'sovereign-runtime-readback-ci' "$authorized_keys" || true
    printf 'command="%s",restrict ' "$RELEASE_READBACK_BIN"
    cat "$key_source"
  } > "$temporary"; then
    rm -f "$temporary"
    restore_managed_private_file_mutation_best_effort "$authorized_keys"
    fail "CI runtime readback authorization write failed"
  fi
  chown root:root "$temporary"
  chmod 0600 "$temporary"
  mv -f "$temporary" "$authorized_keys"
  restore_managed_private_file_mutation "$authorized_keys" "root-authorized-keys"
  grep -Fq 'command="/opt/sovereign-chatgpt-tools/bin/run-coordinated-release-readback",restrict ssh-ed25519 ' "$authorized_keys" \
    || fail "CI runtime readback forced-command authorization is missing"
}


ensure_private_file_mode() {
  local file="$1"
  local label="${2:-${file##*/}}"
  local current_mode attrs=""
  local cleared_immutable=0
  local cleared_append_only=0
  INSTALL_STAGE="ensure_private_file_mode:${label}"
  [[ -f "$file" && ! -L "$file" ]] \
    || fail "private file is not a regular file: label=$label file=$file"
  current_mode="$(stat -c '%a' -- "$file")" \
    || fail "private file mode read failed: label=$label file=$file"
  if [[ "$current_mode" == "600" ]]; then
    return 0
  fi
  if chmod 0600 -- "$file"; then
    return 0
  fi
  attrs="$(lsattr -d -- "$file" 2>/dev/null | awk '{print $1}' || true)"
  if [[ "$attrs" == *i* ]]; then
    chattr -i -- "$file" \
      || fail "private file immutable-bit clear failed for mode repair: label=$label file=$file"
    cleared_immutable=1
  fi
  if [[ "$attrs" == *a* ]]; then
    if ! chattr -a -- "$file"; then
      [[ "$cleared_immutable" != "1" ]] || chattr +i -- "$file" >/dev/null 2>&1 || true
      fail "private file append-only-bit clear failed for mode repair: label=$label file=$file"
    fi
    cleared_append_only=1
  fi
  if [[ "$cleared_immutable" != "1" && "$cleared_append_only" != "1" ]]; then
    fail "private file mode repair failed without protected attributes: label=$label file=$file mode=$current_mode"
  fi
  if ! chmod 0600 -- "$file"; then
    [[ "$cleared_append_only" != "1" ]] || chattr +a -- "$file" >/dev/null 2>&1 || true
    [[ "$cleared_immutable" != "1" ]] || chattr +i -- "$file" >/dev/null 2>&1 || true
    fail "private file mode repair failed after protected-attribute clear: label=$label file=$file"
  fi
  if [[ "$cleared_append_only" == "1" ]]; then
    chattr +a -- "$file" \
      || fail "private file append-only-bit restore failed after mode repair: label=$label file=$file"
  fi
  if [[ "$cleared_immutable" == "1" ]]; then
    chattr +i -- "$file" \
      || fail "private file immutable-bit restore failed after mode repair: label=$label file=$file"
  fi
  current_mode="$(stat -c '%a' -- "$file")" \
    || fail "private file post-repair mode read failed: label=$label file=$file"
  [[ "$current_mode" == "600" ]] \
    || fail "private file mode remains unsafe after repair: label=$label file=$file mode=$current_mode"
}

MANAGED_PRIVATE_FILE_ORIGINAL_ATTRS=""

prepare_managed_private_file_mutation() {
  local file="$1"
  local label="$2"
  local attrs=""
  MANAGED_PRIVATE_FILE_ORIGINAL_ATTRS=""
  INSTALL_STAGE="prepare_managed_private_file:${label}"
  if [[ ! -e "$file" && ! -L "$file" ]]; then
    return 0
  fi
  [[ -f "$file" && ! -L "$file" ]] \
    || fail "managed private mutation target is not a regular file: label=$label file=$file"
  attrs="$(lsattr -d -- "$file" 2>/dev/null | awk '{print $1}' || true)"
  MANAGED_PRIVATE_FILE_ORIGINAL_ATTRS="$attrs"
  if [[ "$attrs" == *i* ]]; then
    chattr -i -- "$file" \
      || fail "managed private file immutable-bit clear failed: label=$label file=$file"
  fi
  if [[ "$attrs" == *a* ]]; then
    if ! chattr -a -- "$file"; then
      [[ "$attrs" != *i* ]] || chattr +i -- "$file" >/dev/null 2>&1 || true
      fail "managed private file append-only-bit clear failed: label=$label file=$file"
    fi
  fi
}

restore_managed_private_file_mutation() {
  local file="$1"
  local label="$2"
  local attrs="$MANAGED_PRIVATE_FILE_ORIGINAL_ATTRS"
  INSTALL_STAGE="restore_managed_private_file:${label}"
  if [[ "$attrs" == *a* ]]; then
    chattr +a -- "$file" \
      || fail "managed private file append-only-bit restore failed: label=$label file=$file"
  fi
  if [[ "$attrs" == *i* ]]; then
    chattr +i -- "$file" \
      || fail "managed private file immutable-bit restore failed: label=$label file=$file"
  fi
  MANAGED_PRIVATE_FILE_ORIGINAL_ATTRS=""
}

restore_managed_private_file_mutation_best_effort() {
  local file="$1"
  local attrs="$MANAGED_PRIVATE_FILE_ORIGINAL_ATTRS"
  [[ "$attrs" != *a* || ! -e "$file" ]] || chattr +a -- "$file" >/dev/null 2>&1 || true
  [[ "$attrs" != *i* || ! -e "$file" ]] || chattr +i -- "$file" >/dev/null 2>&1 || true
  MANAGED_PRIVATE_FILE_ORIGINAL_ATTRS=""
}

set_value() {
  local file="$1"
  local key="$2"
  local value="$3"
  local label="env-set:${key}"
  prepare_managed_private_file_mutation "$file" "$label"
  INSTALL_STAGE="mutate_managed_private_file:${label}"
  if ! python3 - "$file" "$key" "$value" <<'PY'
from pathlib import Path
import errno
import os
import stat
import sys

path = Path(sys.argv[1])
key = sys.argv[2]
value = sys.argv[3]
lines = path.read_text("utf-8").splitlines() if path.exists() else []
out = []
replaced = False
for line in lines:
    if line.startswith(key + "="):
        out.append(f"{key}={value}")
        replaced = True
    else:
        out.append(line)
if not replaced:
    out.append(f"{key}={value}")
payload = "\n".join(out) + "\n"
temporary = path.with_suffix(path.suffix + ".tmp")
temporary.write_text(payload, "utf-8")
os.chmod(temporary, 0o600)
try:
    temporary.replace(path)
except OSError as exc:
    if exc.errno not in {errno.EPERM, errno.EBUSY, errno.EXDEV}:
        temporary.unlink(missing_ok=True)
        raise
    try:
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.chmod(path, 0o600)
        except OSError as chmod_exc:
            if chmod_exc.errno not in {errno.EPERM, errno.EACCES, errno.EROFS}:
                raise
            mode = stat.S_IMODE(path.stat().st_mode)
            if mode & 0o077:
                raise PermissionError(f"protected file has unsafe mode: {mode:o}") from chmod_exc
    finally:
        temporary.unlink(missing_ok=True)
PY
  then
    restore_managed_private_file_mutation_best_effort "$file"
    fail "managed private file set failed: label=$label file=$file"
  fi
  restore_managed_private_file_mutation "$file" "$label"
}

remove_value() {
  local file="$1"
  local key="$2"
  local label="env-remove:${key}"
  [[ -e "$file" ]] || return 0
  prepare_managed_private_file_mutation "$file" "$label"
  INSTALL_STAGE="mutate_managed_private_file:${label}"
  if ! python3 - "$file" "$key" <<'PY'
from pathlib import Path
import os
import sys

path = Path(sys.argv[1])
key = sys.argv[2]
if not path.exists():
    raise SystemExit(0)
lines = path.read_text("utf-8").splitlines()
out = [line for line in lines if not line.startswith(key + "=")]
temporary = path.with_suffix(path.suffix + ".tmp")
temporary.write_text(("\n".join(out) + "\n") if out else "", "utf-8")
os.chmod(temporary, 0o600)
temporary.replace(path)
PY
  then
    restore_managed_private_file_mutation_best_effort "$file"
    fail "managed private file key removal failed: label=$label file=$file"
  fi
  restore_managed_private_file_mutation "$file" "$label"
}

remove_csv_values() {
  local file="$1"
  local key="$2"
  local blocked_csv="$3"
  local label="env-remove-csv:${key}"
  [[ -e "$file" ]] || return 0
  prepare_managed_private_file_mutation "$file" "$label"
  INSTALL_STAGE="mutate_managed_private_file:${label}"
  if ! python3 - "$file" "$key" "$blocked_csv" <<'PY'
from pathlib import Path
import os
import sys

path = Path(sys.argv[1])
key = sys.argv[2]
blocked = {item.strip() for item in sys.argv[3].split(",") if item.strip()}
if not path.exists():
    raise SystemExit(0)
out = []
for line in path.read_text("utf-8").splitlines():
    if not line.startswith(key + "="):
        out.append(line)
        continue
    values = [item.strip() for item in line.split("=", 1)[1].split(",") if item.strip()]
    retained = [item for item in values if item not in blocked]
    if retained:
        out.append(key + "=" + ",".join(dict.fromkeys(retained)))
temporary = path.with_suffix(path.suffix + ".tmp")
temporary.write_text(("\n".join(out) + "\n") if out else "", "utf-8")
os.chmod(temporary, 0o600)
temporary.replace(path)
PY
  then
    restore_managed_private_file_mutation_best_effort "$file"
    fail "managed private file csv removal failed: label=$label file=$file"
  fi
  restore_managed_private_file_mutation "$file" "$label"
}

valid_mcp_image_digest() {
  local value="$1"
  [[ "$value" == "$MCP_IMAGE_REPOSITORY"@sha256:* ]] \
    && [[ "${value#*@}" =~ ^sha256:[0-9a-f]{64}$ ]]
}

resolve_previous_mcp_registry_capture_mode() {
  local container_names=""
  local running_state=""
  container_names="$(
    docker container ls --all \
      --filter 'name=^/sovereign-chatgpt-mcp$' \
      --format '{{.Names}}' 2>/dev/null
  )" || fail "could not enumerate predecessor MCP containers"
  if [[ -z "$container_names" ]]; then
    [[ "$ALLOW_FIRST_INSTALL_WITHOUT_PREDECESSOR" == "1" ]] \
      || fail "no predecessor MCP container exists; explicit first-install attestation is required"
    printf '%s\n' "attested-first-install-no-predecessor"
    return 0
  fi
  [[ "$container_names" == "sovereign-chatgpt-mcp" ]] \
    || fail "predecessor MCP container discovery returned an ambiguous result"
  running_state="$(
    docker container inspect sovereign-chatgpt-mcp --format '{{.State.Running}}' 2>/dev/null
  )" || fail "could not inspect the existing predecessor MCP container state"
  case "$running_state" in
    true)
      # Health may be healthy, starting, or unhealthy.  A running process can
      # still expose its exact registered contract surface through docker exec.
      printf '%s\n' "running-container"
      ;;
    false)
      printf '%s\n' "immutable-image-offline"
      ;;
    *)
      fail "existing predecessor MCP container returned an invalid running state"
      ;;
  esac
}

classify_mcp_image_pull_failure() {
  local log_file="$1"
  if grep -Eqi '(unauthorized|denied|authentication required|insufficient[_ -]scope|no basic auth credentials)' "$log_file"; then
    printf 'registry_auth_denied\n'
  elif grep -Eqi '(manifest unknown|manifest[^[:cntrl:]]*(not found|unknown)|name unknown|repository does not exist|failed to resolve reference[^[:cntrl:]]*not found|(^|[^[:alpha:]])not found([^[:alpha:]]|$))' "$log_file"; then
    printf 'image_not_published\n'
  elif grep -Eqi '(timeout|timed out|connection reset|temporary failure|tls handshake timeout|service unavailable|(^|[^0-9])(502|503|504)([^0-9]|$))' "$log_file"; then
    printf 'registry_transport\n'
  else
    printf 'unexpected_pull_failure\n'
  fi
}

pull_exact_mcp_image() {
  if [[ -n "$DOCKER_CONFIG_VALUE" ]]; then
    docker --config "$DOCKER_CONFIG_VALUE" pull "$MCP_TAGGED_IMAGE"
  else
    docker pull "$MCP_TAGGED_IMAGE"
  fi
}

wait_for_exact_mcp_image() {
  local attempt failure_family pull_log
  pull_log="$(mktemp)"
  for attempt in $(seq 1 "$MCP_IMAGE_PULL_ATTEMPTS"); do
    if pull_exact_mcp_image >"$pull_log" 2>&1; then
      rm -f "$pull_log"
      return 0
    fi
    failure_family="$(classify_mcp_image_pull_failure "$pull_log")"
    if [[ "$failure_family" == "registry_auth_denied" || "$failure_family" == "unexpected_pull_failure" ]]; then
      rm -f "$pull_log"
      fail "immutable MCP image pull failed: family=$failure_family attempt=$attempt/$MCP_IMAGE_PULL_ATTEMPTS"
    fi
    if (( attempt >= MCP_IMAGE_PULL_ATTEMPTS )); then
      rm -f "$pull_log"
      fail "immutable MCP image pull failed: family=$failure_family attempts=$MCP_IMAGE_PULL_ATTEMPTS"
    fi
    sleep "$MCP_IMAGE_PULL_DELAY_SECONDS"
  done
  rm -f "$pull_log"
  fail "immutable MCP image pull failed without a terminal classification"
}

resolve_running_mcp_image_digest() {
  local configured image_id
  configured="$(docker inspect sovereign-chatgpt-mcp --format '{{.Config.Image}}' 2>/dev/null || true)"
  if valid_mcp_image_digest "$configured"; then
    printf '%s\n' "$configured"
    return 0
  fi
  image_id="$(docker inspect sovereign-chatgpt-mcp --format '{{.Image}}' 2>/dev/null || true)"
  [[ -n "$image_id" ]] || return 1
  docker image inspect --format '{{json .RepoDigests}}' "$image_id" 2>/dev/null \
    | python3 -c 'import json,sys; repo=sys.argv[1]+"@"; values=json.load(sys.stdin); print(next((item for item in values if isinstance(item,str) and item.startswith(repo)), ""))' "$MCP_IMAGE_REPOSITORY"
}

backup_control_plane_file() {
  local target="$1"
  local key backup_target
  [[ -n "$ROLLBACK_DIR" && -n "$ROLLBACK_MANIFEST" ]] || fail "rollback storage is not initialized"
  if grep -Fqx "$target" "$ROLLBACK_MANIFEST.paths" 2>/dev/null; then
    return 0
  fi
  printf '%s\n' "$target" >> "$ROLLBACK_MANIFEST.paths" \
    || fail "rollback manifest path write failed: target=$target"
  if ! key="$(printf '%s' "$target" | sha256sum | awk '{print $1}')"; then
    fail "rollback backup key generation failed: target=$target"
  fi
  backup_target="$ROLLBACK_DIR/$key"
  if [[ -e "$target" || -L "$target" ]]; then
    if [[ -f "$target" && ! -L "$target" ]]; then
      if ! python3 - "$target" "$backup_target" <<'PY'
from pathlib import Path
import os
import stat
import sys

source = Path(sys.argv[1])
target = Path(sys.argv[2])
metadata = source.stat(follow_symlinks=False)
payload = source.read_bytes()
with target.open("wb") as handle:
    handle.write(payload)
    handle.flush()
    os.fsync(handle.fileno())
os.chmod(target, stat.S_IMODE(metadata.st_mode))
os.chown(target, metadata.st_uid, metadata.st_gid)
os.utime(
    target,
    ns=(metadata.st_atime_ns, metadata.st_mtime_ns),
    follow_symlinks=False,
)
PY
      then
        fail "rollback regular-file backup failed: target=$target"
      fi
    elif ! cp -a "$target" "$backup_target"; then
      fail "rollback special-file backup failed: target=$target"
    fi
    printf '%s\t%s\n' "$target" "$key" >> "$ROLLBACK_MANIFEST" \
      || fail "rollback manifest write failed: target=$target"
  else
    printf '%s\t%s\n' "$target" "__MISSING__" >> "$ROLLBACK_MANIFEST" \
      || fail "rollback missing-path manifest write failed: target=$target"
  fi
}

install_managed_control_plane_file() {
  local mode="$1"
  local source="$2"
  local target="$3"
  local label="$4"
  local target_attrs=""
  local target_was_immutable=0
  local target_owner_group=""
  INSTALL_STAGE="validate_control_plane_file:${label}"
  [[ -f "$source" && ! -L "$source" ]] || fail "managed control-plane source is not a regular file: $label"
  if [[ -e "$target" || -L "$target" ]]; then
    [[ -f "$target" && ! -L "$target" ]] \
      || fail "managed control-plane target is not a regular file: $target"
  fi
  backup_control_plane_file "$target"
  if [[ -e "$target" ]]; then
    target_attrs="$(lsattr -d -- "$target" 2>/dev/null | awk '{print $1}' || true)"
    if [[ "$target_attrs" == *i* ]]; then
      INSTALL_STAGE="prepare_control_plane_file:${label}"
      chattr -i -- "$target" \
        || fail "managed control-plane immutable-bit clear failed: label=$label target=$target"
      target_was_immutable=1
    fi
  fi
  INSTALL_STAGE="copy_control_plane_file:${label}"
  if ! python3 - "$source" "$target" "$mode" <<'PY'
from pathlib import Path
import errno
import os
import sys

source = Path(sys.argv[1])
target = Path(sys.argv[2])
mode = int(sys.argv[3], 8)
payload = source.read_bytes()
temporary = target.with_name(f".{target.name}.sovereign-install-{os.getpid()}")
temporary.write_bytes(payload)
os.chmod(temporary, mode)
try:
    temporary.replace(target)
except OSError as exc:
    if exc.errno not in {errno.EPERM, errno.EBUSY, errno.EXDEV}:
        temporary.unlink(missing_ok=True)
        raise
    try:
        with target.open("wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(target, mode)
    finally:
        temporary.unlink(missing_ok=True)
PY
  then
    if [[ "$target_was_immutable" == "1" && -e "$target" ]]; then
      chattr +i -- "$target" >/dev/null 2>&1 || true
    fi
    fail "managed control-plane copy failed: label=$label target=$target"
  fi
  case "$target" in
    "$BROKER_DIR"/*|"$BIN_DIR"/*|"$COMPOSE_TEMPLATE_ROOT"/*)
      target_owner_group="root:sovereign-mcp"
      ;;
  esac
  if [[ -n "$target_owner_group" ]]; then
    INSTALL_STAGE="set_control_plane_file_ownership:${label}"
    chown "$target_owner_group" -- "$target" \
      || fail "managed control-plane ownership update failed: label=$label target=$target owner=$target_owner_group"
  fi
  if [[ "$target_was_immutable" == "1" ]]; then
    INSTALL_STAGE="restore_control_plane_file_immutable:${label}"
    chattr +i -- "$target" \
      || fail "managed control-plane immutable-bit restore failed: label=$label target=$target"
  fi
}

backup_managed_control_plane_file() {
  local target="$1"
  local label="$2"
  INSTALL_STAGE="backup_control_plane_file:${label}"
  backup_control_plane_file "$target"
}

remove_managed_legacy_file() {
  local target="$1"
  local label="$2"
  INSTALL_STAGE="remove_legacy_control_plane_file:${label}"
  backup_control_plane_file "$target"
  if [[ ! -e "$target" && ! -L "$target" ]]; then
    return 0
  fi
  [[ -f "$target" && ! -L "$target" ]] \
    || fail "legacy managed path is not a regular file: label=$label target=$target"
  if ! rm -f -- "$target"; then
    command -v chattr >/dev/null 2>&1 \
      || fail "legacy managed file removal failed and chattr is unavailable: label=$label target=$target"
    chattr -i -- "$target" \
      || fail "legacy managed file immutable-bit clear failed: label=$label target=$target"
    rm -f -- "$target" \
      || fail "legacy managed file removal failed after immutable-bit clear: label=$label target=$target"
  fi
  [[ ! -e "$target" && ! -L "$target" ]] \
    || fail "legacy managed file still exists after removal: label=$label target=$target"
}

set_managed_control_plane_directory_ownership() {
  local target="$1"
  local label="$2"
  local target_attrs=""
  local cleared_immutable=0
  local cleared_append_only=0
  INSTALL_STAGE="set_control_plane_directory_ownership:${label}"
  [[ -d "$target" && ! -L "$target" ]] \
    || fail "managed control-plane ownership target is not a regular directory: label=$label target=$target"
  if chown root:sovereign-mcp -- "$target"; then
    return 0
  fi
  target_attrs="$(lsattr -d -- "$target" 2>/dev/null | awk '{print $1}' || true)"
  if [[ "$target_attrs" == *i* ]]; then
    chattr -i -- "$target" \
      || fail "managed control-plane directory immutable-bit clear failed: label=$label target=$target"
    cleared_immutable=1
  fi
  if [[ "$target_attrs" == *a* ]]; then
    chattr -a -- "$target" \
      || {
        if [[ "$cleared_immutable" == "1" ]]; then
          chattr +i -- "$target" >/dev/null 2>&1 || true
        fi
        fail "managed control-plane directory append-only-bit clear failed: label=$label target=$target"
      }
    cleared_append_only=1
  fi
  if [[ "$cleared_immutable" != "1" && "$cleared_append_only" != "1" ]]; then
    fail "managed control-plane directory ownership update failed without protected attributes: label=$label target=$target"
  fi
  if ! chown root:sovereign-mcp -- "$target"; then
    [[ "$cleared_append_only" != "1" ]] || chattr +a -- "$target" >/dev/null 2>&1 || true
    [[ "$cleared_immutable" != "1" ]] || chattr +i -- "$target" >/dev/null 2>&1 || true
    fail "managed control-plane directory ownership update failed after protected-attribute clear: label=$label target=$target"
  fi
  if [[ "$cleared_append_only" == "1" ]]; then
    chattr +a -- "$target" \
      || fail "managed control-plane directory append-only-bit restore failed: label=$label target=$target"
  fi
  if [[ "$cleared_immutable" == "1" ]]; then
    chattr +i -- "$target" \
      || fail "managed control-plane directory immutable-bit restore failed: label=$label target=$target"
  fi
}

remove_managed_legacy_directory() {
  local target="$1"
  local label="$2"
  local target_attrs=""
  local cleared_immutable=0
  local cleared_append_only=0
  INSTALL_STAGE="remove_legacy_control_plane_directory:${label}"
  if [[ ! -e "$target" && ! -L "$target" ]]; then
    return 0
  fi
  [[ -d "$target" && ! -L "$target" ]] \
    || fail "legacy managed directory is not a regular directory: label=$label target=$target"
  if rmdir -- "$target"; then
    return 0
  fi
  if ! target_attrs="$(lsattr -d -- "$target" 2>/dev/null | awk '{print $1}')"; then
    fail "legacy managed directory attribute read failed after removal refusal: label=$label target=$target"
  fi
  if [[ "$target_attrs" == *i* ]]; then
    chattr -i -- "$target" \
      || fail "legacy managed directory immutable-bit clear failed: label=$label target=$target"
    cleared_immutable=1
  fi
  if [[ "$target_attrs" == *a* ]]; then
    chattr -a -- "$target" \
      || {
        if [[ "$cleared_immutable" == "1" ]]; then
          chattr +i -- "$target" >/dev/null 2>&1 || true
        fi
        fail "legacy managed directory append-only-bit clear failed: label=$label target=$target"
      }
    cleared_append_only=1
  fi
  if [[ "$cleared_immutable" == "1" || "$cleared_append_only" == "1" ]]; then
    if rmdir -- "$target"; then
      return 0
    fi
    if [[ "$cleared_append_only" == "1" ]]; then
      chattr +a -- "$target" \
        || fail "legacy managed directory append-only-bit restore failed after removal refusal: label=$label target=$target"
    fi
    if [[ "$cleared_immutable" == "1" ]]; then
      chattr +i -- "$target" \
        || fail "legacy managed directory immutable-bit restore failed after removal refusal: label=$label target=$target"
    fi
    fail "legacy managed directory removal failed after protected-attribute clear: label=$label target=$target"
  fi
  fail "legacy managed directory is not empty or not removable after bounded managed-file cleanup: label=$label target=$target"
}

restore_control_plane_files() {
  [[ "$ROLLBACK_ARMED" == "1" && -f "$ROLLBACK_MANIFEST" ]] || return 0
  while IFS=$'\t' read -r target key; do
    [[ -n "$target" && -n "$key" ]] || continue
    if [[ "$key" == "__MISSING__" ]]; then
      rm -f "$target"
      continue
    fi
    mkdir -p "$(dirname "$target")"
    rm -f "$target"
    cp -a "$ROLLBACK_DIR/$key" "$target"
  done < "$ROLLBACK_MANIFEST"
}

recover_previous_control_plane() {
  set +e
  restore_control_plane_files
  if [[ -f "$ENV_FILE" ]] && valid_mcp_image_digest "$PREVIOUS_MCP_IMAGE_DIGEST"; then
    ensure_managed_env "$MANAGED_ENV"
    set_value "$MANAGED_ENV" SOVEREIGN_MCP_IMAGE "$PREVIOUS_MCP_IMAGE_DIGEST"
    export SOVEREIGN_MCP_IMAGE="$PREVIOUS_MCP_IMAGE_DIGEST"
  fi
  systemctl daemon-reload >/dev/null 2>&1
  systemctl restart sovereign-chatgpt-command-worker.service >/dev/null 2>&1
  systemctl restart sovereign-chatgpt-broker.service >/dev/null 2>&1
  wait_for_broker_ready >/dev/null 2>&1 || true
  if [[ -f "$INSTALL_ROOT/docker-compose.yml" && -f "$ENV_FILE" ]]; then
    local rollback_gid
    rollback_gid="$(getent group sovereign-mcp | cut -d: -f3)"
    if [[ "$rollback_gid" =~ ^[0-9]+$ ]]; then
      BROKER_GID="$rollback_gid" docker compose \
        --project-directory "$INSTALL_ROOT" \
        --file "$INSTALL_ROOT/docker-compose.yml" \
        up -d --no-build --force-recreate sovereign-chatgpt-mcp >/dev/null 2>&1
    fi
  fi
  if [[ "$TUNNEL_MODE" != "disabled" ]]; then
    systemctl restart sovereign-openai-tunnel.service >/dev/null 2>&1
  fi
  set -e
}

on_installer_exit() {
  local exit_code="$?"
  local failed_stage="$INSTALL_STAGE"
  local failed_reason="$INSTALL_FAILURE_REASON"
  trap - EXIT
  if [[ "$exit_code" -eq 0 && "$INSTALL_COMPLETED" == "1" ]]; then
    [[ -z "$ROLLBACK_DIR" ]] || rm -rf "$ROLLBACK_DIR"
    exit 0
  fi
  [[ "$exit_code" -ne 0 ]] || exit_code=1
  recover_previous_control_plane
  printf 'install blocked: stage=%s exit=%s reason=%s rollback_attempted=%s\n' \
    "$failed_stage" "$exit_code" "${failed_reason:-unexpected command failure}" "$ROLLBACK_ARMED" >&2
  [[ -z "$ROLLBACK_DIR" ]] || rm -rf "$ROLLBACK_DIR"
  exit "${exit_code:-1}"
}
trap on_installer_exit EXIT

port_listener_evidence() {
  ss -H -ltnp 2>/dev/null | awk -v suffix=":$MCP_HOST_PORT" '$4 ~ suffix "$" {print}'
}

broker_rpc_ready() {
  python3 - <<'PY'
import json
import socket

payload = json.dumps(
    {"request_id": "broker-readiness-canary", "action": "broker_health", "arguments": {}},
    separators=(",", ":"),
).encode("utf-8") + b"\n"
with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
    client.settimeout(2)
    client.connect("/run/sovereign-chatgpt-broker/operator.sock")
    client.sendall(payload)
    response = json.loads(client.recv(65536).split(b"\n", 1)[0].decode("utf-8"))
result = response.get("result") or {}
if result.get("status") != "BROKER_READY":
    raise SystemExit(1)
PY
}

wait_for_broker_ready() {
  for attempt in $(seq 1 "$BROKER_READY_ATTEMPTS"); do
    if [[ -S /run/sovereign-chatgpt-broker/operator.sock ]] && broker_rpc_ready >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

INSTALL_STAGE="preflight"
[[ "${EUID:-$(id -u)}" -eq 0 ]] || fail "run as root on the VPS"
[[ "$EXPECTED_REVISION" =~ ^[0-9a-f]{40}$ ]] || fail "SOVEREIGN_MCP_EXPECTED_REVISION must be a full commit SHA"
[[ -z "$EXPECTED_MCP_DIGEST" || "$EXPECTED_MCP_DIGEST" =~ ^sha256:[0-9a-f]{64}$ ]] \
  || fail "SOVEREIGN_MCP_EXPECTED_DIGEST must be an immutable SHA-256 digest when set"
[[ "$REQUIRE_TUNNEL" =~ ^[01]$ ]] || fail "SOVEREIGN_MCP_REQUIRE_TUNNEL must be 0 or 1"
[[ "$TUNNEL_MODE" =~ ^(auto|required|disabled)$ ]] || fail "SOVEREIGN_MCP_TUNNEL_MODE must be auto, required or disabled"
[[ "$ALLOW_FIRST_INSTALL_WITHOUT_PREDECESSOR" =~ ^[01]$ ]] \
  || fail "SOVEREIGN_MCP_ALLOW_FIRST_INSTALL_WITHOUT_PREDECESSOR must be 0 or 1"
[[ "$MCP_IMAGE_PULL_ATTEMPTS" =~ ^[0-9]+$ ]] && (( MCP_IMAGE_PULL_ATTEMPTS >= 1 && MCP_IMAGE_PULL_ATTEMPTS <= 120 )) \
  || fail "SOVEREIGN_MCP_IMAGE_PULL_ATTEMPTS must be between 1 and 120"
[[ "$MCP_IMAGE_PULL_DELAY_SECONDS" =~ ^[0-9]+$ ]] && (( MCP_IMAGE_PULL_DELAY_SECONDS >= 1 && MCP_IMAGE_PULL_DELAY_SECONDS <= 60 )) \
  || fail "SOVEREIGN_MCP_IMAGE_PULL_DELAY_SECONDS must be between 1 and 60"
[[ "$BROKER_READY_ATTEMPTS" =~ ^[0-9]+$ ]] && (( BROKER_READY_ATTEMPTS >= 30 && BROKER_READY_ATTEMPTS <= 180 )) \
  || fail "SOVEREIGN_MCP_BROKER_READY_ATTEMPTS must be between 30 and 180"
[[ "$MCP_IMAGE_REPOSITORY" =~ ^ghcr\.io/[a-z0-9_.-]+/[a-z0-9_.-]+$ ]] || fail "SOVEREIGN_MCP_IMAGE_REPOSITORY is invalid"
for command in docker systemctl python3 git ss openssl sha256sum stat lsattr chattr timeout; do
  command -v "$command" >/dev/null 2>&1 || fail "$command is not installed"
done
docker compose version >/dev/null 2>&1 || fail "docker compose plugin is not installed"
[[ -S /var/run/docker.sock ]] || fail "docker socket is missing"
[[ -f "$PGBACKWEB_TEMPLATE_SOURCE/docker-compose.yml" ]] || fail "pgbackweb compose template is missing"
[[ -f "$PATCHMON_TEMPLATE_SOURCE/docker-compose.yml" ]] || fail "patchmon compose template is missing"
[[ -f "$CODE_SERVER_TEMPLATE_SOURCE/docker-compose.yml" ]] || fail "code-server compose template is missing"
[[ -f "$MILVUS_TEMPLATE_SOURCE/docker-compose.yml" ]] || fail "milvus compose template is missing"
[[ -f "$FREELLMAPI_TEMPLATE_SOURCE/docker-compose.yml" ]] || fail "FreeLLM API compose template is missing"
[[ -f "$FREELLMAPI_TEMPLATE_SOURCE/sovereign-freellm-bootstrap.mjs" ]] || fail "FreeLLM API bootstrap template is missing"
[[ -f "$FREELLMPOOL_TEMPLATE_SOURCE/docker-compose.yml" ]] || fail "FreeLLMPool compose template is missing"
[[ -f "$FREELLMPOOL_TEMPLATE_SOURCE/freellmpool-entrypoint.py" ]] || fail "FreeLLMPool entrypoint template is missing"
[[ -f "$SOURCE_DIR/skills/sovereign-operational-governance/SKILL.md" ]] || fail "operational governance skill manifest is missing"
[[ -f "$SOURCE_DIR/skills/sovereign-operational-assurance/SKILL.md" ]] || fail "operational assurance skill manifest is missing"
[[ -f "$SOURCE_DIR/skills/sovereign-mcp-optimal-operation/SKILL.md" ]] || fail "optimal operation skill manifest is missing"
[[ -f "$SOURCE_DIR/config/sovereign-mcp-operating-profile.json" ]] || fail "versioned MCP operating profile is missing"
[[ -f "$SOURCE_DIR/config/sovereign-continuity-policy.json" ]] || fail "versioned continuity policy is missing"
[[ -f "$SOURCE_DIR/config/sovereign-governance-mode.json" ]] || fail "versioned governance mode is missing"
[[ -f "$SOURCE_DIR/continuity.py" ]] || fail "continuity runtime is missing"
[[ -f "$SOURCE_DIR/continuity-data/CONTEXT.md" ]] || fail "runtime continuity context is missing"
[[ -f "$SOURCE_DIR/continuity-data/LEDGER.jsonl" ]] || fail "runtime continuity ledger is missing"
[[ -f "$SOURCE_DIR/deploy/ci-runtime-readback.pub" ]] || fail "CI runtime readback public key is missing"
bash -n "$SOURCE_DIR/deploy/self-update-chatgpt-mcp.sh" \
  || fail "source self-update wrapper has invalid bash syntax"
python3 -m py_compile "$SOURCE_DIR/deploy/reconcile-main-release.py" \
  || fail "source coordinated release reconciler has invalid Python syntax"
python3 -m py_compile "$SOURCE_DIR/deploy/run-coordinated-release-readback.py" \
  || fail "source coordinated release readback entrypoint has invalid Python syntax"
[[ -f "$SOURCE_DIR/deploy/sovereign-release-reconciler.service" ]] \
  || fail "coordinated release reconciler service is missing"
[[ -f "$SOURCE_DIR/deploy/sovereign-release-reconciler.timer" ]] \
  || fail "coordinated release reconciler timer is missing"

getent group sovereign-mcp >/dev/null 2>&1 || groupadd --system sovereign-mcp
install -d -m 0750 "$INSTALL_ROOT" "$BIN_DIR" "$BROKER_DIR" "$COMPOSE_TEMPLATE_ROOT" "$PGBACKWEB_TEMPLATE_DIR" "$PATCHMON_TEMPLATE_DIR" "$CODE_SERVER_TEMPLATE_DIR" "$MILVUS_TEMPLATE_DIR" "$FREELLMAPI_TEMPLATE_DIR" "$FREELLMPOOL_TEMPLATE_DIR" "$INSTALL_ROOT/continuity-data" "$INSTALL_ROOT/tool-routing-state"
for MANAGED_COMPOSE_ROOT in /opt/sovereign-backend /opt/gpt-tools /opt/code-server-46bq /opt/pgbackweb-wq5r /opt/patchmon-sovereign /opt/milvus-sovereign /opt/sovereign-freellmapi /opt/sovereign-freellmpool; do
  if [[ -e "$MANAGED_COMPOSE_ROOT" || -L "$MANAGED_COMPOSE_ROOT" ]]; then
    [[ -d "$MANAGED_COMPOSE_ROOT" && ! -L "$MANAGED_COMPOSE_ROOT" ]] \
      || fail "managed compose root is not a regular directory: $MANAGED_COMPOSE_ROOT"
  else
    install -d -m 0750 "$MANAGED_COMPOSE_ROOT"
  fi
done
unset MANAGED_COMPOSE_ROOT
install -d -m 0755 "$ANDROID_SDK_DIR"
install -d -m 0770 -o root -g sovereign-mcp "$COMMAND_QUEUE_DIR" "$COMMAND_QUEUE_DIR/inbox" "$COMMAND_QUEUE_DIR/processing" "$COMMAND_QUEUE_DIR/outbox"
install -d -m 0700 -o root -g root "$RUNTIME_EVIDENCE_DIR"
install -d -m 0700 -o root -g root "$MAINTENANCE_DIR" "$MAINTENANCE_DIR/backups" "$MAINTENANCE_DIR/receipts"
[[ -d "$RUNTIME_EVIDENCE_DIR" && ! -L "$RUNTIME_EVIDENCE_DIR" ]] \
  || fail "runtime evidence root is not a regular directory"
[[ -w "$RUNTIME_EVIDENCE_DIR" && -x "$RUNTIME_EVIDENCE_DIR" ]] \
  || fail "runtime evidence root is not writable and searchable"
install -d -m 0770 -o "$MCP_UID" -g "$MCP_GID" "$WORKSPACE_DIR"
install -d -m 0750 -o "$MCP_UID" -g "$MCP_GID" "$INSTALL_ROOT/tool-routing-state"
chown -R "$MCP_UID:$MCP_GID" "$WORKSPACE_DIR" "$INSTALL_ROOT/tool-routing-state"
chmod 0770 "$WORKSPACE_DIR"
if [[ -e "$NEURO_RUNTIME_STATE_HOST_DIR" || -L "$NEURO_RUNTIME_STATE_HOST_DIR" ]]; then
  [[ -d "$NEURO_RUNTIME_STATE_HOST_DIR" && ! -L "$NEURO_RUNTIME_STATE_HOST_DIR" ]] \
    || fail "neuro runtime state root is not a regular directory"
else
  install -d -m 0700 -o "$MCP_UID" -g "$MCP_GID" "$NEURO_RUNTIME_STATE_HOST_DIR"
fi
chown "$MCP_UID:$MCP_GID" "$NEURO_RUNTIME_STATE_HOST_DIR"
chmod 0700 "$NEURO_RUNTIME_STATE_HOST_DIR"
[[ -w "$NEURO_RUNTIME_STATE_HOST_DIR" && -x "$NEURO_RUNTIME_STATE_HOST_DIR" ]] \
  || fail "neuro runtime state root is not writable and searchable"
if [[ -e "$OWNER_INPUT_HOST_ROOT" || -L "$OWNER_INPUT_HOST_ROOT" ]]; then
  [[ -d "$OWNER_INPUT_HOST_ROOT" && ! -L "$OWNER_INPUT_HOST_ROOT" ]] \
    || fail "owner input host root is not a regular directory"
else
  mkdir -p "$OWNER_INPUT_HOST_ROOT"
fi
chmod 0700 "$OWNER_INPUT_HOST_ROOT"
[[ -w "$OWNER_INPUT_HOST_ROOT" && -x "$OWNER_INPUT_HOST_ROOT" ]] \
  || fail "owner input host root is not writable and searchable"
if [[ -e "$BACKEND_WORKSPACE_HOST_ROOT" || -L "$BACKEND_WORKSPACE_HOST_ROOT" ]]; then
  [[ -d "$BACKEND_WORKSPACE_HOST_ROOT" && ! -L "$BACKEND_WORKSPACE_HOST_ROOT" ]] \
    || fail "backend workspace host root is not a regular directory"
else
  install -d -m 0770 -o "$BACKEND_WORKSPACE_UID" -g "$BACKEND_WORKSPACE_GID" "$BACKEND_WORKSPACE_HOST_ROOT"
fi
chown "$BACKEND_WORKSPACE_UID:$BACKEND_WORKSPACE_GID" "$BACKEND_WORKSPACE_HOST_ROOT"
chmod 0770 "$BACKEND_WORKSPACE_HOST_ROOT"
[[ -w "$BACKEND_WORKSPACE_HOST_ROOT" && -x "$BACKEND_WORKSPACE_HOST_ROOT" ]] \
  || fail "backend workspace host root is not writable and searchable"

INSTALL_STAGE="backup_existing_control_plane"
ROLLBACK_DIR="$(mktemp -d "$INSTALL_ROOT/.control-plane-backup.XXXXXX")"
chmod 0700 "$ROLLBACK_DIR"
ROLLBACK_MANIFEST="$ROLLBACK_DIR/manifest.tsv"
: > "$ROLLBACK_MANIFEST"
: > "$ROLLBACK_MANIFEST.paths"
backup_control_plane_file "$MANAGED_ENV"
backup_control_plane_file "$BACKEND_MANAGED_ENV"
backup_control_plane_file "$BROKER_ENV"
backup_control_plane_file "$BROKER_SERVICE"
backup_control_plane_file "$COMMAND_WORKER_SERVICE"
backup_control_plane_file "$SELF_UPDATE_SERVICE"
backup_control_plane_file "$RELEASE_RECONCILER_SERVICE"
backup_control_plane_file "$RELEASE_RECONCILER_TIMER"
backup_control_plane_file "$TUNNEL_SERVICE"
if [[ ! -e "$PATCHMON_AGENT_BIN_LINK" && ! -L "$PATCHMON_AGENT_BIN_LINK" ]]; then
  backup_control_plane_file "$PATCHMON_AGENT_BIN_LINK"
fi
if [[ ! -e "$PATCHMON_AGENT_CONFIG_LINK" && ! -L "$PATCHMON_AGENT_CONFIG_LINK" ]]; then
  backup_control_plane_file "$PATCHMON_AGENT_CONFIG_LINK"
fi
if [[ ! -e "$PATCHMON_AGENT_UNIT_LINK" && ! -L "$PATCHMON_AGENT_UNIT_LINK" ]]; then
  backup_control_plane_file "$PATCHMON_AGENT_UNIT_LINK"
fi
PREVIOUS_MCP_IMAGE_DIGEST="$(read_mcp_value SOVEREIGN_MCP_IMAGE 2>/dev/null || true)"
if ! valid_mcp_image_digest "$PREVIOUS_MCP_IMAGE_DIGEST"; then
  PREVIOUS_MCP_IMAGE_DIGEST="$(resolve_running_mcp_image_digest || true)"
fi
ROLLBACK_ARMED=1

INSTALL_STAGE="copy_control_plane_files"
for file in Dockerfile requirements.txt policy.py github_installation_auth.py runtime.py database.py database_evidence_tools.py command_contract.py command_queue.py broker_client.py owner_input_client.py a2a_runtime_client.py document_pipeline.py github_knowledge_canary.py issue_closure_canary.py programming_language_catalog_runtime.py github_issue_contracts.py owner_input_widget.py self_heal.py android_hardening.py android_validation_router.py mcp_protocol_health.py sovereign_cognitive_widget.py sovereign_rescue_widget.py server.py tool_extensions.py llm_boundary_contract.py llm_boundary_ledger.py ci_repair_tools.py repository_skill_tools.py repository_intelligence_tools.py proven_learning_tools.py skill_supply_chain_tools.py deterministic_contract.py deterministic_architecture_tools.py enterprise_backend_tools.py freemium_product_architect_tools.py openai_project_access_tools.py continuity.py validate_continuity.py operating_profile.py predictive_tool_router.py tool_success_ranking.py operational_governance_tools.py operational_assurance_tools.py output_contracts.py toolchain_composition.py neuro_architecture_contract.py neuromorphic_runtime.py foundation_runtime.py neuro_teaching_tools.py patchmon_operator.py patchmon_fleet.py launcher.py docker-compose.yml; do
  install_managed_control_plane_file 0644 "$SOURCE_DIR/$file" "$INSTALL_ROOT/$file" "runtime/$file"
done
install_managed_control_plane_file 0644 "$SOURCE_DIR/continuity-data/CONTEXT.md" "$INSTALL_ROOT/continuity-data/CONTEXT.md" "continuity-data/CONTEXT.md"
install_managed_control_plane_file 0644 "$SOURCE_DIR/continuity-data/LEDGER.jsonl" "$INSTALL_ROOT/continuity-data/LEDGER.jsonl" "continuity-data/LEDGER.jsonl"

for file in broker.py browserless_reader.py document_pipeline.py github_knowledge_canary.py issue_closure_canary.py programming_language_catalog_runtime.py command_contract.py command_queue.py command_worker.py operations.py admin_mode.py github_admin.py ci_repair_tools.py llm_boundary_ledger.py llm_boundary_contract.py self_update.py policy.py self_heal.py managed_compose.py patchmon_operator.py patchmon_fleet.py fleet_maintenance.py; do
  install_managed_control_plane_file 0640 "$SOURCE_DIR/$file" "$BROKER_DIR/$file" "broker/$file"
done
install_managed_control_plane_file 0640 "$SOURCE_DIR/config/sovereign-governance-mode.json" "$BROKER_GOVERNANCE_MODE" "broker/sovereign-governance-mode.json"
[[ "$(sha256sum "$BROKER_GOVERNANCE_MODE" | awk '{print $1}')" == "$(sha256sum "$SOURCE_DIR/config/sovereign-governance-mode.json" | awk '{print $1}')" ]] \
  || fail "installed broker governance mode does not match the exact source revision"
remove_managed_legacy_file "$BROKER_DIR/litellm_stack.py" "broker/litellm_stack.py"
remove_managed_legacy_file "$COMPOSE_TEMPLATE_ROOT/sovereign-litellm/docker-compose.yml" "templates/sovereign-litellm/docker-compose.yml"
remove_managed_legacy_file "$COMPOSE_TEMPLATE_ROOT/sovereign-litellm/config.yaml" "templates/sovereign-litellm/config.yaml"
remove_managed_legacy_file "$COMPOSE_TEMPLATE_ROOT/sovereign-litellm/sovereign-entrypoint.py" "templates/sovereign-litellm/sovereign-entrypoint.py"
backup_managed_control_plane_file "$PGBACKWEB_TEMPLATE_DIR/docker-compose.yml" "templates/pgbackweb-wq5r/docker-compose.yml"
backup_managed_control_plane_file "$PATCHMON_TEMPLATE_DIR/docker-compose.yml" "templates/patchmon-sovereign/docker-compose.yml"
backup_managed_control_plane_file "$CODE_SERVER_TEMPLATE_DIR/docker-compose.yml" "templates/code-server-46bq/docker-compose.yml"
backup_managed_control_plane_file "$MILVUS_TEMPLATE_DIR/docker-compose.yml" "templates/milvus-sovereign/docker-compose.yml"
backup_managed_control_plane_file "$FREELLMAPI_TEMPLATE_DIR/docker-compose.yml" "templates/sovereign-freellmapi/docker-compose.yml"
backup_managed_control_plane_file "$FREELLMAPI_TEMPLATE_DIR/sovereign-freellm-bootstrap.mjs" "templates/sovereign-freellmapi/sovereign-freellm-bootstrap.mjs"
backup_managed_control_plane_file "$FREELLMPOOL_TEMPLATE_DIR/docker-compose.yml" "templates/sovereign-freellmpool/docker-compose.yml"
backup_managed_control_plane_file "$FREELLMPOOL_TEMPLATE_DIR/freellmpool-entrypoint.py" "templates/sovereign-freellmpool/freellmpool-entrypoint.py"
for file in deploy-sovereign-backend rollback-sovereign-backend bootstrap-database install-secure-tunnel validate-tunnel-doctor-report reconcile-main-release run-coordinated-release-readback; do
  backup_managed_control_plane_file "$BIN_DIR/$file" "bin/$file"
done

# The updater is the recovery and diagnostic entrypoint. After syntax validation,
# keep the newest bounded-status wrapper even when the wider control-plane install
# rolls back, otherwise the next attempt reintroduces generic failure evidence.
SELF_UPDATE_NEXT="$(mktemp "$BIN_DIR/.self-update-chatgpt-mcp.XXXXXX")"
install -m 0750 "$SOURCE_DIR/deploy/self-update-chatgpt-mcp.sh" "$SELF_UPDATE_NEXT"
chown root:sovereign-mcp "$SELF_UPDATE_NEXT"
mv -f "$SELF_UPDATE_NEXT" "$SELF_UPDATE_BIN"
unset SELF_UPDATE_NEXT


remove_managed_legacy_directory "$COMPOSE_TEMPLATE_ROOT/sovereign-litellm" "templates/sovereign-litellm"
install_managed_control_plane_file 0640 "$PGBACKWEB_TEMPLATE_SOURCE/docker-compose.yml" "$PGBACKWEB_TEMPLATE_DIR/docker-compose.yml" "templates/pgbackweb-wq5r/docker-compose.yml"
install_managed_control_plane_file 0640 "$PATCHMON_TEMPLATE_SOURCE/docker-compose.yml" "$PATCHMON_TEMPLATE_DIR/docker-compose.yml" "templates/patchmon-sovereign/docker-compose.yml"
install_managed_control_plane_file 0640 "$CODE_SERVER_TEMPLATE_SOURCE/docker-compose.yml" "$CODE_SERVER_TEMPLATE_DIR/docker-compose.yml" "templates/code-server-46bq/docker-compose.yml"
install_managed_control_plane_file 0640 "$MILVUS_TEMPLATE_SOURCE/docker-compose.yml" "$MILVUS_TEMPLATE_DIR/docker-compose.yml" "templates/milvus-sovereign/docker-compose.yml"
install_managed_control_plane_file 0640 "$FREELLMAPI_TEMPLATE_SOURCE/docker-compose.yml" "$FREELLMAPI_TEMPLATE_DIR/docker-compose.yml" "templates/sovereign-freellmapi/docker-compose.yml"
install_managed_control_plane_file 0640 "$FREELLMAPI_TEMPLATE_SOURCE/sovereign-freellm-bootstrap.mjs" "$FREELLMAPI_TEMPLATE_DIR/sovereign-freellm-bootstrap.mjs" "templates/sovereign-freellmapi/sovereign-freellm-bootstrap.mjs"
install_managed_control_plane_file 0640 "$FREELLMPOOL_TEMPLATE_SOURCE/docker-compose.yml" "$FREELLMPOOL_TEMPLATE_DIR/docker-compose.yml" "templates/sovereign-freellmpool/docker-compose.yml"
install_managed_control_plane_file 0640 "$FREELLMPOOL_TEMPLATE_SOURCE/freellmpool-entrypoint.py" "$FREELLMPOOL_TEMPLATE_DIR/freellmpool-entrypoint.py" "templates/sovereign-freellmpool/freellmpool-entrypoint.py"
install_managed_control_plane_file 0750 "$SOURCE_DIR/deploy/deploy-sovereign-backend" "$BIN_DIR/deploy-sovereign-backend" "bin/deploy-sovereign-backend"
install_managed_control_plane_file 0750 "$SOURCE_DIR/deploy/rollback-sovereign-backend" "$BIN_DIR/rollback-sovereign-backend" "bin/rollback-sovereign-backend"
install_managed_control_plane_file 0750 "$SOURCE_DIR/deploy/bootstrap-database.sh" "$BIN_DIR/bootstrap-database" "bin/bootstrap-database"
install_managed_control_plane_file 0750 "$SOURCE_DIR/deploy/install-secure-tunnel.sh" "$BIN_DIR/install-secure-tunnel" "bin/install-secure-tunnel"
install_managed_control_plane_file 0750 "$SOURCE_DIR/deploy/validate-tunnel-doctor-report.py" "$BIN_DIR/validate-tunnel-doctor-report" "bin/validate-tunnel-doctor-report"
install_managed_control_plane_file 0750 "$SOURCE_DIR/deploy/reconcile-main-release.py" "$RELEASE_RECONCILER_BIN" "bin/reconcile-main-release"
install_managed_control_plane_file 0750 "$SOURCE_DIR/deploy/run-coordinated-release-readback.py" "$RELEASE_READBACK_BIN" "bin/run-coordinated-release-readback"
install_ci_runtime_readback_authorization
install_managed_control_plane_file 0644 "$SOURCE_DIR/deploy/sovereign-chatgpt-broker.service" "$BROKER_SERVICE" "systemd/sovereign-chatgpt-broker.service"
install_managed_control_plane_file 0644 "$SOURCE_DIR/deploy/sovereign-chatgpt-command-worker.service" "$COMMAND_WORKER_SERVICE" "systemd/sovereign-chatgpt-command-worker.service"
install_managed_control_plane_file 0644 "$SOURCE_DIR/deploy/sovereign-chatgpt-mcp-self-update.service" "$SELF_UPDATE_SERVICE" "systemd/sovereign-chatgpt-mcp-self-update.service"
install_managed_control_plane_file 0644 "$SOURCE_DIR/deploy/sovereign-release-reconciler.service" "$RELEASE_RECONCILER_SERVICE" "systemd/sovereign-release-reconciler.service"
install_managed_control_plane_file 0644 "$SOURCE_DIR/deploy/sovereign-release-reconciler.timer" "$RELEASE_RECONCILER_TIMER" "systemd/sovereign-release-reconciler.timer"
install_managed_control_plane_file 0644 "$SOURCE_DIR/deploy/sovereign-openai-tunnel.service" "$TUNNEL_SERVICE" "systemd/sovereign-openai-tunnel.service"
INSTALL_STAGE="verify_dormant_tunnel_unit_contract"
grep -q '^ExecStartPre=/usr/bin/python3 /opt/sovereign-chatgpt-tools/mcp_protocol_health.py ' "$TUNNEL_SERVICE" \
  || fail "installed tunnel unit does not use the shared MCP protocol checker"
grep -q '^Restart=on-failure$' "$TUNNEL_SERVICE" || fail "installed tunnel unit has an unsafe restart policy"
grep -q '^StartLimitBurst=3$' "$TUNNEL_SERVICE" || fail "installed tunnel unit has no bounded restart limit"
if grep -Eq 'c[u]rl[[:space:]]' "$TUNNEL_SERVICE"; then
  fail "installed tunnel unit still contains a curl-based MCP probe"
fi
set_managed_control_plane_directory_ownership "$BROKER_DIR" "broker"
set_managed_control_plane_directory_ownership "$BIN_DIR" "bin"
set_managed_control_plane_directory_ownership "$COMPOSE_TEMPLATE_ROOT" "templates"
set_managed_control_plane_directory_ownership "$PGBACKWEB_TEMPLATE_DIR" "templates/pgbackweb-wq5r"
set_managed_control_plane_directory_ownership "$PATCHMON_TEMPLATE_DIR" "templates/patchmon-sovereign"
set_managed_control_plane_directory_ownership "$CODE_SERVER_TEMPLATE_DIR" "templates/code-server-46bq"
set_managed_control_plane_directory_ownership "$MILVUS_TEMPLATE_DIR" "templates/milvus-sovereign"
set_managed_control_plane_directory_ownership "$FREELLMAPI_TEMPLATE_DIR" "templates/sovereign-freellmapi"
set_managed_control_plane_directory_ownership "$FREELLMPOOL_TEMPLATE_DIR" "templates/sovereign-freellmpool"

INSTALL_STAGE="prepare_private_environment_files"
if [[ ! -f "$ENV_FILE" ]]; then
  install -m 0600 "$SOURCE_DIR/.env.example" "$INSTALL_ROOT/.env.example"
  install -m 0600 "$SOURCE_DIR/.ghcr.env.example" "$INSTALL_ROOT/.ghcr.env.example"
  install -m 0600 "$SOURCE_DIR/.tunnel.env.example" "$INSTALL_ROOT/tunnel.env.example"
  fail "create $ENV_FILE from $INSTALL_ROOT/.env.example and fill it only on the VPS"
fi
ensure_private_file_mode "$ENV_FILE" "base-env"
ensure_managed_env "$MANAGED_ENV" "runtime-env"
INSTALL_STAGE="remove_persistent_github_api_credentials"
remove_value "$ENV_FILE" GITHUB_TOKEN
remove_value "$MANAGED_ENV" GITHUB_TOKEN
if [[ -e "$RETIRED_OWNER_GITHUB_PAT_FILE" || -L "$RETIRED_OWNER_GITHUB_PAT_FILE" ]]; then
  [[ -f "$RETIRED_OWNER_GITHUB_PAT_FILE" && ! -L "$RETIRED_OWNER_GITHUB_PAT_FILE" ]] \
    || fail "retired owner GitHub PAT path is not a regular file"
  rm -f "$RETIRED_OWNER_GITHUB_PAT_FILE"
fi

INSTALL_STAGE="configure_private_owner_mode"
PRIVATE_OWNER_MODE="$(read_mcp_value SOVEREIGN_MCP_PRIVATE_OWNER_MODE)"
if [[ -z "$PRIVATE_OWNER_MODE" ]]; then
  PRIVATE_OWNER_MODE="1"
fi
[[ "$PRIVATE_OWNER_MODE" =~ ^[01]$ ]] || fail "SOVEREIGN_MCP_PRIVATE_OWNER_MODE must be 0 or 1"
set_value "$MANAGED_ENV" SOVEREIGN_MCP_PRIVATE_OWNER_MODE "$PRIVATE_OWNER_MODE"
PRIVATE_VPS_DEV_MODE="$(read_mcp_value SOVEREIGN_MCP_PRIVATE_VPS_DEV_MODE)"
if [[ -z "$PRIVATE_VPS_DEV_MODE" ]]; then
  PRIVATE_VPS_DEV_MODE="$PRIVATE_OWNER_MODE"
fi
[[ "$PRIVATE_VPS_DEV_MODE" =~ ^[01]$ ]] || fail "SOVEREIGN_MCP_PRIVATE_VPS_DEV_MODE must be 0 or 1"
if [[ "$PRIVATE_OWNER_MODE" != "1" && "$PRIVATE_VPS_DEV_MODE" == "1" ]]; then
  fail "SOVEREIGN_MCP_PRIVATE_VPS_DEV_MODE requires private owner mode"
fi
set_value "$MANAGED_ENV" SOVEREIGN_MCP_PRIVATE_VPS_DEV_MODE "$PRIVATE_VPS_DEV_MODE"
set_value "$MANAGED_ENV" SOVEREIGN_MCP_DEV_ROOTS "/opt/sovereign-chatgpt-tools/workspaces,/opt/sovereign-backend,/opt/sovereign-operator-source,/opt/sovereign-agent-workspaces,/opt/gpt-tools"
if [[ "$PRIVATE_OWNER_MODE" == "1" ]]; then
  for OWNER_CAPABILITY in \
    SOVEREIGN_MCP_ENABLE_DB_WRITES \
    SOVEREIGN_MCP_ENABLE_DEPLOY \
    SOVEREIGN_MCP_ALLOW_DATA_BACKFILLS \
    SOVEREIGN_MCP_ENABLE_ADMIN_SQL \
    SOVEREIGN_MCP_ENABLE_MAIN_PUSH \
    SOVEREIGN_MCP_ENABLE_PR_MERGE \
    SOVEREIGN_MCP_ENABLE_WORKFLOW_CONTROL \
    SOVEREIGN_MCP_ENABLE_COMPOSE_WRITE; do
    set_value "$MANAGED_ENV" "$OWNER_CAPABILITY" "1"
  done
fi
INSTALL_STAGE="disable_token_dependent_github_capabilities_without_ephemeral_ci_scope"
for TOKEN_DEPENDENT_CAPABILITY in \
  SOVEREIGN_MCP_ENABLE_MAIN_PUSH \
  SOVEREIGN_MCP_ENABLE_PR_MERGE \
  SOVEREIGN_MCP_ENABLE_WORKFLOW_CONTROL \
  SOVEREIGN_MCP_ENABLE_SELF_UPDATE; do
  set_value "$MANAGED_ENV" "$TOKEN_DEPENDENT_CAPABILITY" "0"
done
set_value "$MANAGED_ENV" SOVEREIGN_MCP_GITHUB_CAPABILITIES_AVAILABLE "0"
unset TOKEN_DEPENDENT_CAPABILITY
for GUARDED_CAPABILITY in \
  SOVEREIGN_MCP_ALLOW_DESTRUCTIVE_MIGRATIONS \
  SOVEREIGN_MCP_ALLOW_MERGE_WITHOUT_CHECKS \
  SOVEREIGN_MCP_ENABLE_PATCHMON_PATCH_WRITE; do
  if [[ -z "$(read_mcp_value "$GUARDED_CAPABILITY")" ]]; then
    set_value "$MANAGED_ENV" "$GUARDED_CAPABILITY" "0"
  fi
done
unset PRIVATE_OWNER_MODE PRIVATE_VPS_DEV_MODE OWNER_CAPABILITY GUARDED_CAPABILITY

INSTALL_STAGE="ensure_recovery_image_digest"
CURRENT_MCP_IMAGE_DIGEST="$(read_mcp_value SOVEREIGN_MCP_IMAGE)"
if ! valid_mcp_image_digest "$CURRENT_MCP_IMAGE_DIGEST"; then
  CURRENT_MCP_IMAGE_DIGEST="$PREVIOUS_MCP_IMAGE_DIGEST"
fi
valid_mcp_image_digest "$CURRENT_MCP_IMAGE_DIGEST" \
  || fail "SOVEREIGN_MCP_IMAGE is missing and the running MCP container has no immutable GHCR digest"
set_value "$MANAGED_ENV" SOVEREIGN_MCP_IMAGE "$CURRENT_MCP_IMAGE_DIGEST"
export SOVEREIGN_MCP_IMAGE="$CURRENT_MCP_IMAGE_DIGEST"
unset CURRENT_MCP_IMAGE_DIGEST

INSTALL_STAGE="configure_owner_bridge"
BACKEND_ENV_PATH="$(read_mcp_value SOVEREIGN_BACKEND_ENV_FILE)"
if [[ -z "$BACKEND_ENV_PATH" ]]; then
  for candidate in /run/secrets/sovereign-backend.env /opt/sovereign-backend/.env; do
    if [[ -f "$candidate" ]]; then
      BACKEND_ENV_PATH="$candidate"
      break
    fi
  done
fi
[[ -n "$BACKEND_ENV_PATH" && -f "$BACKEND_ENV_PATH" ]] || fail "backend env file is missing for the owner approval bridge"
ensure_private_file_mode "$BACKEND_ENV_PATH" "backend-base-env"
ensure_managed_env "$BACKEND_MANAGED_ENV" "backend-runtime-env"
OWNER_REQUEST_KEY="$(read_mcp_value SOVEREIGN_OWNER_REQUEST_KEY)"
if [[ -z "$OWNER_REQUEST_KEY" ]]; then
  OWNER_REQUEST_KEY="$(read_backend_value SOVEREIGN_OWNER_REQUEST_KEY)"
fi
if [[ -z "$OWNER_REQUEST_KEY" ]]; then
  OWNER_REQUEST_KEY="$(openssl rand -hex 32)"
fi
set_value "$MANAGED_ENV" SOVEREIGN_OWNER_REQUEST_KEY "$OWNER_REQUEST_KEY"
set_value "$MANAGED_ENV" SOVEREIGN_BACKEND_INTERNAL_URL "http://sovereign-backend:8787"
set_value "$MANAGED_ENV" SOVEREIGN_BACKEND_ENV_FILE "$BACKEND_ENV_PATH"
set_value "$MANAGED_ENV" SOVEREIGN_BACKEND_MANAGED_ENV_FILE "$BACKEND_MANAGED_ENV"
set_value "$BACKEND_MANAGED_ENV" SOVEREIGN_OWNER_REQUEST_KEY "$OWNER_REQUEST_KEY"
set_value "$BACKEND_MANAGED_ENV" SOVEREIGN_OWNER_INPUT_ROOT "/opt/sovereign-owner-managed"
remove_value "$BACKEND_MANAGED_ENV" LITELLM_BASE_URL
remove_value "$BACKEND_MANAGED_ENV" LITELLM_MASTER_KEY_FILE
set_value "$BACKEND_MANAGED_ENV" SOVEREIGN_FREELLMAPI_UNIFIED_KEY_FILE "/opt/sovereign-owner-managed/freellmapi_unified_key.txt"
set_value "$BACKEND_MANAGED_ENV" SOVEREIGN_FREELLMPOOL_PROXY_KEY_FILE "/opt/sovereign-owner-managed/freellmpool_proxy_key.txt"
prepare_mcp_github_app_secret
OWNER_REFERENCE_ID="$(read_backend_value SOVEREIGN_OWNER_REFERENCE_ID)"
OWNER_ADMIN_ID="$(read_backend_value SOVEREIGN_OWNER_ADMIN_ID)"
OWNER_ADMIN_EMAIL="$(read_backend_value SOVEREIGN_OWNER_ADMIN_EMAIL)"
if [[ -z "$OWNER_REFERENCE_ID" ]]; then
  OWNER_REFERENCE_ID="26487"
fi
if [[ -z "$OWNER_ADMIN_ID" && -z "$OWNER_ADMIN_EMAIL" ]]; then
  OWNER_ADMIN_EMAIL="rastamanweeste@gmail.com"
fi
[[ "$OWNER_REFERENCE_ID" =~ ^[0-9]{1,20}$ ]] || fail "SOVEREIGN_OWNER_REFERENCE_ID is invalid"
set_value "$BACKEND_MANAGED_ENV" SOVEREIGN_OWNER_REFERENCE_ID "$OWNER_REFERENCE_ID"
if [[ -n "$OWNER_ADMIN_ID" ]]; then
  [[ "$OWNER_ADMIN_ID" =~ ^[0-9a-fA-F-]{36}$ ]] || fail "SOVEREIGN_OWNER_ADMIN_ID is invalid"
  set_value "$BACKEND_MANAGED_ENV" SOVEREIGN_OWNER_ADMIN_ID "$OWNER_ADMIN_ID"
elif [[ "$OWNER_ADMIN_EMAIL" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]]; then
  set_value "$BACKEND_MANAGED_ENV" SOVEREIGN_OWNER_ADMIN_EMAIL "$OWNER_ADMIN_EMAIL"
else
  fail "configure a valid SOVEREIGN_OWNER_ADMIN_ID or SOVEREIGN_OWNER_ADMIN_EMAIL for the owner approval surface"
fi
unset OWNER_REQUEST_KEY OWNER_REFERENCE_ID OWNER_ADMIN_ID OWNER_ADMIN_EMAIL

for REQUIRED_WORKFLOW in android.yml e2e-testing.yml sovereign-backend-image.yml sovereign-chatgpt-mcp.yml sovereign-agent-backend.yml release-verification.yml; do
  CURRENT_ALLOWED_WORKFLOWS="$(read_mcp_value SOVEREIGN_MCP_ALLOWED_WORKFLOWS)"
  if [[ -z "$CURRENT_ALLOWED_WORKFLOWS" ]]; then
    set_value "$MANAGED_ENV" SOVEREIGN_MCP_ALLOWED_WORKFLOWS "$REQUIRED_WORKFLOW"
  elif [[ ",$CURRENT_ALLOWED_WORKFLOWS," != *",$REQUIRED_WORKFLOW,"* ]]; then
    set_value "$MANAGED_ENV" SOVEREIGN_MCP_ALLOWED_WORKFLOWS "$REQUIRED_WORKFLOW,$CURRENT_ALLOWED_WORKFLOWS"
  fi
done
unset REQUIRED_WORKFLOW CURRENT_ALLOWED_WORKFLOWS

for REQUIRED_CONTAINER in sovereign-backend sovereign-chatgpt-mcp gpt-browserless gpt-tika gpt-gotenberg gpt-dozzle code-server-46bq-code-server-1 pgbackweb-wq5r-pgbackweb-1 pgbackweb-wq5r-db-1 patchmon-sovereign-server-1 patchmon-sovereign-database-1 patchmon-sovereign-redis-1 patchmon-sovereign-guacd-1 sovereign-freellmapi sovereign-freellmpool; do
  CURRENT_ALLOWED_CONTAINERS="$(read_mcp_value SOVEREIGN_MCP_ALLOWED_CONTAINERS)"
  if [[ -z "$CURRENT_ALLOWED_CONTAINERS" ]]; then
    set_value "$MANAGED_ENV" SOVEREIGN_MCP_ALLOWED_CONTAINERS "$REQUIRED_CONTAINER"
  elif [[ ",$CURRENT_ALLOWED_CONTAINERS," != *",$REQUIRED_CONTAINER,"* ]]; then
    set_value "$MANAGED_ENV" SOVEREIGN_MCP_ALLOWED_CONTAINERS "$REQUIRED_CONTAINER,$CURRENT_ALLOWED_CONTAINERS"
  fi
done
remove_csv_values "$MANAGED_ENV" SOVEREIGN_MCP_ALLOWED_CONTAINERS "sovereign-litellm-litellm-1,sovereign-litellm-db-1"
unset REQUIRED_CONTAINER CURRENT_ALLOWED_CONTAINERS

if [[ "$(read_mcp_value SOVEREIGN_MCP_BOOTSTRAP_DATABASE)" == "1" ]]; then
  command -v openssl >/dev/null 2>&1 || fail "openssl is required for database bootstrap"
  BACKEND_ENV_PATH="$(read_mcp_value SOVEREIGN_BACKEND_ENV_FILE)"
  MCP_BASE_ENV_FILE="$ENV_FILE" \
    MCP_ENV_FILE="$MANAGED_ENV" \
    SOVEREIGN_BACKEND_ENV_FILE="${BACKEND_ENV_PATH:-/opt/sovereign-backend/.env}" \
    "$BIN_DIR/bootstrap-database"
  set_value "$MANAGED_ENV" SOVEREIGN_MCP_BOOTSTRAP_DATABASE "0"
fi

[[ -n "$(read_mcp_value POSTGRES_PASSWORD)" ]] || fail "POSTGRES_PASSWORD is missing"
[[ -n "$(read_mcp_value SOVEREIGN_MCP_PREVIEW_POSTGRES_PASSWORD)" ]] || fail "preview database password is missing"

DOCKER_CONFIG_VALUE=""
if [[ -f "$GHCR_ENV" ]]; then
  ensure_private_file_mode "$GHCR_ENV" "ghcr-env"
  INSTALL_STAGE="read_private_environment:ghcr-env"
  GHCR_USERNAME="$(read_value "$GHCR_ENV" GHCR_USERNAME)" \
    || fail "GHCR username metadata read failed"
  GHCR_TOKEN="$(read_value "$GHCR_ENV" GHCR_TOKEN)" \
    || fail "GHCR token metadata read failed"
  if [[ -n "$GHCR_USERNAME" || -n "$GHCR_TOKEN" ]]; then
    [[ -n "$GHCR_USERNAME" && -n "$GHCR_TOKEN" ]] || fail "GHCR_USERNAME and GHCR_TOKEN must both be configured"
    install -d -m 0700 "$DOCKER_AUTH_DIR"
    printf '%s' "$GHCR_TOKEN" | docker --config "$DOCKER_AUTH_DIR" login ghcr.io --username "$GHCR_USERNAME" --password-stdin >/dev/null
    chmod 0600 "$DOCKER_AUTH_DIR/config.json"
    DOCKER_CONFIG_VALUE="$DOCKER_AUTH_DIR"
  fi
fi

INSTALL_STAGE="pull_immutable_image"
MCP_TAGGED_IMAGE="$MCP_IMAGE_REPOSITORY:$EXPECTED_REVISION"
wait_for_exact_mcp_image
MCP_IMAGE_REVISION="$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$MCP_TAGGED_IMAGE")"
[[ "$MCP_IMAGE_REVISION" == "$EXPECTED_REVISION" ]] || fail "MCP image revision label does not match expected revision"
set_value "$MANAGED_ENV" SOVEREIGN_SOURCE_REVISION "$EXPECTED_REVISION"
NEURO_POLICY_SHA256="$(sha256sum "$SOURCE_DIR/config/sovereign-continuity-policy.json" | awk '{print $1}')"
[[ "$NEURO_POLICY_SHA256" =~ ^[0-9a-f]{64}$ ]] || fail "could not bind the embedded neuro policy SHA-256"
set_value "$MANAGED_ENV" SOVEREIGN_NEURO_POLICY_SHA256 "$NEURO_POLICY_SHA256"
MCP_IMAGE_CROSS_RUNTIME_PARITY="$(docker image inspect --format '{{index .Config.Labels "io.ouroboros.sovereign.cross-runtime-parity"}}' "$MCP_TAGGED_IMAGE")"
[[ "$MCP_IMAGE_CROSS_RUNTIME_PARITY" == "$EXPECTED_CROSS_RUNTIME_PARITY" ]] || fail "MCP image does not carry verified cross-runtime parity evidence"
set_value "$MANAGED_ENV" SOVEREIGN_CROSS_RUNTIME_PARITY_PROVEN "1"
MCP_IMAGE_DIGEST="$(docker image inspect --format '{{json .RepoDigests}}' "$MCP_TAGGED_IMAGE" \
  | python3 -c 'import json,sys; repo=sys.argv[1]+"@"; values=json.load(sys.stdin); print(next((item for item in values if isinstance(item,str) and item.startswith(repo)), ""))' "$MCP_IMAGE_REPOSITORY")"
[[ "$MCP_IMAGE_DIGEST" == "$MCP_IMAGE_REPOSITORY"@sha256:* ]] || fail "MCP image digest repository does not match"
[[ "${MCP_IMAGE_DIGEST#*@}" =~ ^sha256:[0-9a-f]{64}$ ]] || fail "MCP image has no immutable repository digest"
if [[ -n "$EXPECTED_MCP_DIGEST" ]]; then
  [[ "$MCP_IMAGE_DIGEST" == "$MCP_IMAGE_REPOSITORY@$EXPECTED_MCP_DIGEST" ]] \
    || fail "MCP image digest differs from CI-bound expected digest"
fi
set_value "$MANAGED_ENV" SOVEREIGN_MCP_IMAGE "$MCP_IMAGE_DIGEST"
export SOVEREIGN_MCP_IMAGE="$MCP_IMAGE_DIGEST"

INSTALL_STAGE="write_broker_environment"
prepare_managed_private_file_mutation "$BROKER_ENV" "broker-environment"
INSTALL_STAGE="mutate_managed_private_file:broker-environment"
if ! {
  for environment_file in "$ENV_FILE" "$MANAGED_ENV"; do
    grep -E '^(SOVEREIGN_MCP_REPOSITORY|SOVEREIGN_MCP_GIT_AUTHOR_NAME|SOVEREIGN_MCP_GIT_AUTHOR_EMAIL|SOVEREIGN_MCP_ALLOWED_CONTAINERS|SOVEREIGN_MCP_ALLOWED_WORKFLOWS|SOVEREIGN_MCP_WORKSPACE_ROOT|SOVEREIGN_MCP_PRIVATE_OWNER_MODE|SOVEREIGN_MCP_PRIVATE_VPS_DEV_MODE|SOVEREIGN_MCP_DEV_ROOTS|SOVEREIGN_MCP_ENABLE_DB_WRITES|SOVEREIGN_MCP_ENABLE_DEPLOY|SOVEREIGN_MCP_ALLOW_DATA_BACKFILLS|SOVEREIGN_MCP_ALLOW_DESTRUCTIVE_MIGRATIONS|SOVEREIGN_MCP_ENABLE_ADMIN_SQL|SOVEREIGN_MCP_ENABLE_MAIN_PUSH|SOVEREIGN_MCP_ENABLE_PR_MERGE|SOVEREIGN_MCP_ENABLE_WORKFLOW_CONTROL|SOVEREIGN_MCP_ALLOW_MERGE_WITHOUT_CHECKS|SOVEREIGN_MCP_ENABLE_SELF_UPDATE|SOVEREIGN_MCP_ENABLE_COMPOSE_WRITE|SOVEREIGN_MCP_ENABLE_PATCHMON_PATCH_WRITE|SOVEREIGN_MCP_PREVIEW_POSTGRES_HOST|SOVEREIGN_MCP_PREVIEW_POSTGRES_PORT|SOVEREIGN_MCP_PREVIEW_POSTGRES_DB|SOVEREIGN_MCP_PREVIEW_POSTGRES_USER|SOVEREIGN_MCP_PREVIEW_POSTGRES_PASSWORD|SOVEREIGN_BACKEND_IMAGE_REPOSITORY|SOVEREIGN_BACKEND_ENV_FILE|SOVEREIGN_BACKEND_MANAGED_ENV_FILE)=' "$environment_file" || true
  done
  printf 'SOVEREIGN_MCP_DEPLOY_SCRIPT=%s\n' "$BIN_DIR/deploy-sovereign-backend"
  printf 'SOVEREIGN_MCP_ROLLBACK_SCRIPT=%s\n' "$BIN_DIR/rollback-sovereign-backend"
  printf 'SOVEREIGN_MCP_SOURCE_DIR=/opt/sovereign-operator-source\n'
  printf 'SOVEREIGN_MCP_GOVERNANCE_MODE_PATH=%s\n' "$BROKER_GOVERNANCE_MODE"
  printf 'SOVEREIGN_MCP_SELF_UPDATE_SERVICE=sovereign-chatgpt-mcp-self-update.service\n'
  printf 'SOVEREIGN_MCP_SELF_UPDATE_STATUS=/var/lib/sovereign-chatgpt-self-update/status.json\n'
  printf 'SOVEREIGN_MCP_COMMAND_QUEUE=%s\n' "$COMMAND_QUEUE_DIR"
  printf 'SOVEREIGN_COMPOSE_TEMPLATE_ROOT=%s\n' "$COMPOSE_TEMPLATE_ROOT"
  printf 'PATCHMON_MCP_ADMIN_TOKEN_FILE=/opt/patchmon-sovereign/mcp-admin.jwt\n'
  printf 'SOVEREIGN_BACKEND_CONTAINER=sovereign-backend\n'
  [[ -z "$DOCKER_CONFIG_VALUE" ]] || printf 'DOCKER_CONFIG=%s\n' "$DOCKER_CONFIG_VALUE"
} > "$BROKER_ENV"; then
  restore_managed_private_file_mutation_best_effort "$BROKER_ENV"
  fail "managed broker environment rewrite failed: file=$BROKER_ENV"
fi
chmod 0600 "$BROKER_ENV" \
  || { restore_managed_private_file_mutation_best_effort "$BROKER_ENV"; fail "managed broker environment mode update failed: file=$BROKER_ENV"; }
chown root:root "$BROKER_ENV" \
  || { restore_managed_private_file_mutation_best_effort "$BROKER_ENV"; fail "managed broker environment ownership update failed: file=$BROKER_ENV"; }
restore_managed_private_file_mutation "$BROKER_ENV" "broker-environment"
unset OWNER_MANAGED_GITHUB_TOKEN PRESERVED_BROKER_GITHUB_TOKEN CONFIGURED_GITHUB_TOKEN EFFECTIVE_GITHUB_TOKEN
# CI-only release credentials are accepted exclusively as a temporary file
# under /run by the scoped reconciler entrypoint. They must never persist in
# a broker or Compose environment source.
remove_value "$BROKER_ENV" GITHUB_TOKEN
for PERSISTENT_ENVIRONMENT_SOURCE in "$ENV_FILE" "$MANAGED_ENV" "$BROKER_ENV"; do
  ! grep -q '^GITHUB_TOKEN=' "$PERSISTENT_ENVIRONMENT_SOURCE" \
    || fail "persistent GitHub API credential remains in $PERSISTENT_ENVIRONMENT_SOURCE"
done
unset PERSISTENT_ENVIRONMENT_SOURCE
INSTALL_STAGE="compose_preflight"
BROKER_GID="$(getent group sovereign-mcp | cut -d: -f3)"
[[ "$BROKER_GID" =~ ^[0-9]+$ ]] || fail "could not resolve sovereign-mcp group id"
export BROKER_GID
cd "$INSTALL_ROOT"
docker compose config >/dev/null

INSTALL_STAGE="prepare_patchmon_agent_sandbox_paths"
prepare_patchmon_agent_sandbox_paths
[[ -e "$PATCHMON_AGENT_BIN_LINK" || -L "$PATCHMON_AGENT_BIN_LINK" ]] \
  || fail "PatchMon agent binary path was not prepared"
[[ -d "$PATCHMON_AGENT_CONFIG_LINK" ]] \
  || fail "PatchMon agent config path was not prepared"
[[ -e "$PATCHMON_AGENT_UNIT_LINK" || -L "$PATCHMON_AGENT_UNIT_LINK" ]] \
  || fail "PatchMon agent unit path was not prepared"

INSTALL_STAGE="start_host_control_plane"
systemctl daemon-reload
systemctl enable --now sovereign-chatgpt-command-worker.service
systemctl restart sovereign-chatgpt-command-worker.service
systemctl is-active --quiet sovereign-chatgpt-command-worker.service || fail "host command worker is not active"
systemctl enable --now sovereign-chatgpt-broker.service
systemctl restart sovereign-chatgpt-broker.service
wait_for_broker_ready || {
  systemctl status sovereign-chatgpt-broker.service --no-pager >&2 || true
  fail "host broker socket exists but the broker RPC did not become ready after ${BROKER_READY_ATTEMPTS}s"
}

# The image is built and dependency-resolved in GitHub Actions. The VPS only
# pulls and verifies the immutable revision before touching the running container.

INSTALL_STAGE="capture_previous_mcp_tool_surface"
PREVIOUS_MCP_REGISTRY_FILE="$ROLLBACK_DIR/previous-mcp-registry-contracts.json"
PREVIOUS_MCP_REGISTRY_CAPTURE_MODE="$(resolve_previous_mcp_registry_capture_mode)"
PREVIOUS_MCP_REGISTRY_CAPTURE_COMMAND=()
PREVIOUS_MCP_INTROSPECTION_CONTAINER=""
case "$PREVIOUS_MCP_REGISTRY_CAPTURE_MODE" in
  attested-first-install-no-predecessor)
    ;;
  running-container)
    PREVIOUS_MCP_CONTAINER_PRESENT=1
    PREVIOUS_MCP_REGISTRY_CAPTURE_COMMAND=(
      timeout --signal=TERM --kill-after=10s 120s
      docker exec -i sovereign-chatgpt-mcp python -
    )
    ;;
  immutable-image-offline)
    PREVIOUS_MCP_CONTAINER_PRESENT=1
    PREVIOUS_MCP_IMAGE_ID="$(
      docker container inspect sovereign-chatgpt-mcp --format '{{.Image}}' 2>/dev/null
    )" || fail "could not resolve the stopped predecessor MCP image"
    [[ "$PREVIOUS_MCP_IMAGE_ID" =~ ^sha256:[0-9a-f]{64}$ ]] \
      || fail "stopped predecessor MCP does not reference a local immutable image id"
    PREVIOUS_MCP_INTROSPECTION_CONTAINER="sovereign-mcp-predecessor-introspection-$$"
    if docker container inspect "$PREVIOUS_MCP_INTROSPECTION_CONTAINER" >/dev/null 2>&1; then
      fail "bounded predecessor introspection container name already exists"
    fi
    PREVIOUS_MCP_REGISTRY_CAPTURE_COMMAND=(
      timeout --signal=TERM --kill-after=10s 120s
      docker run --rm -i
      --name "$PREVIOUS_MCP_INTROSPECTION_CONTAINER"
      --pull never
      --no-healthcheck
      --network none
      --read-only
      --tmpfs /tmp:rw,nosuid,nodev,size=67108864,mode=1777
      --pids-limit 256
      --memory 536870912
      --cpus 1.0
      --user 10001:10001
      --cap-drop ALL
      --security-opt no-new-privileges
      --env HOME=/tmp/home
      --env PYTHONDONTWRITEBYTECODE=1
      --env SOVEREIGN_MCP_HOST=127.0.0.1
      --env SOVEREIGN_MCP_PORT=8090
      --env SOVEREIGN_MCP_WORKSPACE_ROOT=/tmp/workspaces
      --env SOVEREIGN_TOOL_RANKING_STATE_ROOT=/tmp/tool-ranking
      --env SOVEREIGN_NEURO_RUNTIME_STATE_ROOT=/tmp/neuro-runtime
      --env SOVEREIGN_NEURO_RUNTIME_TRACKING_ENABLED=0
      --env SOVEREIGN_ANDROID_NATIVE_BUILD_MODE=github_actions
      --entrypoint python
      "$PREVIOUS_MCP_IMAGE_ID"
      -
    )
    ;;
  *)
    fail "invalid predecessor MCP registry capture mode"
    ;;
esac
if [[ "$PREVIOUS_MCP_CONTAINER_PRESENT" == "1" ]]; then
  if ! "${PREVIOUS_MCP_REGISTRY_CAPTURE_COMMAND[@]}" <<'PY' > "$PREVIOUS_MCP_REGISTRY_FILE"
from dataclasses import asdict
import json

import launcher
import operational_governance_tools

registry = operational_governance_tools.mcp_tool_contract_registry(include_schemas=True)
payload = asdict(registry)
tools = sorted(payload.get("tools") or [], key=lambda item: str(item.get("name") or ""))
names = [item.get("name") for item in tools]
if (
    registry.ok is not True
    or registry.status != "MCP_TOOL_REGISTRY_READY"
    or registry.runtimeVerified is not True
    or registry.truncated is True
    or registry.toolCount != len(tools)
    or not tools
    or any(not isinstance(name, str) or not name for name in names)
    or names != sorted(set(names))
):
    raise SystemExit("predecessor MCP returned an invalid complete contract registry")
print(
    json.dumps(
        {
            "schemaVersion": "sovereign.mcp-deployment-contract-surface.v1",
            "registrySnapshotSha256": registry.registrySnapshotSha256,
            "toolCount": len(tools),
            "tools": tools,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
)
PY
  then
    if [[ -n "$PREVIOUS_MCP_INTROSPECTION_CONTAINER" ]]; then
      docker rm -f "$PREVIOUS_MCP_INTROSPECTION_CONTAINER" >/dev/null 2>&1 || true
    fi
    fail "could not capture the predecessor MCP complete contract registry before replacement: mode=$PREVIOUS_MCP_REGISTRY_CAPTURE_MODE"
  fi
  if [[ -n "$PREVIOUS_MCP_INTROSPECTION_CONTAINER" ]] \
    && docker container inspect "$PREVIOUS_MCP_INTROSPECTION_CONTAINER" >/dev/null 2>&1; then
    docker rm -f "$PREVIOUS_MCP_INTROSPECTION_CONTAINER" >/dev/null 2>&1 || true
    fail "bounded predecessor introspection container was not cleaned"
  fi
  chmod 0600 "$PREVIOUS_MCP_REGISTRY_FILE"
  python3 - "$PREVIOUS_MCP_REGISTRY_FILE" <<'PY'
import json
import sys
from pathlib import Path

value = json.loads(Path(sys.argv[1]).read_text("utf-8"))
tools = value.get("tools") if isinstance(value, dict) else None
if (
    value.get("schemaVersion") != "sovereign.mcp-deployment-contract-surface.v1"
    or not isinstance(tools, list)
    or not tools
    or value.get("toolCount") != len(tools)
):
    raise SystemExit("captured predecessor MCP complete contract registry is invalid")
names = [item.get("name") for item in tools if isinstance(item, dict)]
if len(names) != len(tools) or names != sorted(set(names)):
    raise SystemExit("captured predecessor MCP complete contract registry is not canonical")
for item in tools:
    if (
        not isinstance(item.get("capabilities"), list)
        or not isinstance(item.get("effect"), str)
        or not isinstance(item.get("annotations"), dict)
        or not isinstance(item.get("parameters"), dict)
        or not isinstance(item.get("outputSchema"), dict)
    ):
        raise SystemExit(f"captured predecessor MCP contract is incomplete: {item.get('name')}")
PY
  PREVIOUS_MCP_TOOL_SURFACE_CAPTURED=1
fi

INSTALL_STAGE="replace_mcp_container"
# Stop only the known tunnel and MCP container before claiming the host port.
# Unknown listeners are never killed: they block deployment with bounded evidence.
if [[ "$TUNNEL_MODE" != "disabled" ]] && systemctl is-active --quiet sovereign-openai-tunnel.service; then
  systemctl stop sovereign-openai-tunnel.service
fi
if docker container inspect sovereign-chatgpt-mcp >/dev/null 2>&1; then
  docker rm -f sovereign-chatgpt-mcp >/dev/null
fi

PORT_EVIDENCE=""
for attempt in $(seq 1 10); do
  PORT_EVIDENCE="$(port_listener_evidence)"
  [[ -z "$PORT_EVIDENCE" ]] && break
  sleep 1
done
if [[ -n "$PORT_EVIDENCE" ]]; then
  printf '%s\n' "$PORT_EVIDENCE" >&2
  fail "host port $MCP_HOST_PORT remains occupied after controlled MCP shutdown; refusing to kill an unknown process"
fi

docker compose up -d --no-build --force-recreate --remove-orphans

INSTALL_STAGE="verify_mcp_container"
CONTAINER_STATE=""
for attempt in $(seq 1 30); do
  CONTAINER_STATE="$(docker inspect sovereign-chatgpt-mcp --format '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}no-health{{end}}' 2>/dev/null || true)"
  if [[ "$CONTAINER_STATE" == "running healthy" ]]; then
    break
  fi
  sleep 2
done
if [[ "$CONTAINER_STATE" != "running healthy" ]]; then
  docker logs --tail 200 sovereign-chatgpt-mcp >&2 || true
  fail "MCP container did not pass protocol health: ${CONTAINER_STATE:-missing}"
fi

INSTALL_STAGE="verify_broker_socket_visibility"
[[ -S /run/sovereign-chatgpt-broker/operator.sock ]] || fail "host broker socket disappeared after MCP recreation"
docker exec sovereign-chatgpt-mcp test -S /run/sovereign-chatgpt-broker/operator.sock || fail "broker socket is not visible inside the recreated MCP container"
INSTALL_STAGE="verify_no_persistent_github_token_runtime"
for PERSISTENT_ENVIRONMENT_SOURCE in "$ENV_FILE" "$MANAGED_ENV" "$BROKER_ENV"; do
  ! grep -q '^GITHUB_TOKEN=' "$PERSISTENT_ENVIRONMENT_SOURCE" \
    || fail "persistent GitHub API credential remains in $PERSISTENT_ENVIRONMENT_SOURCE after restart"
done
unset PERSISTENT_ENVIRONMENT_SOURCE
docker exec sovereign-chatgpt-mcp python - <<'PY'
import os
assert "GITHUB_TOKEN" not in os.environ
PY
BROKER_MAIN_PID="$(systemctl show --property MainPID --value sovereign-chatgpt-broker.service)"
[[ "$BROKER_MAIN_PID" =~ ^[1-9][0-9]*$ ]] || fail "broker service has no main process id"
! tr '\0' '\n' < "/proc/$BROKER_MAIN_PID/environ" | grep -q '^GITHUB_TOKEN=' \
  || fail "broker process inherited a persistent GitHub API credential"
unset BROKER_MAIN_PID
INSTALL_STAGE="verify_inbound_mutation_boundary"
docker exec -i sovereign-chatgpt-mcp python - <<'PY'
import json
import socket
import uuid

request_id = uuid.uuid4().hex
payload = json.dumps(
    {"request_id": request_id, "action": "host_worker_canary", "arguments": {}},
    separators=(",", ":"),
).encode("utf-8") + b"\n"
with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
    client.settimeout(5)
    client.connect("/run/sovereign-chatgpt-broker/operator.sock")
    client.sendall(payload)
    response = json.loads(client.recv(65536).split(b"\n", 1)[0].decode("utf-8"))
result = response["result"]
assert result.get("failure_family") == "INBOUND_MUTATION_FORBIDDEN", result
PY

INSTALL_STAGE="verify_runtime_import_contracts"
docker exec sovereign-chatgpt-mcp test -f /app/skills/sovereign-operational-governance/SKILL.md || fail "operational governance skill manifest is missing from the MCP image"
docker exec sovereign-chatgpt-mcp test -f /app/skills/sovereign-operational-assurance/SKILL.md || fail "operational assurance skill manifest is missing from the MCP image"
docker exec sovereign-chatgpt-mcp test -f /app/skills/sovereign-mcp-optimal-operation/SKILL.md || fail "optimal operation skill manifest is missing from the MCP image"
docker exec sovereign-chatgpt-mcp test -f /app/skills/sovereign-neuro-teaching-runtime/SKILL.md || fail "neuro teaching skill manifest is missing from the MCP image"
docker exec sovereign-chatgpt-mcp test -f /app/config/sovereign-mcp-operating-profile.json || fail "versioned MCP operating profile is missing from the MCP image"
docker exec sovereign-chatgpt-mcp test -f /app/config/sovereign-continuity-policy.json || fail "versioned continuity policy is missing from the MCP image"
docker exec sovereign-chatgpt-mcp test -f /app/continuity-data/CONTEXT.md || fail "continuity context is missing from the MCP image"
docker exec sovereign-chatgpt-mcp test -f /app/continuity-data/LEDGER.jsonl || fail "continuity ledger is missing from the MCP image"
docker exec sovereign-chatgpt-mcp python -c 'import continuity; import launcher; import server; import self_heal; import android_hardening; import android_validation_router; import a2a_runtime_client; import document_pipeline; import github_knowledge_canary; import issue_closure_canary; import programming_language_catalog_runtime; import owner_input_widget; import tool_extensions; import repository_skill_tools; import repository_intelligence_tools; import proven_learning_tools; import skill_supply_chain_tools; import deterministic_contract; import deterministic_architecture_tools; import database_evidence_tools; import enterprise_backend_tools; import freemium_product_architect_tools; import openai_project_access_tools; import operating_profile; import predictive_tool_router; import tool_success_ranking; import operational_governance_tools; import operational_assurance_tools; import output_contracts; import toolchain_composition; import patchmon_operator; import patchmon_fleet; assert launcher.mcp is server.mcp; assert launcher.TOOL_SUCCESS_TRACKING.get("ok") is True, launcher.TOOL_SUCCESS_TRACKING; output_contract_report=launcher.OUTPUT_CONTRACT_INSTALLATION; assert output_contract_report.get("ok") is True, output_contract_report; assert output_contract_report.get("missingOutputSchemaCount") == 0, output_contract_report; operating_profile_report=launcher.OPERATING_PROFILE_ENFORCEMENT; assert operating_profile_report.ok is True, operating_profile_report; assert operating_profile_report.enforcedToolCount == operating_profile_report.mutableToolCount, operating_profile_report; assert self_heal.REPAIR_ENGINE is not None; assert android_hardening.AndroidHardeningRuntime is not None; assert getattr(server.android, "_native_validation_router_installed", False) is True; assert callable(tool_extensions.repository_dispatch_workflow); assert callable(tool_extensions.repository_workflow_run_status); assert callable(repository_skill_tools.repository_knowledge_surface_scan); assert callable(repository_skill_tools.repository_product_logic_map); assert callable(repository_skill_tools.repository_change_impact_manifest); assert callable(repository_skill_tools.repository_architecture_snapshot); assert callable(repository_skill_tools.repository_architecture_drift_report); assert callable(repository_skill_tools.repository_architecture_runtime_drift_evidence); assert callable(repository_skill_tools.repository_mirror_diff_report); assert callable(repository_skill_tools.repository_endpoint_reference); assert callable(repository_skill_tools.repository_learning_records_normalize_preview); assert callable(repository_skill_tools.repository_release_hunt_manifest); assert callable(repository_intelligence_tools.repository_intelligence_index_build); assert callable(repository_intelligence_tools.repository_hash_bound_replace); assert callable(repository_intelligence_tools.repository_schema_diagnostics); assert callable(repository_intelligence_tools.deployment_evidence_session_capture); assert callable(repository_intelligence_tools.sovereign_resource_explorer); assert callable(proven_learning_tools.proven_learning_pattern_plan); assert callable(proven_learning_tools.proven_learning_owner_approval_request); assert callable(proven_learning_tools.proven_learning_pattern_apply); assert callable(proven_learning_tools.repository_learning_logbook_update); assert callable(skill_supply_chain_tools.skill_supply_chain_inventory); assert callable(skill_supply_chain_tools.skill_archive_inspect); assert callable(skill_supply_chain_tools.goal_transition_preview); assert callable(skill_supply_chain_tools.template_generation_plan); assert deterministic_contract.KAPPA_SCALE == 1000000; inventory=deterministic_architecture_tools.deterministic_tool_inventory(); assert inventory.get("crossRuntimeParityProven") is True, inventory; assert callable(deterministic_architecture_tools.deterministic_tool_inventory); assert callable(deterministic_architecture_tools.deterministic_architecture_inventory); assert callable(deterministic_architecture_tools.deterministic_nondeterminism_scan); assert callable(deterministic_architecture_tools.deterministic_kappa_contract_audit); assert callable(deterministic_architecture_tools.deterministic_sql_contract_audit); assert callable(deterministic_architecture_tools.deterministic_transition_validate); assert callable(deterministic_architecture_tools.deterministic_replay_verify); assert callable(deterministic_architecture_tools.deterministic_transformation_plan); assert callable(database_evidence_tools.database_evidence_skill_inventory); assert callable(database_evidence_tools.database_evidence_architecture_inventory); assert callable(database_evidence_tools.postgres_evidence_read); assert callable(database_evidence_tools.postgres_evidence_migration_preview); assert callable(database_evidence_tools.database_evidence_receipt_verify); db_evidence_names={"database_evidence_skill_inventory","database_evidence_architecture_inventory","postgres_evidence_read","postgres_evidence_migration_preview","database_evidence_receipt_verify"}; registered_names={tool.name for tool in launcher.mcp._tool_manager.list_tools()}; assert db_evidence_names <= registered_names, db_evidence_names - registered_names; assert callable(enterprise_backend_tools.backend_engineering_tool_inventory); assert callable(enterprise_backend_tools.backend_architecture_assess); assert callable(enterprise_backend_tools.backend_stack_select); assert callable(enterprise_backend_tools.backend_delivery_plan); assert callable(enterprise_backend_tools.backend_api_security_plan); assert callable(enterprise_backend_tools.repository_revision_resolve); assert callable(freemium_product_architect_tools.freemium_product_tool_inventory); assert callable(freemium_product_architect_tools.freemium_market_opportunity_score); assert callable(freemium_product_architect_tools.freemium_offer_contract_build); assert callable(freemium_product_architect_tools.freemium_product_contract_validate); assert callable(freemium_product_architect_tools.freemium_product_bundle_manifest); assert callable(openai_project_access_tools.openai_project_access_plan); assert callable(openai_project_access_tools.openai_project_access_runtime_evidence); assert callable(operating_profile.sovereign_operating_profile_status); assert callable(operating_profile.sovereign_mission_preflight); profile_status=operating_profile.sovereign_operating_profile_status(); assert profile_status.status == "OPERATING_PROFILE_ENFORCED", profile_status; assert callable(operational_governance_tools.operational_skill_inventory); assert callable(operational_governance_tools.mcp_tool_contract_registry); assert callable(operational_governance_tools.tool_recommend_for_mission); assert callable(operational_governance_tools.tool_success_ranking); assert callable(operational_governance_tools.mcp_registry_snapshot_verify); assert callable(operational_governance_tools.evidence_graph_build); assert callable(operational_governance_tools.schema_migration_reconcile); assert callable(operational_governance_tools.llm_route_reliability_assess); assert callable(operational_governance_tools.agent_run_liveness_assess); assert callable(operational_governance_tools.semantic_intent_boundary_audit); assert callable(operational_governance_tools.cost_credit_settlement_reconcile); assert callable(operational_governance_tools.backup_restore_evidence_verify); assert callable(operational_governance_tools.slo_error_budget_assess); assert callable(operational_governance_tools.configuration_drift_assess); assert callable(operational_governance_tools.runtime_runbook_generate); assert callable(operational_governance_tools.ownership_codeowners_guard); assert callable(operational_governance_tools.compliance_evidence_export); assert callable(operational_assurance_tools.operational_assurance_skill_inventory); assert callable(operational_assurance_tools.vps_capacity_resource_pressure_assess); assert callable(operational_assurance_tools.runtime_dependency_health_matrix); assert callable(operational_assurance_tools.outbox_queue_liveness_assess); assert callable(operational_assurance_tools.scheduled_maintenance_coordinate); assert callable(operational_assurance_tools.runtime_topology_change_audit); assert callable(operational_assurance_tools.postgres_query_index_performance_assess); assert callable(operational_assurance_tools.data_integrity_invariant_audit); assert callable(operational_assurance_tools.data_repair_plan_build); assert callable(operational_assurance_tools.vector_memory_consistency_assess); assert callable(operational_assurance_tools.memory_poisoning_provenance_guard); assert callable(operational_assurance_tools.learning_pattern_lifecycle_preview); assert callable(operational_assurance_tools.data_retention_privacy_audit); assert callable(operational_assurance_tools.multi_tenant_isolation_verify); assert callable(operational_assurance_tools.mcp_schema_compatibility_audit); assert callable(operational_assurance_tools.mcp_protocol_conformance_fuzz_plan); assert callable(operational_assurance_tools.tool_permission_minimize); assert callable(operational_assurance_tools.dynamic_execution_containment_audit); assert callable(operational_assurance_tools.skill_capability_coverage_map); assert callable(operational_assurance_tools.skill_lifecycle_deprecation_preview); assert callable(operational_assurance_tools.skill_regression_benchmark); assert callable(operational_assurance_tools.tool_idempotency_verify); assert callable(operational_assurance_tools.owner_approval_policy_evaluate); assert callable(operational_assurance_tools.secret_lifecycle_rotation_assess); assert callable(operational_assurance_tools.secret_literal_triage); assert callable(operational_assurance_tools.sbom_provenance_image_signing_verify); assert callable(operational_assurance_tools.dependency_vulnerability_remediation_plan); assert callable(operational_assurance_tools.authentication_chaos_negative_test_assess); assert output_contracts.ToolOutputEnvelope is not None; assert callable(toolchain_composition.mcp_toolchain_contract_inventory); assert callable(toolchain_composition.mcp_toolchain_compile); assert callable(toolchain_composition.mcp_toolchain_validate); assert callable(toolchain_composition.mcp_toolchain_next_step); assert callable(toolchain_composition.mcp_diagnostic_chain_plan); assert all(getattr(tool, "output_schema", None) for tool in launcher.mcp._tool_manager.list_tools()); assurance=operational_assurance_tools.operational_assurance_skill_inventory(); assert assurance.status == "OPERATIONAL_ASSURANCE_SKILLS_READY", assurance; registry=operational_governance_tools.mcp_tool_contract_registry(include_schemas=False); assert registry.status == "MCP_TOOL_REGISTRY_READY", registry; assert registry.toolCount >= 43, registry; assert callable(server.repository_sync_workspace_to_pr_head); assert callable(server.repository_merge_pr_series); assert callable(server.vps_dev_exec); assert callable(server.postgres_schema_inventory); assert callable(server.managed_compose_stack_plan); assert callable(server.deploy_managed_compose_stack); assert callable(server.memory_gateway_collection_canary); assert callable(server.patchmon_tool_inventory); assert callable(server.patchmon_runtime_inventory); assert callable(server.patchmon_database_inventory); assert callable(server.patchmon_query); assert callable(server.patchmon_brain_snapshot); assert callable(server.patchmon_patch_action_plan); assert callable(server.patchmon_patch_action_apply); assert callable(server.patchmon_fleet_bootstrap_plan); assert callable(server.patchmon_fleet_bootstrap_apply); assert callable(server.patchmon_fleet_orchestrator_status); assert patchmon_operator.PatchmonOperatorRuntime is not None; assert patchmon_fleet.PatchmonFleetRuntime is not None; assert callable(server.a2a_live_canary); assert callable(server.controller_run_external_event); assert callable(server.document_pipeline_live_canary); assert callable(server.github_knowledge_live_canary); assert callable(server.issue_closure_runtime_canary); assert callable(server.programming_language_catalog_persistent_import); assert a2a_runtime_client.A2A_VERSION == "1.0"; assert document_pipeline.DocumentPipelineRuntime is not None; assert github_knowledge_canary.GitHubKnowledgeCanaryRuntime is not None; assert issue_closure_canary.IssueClosureCanaryRuntime is not None; assert programming_language_catalog_runtime.ProgrammingLanguageCatalogRuntime is not None; assert owner_input_widget.WIDGET_URI in {str(item.uri) for item in server.mcp._resource_manager.list_resources()}; status=server.broker.status(); assert status.get("status") == "BROKER_READY", status'

docker exec sovereign-chatgpt-mcp python -c 'import neuro_architecture_contract; import neuromorphic_runtime; import foundation_runtime; import neuro_teaching_tools; assert callable(neuro_teaching_tools.neuro_runtime_contract_status); assert callable(neuro_teaching_tools.neuro_event_route_preview); assert callable(neuro_teaching_tools.neuro_event_commit); assert callable(neuro_teaching_tools.teaching_package_assess); assert callable(neuro_teaching_tools.teaching_lesson_simulate)'

INSTALL_STAGE="verify_live_tool_surface_and_widget_domain"
docker exec -i sovereign-chatgpt-mcp python - <<'PY'
import asyncio

import launcher
import server

required_tools = {
    "backend_architecture_assess",
    "deterministic_architecture_inventory",
    "mcp_tool_contract_registry",
    "neuro_event_commit",
    "neuro_event_route_preview",
    "neuro_runtime_contract_status",
    "operational_assurance_skill_inventory",
    "patchmon_tool_inventory",
    "repository_architecture_drift_report",
    "repository_architecture_snapshot",
    "vps_dev_exec",
    "teaching_lesson_simulate",
    "teaching_package_assess",
}
tools = asyncio.run(launcher.mcp.list_tools())
tool_names = {tool.name for tool in tools}
neuro_tools = {
    "neuro_event_commit",
    "neuro_event_route_preview",
    "neuro_runtime_contract_status",
    "teaching_lesson_simulate",
    "teaching_package_assess",
}
missing_tools = sorted(required_tools - tool_names)
assert not missing_tools, {"missingRequiredTools": missing_tools, "toolCount": len(tool_names)}
assert len(tool_names) == 250, {"expectedToolCount": 250, "actualToolCount": len(tool_names)}
assert neuro_tools <= tool_names, sorted(neuro_tools - tool_names)
registry = server._live_mcp_registry_evidence()
assert registry.get("registry_runtime_verified") is True, registry
assert registry.get("registry_tool_count") == len(tool_names), (registry, len(tool_names))
resources = asyncio.run(launcher.mcp.list_resources())
cognitive_resource = next(
    resource
    for resource in resources
    if str(resource.uri) == "ui://sovereign/dev_dashboard.v2.html"
)
serialized = cognitive_resource.model_dump(by_alias=True)
resource_meta = serialized.get("_meta") or {}
expected_domain = "https://sovereign-backend.arelorian.de"
assert (resource_meta.get("ui") or {}).get("domain") == expected_domain, resource_meta
assert resource_meta.get("openai/widgetDomain") == expected_domain, resource_meta
print(
    {
        "toolCount": len(tool_names),
        "registrySha256": registry.get("registry_tool_names_sha256"),
        "widgetDomain": expected_domain,
        "widgetUri": str(cognitive_resource.uri),
    }
)
PY

INSTALL_STAGE="verify_mcp_tool_surface_preservation"
NEW_MCP_REGISTRY_FILE="$ROLLBACK_DIR/new-mcp-registry-contracts.json"
docker exec -i sovereign-chatgpt-mcp python - <<'PY' > "$NEW_MCP_REGISTRY_FILE"
from dataclasses import asdict
import json

import launcher
import operational_governance_tools

registry = operational_governance_tools.mcp_tool_contract_registry(include_schemas=True)
payload = asdict(registry)
tools = sorted(payload.get("tools") or [], key=lambda item: str(item.get("name") or ""))
names = [item.get("name") for item in tools]
if (
    registry.ok is not True
    or registry.status != "MCP_TOOL_REGISTRY_READY"
    or registry.runtimeVerified is not True
    or registry.truncated is True
    or registry.toolCount != len(tools)
    or any(not isinstance(name, str) or not name for name in names)
    or names != sorted(set(names))
):
    raise SystemExit("replacement MCP returned an invalid complete contract registry")
print(
    json.dumps(
        {
            "schemaVersion": "sovereign.mcp-deployment-contract-surface.v1",
            "registrySnapshotSha256": registry.registrySnapshotSha256,
            "toolCount": len(tools),
            "tools": tools,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
)
PY
chmod 0600 "$NEW_MCP_REGISTRY_FILE"
python3 - "$PREVIOUS_MCP_REGISTRY_FILE" "$NEW_MCP_REGISTRY_FILE" "$PREVIOUS_MCP_TOOL_SURFACE_CAPTURED" "$EXPECTED_MCP_TOOL_COUNT" <<'PY'
from decimal import Decimal, InvalidOperation
import json
import sys
from pathlib import Path
from typing import Any

previous_path = Path(sys.argv[1])
new_path = Path(sys.argv[2])
predecessor_captured = sys.argv[3] == "1"
expected_count = int(sys.argv[4])
expected_additions = {
    "neuro_event_commit",
    "neuro_event_route_preview",
    "neuro_runtime_contract_status",
    "teaching_lesson_simulate",
    "teaching_package_assess",
    "vps_dev_exec",
}


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def registry_tools(path: Path, *, expected_tool_count: int | None = None) -> list[dict[str, Any]]:
    value = json.loads(path.read_text("utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"invalid complete MCP contract registry: {path.name}")
    tools = value.get("tools")
    if (
        value.get("schemaVersion") != "sovereign.mcp-deployment-contract-surface.v1"
        or not isinstance(tools, list)
        or value.get("toolCount") != len(tools)
        or (expected_tool_count is not None and len(tools) != expected_tool_count)
    ):
        raise SystemExit(f"invalid complete MCP contract registry: {path.name}")
    names = [item.get("name") for item in tools if isinstance(item, dict)]
    if len(names) != len(tools) or names != sorted(set(names)):
        raise SystemExit(f"non-canonical complete MCP contract registry: {path.name}")
    for item in tools:
        if (
            not isinstance(item.get("capabilities"), list)
            or any(not isinstance(capability, str) or not capability for capability in item["capabilities"])
            or not isinstance(item.get("effect"), str)
            or not isinstance(item.get("annotations"), dict)
            or not isinstance(item.get("parameters"), dict)
            or not isinstance(item.get("outputSchema"), dict)
        ):
            raise SystemExit(f"incomplete MCP contract: {item.get('name')}")
    return tools


ANNOTATION_KEYWORDS = {
    "$comment",
    "$id",
    "$schema",
    "default",
    "deprecated",
    "description",
    "examples",
    "readOnly",
    "title",
    "writeOnly",
}
LOWER_BOUNDS = {
    "exclusiveMinimum",
    "minContains",
    "minItems",
    "minLength",
    "minProperties",
    "minimum",
}
UPPER_BOUNDS = {
    "exclusiveMaximum",
    "maxContains",
    "maxItems",
    "maxLength",
    "maxProperties",
    "maximum",
}
EXACT_ASSERTIONS = {
    "$ref",
    "contentEncoding",
    "contentMediaType",
    "format",
    "pattern",
}
HANDLED_KEYWORDS = {
    "additionalProperties",
    "allOf",
    "anyOf",
    "const",
    "contains",
    "dependentRequired",
    "enum",
    "items",
    "multipleOf",
    "not",
    "oneOf",
    "prefixItems",
    "properties",
    "propertyNames",
    "required",
    "type",
    "uniqueItems",
    *LOWER_BOUNDS,
    *UPPER_BOUNDS,
    *EXACT_ASSERTIONS,
}


def type_set(value: Any) -> set[str] | None:
    if isinstance(value, str):
        return {value}
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return set(value)
    return None


def input_enum_widening_proof_errors(old: Any, new: Any, *, path: str) -> list[str]:
    """Prove old inputs remain accepted using the sole approved schema evolution.

    The replacement release changes five predecessor parameter schemas only by
    extending one nested capability enum.  JSON Schema applicators interact in
    ways that make a general structural subset checker unsafe (especially
    oneOf, contains/prefixItems, and unevaluated*).  Keep this release gate
    deliberately conservative: structure and every constraint must be exact;
    the only admitted delta is an enum superset reached through an unchanged
    properties/items path.
    """
    if canonical(old) == canonical(new):
        return []
    if not isinstance(old, dict) or not isinstance(new, dict):
        return [f"{path}: schema structure changed outside the approved input enum widening"]
    if set(old) != set(new):
        return [f"{path}: schema keywords changed outside the approved input enum widening"]

    errors: list[str] = []
    for keyword in sorted(old):
        old_value = old[keyword]
        new_value = new[keyword]
        if canonical(old_value) == canonical(new_value):
            continue
        if keyword == "enum":
            if not isinstance(old_value, list) or not isinstance(new_value, list):
                errors.append(f"{path}.enum: enum declarations must be lists")
                continue
            old_values = [canonical(item) for item in old_value]
            new_values = [canonical(item) for item in new_value]
            if len(set(old_values)) != len(old_values) or len(set(new_values)) != len(new_values):
                errors.append(f"{path}.enum: enum declarations must contain unique values")
            elif not set(old_values) <= set(new_values):
                errors.append(f"{path}.enum: replacement removed predecessor enum values")
            continue
        if keyword == "properties":
            if not isinstance(old_value, dict) or not isinstance(new_value, dict):
                errors.append(f"{path}.properties: property maps must remain objects")
                continue
            if set(old_value) != set(new_value):
                errors.append(
                    f"{path}.properties: property set changed outside the approved input enum widening"
                )
                continue
            for name in sorted(old_value):
                errors.extend(
                    input_enum_widening_proof_errors(
                        old_value[name],
                        new_value[name],
                        path=f"{path}.properties.{name}",
                    )
                )
            continue
        if keyword == "items":
            errors.extend(
                input_enum_widening_proof_errors(
                    old_value,
                    new_value,
                    path=f"{path}.items",
                )
            )
            continue
        errors.append(f"{path}.{keyword}: constraint changed outside the approved input enum widening")
    return errors


def schema_compatibility_errors(
    old: Any,
    new: Any,
    *,
    path: str,
    allow_input_enum_widening: bool = True,
) -> list[str]:
    if canonical(old) == canonical(new):
        return []
    if not allow_input_enum_widening:
        return [f"{path}: schema must remain exact for predecessor output compatibility"]
    proof_errors = input_enum_widening_proof_errors(old, new, path=path)
    if proof_errors:
        return proof_errors
    if isinstance(old, bool):
        if old is False:
            return []
        return [] if new is True or new == {} else [f"{path}: previously unconstrained schema became restrictive"]
    if not isinstance(old, dict):
        return [f"{path}: predecessor schema is not an object or boolean"]
    if new is True or new == {}:
        return []
    if not isinstance(new, dict):
        return [f"{path}: replacement schema is not an object"]

    errors: list[str] = []
    old_types = type_set(old.get("type")) if "type" in old else None
    new_types = type_set(new.get("type")) if "type" in new else None
    if old_types is None and "type" in old:
        errors.append(f"{path}.type: predecessor type declaration is invalid")
    elif new_types is not None and old_types is None:
        errors.append(f"{path}.type: replacement added a type restriction")
    elif old_types is not None and new_types is not None and not old_types <= new_types:
        errors.append(f"{path}.type: replacement removed predecessor types {sorted(old_types - new_types)}")

    old_required = old.get("required", [])
    new_required = new.get("required", [])
    if not isinstance(old_required, list) or not all(isinstance(item, str) for item in old_required):
        errors.append(f"{path}.required: predecessor declaration is invalid")
        old_required = []
    if not isinstance(new_required, list) or not all(isinstance(item, str) for item in new_required):
        errors.append(f"{path}.required: replacement declaration is invalid")
        new_required = []
    newly_required = sorted(set(new_required) - set(old_required))
    if newly_required:
        errors.append(f"{path}.required: replacement added required fields {newly_required}")

    old_properties = old.get("properties", {})
    new_properties = new.get("properties", {})
    old_additional = old.get("additionalProperties", True)
    new_additional = new.get("additionalProperties", True)
    if not isinstance(old_properties, dict) or not isinstance(new_properties, dict):
        errors.append(f"{path}.properties: property maps must remain objects")
    else:
        for name, old_property in old_properties.items():
            if name not in new_properties:
                errors.append(f"{path}.properties.{name}: predecessor property was removed")
                continue
            errors.extend(
                schema_compatibility_errors(
                    old_property,
                    new_properties[name],
                    path=f"{path}.properties.{name}",
                )
            )
        for name, new_property in new_properties.items():
            if name in old_properties or old_additional is False:
                continue
            if old.get("patternProperties") or "unevaluatedProperties" in old:
                errors.append(
                    f"{path}.properties.{name}: replacement property interacts with an unverified predecessor property domain"
                )
                continue
            if old_additional is True:
                errors.extend(
                    schema_compatibility_errors(
                        True,
                        new_property,
                        path=f"{path}.properties.{name}",
                    )
                )
            elif isinstance(old_additional, dict):
                errors.extend(
                    schema_compatibility_errors(
                        old_additional,
                        new_property,
                        path=f"{path}.properties.{name}",
                    )
                )
            else:
                errors.append(f"{path}.additionalProperties: predecessor declaration is invalid")

    if "enum" in new:
        if "enum" not in old:
            errors.append(f"{path}.enum: replacement added an enum restriction")
        elif not isinstance(old["enum"], list) or not isinstance(new["enum"], list):
            errors.append(f"{path}.enum: enum declarations must be lists")
        else:
            old_values = {canonical(item) for item in old["enum"]}
            new_values = {canonical(item) for item in new["enum"]}
            if not old_values <= new_values:
                errors.append(f"{path}.enum: replacement removed predecessor enum values")
    if "const" in new and ("const" not in old or canonical(old["const"]) != canonical(new["const"])):
        errors.append(f"{path}.const: replacement added or changed a const restriction")

    if canonical(old.get("oneOf")) != canonical(new.get("oneOf")):
        errors.append(f"{path}.oneOf: replacement changed an exclusive alternative set")

    for keyword in ("anyOf",):
        old_alternatives = old.get(keyword)
        new_alternatives = new.get(keyword)
        if new_alternatives is not None and old_alternatives is None:
            errors.append(f"{path}.{keyword}: replacement added alternatives as a restriction")
        elif old_alternatives is not None and new_alternatives is not None:
            if not isinstance(old_alternatives, list) or not isinstance(new_alternatives, list):
                errors.append(f"{path}.{keyword}: alternatives must be lists")
            else:
                for index, old_alternative in enumerate(old_alternatives):
                    if not any(
                        not schema_compatibility_errors(
                            old_alternative,
                            new_alternative,
                            path=f"{path}.{keyword}[{index}]",
                        )
                        for new_alternative in new_alternatives
                    ):
                        errors.append(f"{path}.{keyword}[{index}]: predecessor alternative is no longer covered")

    old_all = old.get("allOf")
    new_all = new.get("allOf")
    if new_all is not None and old_all is None:
        errors.append(f"{path}.allOf: replacement added a conjunctive restriction")
    elif old_all is not None and new_all is not None:
        if not isinstance(old_all, list) or not isinstance(new_all, list):
            errors.append(f"{path}.allOf: declarations must be lists")
        else:
            for index, new_alternative in enumerate(new_all):
                if not any(
                    not schema_compatibility_errors(
                        old_alternative,
                        new_alternative,
                        path=f"{path}.allOf[{index}]",
                    )
                    for old_alternative in old_all
                ):
                    errors.append(f"{path}.allOf[{index}]: replacement added an uncovered restriction")

    for keyword in ("items", "contains", "propertyNames"):
        if keyword in new and keyword not in old:
            errors.append(f"{path}.{keyword}: replacement added a schema restriction")
        elif keyword in old and keyword in new:
            errors.extend(schema_compatibility_errors(old[keyword], new[keyword], path=f"{path}.{keyword}"))

    old_prefix = old.get("prefixItems")
    new_prefix = new.get("prefixItems")
    if new_prefix is not None and old_prefix is None:
        errors.append(f"{path}.prefixItems: replacement added tuple restrictions")
    elif old_prefix is not None and new_prefix is not None:
        if not isinstance(old_prefix, list) or not isinstance(new_prefix, list):
            errors.append(f"{path}.prefixItems: declarations must be lists")
        elif len(new_prefix) > len(old_prefix):
            errors.append(f"{path}.prefixItems: replacement added tuple positions")
        else:
            for index, new_item in enumerate(new_prefix):
                errors.extend(
                    schema_compatibility_errors(old_prefix[index], new_item, path=f"{path}.prefixItems[{index}]")
                )

    if not isinstance(old_additional, (bool, dict)) or not isinstance(new_additional, (bool, dict)):
        errors.append(f"{path}.additionalProperties: declarations must be booleans or objects")
    elif old_additional is True and not (new_additional is True or new_additional == {}):
        errors.append(f"{path}.additionalProperties: replacement restricted predecessor extension fields")
    elif isinstance(old_additional, dict) and isinstance(new_additional, dict):
        errors.extend(
            schema_compatibility_errors(
                old_additional,
                new_additional,
                path=f"{path}.additionalProperties",
            )
        )
    elif isinstance(old_additional, dict) and new_additional is False:
        errors.append(f"{path}.additionalProperties: replacement forbids predecessor extension fields")

    for keyword in LOWER_BOUNDS:
        if keyword in new and keyword not in old:
            errors.append(f"{path}.{keyword}: replacement added a lower bound")
        elif keyword in old and keyword in new:
            try:
                if Decimal(str(new[keyword])) > Decimal(str(old[keyword])):
                    errors.append(f"{path}.{keyword}: replacement tightened the lower bound")
            except InvalidOperation:
                errors.append(f"{path}.{keyword}: bound is not numeric")
    for keyword in UPPER_BOUNDS:
        if keyword in new and keyword not in old:
            errors.append(f"{path}.{keyword}: replacement added an upper bound")
        elif keyword in old and keyword in new:
            try:
                if Decimal(str(new[keyword])) < Decimal(str(old[keyword])):
                    errors.append(f"{path}.{keyword}: replacement tightened the upper bound")
            except InvalidOperation:
                errors.append(f"{path}.{keyword}: bound is not numeric")

    if "multipleOf" in new:
        if "multipleOf" not in old:
            errors.append(f"{path}.multipleOf: replacement added a divisibility restriction")
        else:
            try:
                old_multiple = Decimal(str(old["multipleOf"]))
                new_multiple = Decimal(str(new["multipleOf"]))
                if new_multiple <= 0 or old_multiple % new_multiple != 0:
                    errors.append(f"{path}.multipleOf: replacement rejects predecessor multiples")
            except (InvalidOperation, ZeroDivisionError):
                errors.append(f"{path}.multipleOf: divisibility declaration is invalid")

    for keyword in EXACT_ASSERTIONS:
        if keyword in new and (keyword not in old or canonical(new[keyword]) != canonical(old[keyword])):
            errors.append(f"{path}.{keyword}: replacement added or changed an exact assertion")
    if new.get("uniqueItems") is True and old.get("uniqueItems") is not True:
        errors.append(f"{path}.uniqueItems: replacement now rejects duplicate items")
    if "not" in new and ("not" not in old or canonical(new["not"]) != canonical(old["not"])):
        errors.append(f"{path}.not: replacement added or changed a negative assertion")

    old_dependencies = old.get("dependentRequired", {})
    new_dependencies = new.get("dependentRequired", {})
    if not isinstance(old_dependencies, dict) or not isinstance(new_dependencies, dict):
        errors.append(f"{path}.dependentRequired: declarations must be objects")
    else:
        for name, new_dependency in new_dependencies.items():
            old_dependency = old_dependencies.get(name)
            if not isinstance(new_dependency, list) or not isinstance(old_dependency, list):
                errors.append(f"{path}.dependentRequired.{name}: replacement added an unsupported dependency")
            elif not set(new_dependency) <= set(old_dependency):
                errors.append(f"{path}.dependentRequired.{name}: replacement added required peers")

    known = ANNOTATION_KEYWORDS | HANDLED_KEYWORDS
    for keyword in sorted((set(new) | set(old)) - known):
        if keyword not in old:
            errors.append(f"{path}.{keyword}: replacement added an unverified constraint")
        elif keyword in new and canonical(new[keyword]) != canonical(old[keyword]):
            errors.append(f"{path}.{keyword}: unverified constraint changed")
    return errors


new_tools = registry_tools(new_path, expected_tool_count=expected_count)
new_by_name = {item["name"]: item for item in new_tools}
new_names = sorted(new_by_name)
if len(new_names) != expected_count:
    raise SystemExit(
        f"replacement MCP tool surface is not the exact expected {expected_count}-tool registry"
    )
if not expected_additions.issubset(new_names):
    raise SystemExit("replacement MCP is missing one or more neuro/teaching tools")

previous_count = 0
additions = []
changed_compatible_contracts: list[str] = []
incompatible_contracts: list[dict[str, Any]] = []
removed: list[str] = []
if predecessor_captured:
    previous_tools = registry_tools(previous_path)
    previous_by_name = {item["name"]: item for item in previous_tools}
    previous_names = sorted(previous_by_name)
    previous_count = len(previous_tools)
    removed = sorted(set(previous_by_name) - set(new_by_name))
    if removed:
        raise SystemExit("replacement MCP removed predecessor tools: " + ",".join(removed))
    additions = sorted(set(new_by_name) - set(previous_by_name))
    if len(previous_names) == 244 and expected_additions.isdisjoint(previous_names):
        if set(additions) != expected_additions:
            raise SystemExit("244-tool predecessor did not receive exactly the six approved additions")
    for name in previous_names:
        old = previous_by_name[name]
        new = new_by_name[name]
        errors: list[str] = []
        old_capabilities = set(old["capabilities"])
        new_capabilities = set(new["capabilities"])
        if not old_capabilities <= new_capabilities:
            errors.append(f"capabilities removed: {sorted(old_capabilities - new_capabilities)}")
        if canonical(old["effect"]) != canonical(new["effect"]):
            errors.append("effect changed")
        if canonical(old["annotations"]) != canonical(new["annotations"]):
            errors.append("annotations changed")
        if canonical(old["description"]) != canonical(new["description"]):
            errors.append("description changed")
        errors.extend(
            schema_compatibility_errors(
                old["parameters"],
                new["parameters"],
                path="parameters",
                allow_input_enum_widening=True,
            )
        )
        # Existing callers must remain valid inputs to the replacement, while
        # every replacement output must remain consumable by predecessor
        # clients.  The output compatibility direction is therefore reversed.
        errors.extend(
            schema_compatibility_errors(
                new["outputSchema"],
                old["outputSchema"],
                path="outputSchema(replacement-to-predecessor)",
                allow_input_enum_widening=False,
            )
        )
        if errors:
            incompatible_contracts.append({"name": name, "errors": errors[:64]})
            continue
        changed_fields = [
            field
            for field in (
                "annotations",
                "capabilities",
                "description",
                "effect",
                "outputSchema",
                "parameters",
            )
            if canonical(old.get(field)) != canonical(new.get(field))
        ]
        if changed_fields or old.get("contractSha256") != new.get("contractSha256"):
            changed_compatible_contracts.append(name)
    if incompatible_contracts:
        raise SystemExit(
            "replacement MCP has backward-incompatible predecessor contracts: "
            + canonical(incompatible_contracts)
        )

print(
    json.dumps(
        {
            "expectedToolCount": expected_count,
            "newToolCount": len(new_names),
            "predecessorCaptured": predecessor_captured,
            "predecessorToolCount": previous_count,
            "predecessorToolsRemoved": removed,
            "predecessorToolsRemovedCount": len(removed),
            "changedCompatibleContracts": changed_compatible_contracts,
            "incompatibleContracts": incompatible_contracts,
            "incompatibleContractCount": len(incompatible_contracts),
            "semanticCompatibilityVerified": predecessor_captured,
            "additions": additions,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
)
PY

INSTALL_STAGE="verify_isolated_neuro_runtime_canary"
docker exec -i \
  -e SOVEREIGN_EXPECTED_CANARY_REVISION="$EXPECTED_REVISION" \
  sovereign-chatgpt-mcp python - <<'PY'
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile


temporary_root = None
workspace_temporary_root = None
with tempfile.TemporaryDirectory(
    prefix="sovereign-neuro-deployment-canary-",
    dir="/var/lib/sovereign-tool-routing",
) as temporary_directory:
    temporary_root = Path(temporary_directory)
    isolated_state = temporary_root / "state"
    isolated_ranking_state = temporary_root / "tool-ranking"
    os.environ["SOVEREIGN_NEURO_RUNTIME_STATE_ROOT"] = str(isolated_state)
    os.environ["SOVEREIGN_TOOL_RANKING_STATE_ROOT"] = str(isolated_ranking_state)
    # The canary explicitly commits one source event below.  Disable only the
    # advisory outcome-to-neuro projection in this one-off process so wrapper
    # telemetry cannot manufacture additional canonical source events.
    os.environ["SOVEREIGN_NEURO_RUNTIME_TRACKING_ENABLED"] = "0"

    import launcher
    import neuro_teaching_tools
    from neuromorphic_runtime import ChangeEvent, ZERO_SHA256
    from policy import validate_workspace_id

    tracking_contract = launcher.TOOL_SUCCESS_TRACKING
    assert tracking_contract["telemetryScope"] == "mutable-tool-outcomes-only", tracking_contract
    assert tracking_contract["readOnlyCallsPersisted"] is False, tracking_contract

    expected_revision = os.environ["SOVEREIGN_EXPECTED_CANARY_REVISION"]
    assert os.environ.get("SOVEREIGN_SOURCE_REVISION") == expected_revision
    policy_path = Path(neuro_teaching_tools.__file__).resolve().parent / "config" / "sovereign-continuity-policy.json"
    embedded_policy_sha256 = hashlib.sha256(policy_path.read_bytes()).hexdigest()
    assert os.environ.get("SOVEREIGN_NEURO_POLICY_SHA256") == embedded_policy_sha256

    # Invoke all five new tools through the registered FastMCP ToolManager so
    # Pydantic arguments/results, the operating-profile gate and success
    # tracking stay in the exercised path.  Only the expected routed target is
    # replaced with a fail-closed guard; previews must never execute it.
    tool_manager = launcher.mcp._tool_manager
    canary_tool_names = {
        "neuro_event_commit",
        "neuro_event_route_preview",
        "neuro_runtime_contract_status",
        "teaching_lesson_simulate",
        "teaching_package_assess",
    }
    read_only_canary_tool_names = canary_tool_names - {"neuro_event_commit"}
    for canary_tool_name in canary_tool_names:
        registered_canary_tool = tool_manager.get_tool(canary_tool_name)
        assert registered_canary_tool is not None, canary_tool_name
        assert registered_canary_tool.output_schema, canary_tool_name
        assert registered_canary_tool.fn_metadata.output_model is not None, canary_tool_name
    for read_only_canary_tool_name in read_only_canary_tool_names:
        read_only_canary_tool = tool_manager.get_tool(read_only_canary_tool_name)
        assert not getattr(read_only_canary_tool.fn, "__sovereign_success_tracking__", False)
        assert not getattr(read_only_canary_tool.fn, "__sovereign_operating_profile_wrapped__", False)
    commit_tool = tool_manager.get_tool("neuro_event_commit")
    assert getattr(commit_tool.fn, "__sovereign_success_tracking__", False)
    assert getattr(commit_tool.fn, "__sovereign_operating_profile_wrapped__", False)

    registered_tools = list(launcher.mcp._tool_manager.list_tools())
    assert len({tool.name for tool in registered_tools}) == 250

    def call_registered(tool_name: str, arguments: dict[str, object]):
        return asyncio.run(tool_manager.call_tool(tool_name, arguments, convert_result=False))

    empty_status = call_registered("neuro_runtime_contract_status", {})
    assert empty_status.ok is True, empty_status
    assert empty_status.status == "NEURO_RUNTIME_CONTRACT_READY", empty_status
    assert empty_status.evidence["toolCount"] == 250, empty_status
    assert empty_status.data["stateInitializedByThisCall"] is False, empty_status
    assert not isolated_state.exists(), "read-only status initialized isolated state"
    continuity_binding = call_registered("sovereign_continuity_context_read", {})
    assert continuity_binding.ok is True, continuity_binding
    assert continuity_binding.status == "CONTINUITY_CONTEXT_BOUND", continuity_binding

    # Continuity is now bound.  Guard every one of the 244 predecessor tools
    # for the remainder of the canary while leaving only the five additive
    # Neuro/Teacher wrapper chains callable.
    guarded_tool_calls: list[str] = []
    guarded_tool_names: list[str] = []
    for registered_tool in registered_tools:
        tool_name = registered_tool.name
        if tool_name in canary_tool_names:
            continue

        def forbidden_selected_tool_call(*_args, _tool_name=tool_name, **_kwargs):
            guarded_tool_calls.append(_tool_name)
            raise AssertionError(f"canary executed guarded predecessor tool: {_tool_name}")

        registered_tool.fn = forbidden_selected_tool_call
        guarded_tool_names.append(tool_name)
    assert len(set(guarded_tool_names)) == 245, len(set(guarded_tool_names))

    now = datetime.now(timezone.utc)
    now = now.replace(microsecond=(now.microsecond // 1000) * 1000)
    event = ChangeEvent.create(
        event_id="event.neuro-deployment-canary",
        system_id="sovereign-studio-ato",
        revision_sha=expected_revision,
        policy_sha256=embedded_policy_sha256,
        lane="deterministic-verification",
        tick=0,
        sequence=0,
        event_time=now,
        delta_ms=0,
        kind="runtime.change",
        source="runtime.deployment-canary",
        entity="mcp.registry",
        field="tool-surface",
        old_hash=ZERO_SHA256,
        new_hash="1" * 64,
        magnitude=1,
        previous_evidence_sha256=ZERO_SHA256,
        causal_parent_sha256=ZERO_SHA256,
        producer_identity="sovereign.deployment-canary",
        canonical=True,
        payload={"units": 1, "max_units": 2, "scope": "mcp-runtime"},
    )
    preview_arguments = {
        "change_event": event.to_dict(),
        "request_id": "request.neuro-deployment-canary",
        "session_id": "session.neuro-deployment-canary",
        "mission_summary": "Read MCP runtime status.",
        "required_capabilities": ["runtime"],
        "allowed_effects": ["read"],
        "relevance_threshold": 1,
        "max_tools": 3,
    }

    quarantined = call_registered(
        "neuro_event_route_preview",
        {"foundation_event_kind": "unknown_canary_kind", **preview_arguments},
    )
    assert quarantined.ok is False, quarantined
    assert quarantined.status == "NEURO_EVENT_QUARANTINED", quarantined
    assert quarantined.mutationPerformed is False, quarantined
    assert quarantined.data["previewArtifact"]["proposal"]["selectedToolContracts"] == [], quarantined
    assert quarantined.data["previewArtifact"]["proposal"]["mayExecute"] is False, quarantined
    assert not isolated_state.exists(), "quarantine initialized isolated state"

    preview = call_registered(
        "neuro_event_route_preview",
        {"foundation_event_kind": "work_request", **preview_arguments},
    )
    assert preview.ok is True, preview
    assert preview.status == "NEURO_EVENT_CANDIDATE", preview
    artifact = preview.data["previewArtifact"]
    selected_contracts = artifact["proposal"]["selectedToolContracts"]
    assert artifact["route"]["routeComplete"] is True, artifact
    assert selected_contracts, artifact
    assert [contract["name"] for contract in selected_contracts] == ["mcp_self_update_status"], selected_contracts
    assert all(contract["effect"] == "read" for contract in selected_contracts), selected_contracts
    assert artifact["proposal"]["proposalOnly"] is True, artifact
    assert artifact["proposal"]["mayExecute"] is False, artifact
    assert artifact["proposal"]["autoExecute"] is False, artifact
    assert artifact["proposal"]["externalEffects"] == [], artifact
    assert guarded_tool_calls == [], guarded_tool_calls

    workspace_parent = Path(os.environ["SOVEREIGN_MCP_WORKSPACE_ROOT"])
    workspace_context = None
    for _workspace_attempt in range(32):
        candidate_context = tempfile.TemporaryDirectory(
            prefix="neurocanary-",
            dir=workspace_parent,
        )
        try:
            validate_workspace_id(Path(candidate_context.name).name)
        except ValueError:
            candidate_context.cleanup()
            continue
        workspace_context = candidate_context
        break
    assert workspace_context is not None, "could not allocate a valid bounded workspace id"
    with workspace_context as workspace_temporary_directory:
        workspace_temporary_root = Path(workspace_temporary_directory)
        workspace_id = workspace_temporary_root.name
        repository = workspace_temporary_root / "repo"
        (repository / ".git").mkdir(parents=True)
        excerpt = "Runtime inspection is read-only evidence collection."
        source_path = repository / "docs" / "runtime.md"
        source_path.parent.mkdir(parents=True)
        source_bytes = (
            "# Runtime evidence\n\n"
            f"{excerpt}\n"
            "This bounded source is used only by the deployment teaching canary.\n"
        ).encode("utf-8")
        source_path.write_bytes(source_bytes)
        source_sha256 = hashlib.sha256(source_bytes).hexdigest()
        source_mtime_ns = source_path.stat().st_mtime_ns
        teaching_package = {
            "schema_version": "1.0",
            "package": {
                "id": "runtime-evidence-canary",
                "title": "Runtime evidence canary lesson",
                "version": "1.0.0",
                "created_at": "2026-08-14T00:00:00Z",
                "language": "en",
                "scope": "read-only runtime evidence",
                "source_profile_ref": "source-local",
                "limitations": ["no tool execution", "no package mutation"],
            },
            "provenance": [
                {
                    "id": "prov-runtime",
                    "source_type": "files",
                    "locator": "docs/runtime.md",
                    "retrieved_at": "2026-08-14T00:00:00Z",
                    "content_hash": source_sha256,
                    "trust_level": "repository",
                    "license_or_policy": "repository-owner-policy",
                }
            ],
            "evidence": [
                {
                    "id": "ev-runtime",
                    "provenance_ref": "prov-runtime",
                    "locator": "docs/runtime.md#L3",
                    "excerpt": excerpt,
                    "content_hash": hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
                    "classification": "internal",
                }
            ],
            "knowledge_units": [
                {
                    "id": "ku-runtime",
                    "claim": "Inspect runtime evidence before drawing a conclusion.",
                    "explanation": "The registered read-only contract returns bounded evidence.",
                    "scope": "runtime inspection",
                    "assumptions": ["live registry available"],
                    "evidence_refs": ["ev-runtime"],
                    "confidence": "high",
                }
            ],
            "skills": [
                {
                    "id": "skill-runtime",
                    "title": "Runtime evidence canary lesson",
                    "outcome": "A bounded runtime evidence report.",
                    "knowledge_refs": ["ku-runtime"],
                    "preconditions": ["live registry is available"],
                    "inputs_schema": {
                        "type": "object",
                        "properties": {"scope": {"type": "string"}},
                        "required": ["scope"],
                        "additionalProperties": False,
                    },
                    "steps": [
                        {
                            "id": "inspect",
                            "action": "Inspect runtime health evidence",
                            "why": "Runtime truth requires readback.",
                            "tool_ref": selected_contracts[0],
                        }
                    ],
                    "verification": {
                        "success_conditions": ["evidence is bounded"],
                        "failure_signals": ["registry drift"],
                        "fallback": "stop and reassess",
                    },
                    "safety_boundaries": ["read-only", "no automatic execution"],
                }
            ],
            "assessments": [
                {
                    "id": "assess-runtime",
                    "skill_or_knowledge_ref": "skill-runtime",
                    "type": "dry_run",
                    "prompt": "Explain the evidence boundary.",
                    "rubric": ["names the live contract"],
                }
            ],
            "target_adapters": [
                {
                    "id": "adapter-mcp",
                    "target_kind": "mcp",
                    "format": "lesson",
                    "mapping": {"skill": "tool"},
                    "write_mode": "read_only",
                    "approval_required": False,
                }
            ],
        }
        package_path = repository / "teaching" / "knowledge-package.json"
        package_path.parent.mkdir(parents=True)
        package_bytes = json.dumps(
            teaching_package,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        package_path.write_bytes(package_bytes)
        package_sha256 = hashlib.sha256(package_bytes).hexdigest()
        package_mtime_ns = package_path.stat().st_mtime_ns

        def repository_file_tree() -> dict[str, dict[str, object]]:
            return {
                str(path.relative_to(repository)): {
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "size": path.stat().st_size,
                    "mtimeNs": path.stat().st_mtime_ns,
                }
                for path in sorted(repository.rglob("*"))
                if path.is_file()
            }

        repository_tree_before = repository_file_tree()
        assert repository_tree_before["docs/runtime.md"]["sha256"] == source_sha256
        assert repository_tree_before["teaching/knowledge-package.json"]["sha256"] == package_sha256

        assessment = call_registered(
            "teaching_package_assess",
            {
                "workspace_id": workspace_id,
                "relative_path": "teaching/knowledge-package.json",
                "expected_sha256": package_sha256,
            },
        )
        assert assessment.ok is True, assessment
        assert assessment.status == "TEACHING_PACKAGE_ASSESSED", assessment
        assert assessment.mutationPerformed is False, assessment
        assert assessment.evidence["packageWritten"] is False, assessment
        assert assessment.evidence["externalEffectPerformed"] is False, assessment
        assessment_receipt = assessment.data["assessmentReceipt"]
        assert assessment_receipt["mutationPerformed"] is False, assessment_receipt
        assert assessment_receipt["externalEffects"] == [], assessment_receipt

        lesson = call_registered(
            "teaching_lesson_simulate",
            {
                "workspace_id": workspace_id,
                "relative_path": "teaching/knowledge-package.json",
                "package_sha256": package_sha256,
                "assessment_receipt": assessment_receipt,
                "skill_id": "skill-runtime",
                "exercise_inputs": {"scope": "mcp-runtime"},
                "max_output_chars": 4000,
            },
        )
        assert lesson.ok is True, lesson
        assert lesson.status == "TEACHING_LESSON_SIMULATED", lesson
        assert lesson.mutationPerformed is False, lesson
        assert lesson.evidence["packageWritten"] is False, lesson
        assert lesson.evidence["toolExecuted"] is False, lesson
        assert lesson.evidence["externalEffectPerformed"] is False, lesson
        assert lesson.data["proposalOnly"] is True, lesson
        assert lesson.data["mayExecute"] is False, lesson
        assert lesson.data["autoExecute"] is False, lesson
        assert package_path.read_bytes() == package_bytes, "teacher tools changed package bytes"
        assert package_path.stat().st_mtime_ns == package_mtime_ns, "teacher tools touched package metadata"
        assert source_path.read_bytes() == source_bytes, "teacher tools changed provenance source bytes"
        assert source_path.stat().st_mtime_ns == source_mtime_ns, "teacher tools touched provenance source metadata"
        repository_tree_after = repository_file_tree()
        assert repository_tree_after == repository_tree_before, "teacher tools changed repository tree"
        assert guarded_tool_calls == [], guarded_tool_calls

    assert workspace_temporary_root is not None and not workspace_temporary_root.exists()

    committed = call_registered(
        "neuro_event_commit",
        {
            "preview_artifact": artifact,
            "preview_sha256": artifact["previewSha256"],
            "expected_head_sha256": ZERO_SHA256,
            "expected_sequence": 0,
        },
    )
    assert committed.ok is True, committed
    assert committed.status == "NEURO_EVENT_COMMITTED", committed
    assert committed.mutationPerformed is True, committed
    assert committed.evidence["sourceChainVerified"] is True, committed
    assert committed.evidence["foundationChainVerified"] is True, committed
    assert committed.evidence["crossLedgerCommitComplete"] is True, committed
    assert committed.evidence["externalEffectPerformed"] is False, committed
    assert committed.data["proposalOnly"] is True, committed
    assert committed.data["mayExecute"] is False, committed
    assert guarded_tool_calls == [], guarded_tool_calls

    replay = call_registered(
        "neuro_event_commit",
        {
            "preview_artifact": artifact,
            "preview_sha256": artifact["previewSha256"],
            "expected_head_sha256": ZERO_SHA256,
            "expected_sequence": 0,
        },
    )
    assert replay.ok is True, replay
    assert replay.status == "NEURO_EVENT_ALREADY_COMMITTED", replay
    assert replay.mutationPerformed is False, replay
    assert replay.evidence["receiptHash"] == committed.evidence["receiptHash"], replay

    tampered_preview = json.loads(json.dumps(artifact))
    tampered_preview["request"]["missionSummary"] = "Tampered mission."
    rejected_tamper = call_registered(
        "neuro_event_commit",
        {
            "preview_artifact": tampered_preview,
            "preview_sha256": artifact["previewSha256"],
            "expected_head_sha256": ZERO_SHA256,
            "expected_sequence": 0,
        },
    )
    assert rejected_tamper.ok is False, rejected_tamper
    assert rejected_tamper.status == "NEURO_EVENT_COMMIT_REJECTED", rejected_tamper
    assert rejected_tamper.mutationPerformed is False, rejected_tamper

    readback = call_registered("neuro_runtime_contract_status", {})
    assert readback.ok is True, readback
    assert readback.data["ledger"]["eventCount"] == 1, readback
    assert readback.data["ledger"]["integrityVerified"] is True, readback
    assert readback.data["foundationLedger"]["entryCount"] == 1, readback
    assert readback.data["foundationLedger"]["integrityVerified"] is True, readback
    assert readback.data["admissions"]["pending"] == 0, readback
    assert readback.data["admissions"]["complete"] == 1, readback
    assert readback.data["admissions"]["integrityVerified"] is True, readback

    ledger_path = isolated_state / "neuromorphic-runtime.sqlite3"
    with sqlite3.connect(ledger_path) as connection:
        cursor = connection.execute("UPDATE projections SET value_hash = ?", ("f" * 64,))
        assert cursor.rowcount == 1
        connection.commit()
    tamper_readback = call_registered("neuro_runtime_contract_status", {})
    assert tamper_readback.ok is False, tamper_readback
    assert tamper_readback.status == "NEURO_RUNTIME_CONTRACT_DEGRADED", tamper_readback
    assert tamper_readback.data["ledger"]["integrityVerified"] is False, tamper_readback
    assert tamper_readback.data["ledger"]["failureFamily"] == "ChainIntegrityError", tamper_readback
    assert guarded_tool_calls == [], guarded_tool_calls
    tracking_events = [
        json.loads(line)
        for line in (isolated_ranking_state / "tool-events.jsonl").read_text("utf-8").splitlines()
        if line.strip()
    ]
    tracked_canary_tools = {event.get("tool") for event in tracking_events}
    assert tracked_canary_tools == {"neuro_event_commit"}, tracked_canary_tools
    assert "mcp_self_update_status" not in tracked_canary_tools, tracked_canary_tools
    persisted_outcome_tools = sorted(tracked_canary_tools)

assert temporary_root is not None and not temporary_root.exists(), "isolated canary state was not cleaned"
print(
    json.dumps(
        {
            "status": "NEURO_DEPLOYMENT_CANARY_VERIFIED",
            "registryToolCount": 250,
            "guardedPredecessorToolCount": 245,
            "quarantineNoMutation": True,
            "previewProposalOnly": True,
            "selectedToolsExecuted": False,
            "commitReplayVerified": True,
            "tamperDetected": True,
            "canonicalReadbackVerified": True,
            "registeredToolSurfaceVerified": True,
            "teacherAssessmentVerified": True,
            "teacherLessonSimulationVerified": True,
            "teachingSourceProvenanceVerified": True,
            "teachingPackageUnchanged": True,
            "telemetryScope": "mutable-tool-outcomes-only",
            "readOnlyCallsPersisted": False,
            "persistedOutcomeTools": persisted_outcome_tools,
            "isolatedStateCleaned": True,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
)
PY

INSTALL_STAGE="verify_operating_profile_canaries"
docker exec -i sovereign-chatgpt-mcp python - <<'PY'
import json

import continuity
import launcher
import operating_profile

continuity_read = continuity.sovereign_continuity_context_read()
assert continuity_read.ok is True, continuity_read
assert continuity_read.status == "CONTINUITY_CONTEXT_BOUND", continuity_read
status = operating_profile.sovereign_operating_profile_status()
assert status.ok is True, status
assert status.status == "OPERATING_PROFILE_ENFORCED", status
assert status.enforcedToolCount == status.mutableToolCount, status
preflight = operating_profile.sovereign_mission_preflight(
    mission_summary="Inspect and verify the live MCP operating-profile contract.",
    required_capabilities=["mcp"],
    allowed_effects=["read"],
    required_evidence=["profile digest", "registry snapshot", "output schemas"],
    max_nodes=4,
)
assert preflight.ok is True, preflight
assert preflight.status == "MISSION_PREFLIGHT_VALID", preflight
merge_tool = next(
    tool
    for tool in launcher.mcp._tool_manager.list_tools()
    if tool.name == "repository_merge_pr"
)
blocked = None
try:
    merge_tool.fn(
        pr_number=1,
        expected_head_sha="a" * 40,
        merge_method="squash",
        self_update_after_merge=True,
        owner_approved=False,
        mark_ready_if_draft=False,
        allow_unrelated_android_pending=False,
    )
except operating_profile.OperatingProfileBlocked as exc:
    blocked = json.loads(str(exc))
assert blocked is not None, "mutation unexpectedly reached the broker boundary"
assert blocked["status"] == "MUTATION_BLOCKED_BY_OPERATING_PROFILE", blocked
assert blocked["failureFamily"] == "OPERATING_PROFILE_OWNER_APPROVAL_REQUIRED", blocked
assert blocked["mutationPerformed"] is False, blocked
series_tool = next(
    tool
    for tool in launcher.mcp._tool_manager.list_tools()
    if tool.name == "repository_merge_pr_series"
)
series_blocked = None
try:
    series_tool.fn(
        pull_requests=[{"pr_number": 1, "expected_head_sha": "a" * 40}],
        merge_method="squash",
        owner_approved=False,
        mark_ready_if_draft=True,
        allow_unrelated_android_pending=False,
        wait_seconds_per_pr=30,
        poll_seconds=2,
    )
except operating_profile.OperatingProfileBlocked as exc:
    series_blocked = json.loads(str(exc))
assert series_blocked is not None, "series mutation unexpectedly reached the broker boundary"
assert series_blocked["failureFamily"] == "OPERATING_PROFILE_OWNER_APPROVAL_REQUIRED", series_blocked
assert series_blocked["mutationPerformed"] is False, series_blocked
print(
    json.dumps(
        {
            "continuity": continuity_read.status,
            "continuityPolicySha256": continuity_read.policySha256,
            "continuityContextSha256": continuity_read.contextSha256,
            "continuityLedgerSha256": continuity_read.ledgerSha256,
            "operatingProfile": status.status,
            "profileSha256": status.profileSha256,
            "registrySnapshotSha256": status.registrySnapshotSha256,
            "mutableToolCount": status.mutableToolCount,
            "enforcedToolCount": status.enforcedToolCount,
            "missionPreflight": preflight.status,
            "negativeMutationCanary": blocked["failureFamily"],
            "secretValuesReturned": False,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
)
PY

INSTALL_STAGE="verify_host_worker_canary"
docker exec sovereign-chatgpt-mcp python -c 'import server; worker=server.broker.call("host_worker_canary", {}, timeout=10); assert worker.get("status") == "HOST_WORKER_READY", worker; assert worker.get("execution_origin") == "host_worker", worker'

INSTALL_STAGE="verify_mcp_protocol_handshake"
docker exec sovereign-chatgpt-mcp python /app/mcp_protocol_health.py --url http://127.0.0.1:8090/mcp --timeout-seconds 5

INSTALL_STAGE="verify_android_native_boundary"
docker exec sovereign-chatgpt-mcp python -c 'import os; assert os.getenv("SOVEREIGN_ANDROID_NATIVE_BUILD_MODE", "github_actions") == "github_actions"'

INSTALL_STAGE="verify_workspace_write_boundary"
docker exec sovereign-chatgpt-mcp python -c 'from pathlib import Path; root=Path("/opt/sovereign-chatgpt-tools/workspaces"); probe=root/".permission-probe"; probe.write_text("ok", encoding="utf-8"); probe.unlink()'

INSTALL_STAGE="verify_tunnel_configuration"
TUNNEL_CONFIGURED=0
if [[ "$TUNNEL_MODE" == "disabled" ]]; then
  printf 'Tunnel checks skipped for the tunnel-independent MCP profile.\n'
elif [[ -f "$TUNNEL_ENV" ]] \
  && grep -Eq '^OPENAI_TUNNEL_ID=tunnel_.+' "$TUNNEL_ENV" \
  && grep -Eq '^CONTROL_PLANE_API_KEY=.+$' "$TUNNEL_ENV"; then
  TUNNEL_CONFIGURED=1
elif [[ "$REQUIRE_TUNNEL" == "1" || "$TUNNEL_MODE" == "required" ]]; then
  fail "the selected MCP profile requires a valid tunnel.env with OPENAI_TUNNEL_ID and CONTROL_PLANE_API_KEY"
fi

INSTALL_STAGE="verify_tunnel"
if [[ "$TUNNEL_CONFIGURED" == "1" ]]; then
  "$BIN_DIR/install-secure-tunnel"
  systemctl is-active --quiet sovereign-openai-tunnel.service \
    || fail "tunnel installer returned without an active service"
  sleep 11
  MALFORMED_MCP_REQUESTS="$(docker logs --since 20s sovereign-chatgpt-mcp 2>&1 \
    | grep -Ec 'POST /mcp HTTP/1\.1" 400 Bad Request' || true)"
  SUCCESSFUL_MCP_REQUESTS="$(docker logs --since 20s sovereign-chatgpt-mcp 2>&1 \
    | grep -Ec 'POST /mcp HTTP/1\.1" (200 OK|202 Accepted)' || true)"
  [[ "$MALFORMED_MCP_REQUESTS" =~ ^[0-9]+$ ]] || fail "could not count malformed MCP requests"
  [[ "$SUCCESSFUL_MCP_REQUESTS" =~ ^[0-9]+$ ]] || fail "could not count successful MCP requests"
  if (( MALFORMED_MCP_REQUESTS >= 2 && SUCCESSFUL_MCP_REQUESTS == 0 )); then
    docker logs --since 20s sovereign-chatgpt-mcp 2>&1 | tail -n 80 >&2 || true
    fail "repeated malformed MCP requests detected after tunnel start"
  fi
else
  printf 'Tunnel not installed: configure %s before using the ChatGPT app connection.\n' "$TUNNEL_ENV"
fi
unset TUNNEL_CONFIGURED

INSTALL_STAGE="enable_coordinated_release_reconciler"
systemctl enable --now sovereign-release-reconciler.timer
systemctl is-enabled --quiet sovereign-release-reconciler.timer \
  || fail "coordinated release reconciler timer is not enabled"
systemctl is-active --quiet sovereign-release-reconciler.timer \
  || fail "coordinated release reconciler timer is not active"

if [[ "$PREVIOUS_MCP_CONTAINER_PRESENT" == "1" ]]; then
  [[ "$PREVIOUS_MCP_TOOL_SURFACE_CAPTURED" == "1" ]] \
    || fail "predecessor MCP existed but semantic compatibility was not verified"
else
  [[ "$PREVIOUS_MCP_TOOL_SURFACE_CAPTURED" == "0" ]] \
    || fail "first-install state conflicts with predecessor registry evidence"
fi
INSTALL_STAGE="completed"
INSTALL_COMPLETED=1
ROLLBACK_ARMED=0
PREVIOUS_TOOL_SURFACE_COMPARED_JSON=false
[[ "$PREVIOUS_MCP_TOOL_SURFACE_CAPTURED" != "1" ]] || PREVIOUS_TOOL_SURFACE_COMPARED_JSON=true
PREDECESSOR_CONTAINER_PRESENT_JSON=false
SEMANTIC_COMPATIBILITY_VERIFIED_JSON=false
FIRST_INSTALL_WITHOUT_PREDECESSOR_JSON=true
if [[ "$PREVIOUS_MCP_CONTAINER_PRESENT" == "1" ]]; then
  PREDECESSOR_CONTAINER_PRESENT_JSON=true
  SEMANTIC_COMPATIBILITY_VERIFIED_JSON=true
  FIRST_INSTALL_WITHOUT_PREDECESSOR_JSON=false
fi
printf '{"ok":true,"mcp":"http://127.0.0.1:8090/mcp","mcp_protocol_ready":true,"broker":"active","broker_rpc_ready":true,"broker_socket_host_visible":true,"broker_socket_container_visible":true,"host_command_worker_active":true,"inbound_mutation_forbidden":true,"container":"sovereign-chatgpt-mcp","mcp_image":"%s","mcp_revision":"%s","tunnel_mode":"%s","workspace_writable":true,"policy_repair_engine":true,"private_admin_mode_available":true,"self_update_available":false,"android_hardening_available":true,"android_native_build_mode":"github_actions","android_native_validation_router":true,"deterministic_architecture_tools":true,"database_evidence_tools":true,"enterprise_backend_tools":true,"freemium_product_architect_tools":true,"operational_governance_tools":true,"operational_assurance_tools":true,"neuro_runtime_tools":true,"foundation_runtime":true,"teaching_runtime_tools":true,"neuro_functional_canary":true,"neuro_tamper_detection":true,"neuro_selected_tools_executed":false,"registered_tool_surface_canary":true,"teaching_functional_canary":true,"teaching_source_provenance_canary":true,"teaching_package_mutated":false,"tool_outcome_telemetry_scope":"mutable-tool-outcomes-only","read_only_tool_calls_persisted":false,"canary_persisted_outcome_tools":["neuro_event_commit"],"mcp_tool_count":%s,"predecessor_container_present":%s,"predecessor_registry_capture_mode":"%s","previous_tool_surface_compared":%s,"semantic_compatibility_verified":%s,"first_install_without_predecessor":%s,"first_install_attested":%s,"event_delta_projection":"incremental","operating_profile_enforced":true,"continuity_enforced":true,"repository_revision_resolver":true,"kappa_scale":1000000,"cross_runtime_parity_proven":true,"pr_lifecycle_available":false,"workspace_pr_head_sync_available":false,"workflow_dispatch_available":false,"managed_compose_write_available":true,"patchmon_operator_available":true,"managed_compose_stacks":["sovereign-backend","gpt-tools","code-server-46bq","pgbackweb-wq5r","patchmon-sovereign","milvus-sovereign","sovereign-freellmapi","sovereign-freellmpool"]}\n' "$MCP_IMAGE_DIGEST" "$EXPECTED_REVISION" "$TUNNEL_MODE" "$EXPECTED_MCP_TOOL_COUNT" "$PREDECESSOR_CONTAINER_PRESENT_JSON" "$PREVIOUS_MCP_REGISTRY_CAPTURE_MODE" "$PREVIOUS_TOOL_SURFACE_COMPARED_JSON" "$SEMANTIC_COMPATIBILITY_VERIFIED_JSON" "$FIRST_INSTALL_WITHOUT_PREDECESSOR_JSON" "$FIRST_INSTALL_WITHOUT_PREDECESSOR_JSON"
