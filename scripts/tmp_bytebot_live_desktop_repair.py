from __future__ import annotations

from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text('utf-8')


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, 'utf-8')


def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    if text.count(old) != 1:
        raise SystemExit(f'anchor mismatch: {path}: {old[:100]!r}: count={text.count(old)}')
    write(path, text.replace(old, new, 1))


def insert_before_once(path: str, marker: str, content: str) -> None:
    text = read(path)
    if text.count(marker) != 1:
        raise SystemExit(f'insert marker mismatch: {path}: count={text.count(marker)}')
    write(path, text.replace(marker, content + marker, 1))


# ── Frontend dependency ───────────────────────────────────────────────────────
package_path = 'package.json'
package = json.loads(read(package_path))
deps = package.setdefault('dependencies', {})
deps['react-vnc'] = '^3.1.0'
# Preserve the repo's compact two-space JSON style while sorting only dependency keys.
package['dependencies'] = dict(sorted(deps.items()))
write(package_path, json.dumps(package, ensure_ascii=False, indent=2) + '\n')

# ── Backend WebSocket dependencies ────────────────────────────────────────────
for requirements_path in ('scripts/sovereign-backend/requirements.txt',):
    text = read(requirements_path)
    for dependency in ('flask-sock==0.7.0', 'websocket-client==1.8.0'):
        if dependency not in text:
            text = text.rstrip() + '\n' + dependency + '\n'
    write(requirements_path, text)

# ── Real RFB/WebSocket desktop worker ─────────────────────────────────────────
dockerfile = 'containers/sovereign-desktop-worker/Dockerfile'
text = read(dockerfile)
if 'ARG SOVEREIGN_SOURCE_REVISION' not in text:
    text = text.replace('FROM ', 'ARG SOVEREIGN_SOURCE_REVISION=unverified\nFROM ', 1)
    # ARG before FROM is global; redeclare it in the stage for LABEL expansion.
    first_newline = text.find('\n', text.find('\n') + 1)
    text = text[: first_newline + 1] + 'ARG SOVEREIGN_SOURCE_REVISION\nLABEL org.opencontainers.image.revision=${SOVEREIGN_SOURCE_REVISION}\n' + text[first_newline + 1 :]
if 'x11vnc' not in text:
    text = text.replace('    xvfb \\\n', '    xvfb \\\n    x11vnc \\\n    websockify \\\n', 1)
text = text.replace('EXPOSE 8765', 'EXPOSE 8765 6080 6081')
# Health means the HTTP control bridge and both VNC websocket listeners exist.
text = re.sub(
    r'HEALTHCHECK[^\n]*\n(?:\s+CMD.*\n)?',
    "HEALTHCHECK --interval=10s --timeout=4s --start-period=8s --retries=3 \\\n  CMD python3 -c \"import socket,urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/health',timeout=2).read(); [socket.create_connection(('127.0.0.1',p),2).close() for p in (6080,6081)]\" || exit 1\n",
    text,
    count=1,
)
write(dockerfile, text)

entrypoint = r'''#!/bin/sh
set -eu

export DISPLAY="${DISPLAY:-:99}"

Xvfb "$DISPLAY" -screen 0 1440x900x24 -nolisten tcp >/tmp/xvfb.log 2>&1 &
sleep 1
openbox-session >/tmp/openbox.log 2>&1 &
xterm -geometry 120x34+24+24 -title "Sovereign Terminal" >/tmp/xterm.log 2>&1 &
code-server --bind-addr 0.0.0.0:13337 --auth none /workspace >/tmp/code-server.log 2>&1 &

if command -v firefox-esr >/dev/null 2>&1; then
  firefox-esr --no-remote --new-instance about:blank >/tmp/browser.log 2>&1 &
elif command -v firefox >/dev/null 2>&1; then
  firefox --no-remote --new-instance about:blank >/tmp/browser.log 2>&1 &
elif command -v epiphany >/dev/null 2>&1; then
  epiphany about:blank >/tmp/browser.log 2>&1 &
fi

# Two physically separate RFB surfaces. The normal monitor can never inject
# input even if a browser client is compromised because x11vnc itself is
# view-only on 5900. The control RFB surface is reachable only through the
# backend lease-gated websocket bridge.
x11vnc -display "$DISPLAY" -localhost -forever -shared -nopw -viewonly -rfbport 5900 -noxdamage >/tmp/x11vnc-view.log 2>&1 &
x11vnc -display "$DISPLAY" -localhost -forever -shared -nopw -rfbport 5901 -noxdamage >/tmp/x11vnc-control.log 2>&1 &
websockify --heartbeat 30 0.0.0.0:6080 127.0.0.1:5900 >/tmp/websockify-view.log 2>&1 &
websockify --heartbeat 30 0.0.0.0:6081 127.0.0.1:5901 >/tmp/websockify-control.log 2>&1 &

exec python3 /opt/sovereign-desktop/desktop_worker.py
'''
write('containers/sovereign-desktop-worker/entrypoint.sh', entrypoint)

