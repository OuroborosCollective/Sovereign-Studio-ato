#!/usr/bin/env python3
from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    target = Path(path)
    text = target.read_text("utf-8")
    actual = text.count(old)
    if actual != count:
        raise SystemExit(f"{path}: expected {count} anchor(s), found {actual}: {old[:80]!r}")
    target.write_text(text.replace(old, new), "utf-8")


for path in ("backend/agent_runtime/routes.py", "scripts/sovereign-backend/agent_runtime/routes.py"):
    replace(path, "from flask import Response, jsonify, request\n", "from flask import Response, jsonify, request\nfrom flask_sock import Sock\n")
    replace(path, "from .fleet_supervisor import FleetContractError\n", "from .fleet_supervisor import FleetContractError\nfrom .desktop_stream import DesktopStreamError, issue_stream_ticket, proxy_rfb_websocket, verify_stream_ticket\n")
    replace(path, "    def _connection():\n        return get_connection()\n", "    sock = Sock(app)\n    app.config.setdefault('SOCK_SERVER_OPTIONS', {'ping_interval': 25, 'max_message_size': 2_000_000})\n\n    def _connection():\n        return get_connection()\n")
    activation_anchor = '''            return jsonify({\n                "ok": True,\n                "runtime": "sovereign-agent",\n                "jobId": job_id,\n                "desktopActivation": payload,\n            })\n        finally:\n            _close(conn)\n\n    @app.route("/api/user/agent/jobs/<job_id>/live-workspace/desktop/takeover", methods=["POST"])\n'''
    activation_replacement = '''            return jsonify({\n                "ok": True,\n                "runtime": "sovereign-agent",\n                "jobId": job_id,\n                "desktopActivation": payload,\n            })\n        finally:\n            _close(conn)\n\n    @app.route("/api/user/agent/jobs/<job_id>/live-workspace/desktop/stream-ticket", methods=["POST"])\n    @require_session\n    def user_issue_live_workspace_desktop_stream_ticket(job_id: str):\n        user_id = _current_session_user_id()\n        conn = _connection()\n        try:\n            job = _read_owned_job(conn, user_id, job_id)\n            if not job:\n                return jsonify({"error": "Job nicht gefunden"}), 404\n            context = _resolve_live_workspace_context(conn, job)\n            if context is None or issue_desktop_activation is None:\n                return _desktop_control_block(job_id, "DESKTOP_STREAM_UNAVAILABLE")\n            try:\n                activation = issue_desktop_activation(context)\n                handle = activation.to_dict() if activation is not None else None\n                if not isinstance(handle, dict) or _contains_live_workspace_path(handle):\n                    raise DesktopStreamError("desktop stream activation is unavailable")\n                ticket = issue_stream_ticket(user_id=user_id, job_id=job_id, activation_id=str(handle.get("activationId") or ""), session_binding_hash=context.session.session_binding_hash)\n            except Exception:\n                return _desktop_control_block(job_id, "DESKTOP_STREAM_UNAVAILABLE")\n            return jsonify({"ok": True, "runtime": "sovereign-agent", "jobId": job_id, "desktopStream": {"activationId": handle["activationId"], "sessionBindingHash": context.session.session_binding_hash, "ticket": ticket["ticket"], "expiresAtEpoch": ticket["expiresAtEpoch"], "transport": "rfb-websocket", "viewOnly": True}})\n        finally:\n            _close(conn)\n\n    @sock.route("/api/user/agent/jobs/<job_id>/live-workspace/desktop/stream")\n    def user_stream_live_workspace_desktop(ws, job_id: str):\n        try:\n            payload = verify_stream_ticket(str(request.args.get("ticket") or ""), job_id=job_id)\n            proxy_rfb_websocket(ws, session_binding_hash=str(payload["session"]))\n        except Exception:\n            try:\n                ws.close(reason=1008, message="desktop stream unavailable")\n            except Exception:\n                pass\n\n    @app.route("/api/user/agent/jobs/<job_id>/live-workspace/desktop/takeover", methods=["POST"])\n'''
    replace(path, activation_anchor, activation_replacement)

