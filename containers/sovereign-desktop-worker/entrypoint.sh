#!/bin/sh
set -eu

export HOME=/home/desktop
export DISPLAY=${DISPLAY:-:99}
export XDG_RUNTIME_DIR=/run/user/10001
RFB_PORT="${SOVEREIGN_DESKTOP_RFB_PORT:-5900}"
WS_PORT="${SOVEREIGN_DESKTOP_WEBSOCKET_PORT:-6080}"
mkdir -p "$HOME" "$XDG_RUNTIME_DIR" "$HOME/Downloads"
chmod 0700 "$HOME" "$XDG_RUNTIME_DIR"

Xvfb "$DISPLAY" -screen 0 1440x900x24 -nolisten tcp &
openbox-session >/tmp/openbox.log 2>&1 &
xterm -geometry 120x34+20+30 -e sh -lc 'cd /workspace && exec sh' >/tmp/xterm.log 2>&1 &

if command -v code-server >/dev/null 2>&1; then
  code-server --auth none --bind-addr 127.0.0.1:8443 /workspace >/tmp/code-server.log 2>&1 &
fi

if command -v firefox >/dev/null 2>&1; then
  firefox --no-remote --private-window about:blank >/tmp/firefox.log 2>&1 &
elif command -v firefox-esr >/dev/null 2>&1; then
  firefox-esr --no-remote --private-window about:blank >/tmp/firefox.log 2>&1 &
elif command -v epiphany >/dev/null 2>&1; then
  epiphany --incognito about:blank >/tmp/browser.log 2>&1 &
fi

# Raw RFB never leaves loopback. Websockify is the sole worker-network ingress,
# and RFB itself remains server-side view-only so pointer/keyboard authority
# stays on Sovereign's separate takeover lease + /desktop/input path.
x11vnc \
  -display "$DISPLAY" \
  -rfbport "$RFB_PORT" \
  -localhost \
  -forever \
  -shared \
  -viewonly \
  -nopw \
  -noxdamage \
  >/tmp/x11vnc.log 2>&1 &

websockify \
  --heartbeat 20 \
  "0.0.0.0:${WS_PORT}" \
  "127.0.0.1:${RFB_PORT}" \
  >/tmp/websockify.log 2>&1 &

exec python3 /opt/sovereign-desktop-worker/desktop_worker.py