# ── Lease-aware WebSocket bridge ──────────────────────────────────────────────
desktop_stream = r'''"""Authenticated RFB websocket bridge for the Sovereign live desktop.

The browser never receives a container hostname, host path, view scope or input
scope.  View mode terminates on a physically read-only x11vnc server.  Control
mode terminates on a separate RFB server and remains open only while the exact
attempt-bound user takeover lease is valid.
"""
from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Any
from urllib.request import Request, urlopen

import websocket

from .desktop_activation import DesktopActivationHandleV1, DesktopActivationIssuerV1
from .desktop_control import DesktopControlGatewayV1
from .desktop_projection import DesktopFrameProxyV1
from .fleet_supervisor import FleetContractError


@dataclass(frozen=True)
class DesktopStreamBindingV1:
    activation_id: str
    session_binding_hash: str
    attempt_id: str
    workspace_id: str
    mode: str


class DesktopStreamGatewayV1:
    def __init__(self, *, issuer: DesktopActivationIssuerV1, control: DesktopControlGatewayV1) -> None:
        self.issuer = issuer
        self.control = control
        self.frame_proxy = DesktopFrameProxyV1(activation_root=issuer.activation_root)

    @classmethod
    def from_env(cls) -> "DesktopStreamGatewayV1":
        issuer = DesktopActivationIssuerV1.from_env()
        return cls(issuer=issuer, control=DesktopControlGatewayV1(issuer=issuer))

    @staticmethod
    def _container_name(handle: DesktopActivationHandleV1) -> str:
        return f"sovereign-desktop-{handle.session_binding_hash[:20]}"

    def _heartbeat(self, handle: DesktopActivationHandleV1) -> None:
        # Keep the bounded worker idle timer alive without creating screenshots.
        scope = self.frame_proxy._scope(handle)
        request = Request(
            f"http://{self._container_name(handle)}:8765/viewport",
            headers={"X-Sovereign-Desktop-Scope": scope},
            method="GET",
        )
        with urlopen(request, timeout=3) as response:
            if int(response.status) != 200:
                raise FleetContractError("desktop stream heartbeat failed")
            response.read(4096)

    def _connect_upstream(self, handle: DesktopActivationHandleV1, mode: str):
        port = 6080 if mode == "view" else 6081
        url = f"ws://{self._container_name(handle)}:{port}/"
        deadline = time.monotonic() + 20.0
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                return websocket.create_connection(
                    url,
                    subprotocols=["binary"],
                    timeout=2.0,
                    enable_multithread=True,
                )
            except Exception as exc:  # worker is reconciled asynchronously on the host
                last_error = exc
                time.sleep(0.35)
        raise FleetContractError("desktop stream worker is unavailable") from last_error

    def bridge(
        self,
        *,
        downstream: Any,
        context: Any,
        user_id: str,
        mode: str,
        lease_id: str | None,
    ) -> DesktopStreamBindingV1:
        selected_mode = str(mode or "view").strip().lower()
        if selected_mode not in {"view", "control"}:
            raise FleetContractError("desktop stream mode is invalid")
        handle = self.issuer.issue(context=context)
        if selected_mode == "control" and not self.control.stream_control_allowed(
            context=context,
            owner_subject=user_id,
            activation_id=handle.activation_id,
            lease_id=str(lease_id or ""),
        ):
            raise FleetContractError("desktop control stream requires a current takeover lease")

        upstream = self._connect_upstream(handle, selected_mode)
        stop = threading.Event()

        def control_still_allowed() -> bool:
            return selected_mode == "view" or self.control.stream_control_allowed(
                context=context,
                owner_subject=user_id,
                activation_id=handle.activation_id,
                lease_id=str(lease_id or ""),
            )

        def upstream_to_browser() -> None:
            try:
                while not stop.is_set():
                    if not control_still_allowed():
                        break
                    try:
                        value = upstream.recv()
                    except websocket.WebSocketTimeoutException:
                        continue
                    except websocket.WebSocketConnectionClosedException:
                        break
                    if value is None:
                        break
                    downstream.send(value)
            except Exception:
                pass
            finally:
                stop.set()

        relay = threading.Thread(target=upstream_to_browser, daemon=True)
        relay.start()
        last_heartbeat = 0.0
        try:
            while not stop.is_set():
                if not control_still_allowed():
                    break
                now = time.monotonic()
                if now - last_heartbeat >= 5.0:
                    self._heartbeat(handle)
                    last_heartbeat = now
                try:
                    value = downstream.receive(timeout=1)
                except TimeoutError:
                    continue
                except Exception:
                    break
                if value is None:
                    continue
                opcode = websocket.ABNF.OPCODE_BINARY if isinstance(value, (bytes, bytearray)) else websocket.ABNF.OPCODE_TEXT
                upstream.send(value, opcode=opcode)
        finally:
            stop.set()
            try:
                upstream.close()
            except Exception:
                pass
            try:
                downstream.close()
            except Exception:
                pass
            relay.join(timeout=2)
        return DesktopStreamBindingV1(
            activation_id=handle.activation_id,
            session_binding_hash=handle.session_binding_hash,
            attempt_id=handle.attempt_id,
            workspace_id=handle.workspace_id,
            mode=selected_mode,
        )


__all__ = ["DesktopStreamBindingV1", "DesktopStreamGatewayV1"]
'''
for target in ('backend/agent_runtime/desktop_stream.py', 'scripts/sovereign-backend/agent_runtime/desktop_stream.py'):
    write(target, desktop_stream)