client = "src/features/product/runtime/sovereignAgentClient.ts"
replace(client, "export interface SovereignDesktopFrameObservation {\n  readonly blob: Blob;\n  readonly frameHash: string;\n  readonly observedAt: number;\n}\n", "export interface SovereignDesktopFrameObservation {\n  readonly blob: Blob;\n  readonly frameHash: string;\n  readonly observedAt: number;\n}\n\nexport interface SovereignDesktopStreamTicket {\n  readonly activationId: string;\n  readonly sessionBindingHash: string;\n  readonly ticket: string;\n  readonly expiresAtEpoch: number;\n  readonly transport: 'rfb-websocket';\n  readonly viewOnly: true;\n}\n")
frame_method = "  async getDesktopFrame(jobId: string): Promise<SovereignDesktopFrameObservation> {\n"
stream_method = """  async getDesktopStreamTicket(jobId: string): Promise<SovereignDesktopStreamTicket> {\n    assertReady(this.config);\n    const requestedJobId = jobId.trim();\n    if (!requestedJobId) throw new Error('Sovereign Agent job id is required.');\n    const body = await requestObject({ url: endpoint(this.config.agentApiUrl, jobPath(requestedJobId, '/live-workspace/desktop/stream-ticket')), init: { method: 'POST', headers: headers(), credentials: 'include', body: '{}' }, fetcher: this.fetcher, fallback: 'Sovereign Live Desktop stream ticket' });\n    const stream = isObject(body.desktopStream) ? body.desktopStream : {};\n    const activationId = stringValue(stream.activationId)?.toLowerCase() ?? '';\n    const sessionBindingHash = stringValue(stream.sessionBindingHash)?.toLowerCase() ?? '';\n    const ticket = stringValue(stream.ticket) ?? '';\n    const expiresAtEpoch = typeof stream.expiresAtEpoch === 'number' ? stream.expiresAtEpoch : 0;\n    if (stringValue(body.jobId) !== requestedJobId || !SHA256_RE.test(activationId) || !SHA256_RE.test(sessionBindingHash) || !ticket.includes('.') || expiresAtEpoch <= Math.floor(this.now() / 1000) || stream.transport !== 'rfb-websocket' || stream.viewOnly !== true) throw new Error('Sovereign Live Desktop returned no valid revision-bound RFB stream ticket.');\n    return { activationId, sessionBindingHash, ticket, expiresAtEpoch, transport: 'rfb-websocket', viewOnly: true };\n  }\n\n  async getDesktopFrame(jobId: string): Promise<SovereignDesktopFrameObservation> {\n"""
replace(client, frame_method, stream_method)

app_path = Path("src/App.tsx")
app_text = app_path.read_text("utf-8")
old_state = "  const [desktopFrame, setDesktopFrame] = useState<{\n    readonly jobId: string;\n    readonly url: string;\n    readonly frameHash: string;\n    readonly observedAt: number;\n  } | null>(null);\n  const desktopFrameUrlRef = useRef<string | null>(null);\n"
new_state = "  const [desktopStream, setDesktopStream] = useState<{\n    readonly jobId: string;\n    readonly url: string;\n    readonly activationId: string;\n    readonly sessionBindingHash: string;\n    readonly expiresAtEpoch: number;\n  } | null>(null);\n"
if app_text.count(old_state) != 1:
    raise SystemExit("src/App.tsx: desktop frame state anchor mismatch")
app_text = app_text.replace(old_state, new_state)
start_anchor = "  useEffect(() => {\n    const jobId = canonicalAgentJob.jobId;\n    const canReadFrame = Boolean("
start = app_text.index(start_anchor)
end_marker = "  const evidenceWithReusableMemory = async (query: string): Promise<string> => {"
end = app_text.index(end_marker, start)
new_effect = """  useEffect(() => {\n    const jobId = canonicalAgentJob.jobId;\n    const active = Boolean(agentConfig.ready && jobId && canonicalAgentJob.status !== 'idle' && canonicalAgentJob.status !== 'cleaned');\n    if (!active || !jobId) { setDesktopStream(null); return; }\n    let cancelled = false;\n    const connect = async () => {\n      try {\n        const stream = await agentClient.getDesktopStreamTicket(jobId);\n        if (cancelled) return;\n        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';\n        const route = `/api/user/agent/jobs/${encodeURIComponent(jobId)}/live-workspace/desktop/stream`;\n        setDesktopStream({ jobId, activationId: stream.activationId, sessionBindingHash: stream.sessionBindingHash, expiresAtEpoch: stream.expiresAtEpoch, url: `${protocol}//${window.location.host}${route}?ticket=${encodeURIComponent(stream.ticket)}` });\n      } catch { if (!cancelled) setDesktopStream(null); }\n    };\n    void connect();\n    return () => { cancelled = true; };\n  }, [agentClient, agentConfig.ready, canonicalAgentJob.jobId, canonicalAgentJob.status]);\n\n"""
app_text = app_text[:start] + new_effect + app_text[end:]
app_text = app_text.replace("desktopFrame={desktopFrame}", "desktopStream={desktopStream}")
app_path.write_text(app_text, "utf-8")

