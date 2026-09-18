#!/usr/bin/env bash
set -Eeuo pipefail

AGENT_ZERO_CONTAINER="agent-zero-xrev-agent-zero-1"
BACKEND_CONTAINER="sovereign-backend"
HOST_WORKSPACE_ROOT="/opt/sovereign-agent-workspaces"
BACKEND_WORKSPACE_ROOT="/var/lib/sovereign-agent/workspaces"
AGENT_ZERO_WORKSPACE_ROOT="/a0/sovereign-workspaces"
OVERRIDE_ROOT="/opt/sovereign-chatgpt-tools/maintenance/agent-zero-workspace-mount"
OVERRIDE_FILE="$OVERRIDE_ROOT/docker-compose.override.yml"
LOCK_FILE="/run/lock/sovereign-agent-zero-workspace-mount.lock"
CANARY_NAME=".sovereign-shared-workspace-canary"

fail() {
  printf 'AGENT_ZERO_SHARED_WORKSPACE_MOUNT_BLOCKED:%s\n' "$1" >&2
  exit 1
}

[[ "$(id -u)" -eq 0 ]] || fail "root_required"
command -v docker >/dev/null 2>&1 || fail "docker_unavailable"
command -v flock >/dev/null 2>&1 || fail "flock_unavailable"

exec 9>"$LOCK_FILE"
flock -n 9 || fail "reconcile_already_running"

docker inspect "$AGENT_ZERO_CONTAINER" >/dev/null 2>&1 || fail "agent_zero_container_missing"
docker inspect "$BACKEND_CONTAINER" >/dev/null 2>&1 || fail "backend_container_missing"

[[ "$(docker inspect -f '{{.State.Running}}' "$BACKEND_CONTAINER")" == "true" ]] || fail "backend_not_running"
[[ "$(docker inspect -f '{{.State.Running}}' "$AGENT_ZERO_CONTAINER")" == "true" ]] || fail "agent_zero_not_running"

install -d -m 0770 -o 10001 -g 10001 "$HOST_WORKSPACE_ROOT"
install -d -m 0700 "$OVERRIDE_ROOT"

mount_present() {
  local container="$1"
  local source="$2"
  local destination="$3"
  docker inspect -f '{{range .Mounts}}{{println .Source "|" .Destination "|" .RW}}{{end}}' "$container" \
    | awk -F'|' -v source="$source" -v destination="$destination" \
        '$1 == source && $2 == destination && $3 == "true" { found=1 } END { exit(found ? 0 : 1) }'
}

mount_present "$BACKEND_CONTAINER" "$HOST_WORKSPACE_ROOT" "$BACKEND_WORKSPACE_ROOT" \
  || fail "backend_shared_workspace_mount_missing"

if ! mount_present "$AGENT_ZERO_CONTAINER" "$HOST_WORKSPACE_ROOT" "$AGENT_ZERO_WORKSPACE_ROOT"; then
  project="$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' "$AGENT_ZERO_CONTAINER")"
  service="$(docker inspect -f '{{index .Config.Labels "com.docker.compose.service"}}' "$AGENT_ZERO_CONTAINER")"
  working_dir="$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' "$AGENT_ZERO_CONTAINER")"
  config_files="$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project.config_files"}}' "$AGENT_ZERO_CONTAINER")"

  [[ "$project" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$ ]] || fail "compose_project_invalid"
  [[ "$service" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$ ]] || fail "compose_service_invalid"
  [[ "$working_dir" == /* && -d "$working_dir" && ! -L "$working_dir" ]] || fail "compose_working_dir_invalid"
  [[ -n "$config_files" ]] || fail "compose_config_files_missing"

  compose_args=(docker compose -p "$project")
  IFS=',' read -r -a raw_configs <<< "$config_files"
  for raw_config in "${raw_configs[@]}"; do
    raw_config="${raw_config#" "${raw_config%%[![:space:]]*}"}"
    raw_config="${raw_config%" "${raw_config##*[![:space:]]}"}"
    [[ -n "$raw_config" ]] || fail "compose_config_file_empty"
    if [[ "$raw_config" == /* ]]; then
      config_path="$raw_config"
    else
      config_path="$working_dir/$raw_config"
    fi
    config_path="$(readlink -f -- "$config_path")"
    [[ -f "$config_path" && ! -L "$config_path" ]] || fail "compose_config_file_invalid"
    compose_args+=(-f "$config_path")
  done

  cat >"$OVERRIDE_FILE" <<YAML
services:
  $service:
    volumes:
      - type: bind
        source: $HOST_WORKSPACE_ROOT
        target: $AGENT_ZERO_WORKSPACE_ROOT
        read_only: false
YAML
  chmod 0600 "$OVERRIDE_FILE"

  compose_args+=(-f "$OVERRIDE_FILE" up -d --no-deps "$service")
  "${compose_args[@]}"

  for _ in $(seq 1 30); do
    [[ "$(docker inspect -f '{{.State.Running}}' "$AGENT_ZERO_CONTAINER" 2>/dev/null || true)" == "true" ]] && break
    sleep 2
  done
fi

[[ "$(docker inspect -f '{{.State.Running}}' "$AGENT_ZERO_CONTAINER")" == "true" ]] || fail "agent_zero_not_running_after_reconcile"
mount_present "$AGENT_ZERO_CONTAINER" "$HOST_WORKSPACE_ROOT" "$AGENT_ZERO_WORKSPACE_ROOT" \
  || fail "agent_zero_shared_workspace_mount_missing_after_reconcile"

CANARY_PATH="$HOST_WORKSPACE_ROOT/$CANARY_NAME"
cleanup() {
  rm -f -- "$CANARY_PATH"
}
trap cleanup EXIT

printf 'sovereign-shared-workspace-canary\n' >"$CANARY_PATH"
chown 10001:10001 "$CANARY_PATH"
chmod 0660 "$CANARY_PATH"

docker exec --user 0 "$BACKEND_CONTAINER" sh -eu -c \
  "test \"\$(cat '$BACKEND_WORKSPACE_ROOT/$CANARY_NAME')\" = sovereign-shared-workspace-canary" \
  || fail "backend_canary_readback_failed"
docker exec --user 0 "$AGENT_ZERO_CONTAINER" sh -eu -c \
  "test \"\$(cat '$AGENT_ZERO_WORKSPACE_ROOT/$CANARY_NAME')\" = sovereign-shared-workspace-canary" \
  || fail "agent_zero_canary_readback_failed"

cleanup
trap - EXIT

docker exec --user 0 "$BACKEND_CONTAINER" test ! -e "$BACKEND_WORKSPACE_ROOT/$CANARY_NAME" \
  || fail "backend_canary_cleanup_unverified"
docker exec --user 0 "$AGENT_ZERO_CONTAINER" test ! -e "$AGENT_ZERO_WORKSPACE_ROOT/$CANARY_NAME" \
  || fail "agent_zero_canary_cleanup_unverified"

printf '%s\n' '{"ok":true,"status":"AGENT_ZERO_SHARED_WORKSPACE_MOUNT_VERIFIED","hostRoot":"/opt/sovereign-agent-workspaces","backendRoot":"/var/lib/sovereign-agent/workspaces","agentZeroRoot":"/a0/sovereign-workspaces","canaryReadbackVerified":true,"cleanupVerified":true,"secretValuesReturned":false}'