# ── Consent lease validation for a long-running control websocket ─────────────
lease_method = r'''    def stream_control_allowed(
        self,
        *,
        context: Any,
        owner_subject: str,
        activation_id: str,
        lease_id: str,
    ) -> bool:
        """Return true only while this exact human takeover lease is current."""
        try:
            handle, _raw = self._activation_document(context=context, activation_id=activation_id)
            selected_lease = _text(lease_id, "lease id", 80)
            owner_hash = hashlib.sha256(
                ("sovereign.user-input.v1|" + _text(owner_subject, "owner subject", 256)).encode("utf-8")
            ).hexdigest()
            with self._locked_control(handle.activation_id):
                record = self._read_record(handle=handle)
            now = int(self.clock())
            return (
                record.lease_id == selected_lease
                and record.state == "USER_CONTROLLED"
                and record.owner_subject_hash == owner_hash
                and record.session_binding_hash == handle.session_binding_hash
                and record.attempt_id == handle.attempt_id
                and record.workspace_id == handle.workspace_id
                and record.worktree_identity_hash == handle.worktree_identity_hash
                and record.issued_at <= now < record.expires_at
            )
        except (FleetContractError, OSError, ValueError):
            return False

'''
for target in ('backend/agent_runtime/desktop_control.py', 'scripts/sovereign-backend/agent_runtime/desktop_control.py'):
    if 'def stream_control_allowed(' not in read(target):
        insert_before_once(target, '    def frame_allowed(self, *, context: Any) -> bool:\n', lease_method)

