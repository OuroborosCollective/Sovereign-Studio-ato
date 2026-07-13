#!/usr/bin/env bash
set -Eeuo pipefail

INSTALL_ROOT="/opt/sovereign-chatgpt-tools"
TUNNEL_ENV="${TUNNEL_ENV:-$INSTALL_ROOT/tunnel.env}"
TUNNEL_HOME="/var/lib/sovereign-tunnel"
BINARY="/usr/local/bin/tunnel-client"
TUNNEL_SERVICE="/etc/systemd/system/sovereign-openai-tunnel.service"

fail() {
  printf 'tunnel install blocked: %s\n' "$*" >&2
  exit 1
}

read_value() {
  local key="$1"
  sed -n "s/^${key}=//p" "$TUNNEL_ENV" | tail -n 1
}

run_as_tunnel_user() {
  runuser -u sovereign-tunnel -- env \
    HOME="$TUNNEL_HOME" \
    CONTROL_PLANE_API_KEY="$CONTROL_PLANE_API_KEY" \
    "$@"
}

[[ "${EUID:-$(id -u)}" -eq 0 ]] || fail "run as root"
[[ -f "$TUNNEL_ENV" ]] || fail "missing $TUNNEL_ENV"
chmod 0600 "$TUNNEL_ENV"
chown root:root "$TUNNEL_ENV"

OPENAI_TUNNEL_ID="$(read_value OPENAI_TUNNEL_ID)"
CONTROL_PLANE_API_KEY="$(read_value CONTROL_PLANE_API_KEY)"
TUNNEL_PROFILE="$(read_value TUNNEL_PROFILE)"
TUNNEL_MCP_SERVER_URL="$(read_value TUNNEL_MCP_SERVER_URL)"
TUNNEL_PROFILE="${TUNNEL_PROFILE:-sovereign-chatgpt}"
TUNNEL_MCP_SERVER_URL="${TUNNEL_MCP_SERVER_URL:-http://127.0.0.1:8090/mcp}"

[[ "$OPENAI_TUNNEL_ID" =~ ^tunnel_[A-Za-z0-9_-]+$ ]] || fail "OPENAI_TUNNEL_ID is missing or invalid"
[[ -n "$CONTROL_PLANE_API_KEY" ]] || fail "CONTROL_PLANE_API_KEY is missing"
[[ "$TUNNEL_PROFILE" =~ ^[A-Za-z0-9._-]+$ ]] || fail "TUNNEL_PROFILE is invalid"
[[ "$TUNNEL_MCP_SERVER_URL" == "http://127.0.0.1:8090/mcp" ]] || fail "only the loopback MCP endpoint is permitted"

for command in python3 runuser systemctl sha256sum; do
  command -v "$command" >/dev/null 2>&1 || fail "$command is required"
done
[[ -f "$TUNNEL_SERVICE" ]] || fail "missing $TUNNEL_SERVICE"
grep -q '^ExecStartPre=/usr/bin/python3 /opt/sovereign-chatgpt-tools/mcp_protocol_health.py ' "$TUNNEL_SERVICE" \
  || fail "installed tunnel service does not use the shared MCP protocol checker"
if grep -Eq 'c[u]rl[[:space:]]' "$TUNNEL_SERVICE"; then
  fail "installed tunnel service still contains a curl-based MCP probe"
fi

if [[ ! -x "$BINARY" ]]; then
  TMP_DIR="$(mktemp -d)"
  trap 'rm -rf "$TMP_DIR"' EXIT
  python3 - "$TMP_DIR" <<'PY'
import hashlib
import json
import platform
import stat
import sys
import urllib.request
import zipfile
from pathlib import Path

out = Path(sys.argv[1])
request = urllib.request.Request(
    "https://api.github.com/repos/openai/tunnel-client/releases/latest",
    headers={"Accept": "application/vnd.github+json", "User-Agent": "sovereign-installer"},
)
with urllib.request.urlopen(request, timeout=30) as response:
    release = json.load(response)
assets = release.get("assets") or []
machine = platform.machine().lower()
arch_tokens = ("amd64", "x86_64") if machine in {"x86_64", "amd64"} else ("arm64", "aarch64") if machine in {"aarch64", "arm64"} else ()
if not arch_tokens:
    raise SystemExit(f"unsupported architecture: {machine}")

def pick(predicate):
    return next((asset for asset in assets if predicate(str(asset.get("name") or "").lower())), None)