for path in ("src/features/product/containers/BuilderContainer.tsx", "src/features/product/components/AgentEventStream.tsx"):
    target = Path(path); target.write_text(target.read_text("utf-8").replace("desktopFrame", "desktopStream"), "utf-8")

monitor = Path("src/features/product/components/LiveWorkspaceMonitor.tsx")
text = monitor.read_text("utf-8").replace("desktopFrame", "desktopStream")
text = text.replace("import React, { useEffect, useId, useMemo, useRef, useState } from 'react';\n", "import React, { useEffect, useId, useMemo, useRef, useState } from 'react';\nimport { VncScreen } from 'react-vnc';\n")
old_pane_start = text.index("function DesktopFramePane({")
old_pane_end = text.index("\nfunction EmptyProjectionPane()", old_pane_start)
new_pane = """function DesktopFramePane({ stream, job }: { readonly stream?: LiveWorkspaceMonitorProps['desktopStream']; readonly job?: SovereignAgentJobSnapshot | null; }) {\n  return (\n    <div className=\"live-workspace-monitor__desktop\" data-testid=\"live-workspace-monitor-desktop\">\n      <div className=\"live-workspace-monitor__surface-toolbar\"><span style={{ color: C.green }}>DESKTOP · LIVE RFB STREAM</span><span>{stream ? 'CONNECTED · VIEW ONLY' : 'warte auf Desktop-Worker'}</span></div>\n      {stream ? (<>\n        <div className=\"live-workspace-monitor__desktop-frame-wrap\" data-testid=\"live-workspace-monitor-rfb-stream\"><VncScreen key={`${stream.activationId}:${stream.expiresAtEpoch}`} url={stream.url} scaleViewport viewOnly rfbOptions={{ secure: false, shared: true, wsProtocols: ['binary'] }} style={{ width: '100%', height: '100%', minHeight: 420 }} /></div>\n        <div className=\"live-workspace-monitor__metadata-grid\"><MetaPill label=\"Activation\" value={shortIdentity(stream.activationId, 20)} /><MetaPill label=\"Session\" value={shortIdentity(stream.sessionBindingHash, 20)} /><MetaPill label=\"Job\" value={shortIdentity(job?.jobId, 18)} /></div>\n      </>) : (<div className=\"live-workspace-monitor__honest-empty\" data-testid=\"live-workspace-monitor-desktop-unavailable\"><span aria-hidden=\"true\">▣</span><p>{job?.jobId ? 'Der Monitor wartet auf den echten Desktop-Worker und seinen RFB-WebSocket. Es werden keine Ersatzbilder erzeugt.' : 'Noch kein aktiver Workspace-Job. Der Live-Desktop startet mit dem ersten echten AttemptWorkspace.'}</p></div>)}\n    </div>\n  );\n}\n"""
text = text[:old_pane_start] + new_pane + text[old_pane_end:]
text = text.replace("<DesktopFramePane frame={desktopStream} job={job} />", "<DesktopFramePane stream={desktopStream} job={job} />")
monitor.write_text(text, "utf-8")

package = Path("package.json")
text = package.read_text("utf-8")
if '"react-vnc"' not in text:
    text = text.replace('    "react-redux": "^9.2.0",\n', '    "react-redux": "^9.2.0",\n    "react-vnc": "^3.1.0",\n')
package.write_text(text, "utf-8")
print("BYTEBOT_LIVE_DESKTOP_STREAM_PATCH_APPLIED")