# ── Flask-Sock authenticated websocket route ──────────────────────────────────
app_path = 'scripts/sovereign-backend/app.py'
replace_once(app_path, 'from flask import Flask, jsonify, request, make_response, g, abort, redirect, send_from_directory\n', 'from flask import Flask, jsonify, request, make_response, g, abort, redirect, send_from_directory\nfrom flask_sock import Sock\n')
replace_once(app_path, 'from agent_runtime.desktop_projection import DesktopFrameProxyV1\n', 'from agent_runtime.desktop_projection import DesktopFrameProxyV1\nfrom agent_runtime.desktop_stream import DesktopStreamGatewayV1\nfrom agent_runtime.job_store import read_agent_job\n')
replace_once(app_path, 'app = Flask(__name__)\n', 'app = Flask(__name__)\nsock = Sock(app)\n')
stream_route = r'''

_DESKTOP_STREAM_ALLOWED_ORIGINS = frozenset(_DEFAULT_CORS_ORIGINS)
_desktop_stream_context_resolver = build_live_workspace_context_resolver()
_desktop_stream_gateway = DesktopStreamGatewayV1.from_env()

@sock.route("/api/user/agent/jobs/<job_id>/live-workspace/desktop/stream")
def user_live_workspace_desktop_stream(ws, job_id: str):
    """Proxy one authenticated RFB websocket without exposing worker authority."""
    user_id = _get_session_user_id()
    if not user_id:
        ws.close(reason="UNAUTHENTICATED")
        return
    origin = str(request.headers.get("Origin") or "").strip()
    if origin and origin not in _DESKTOP_STREAM_ALLOWED_ORIGINS:
        ws.close(reason="ORIGIN_NOT_ALLOWED")
        return
    mode = str(request.args.get("mode") or "view").strip().lower()
    lease_id = str(request.args.get("leaseId") or "").strip() or None
    conn = get_agent_runtime_connection()
    try:
        job = read_agent_job(conn, user_id=str(user_id), job_id=str(job_id))
        if job is None:
            ws.close(reason="JOB_NOT_FOUND")
            return
        try:
            context = _desktop_stream_context_resolver(conn, job)
        except Exception:
            context = None
        if context is None:
            ws.close(reason="LIVE_WORKSPACE_CONTEXT_UNAVAILABLE")
            return
        try:
            _desktop_stream_gateway.bridge(
                downstream=ws,
                context=context,
                user_id=str(user_id),
                mode=mode,
                lease_id=lease_id,
            )
        except Exception:
            try:
                ws.close(reason="DESKTOP_STREAM_UNAVAILABLE")
            except Exception:
                pass
    finally:
        conn.close()
'''
require_session_marker = 'register_progressive_skill_routes(\n'
if 'def user_live_workspace_desktop_stream(' not in read(app_path):
    insert_before_once(app_path, require_session_marker, stream_route + '\n')

# ── Typed frontend stream/control API ─────────────────────────────────────────
client_path = 'src/features/product/runtime/sovereignAgentClient.ts'
control_types = r'''
export interface SovereignDesktopControlLease {
  readonly activationId: string;
  readonly leaseId: string;
  readonly expiresAt: number;
}

'''
if 'export interface SovereignDesktopControlLease' not in read(client_path):
    insert_before_once(client_path, 'export class SovereignAgentClient {\n', control_types)
client_methods = r'''  desktopStreamUrl(jobId: string, mode: 'view' | 'control' = 'view', leaseId?: string): string {
    assertReady(this.config);
    const selectedJobId = jobId.trim();
    if (!selectedJobId) throw new Error('Sovereign Agent job id is required.');
    if (mode === 'control' && !leaseId?.trim()) throw new Error('Desktop control stream requires a takeover lease.');
    const url = new URL(endpoint(this.config.agentApiUrl, jobPath(selectedJobId, '/live-workspace/desktop/stream')));
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
    url.searchParams.set('mode', mode);
    if (mode === 'control' && leaseId) url.searchParams.set('leaseId', leaseId.trim());
    return url.toString();
  }
  async takeDesktopControl(jobId: string): Promise<SovereignDesktopControlLease> {
    assertReady(this.config);
    const selectedJobId = jobId.trim();
    if (!selectedJobId) throw new Error('Sovereign Agent job id is required.');
    const body = await requestObject({
      url: endpoint(this.config.agentApiUrl, jobPath(selectedJobId, '/live-workspace/desktop/takeover')),
      init: { method: 'POST', headers: headers(), credentials: 'include', body: '{}' },
      fetcher: this.fetcher,
      fallback: 'Sovereign Live Desktop takeover',
    });
    const activation = isObject(body.desktopActivation) ? body.desktopActivation : {};
    const control = isObject(body.control) ? body.control : {};
    const activationId = stringValue(activation.activationId);
    const leaseId = stringValue(control.leaseId);
    const expiresAt = integerValue(control.expiresAt);
    if (!activationId || !leaseId || expiresAt === undefined) {
      throw new Error('Sovereign Live Desktop takeover returned no exact activation/lease binding.');
    }
    return { activationId, leaseId, expiresAt };
  }
  async giveBackDesktopControl(jobId: string, lease: SovereignDesktopControlLease): Promise<void> {
    assertReady(this.config);
    const selectedJobId = jobId.trim();
    if (!selectedJobId) throw new Error('Sovereign Agent job id is required.');
    await requestObject({
      url: endpoint(this.config.agentApiUrl, jobPath(selectedJobId, '/live-workspace/desktop/give-back')),
      init: {
        method: 'POST',
        headers: headers(),
        credentials: 'include',
        body: JSON.stringify({ activationId: lease.activationId, leaseId: lease.leaseId }),
      },
      fetcher: this.fetcher,
      fallback: 'Sovereign Live Desktop give-back',
    });
  }
'''
if 'desktopStreamUrl(jobId:' not in read(client_path):
    insert_before_once(client_path, '  async getDesktopFrame(jobId: string): Promise<SovereignDesktopFrameObservation> {\n', client_methods)