archive = pick(lambda name: name.endswith(".zip") and "linux" in name and any(token in name for token in arch_tokens) and "source" not in name)
checksums = pick(lambda name: name == "sha256sums.txt")
if not archive or not checksums:
    raise SystemExit("latest tunnel-client release has no supported Linux archive or SHA256SUMS.txt")

for asset in (archive, checksums):
    target = out / asset["name"]
    request = urllib.request.Request(asset["browser_download_url"], headers={"User-Agent": "sovereign-installer"})
    with urllib.request.urlopen(request, timeout=120) as response, target.open("wb") as handle:
        handle.write(response.read())

archive_path = out / archive["name"]
expected = None
for line in (out / checksums["name"]).read_text("utf-8").splitlines():
    parts = line.strip().split()
    if len(parts) >= 2 and parts[-1].lstrip("*") == archive_path.name:
        expected = parts[0].lower()
        break
if not expected:
    raise SystemExit("archive checksum is missing")
if hashlib.sha256(archive_path.read_bytes()).hexdigest() != expected:
    raise SystemExit("tunnel-client checksum mismatch")

extract_dir = out / "extract"
extract_dir.mkdir()
with zipfile.ZipFile(archive_path) as bundle:
    bundle.extractall(extract_dir)
candidates = [path for path in extract_dir.rglob("tunnel-client") if path.is_file()]
if len(candidates) != 1:
    raise SystemExit(f"expected one tunnel-client binary, found {len(candidates)}")
binary = out / "tunnel-client"
binary.write_bytes(candidates[0].read_bytes())
binary.chmod(binary.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
PY
  install -m 0755 "$TMP_DIR/tunnel-client" "$BINARY"
fi

getent passwd sovereign-tunnel >/dev/null 2>&1 || useradd --system --home-dir "$TUNNEL_HOME" --shell /usr/sbin/nologin sovereign-tunnel
usermod --home "$TUNNEL_HOME" sovereign-tunnel
install -d -m 0750 -o sovereign-tunnel -g sovereign-tunnel "$TUNNEL_HOME"

FINGERPRINT="$(printf '%s|%s|%s' "$OPENAI_TUNNEL_ID" "$TUNNEL_PROFILE" "$TUNNEL_MCP_SERVER_URL" | sha256sum | cut -d' ' -f1)"
CURRENT_FINGERPRINT="$(cat "$TUNNEL_HOME/.profile-fingerprint" 2>/dev/null || true)"
if [[ "$CURRENT_FINGERPRINT" != "$FINGERPRINT" ]]; then
  find "$TUNNEL_HOME" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
  install -d -m 0750 -o sovereign-tunnel -g sovereign-tunnel "$TUNNEL_HOME"
  run_as_tunnel_user "$BINARY" init \
    --profile "$TUNNEL_PROFILE" \
    --tunnel-id "$OPENAI_TUNNEL_ID" \
    --mcp-server-url "$TUNNEL_MCP_SERVER_URL"
  printf '%s\n' "$FINGERPRINT" > "$TUNNEL_HOME/.profile-fingerprint"
  chown sovereign-tunnel:sovereign-tunnel "$TUNNEL_HOME/.profile-fingerprint"
  chmod 0600 "$TUNNEL_HOME/.profile-fingerprint"
fi

run_as_tunnel_user "$BINARY" doctor --profile "$TUNNEL_PROFILE" --explain
systemctl daemon-reload
systemctl enable sovereign-openai-tunnel.service
systemctl reset-failed sovereign-openai-tunnel.service || true
systemctl restart sovereign-openai-tunnel.service
TUNNEL_STATE=""
for attempt in $(seq 1 15); do
  TUNNEL_STATE="$(systemctl is-active sovereign-openai-tunnel.service 2>/dev/null || true)"
  [[ "$TUNNEL_STATE" == "active" ]] && break
  [[ "$TUNNEL_STATE" == "failed" ]] && break
  sleep 1
done
if [[ "$TUNNEL_STATE" != "active" ]]; then
  systemctl status sovereign-openai-tunnel.service --no-pager >&2 || true
  journalctl -u sovereign-openai-tunnel.service -n 80 --no-pager >&2 || true
  fail "tunnel service is not active: ${TUNNEL_STATE:-unknown}"
fi

printf '{"ok":true,"tunnel_id":"%s","profile":"%s","mcp_server":"%s","state_dir":"%s"}\n' \
  "$OPENAI_TUNNEL_ID" "$TUNNEL_PROFILE" "$TUNNEL_MCP_SERVER_URL" "$TUNNEL_HOME"
