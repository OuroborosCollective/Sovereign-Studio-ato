#!/usr/bin/env python3
from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    target = Path(path)
    text = target.read_text("utf-8")
    actual = text.count(old)
    if actual != count:
        raise SystemExit(f"{path}: expected {count} anchor(s), found {actual}: {old[:80]!r}")
    target.write_text(text.replace(old, new), "utf-8")


# Backend websocket route + ticket issuance. Keep canonical and production mirror equal.
for path in ("backend/agent_runtime/routes.py", "scripts/sovereign-backend/agent_runtime/routes.py"):
    replace(path, "from flask import Response, jsonify, request\n", "from flask import Response, jsonify, request\nfrom flask_sock import Sock\n")
    replace(
        path,
        "from .fleet_supervisor import FleetContractError\n",
        "from .fleet_supervisor import FleetContractError\nfrom .desktop_stream import DesktopStreamError, issue_stream_ticket, proxy_rfb_websocket, verify_stream_ticket\n",
    )
    replace(
        path,
        "    def _connection():\n        return get_connection()\n",
        "    sock = Sock(app)\n    app.config.setdefault('SOCK_SERVER_OPTIONS', {'ping_interval': 25, 'max_message_size': 2_000_000})\n\n    def _connection():\n        return get_connection()\n",
    )
    activation_anchor = '''            return jsonify({\n                "ok": True,\n                "runtime": "sovereign-agent",\n                "jobId": job_id,\n                "desktopActivation": payload,\n            })\n        finally:\n            _close(conn)\n\n    @app.route("/api/user/agent/jobs/<job_id>/live-workspace/desktop/takeover", methods=["POST"])\n'''
    activation_replacement = '''            return jsonify({\n                "ok": True,\n                "runtime": "sovereign-agent",\n                "jobId": job_id,\n                "desktopActivation": payload,\n            })\n        finally:\n            _close(conn)\n\n    @app.route("/api/user/agent/jobs/<job_id>/live-workspace/desktop/stream-ticket", methods=["POST"])\n    @require_session\n    def user_issue_live_workspace_desktop_stream_ticket(job_id: str):\n        """Issue a short-lived view-only stream ticket for the exact live attempt."""\n        user_id = _current_session_user_id()\n        conn = _connection()\n        try:\n            job = _read_owned_job(conn, user_id, job_id)\n            if not job:\n                return jsonify({"error": "Job nicht gefunden"}), 404\n            context = _resolve_live_workspace_context(conn, job)\n            if context is None or issue_desktop_activation is None:\n                return _desktop_control_block(job_id, "DESKTOP_STREAM_UNAVAILABLE")\n            try:\n                activation = issue_desktop_activation(context)\n                handle = activation.to_dict() if activation is not None else None\n                if not isinstance(handle, dict) or _contains_live_workspace_path(handle):\n                    raise DesktopStreamError("desktop stream activation is unavailable")\n                ticket = issue_stream_ticket(\n                    user_id=user_id,\n                    job_id=job_id,\n                    activation_id=str(handle.get("activationId") or ""),\n                    session_binding_hash=context.session.session_binding_hash,\n                )\n            except Exception:\n                return _desktop_control_block(job_id, "DESKTOP_STREAM_UNAVAILABLE")\n            return jsonify({\n                "ok": True,\n                "runtime": "sovereign-agent",\n                "jobId": job_id,\n                "desktopStream": {\n                    "activationId": handle["activationId"],\n                    "sessionBindingHash": context.session.session_binding_hash,\n                    "ticket": ticket["ticket"],\n                    "expiresAtEpoch": ticket["expiresAtEpoch"],\n                    "transport": "rfb-websocket",\n                    "viewOnly": True,\n                },\n            })\n        finally:\n            _close(conn)\n\n    @sock.route("/api/user/agent/jobs/<job_id>/live-workspace/desktop/stream")\n    def user_stream_live_workspace_desktop(ws, job_id: str):\n        """Proxy the real worker RFB stream; VNC input is disabled at the worker."""\n        try:\n            ticket = str(request.args.get("ticket") or "")\n            payload = verify_stream_ticket(ticket, job_id=job_id)\n            proxy_rfb_websocket(ws, session_binding_hash=str(payload["session"]))\n        except Exception:\n            try:\n                ws.close(reason=1008, message="desktop stream unavailable")\n            except Exception:\n                pass\n\n    @app.route("/api/user/agent/jobs/<job_id>/live-workspace/desktop/takeover", methods=["POST"])\n'''
    replace(path, activation_anchor, activation_replacement)