# ── React VNC monitor ─────────────────────────────────────────────────────────
stream_pane = r'''import React, { useEffect, useMemo, useState } from 'react';
import { VncScreen } from 'react-vnc';
import type { SovereignAgentJobSnapshot } from '../runtime/sovereignAgentRuntime';
import { createSovereignAgentClient, type SovereignDesktopControlLease } from '../runtime/sovereignAgentClient';
import { C } from './builderConstants';

export function LiveDesktopStreamPane({ job }: { readonly job?: SovereignAgentJobSnapshot | null }) {
  const client = useMemo(() => createSovereignAgentClient(), []);
  const jobId = job?.jobId ?? '';
  const [lease, setLease] = useState<SovereignDesktopControlLease | null>(null);
  const [state, setState] = useState<'idle' | 'connecting' | 'live' | 'control' | 'blocked'>('idle');
  const [message, setMessage] = useState('');

  useEffect(() => {
    setLease(null);
    setState(jobId ? 'connecting' : 'idle');
    setMessage('');
  }, [jobId]);

  useEffect(() => {
    if (!lease) return;
    const remaining = Math.max(0, lease.expiresAt * 1000 - Date.now());
    const timer = window.setTimeout(() => {
      setLease(null);
      setState('connecting');
      setMessage('Takeover-Lease abgelaufen · wieder nur Beobachtung.');
    }, remaining + 150);
    return () => window.clearTimeout(timer);
  }, [lease]);

  if (!jobId) {
    return (
      <div className="live-workspace-monitor__honest-empty" data-testid="live-desktop-stream-idle">
        <span aria-hidden="true">▣</span>
        <p>Noch kein aktiver Workspace-Job. Der echte Desktop-Stream startet mit dem gebundenen Job.</p>
      </div>
    );
  }

  const streamUrl = client.desktopStreamUrl(jobId, lease ? 'control' : 'view', lease?.leaseId);

  async function takeover() {
    setMessage('');
    try {
      const next = await client.takeDesktopControl(jobId);
      setLease(next);
      setState('control');
    } catch (error) {
      setState('blocked');
      setMessage(error instanceof Error ? error.message : 'Desktop-Takeover konnte nicht bestätigt werden.');
    }
  }

  async function giveBack() {
    if (!lease) return;
    try {
      await client.giveBackDesktopControl(jobId, lease);
      setLease(null);
      setState('connecting');
      setMessage('Steuerung zurückgegeben · Agentenmodus ist wieder read-only sichtbar.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Desktop-Steuerung konnte nicht zurückgegeben werden.');
    }
  }

  return (
    <div data-testid="live-desktop-rfb-stream" style={{ minHeight: 360, display: 'flex', flexDirection: 'column', background: '#05070a' }}>
      <div className="live-workspace-monitor__surface-toolbar" style={{ gap: 8 }}>
        <span style={{ color: lease ? C.amber : C.green }}>DESKTOP · RFB LIVE STREAM</span>
        <span style={{ flex: 1 }}>{lease ? 'USER CONTROLLED' : state === 'live' ? 'LIVE · READ ONLY' : 'VERBINDE…'}</span>
        {lease ? (
          <button type="button" onClick={giveBack} style={{ border: `1px solid ${C.amber}`, color: C.amber, background: 'transparent', borderRadius: 6, padding: '4px 8px', cursor: 'pointer' }}>
            Steuerung zurückgeben
          </button>
        ) : (
          <button type="button" onClick={takeover} style={{ border: `1px solid ${C.sky}`, color: C.sky, background: 'transparent', borderRadius: 6, padding: '4px 8px', cursor: 'pointer' }}>
            Desktop übernehmen
          </button>
        )}
      </div>
      <div style={{ flex: 1, minHeight: 330, position: 'relative', overflow: 'hidden' }}>
        <VncScreen
          key={`${jobId}:${lease?.leaseId ?? 'view'}`}
          url={streamUrl}
          scaleViewport
          viewOnly={!lease}
          retryDuration={1000}
          rfbOptions={{ wsProtocols: ['binary'] }}
          onConnect={() => setState(lease ? 'control' : 'live')}
          onDisconnect={() => setState('connecting')}
          style={{ width: '100%', height: '100%', minHeight: 330 }}
        />
      </div>
      {message && <div style={{ padding: '6px 10px', fontSize: 11, color: state === 'blocked' ? C.rose : C.textSub }}>{message}</div>}
      <div style={{ padding: '5px 10px', fontSize: 10, color: C.textMuted, borderTop: `1px solid ${C.border}` }}>
        Kontinuierlicher RFB/WebSocket-Stream. Beobachten erteilt keine Eingabe-Autorität; Maus/Tastatur werden erst mit dem kurzlebigen Takeover-Lease freigeschaltet.
      </div>
    </div>
  );
}
'''
write('src/features/product/components/LiveDesktopStreamPane.tsx', stream_pane)
monitor_path = 'src/features/product/components/LiveWorkspaceMonitor.tsx'
if "from './LiveDesktopStreamPane'" not in read(monitor_path):
    replace_once(monitor_path, "import { C } from './builderConstants';\n", "import { C } from './builderConstants';\nimport { LiveDesktopStreamPane } from './LiveDesktopStreamPane';\n")