# Frontend client: stream ticket replaces PNG observation as primary monitor transport.
client = "src/features/product/runtime/sovereignAgentClient.ts"
replace(
    client,
    "export interface SovereignDesktopFrameObservation {\n  readonly blob: Blob;\n  readonly frameHash: string;\n  readonly observedAt: number;\n}\n",
    "export interface SovereignDesktopFrameObservation {\n  readonly blob: Blob;\n  readonly frameHash: string;\n  readonly observedAt: number;\n}\n\nexport interface SovereignDesktopStreamTicket {\n  readonly activationId: string;\n  readonly sessionBindingHash: string;\n  readonly ticket: string;\n  readonly expiresAtEpoch: number;\n  readonly transport: 'rfb-websocket';\n  readonly viewOnly: true;\n}\n",
)
frame_method = '''  async getDesktopFrame(jobId: string): Promise<SovereignDesktopFrameObservation> {\n'''
stream_method = '''  async getDesktopStreamTicket(jobId: string): Promise<SovereignDesktopStreamTicket> {\n    assertReady(this.config);\n    const requestedJobId = jobId.trim();\n    if (!requestedJobId) throw new Error('Sovereign Agent job id is required.');\n    const body = await requestObject({\n      url: endpoint(this.config.agentApiUrl, jobPath(requestedJobId, '/live-workspace/desktop/stream-ticket')),\n      init: { method: 'POST', headers: headers(), credentials: 'include', body: '{}' },\n      fetcher: this.fetcher,\n      fallback: 'Sovereign Live Desktop stream ticket',\n    });\n    const stream = isObject(body.desktopStream) ? body.desktopStream : {};\n    const activationId = stringValue(stream.activationId)?.toLowerCase() ?? '';\n    const sessionBindingHash = stringValue(stream.sessionBindingHash)?.toLowerCase() ?? '';\n    const ticket = stringValue(stream.ticket) ?? '';\n    const expiresAtEpoch = typeof stream.expiresAtEpoch === 'number' ? stream.expiresAtEpoch : 0;\n    if (\n      stringValue(body.jobId) !== requestedJobId\n      || !SHA256_RE.test(activationId)\n      || !SHA256_RE.test(sessionBindingHash)\n      || !ticket.includes('.')\n      || expiresAtEpoch <= Math.floor(this.now() / 1000)\n      || stream.transport !== 'rfb-websocket'\n      || stream.viewOnly !== true\n    ) {\n      throw new Error('Sovereign Live Desktop returned no valid revision-bound RFB stream ticket.');\n    }\n    return { activationId, sessionBindingHash, ticket, expiresAtEpoch, transport: 'rfb-websocket', viewOnly: true };\n  }\n\n  async getDesktopFrame(jobId: string): Promise<SovereignDesktopFrameObservation> {\n'''
replace(client, frame_method, stream_method)

# App: remove blob polling and keep one continuous WebSocket descriptor per active job.
app = "src/App.tsx"
replace(
    app,
    "  const [desktopFrame, setDesktopFrame] = useState<{\n    readonly jobId: string;\n    readonly url: string;\n    readonly frameHash: string;\n    readonly observedAt: number;\n  } | null>(null);\n  const desktopFrameUrlRef = useRef<string | null>(null);\n",
    "  const [desktopStream, setDesktopStream] = useState<{\n    readonly jobId: string;\n    readonly url: string;\n    readonly activationId: string;\n    readonly sessionBindingHash: string;\n    readonly expiresAtEpoch: number;\n  } | null>(null);\n",
)
start = app.index("  useEffect(() => {\n    const jobId = canonicalAgentJob.jobId;\n    const canReadFrame = Boolean(")
end_marker = "  const evidenceWithReusableMemory = async (query: string): Promise<string> => {"
end = app.index(end_marker, start)
new_effect = '''  useEffect(() => {\n    const jobId = canonicalAgentJob.jobId;\n    const active = Boolean(\n      agentConfig.ready\n      && jobId\n      && canonicalAgentJob.status !== 'idle'\n      && canonicalAgentJob.status !== 'cleaned'\n    );\n    if (!active || !jobId) {\n      setDesktopStream(null);\n      return;\n    }\n    let cancelled = false;\n    const connect = async () => {\n      try {\n        const stream = await agentClient.getDesktopStreamTicket(jobId);\n        if (cancelled) return;\n        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';\n        const route = `/api/user/agent/jobs/${encodeURIComponent(jobId)}/live-workspace/desktop/stream`;\n        setDesktopStream({\n          jobId,\n          activationId: stream.activationId,\n          sessionBindingHash: stream.sessionBindingHash,\n          expiresAtEpoch: stream.expiresAtEpoch,\n          url: `${protocol}//${window.location.host}${route}?ticket=${encodeURIComponent(stream.ticket)}`,\n        });\n      } catch {\n        if (!cancelled) setDesktopStream(null);\n      }\n    };\n    void connect();\n    return () => { cancelled = true; };\n  }, [agentClient, agentConfig.ready, canonicalAgentJob.jobId, canonicalAgentJob.status]);\n\n'''
Path(app).write_text(Path(app).read_text("utf-8")[:start] + new_effect + Path(app).read_text("utf-8")[end:], "utf-8")
replace(app, "desktopFrame={desktopFrame}", "desktopStream={desktopStream}")