monitor = read(monitor_path)
start = monitor.index('function DesktopFramePane({')
end = monitor.index('function EmptyProjectionPane()', start)
monitor = monitor[:start] + "function DesktopFramePane({ job }: { readonly frame?: LiveWorkspaceMonitorProps['desktopFrame']; readonly job?: SovereignAgentJobSnapshot | null }) {\n  return <LiveDesktopStreamPane job={job} />;\n}\n\n" + monitor[end:]
write(monitor_path, monitor)

# Remove the obsolete 1.5 second PNG polling loop from the permanent app root.
app_tsx = 'src/App.tsx'
app_text = read(app_tsx)
state_match = re.search(r"\n  const \[desktopFrame, setDesktopFrame\] = useState<\{.*?\n  const desktopFrameUrlRef = useRef<string \| null>\(null\);", app_text, re.S)
if not state_match:
    raise SystemExit('App desktop frame state anchor missing')
app_text = app_text[:state_match.start()] + app_text[state_match.end():]
poll_start = app_text.find("  useEffect(() => {\n    const jobId = canonicalAgentJob.jobId;\n    const canReadFrame = Boolean(")
if poll_start < 0:
    raise SystemExit('App PNG polling start anchor missing')
poll_end = app_text.find('  const evidenceWithReusableMemory', poll_start)
if poll_end < 0:
    raise SystemExit('App PNG polling end anchor missing')
app_text = app_text[:poll_start] + app_text[poll_end:]
app_text = app_text.replace('          desktopFrame={desktopFrame}\n', '')
write(app_tsx, app_text)

# ── Host-only Activation → Worker lifecycle reconciler ────────────────────────
reconciler = r'''#!/usr/bin/env python3
"""Host-only reconciler that closes Activation -> Desktop Worker lifecycle."""
from __future__ import annotations

import json
from pathlib import Path
import signal
import time

from desktop_worker import DesktopWorkerRuntime, DesktopWorkerError


STOP = False


def _stop(_signum, _frame):
    global STOP
    STOP = True


def activation_ids(root: Path):
    if not root.is_dir() or root.is_symlink():
        return []
    result = []
    for path in root.glob('*.json'):
        if path.name.endswith('.control.json') or path.is_symlink() or not path.is_file():
            continue
        stem = path.name[:-5]
        if len(stem) == 64 and all(c in '0123456789abcdef' for c in stem):
            result.append(stem)
    return sorted(result)


def reconcile_one(runtime: DesktopWorkerRuntime, activation_id: str) -> None:
    try:
        activation = runtime._load_activation(activation_id)
        document = runtime.activation_root / f'{activation_id}.json'
        age = max(0, int(time.time() - document.stat().st_mtime))
        if age > activation.wall_time_seconds:
            runtime.remove(activation_id=activation_id)
            return
        readback = runtime.readback(activation_id=activation_id)
        if readback.get('ok') is not True:
            if readback.get('failure_family') != 'DESKTOP_INSPECT_UNAVAILABLE':
                runtime.remove(activation_id=activation_id)
            started = runtime.start(activation_id=activation_id)
            if started.get('ok') is not True and started.get('failure_family') != 'DESKTOP_ALREADY_EXISTS':
                return
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline:
                readback = runtime.readback(activation_id=activation_id)
                if readback.get('ok') is True:
                    break
                time.sleep(0.35)
        runtime.canary(activation_id=activation_id)
    except (DesktopWorkerError, OSError, ValueError, json.JSONDecodeError):
        return


def main() -> int:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    runtime = DesktopWorkerRuntime()
    while not STOP:
        for activation_id in activation_ids(runtime.activation_root):
            reconcile_one(runtime, activation_id)
            if STOP:
                break
        time.sleep(0.5)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
'''
write('tools/sovereign-chatgpt-mcp/desktop_activation_reconciler.py', reconciler)
service = r'''[Unit]
Description=Sovereign live desktop activation reconciler
After=docker.service sovereign-chatgpt-broker.service
Requires=docker.service

[Service]
Type=simple
User=root
Group=sovereign-mcp
EnvironmentFile=/opt/sovereign-chatgpt-tools/broker.env
Environment=PYTHONDONTWRITEBYTECODE=1
Environment=PYTHONUNBUFFERED=1
WorkingDirectory=/opt/sovereign-chatgpt-tools/broker
ExecStartPre=/usr/bin/test -S /var/run/docker.sock
ExecStart=/usr/bin/python3 /opt/sovereign-chatgpt-tools/broker/desktop_activation_reconciler.py
Restart=always
RestartSec=1
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadOnlyPaths=/opt/sovereign-chatgpt-tools
ReadWritePaths=/opt/sovereign-desktop-activations /opt/sovereign-agent-workspaces
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
LockPersonality=true
RestrictRealtime=true

[Install]
WantedBy=multi-user.target
'''
write('tools/sovereign-chatgpt-mcp/deploy/sovereign-desktop-reconciler.service', service)

# Installer installs and starts the host-only reconciler and provisions private activation material.
installer = 'tools/sovereign-chatgpt-mcp/deploy/install-on-vps.sh'
if 'DESKTOP_RECONCILER_SERVICE=' not in read(installer):
    replace_once(installer, 'BROKER_SERVICE="/etc/systemd/system/sovereign-chatgpt-broker.service"\n', 'BROKER_SERVICE="/etc/systemd/system/sovereign-chatgpt-broker.service"\nDESKTOP_RECONCILER_SERVICE="/etc/systemd/system/sovereign-desktop-reconciler.service"\nDESKTOP_ACTIVATION_HOST_ROOT="/opt/sovereign-desktop-activations"\nDESKTOP_ACTIVATION_KEY_FILE="$OWNER_INPUT_HOST_ROOT/desktop_activation_key.txt"\n')
    replace_once(installer, 'backup_control_plane_file "$BROKER_SERVICE"\n', 'backup_control_plane_file "$BROKER_SERVICE"\nbackup_control_plane_file "$DESKTOP_RECONCILER_SERVICE"\n')
    replace_once(installer, 'for file in broker.py desktop_worker.py browserless_reader.py', 'for file in broker.py desktop_worker.py desktop_activation_reconciler.py browserless_reader.py')
    replace_once(installer, 'install_managed_control_plane_file 0644 "$SOURCE_DIR/deploy/sovereign-chatgpt-broker.service" "$BROKER_SERVICE" "systemd/sovereign-chatgpt-broker.service"\n', 'install_managed_control_plane_file 0644 "$SOURCE_DIR/deploy/sovereign-chatgpt-broker.service" "$BROKER_SERVICE" "systemd/sovereign-chatgpt-broker.service"\ninstall_managed_control_plane_file 0644 "$SOURCE_DIR/deploy/sovereign-desktop-reconciler.service" "$DESKTOP_RECONCILER_SERVICE" "systemd/sovereign-desktop-reconciler.service"\n')
    network_anchor = 'INSTALL_STAGE="start_host_control_plane"\n'
    prepare = r'''INSTALL_STAGE="prepare_desktop_runtime"
install -d -m 0700 -o root -g root "$DESKTOP_ACTIVATION_HOST_ROOT"
if [[ ! -f "$DESKTOP_ACTIVATION_KEY_FILE" ]]; then
  umask 077
  python3 - <<'PY' > "$DESKTOP_ACTIVATION_KEY_FILE"
import secrets
print(secrets.token_hex(48))
PY
fi
chown root:root "$DESKTOP_ACTIVATION_KEY_FILE"
chmod 0600 "$DESKTOP_ACTIVATION_KEY_FILE"
docker network inspect sovereign-desktop >/dev/null 2>&1 || docker network create --internal sovereign-desktop >/dev/null

'''
    insert_before_once(installer, network_anchor, prepare)
    replace_once(installer, 'systemctl is-active --quiet sovereign-chatgpt-command-worker.service || fail "host command worker is not active"\n', 'systemctl is-active --quiet sovereign-chatgpt-command-worker.service || fail "host command worker is not active"\nsystemctl enable --now sovereign-desktop-reconciler.service\nsystemctl restart sovereign-desktop-reconciler.service\nsystemctl is-active --quiet sovereign-desktop-reconciler.service || fail "desktop reconciler is not active"\n')