# Prop plumbing across monitor-first components.
for path in ("src/features/product/containers/BuilderContainer.tsx", "src/features/product/components/AgentEventStream.tsx"):
    text = Path(path).read_text("utf-8")
    text = text.replace("desktopFrame", "desktopStream")
    Path(path).write_text(text, "utf-8")

monitor = "src/features/product/components/LiveWorkspaceMonitor.tsx"
replace(monitor, "import React, { useEffect, useId, useMemo, useRef, useState } from 'react';\n", "import React, { useEffect, useId, useMemo, useRef, useState } from 'react';\nimport { VncScreen } from 'react-vnc';\n")
text = Path(monitor).read_text("utf-8").replace("desktopFrame", "desktopStream")
old_pane_start = text.index("function DesktopFramePane({")
old_pane_end = text.index("\nfunction EmptyProjectionPane()", old_pane_start)
new_pane = '''function DesktopFramePane({\n  stream,\n  job,\n}: {\n  readonly stream?: LiveWorkspaceMonitorProps['desktopStream'];\n  readonly job?: SovereignAgentJobSnapshot | null;\n}) {\n  return (\n    <div className="live-workspace-monitor__desktop" data-testid="live-workspace-monitor-desktop">\n      <div className="live-workspace-monitor__surface-toolbar">\n        <span style={{ color: C.green }}>DESKTOP · LIVE RFB STREAM</span>\n        <span>{stream ? 'CONNECTED · VIEW ONLY' : 'warte auf Desktop-Worker'}</span>\n      </div>\n      {stream ? (\n        <>\n          <div className="live-workspace-monitor__desktop-frame-wrap" data-testid="live-workspace-monitor-rfb-stream">\n            <VncScreen\n              key={`${stream.activationId}:${stream.expiresAtEpoch}`}\n              url={stream.url}\n              scaleViewport\n              viewOnly\n              rfbOptions={{ secure: false, shared: true, wsProtocols: ['binary'] }}\n              style={{ width: '100%', height: '100%', minHeight: 420 }}\n            />\n          </div>\n          <div className="live-workspace-monitor__metadata-grid">\n            <MetaPill label="Activation" value={shortIdentity(stream.activationId, 20)} />\n            <MetaPill label="Session" value={shortIdentity(stream.sessionBindingHash, 20)} />\n            <MetaPill label="Job" value={shortIdentity(job?.jobId, 18)} />\n          </div>\n        </>\n      ) : (\n        <div className="live-workspace-monitor__honest-empty" data-testid="live-workspace-monitor-desktop-unavailable">\n          <span aria-hidden="true">▣</span>\n          <p>\n            {job?.jobId\n              ? 'Der Monitor wartet auf den echten Desktop-Worker und seinen RFB-WebSocket. Es werden keine Ersatzbilder erzeugt.'\n              : 'Noch kein aktiver Workspace-Job. Der Live-Desktop startet mit dem ersten echten AttemptWorkspace.'}\n          </p>\n        </div>\n      )}\n    </div>\n  );\n}\n'''
text = text[:old_pane_start] + new_pane + text[old_pane_end:]
text = text.replace("<DesktopFramePane frame={desktopStream} job={job} />", "<DesktopFramePane stream={desktopStream} job={job} />")
Path(monitor).write_text(text, "utf-8")

# Add react-vnc dependency; pnpm will refresh the lockfile in CI.
package = Path("package.json")
text = package.read_text("utf-8")
replace_anchor = '    "react-redux": "^9.2.0",\n'
if '"react-vnc"' not in text:
    text = text.replace(replace_anchor, replace_anchor + '    "react-vnc": "^3.1.0",\n')
package.write_text(text, "utf-8")

print("BYTEBOT_LIVE_DESKTOP_STREAM_PATCH_APPLIED")