# Required release files include the reconciler contract.
verify_installer = 'tools/sovereign-chatgpt-mcp/deploy/install-and-verify-private-mcp-on-vps.sh'
if 'desktop_activation_reconciler.py' not in read(verify_installer):
    replace_once(verify_installer, 'for required in Dockerfile docker-compose.yml command_contract.py command_queue.py', 'for required in Dockerfile docker-compose.yml command_contract.py command_queue.py desktop_worker.py desktop_activation_reconciler.py deploy/sovereign-desktop-reconciler.service')

# Upgrade host canary from PNG-only proof to actual websocket/RFB endpoint proof.
dw_path = 'tools/sovereign-chatgpt-mcp/desktop_worker.py'
dw = read(dw_path)
old_canary = '''        script = (\n            "from pathlib import Path; from urllib.request import Request, urlopen; "\n            "scope=Path('/opt/desktop-scopes/view').read_text('utf-8').strip(); "\n            "request=Request('http://127.0.0.1:8765/frame',headers={'X-Sovereign-Desktop-Scope':scope}); "\n            "response=urlopen(request,timeout=8); body=response.read(64); "\n            "assert response.status==200 and response.headers.get('Content-Type')=='image/png' and body.startswith(bytes([137,80,78,71]))"\n        )\n'''
new_canary = '''        script = (\n            "import base64,os,socket; from pathlib import Path; from urllib.request import Request,urlopen; "\n            "scope=Path('/opt/desktop-scopes/view').read_text('utf-8').strip(); "\n            "response=urlopen(Request('http://127.0.0.1:8765/viewport',headers={'X-Sovereign-Desktop-Scope':scope}),timeout=8); assert response.status==200; "\n            "key=base64.b64encode(os.urandom(16)).decode(); "\n            "ports=(6080,6081); "\n            "[(lambda s,p: (s.sendall(('GET / HTTP/1.1\\r\\nHost: 127.0.0.1:%d\\r\\nUpgrade: websocket\\r\\nConnection: Upgrade\\r\\nSec-WebSocket-Key: %s\\r\\nSec-WebSocket-Version: 13\\r\\nSec-WebSocket-Protocol: binary\\r\\n\\r\\n' % (p,key)).encode()), (b' 101 ' in s.recv(2048)), s.close()))(socket.create_connection(('127.0.0.1',p),5),p) for p in ports]"\n        )\n'''
if old_canary not in dw:
    raise SystemExit('desktop worker canary anchor missing')
dw = dw.replace(old_canary, new_canary, 1)
write(dw_path, dw)

print('BYTEBOT_LIVE_DESKTOP_PATCH_APPLIED')
