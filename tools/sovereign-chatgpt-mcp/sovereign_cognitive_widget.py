"""Apps SDK widget and metadata for the Sovereign cognitive architecture."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from mcp import types
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field


WIDGET_URI = "ui://sovereign/dev_dashboard.v2.html"
WIDGET_MIME_TYPE = "text/html;profile=mcp-app"
WIDGET_DOMAIN = "https://sovereign-backend.arelorian.de"


class SovereignCognitiveStatusOutput(BaseModel):
    """Model-visible, secret-free status contract for the cognitive widget."""

    model_config = ConfigDict(extra="allow")

    manifest: dict[str, Any] = Field(
        description="Static eight-role, double-loop and Draft-PR-only manifest."
    )
    ok: bool = Field(description="Whether current control-plane evidence is ready.")
    status: str = Field(description="Bounded overall runtime status family.")
    summary: str = Field(description="Human-readable evidence summary.")
    controlPlane: dict[str, Any] = Field(
        description="Bounded broker and control-plane evidence."
    )
    agentsSdkState: str = Field(
        description="Latest persisted Agents SDK state or configuration state."
    )
    controllerRuns: dict[str, Any] = Field(
        description="Bounded persisted run, task, event and failure evidence."
    )
    draftPr: dict[str, Any] = Field(
        description="Draft PR evidence; never authorizes merge automatically."
    )
    secretsExposed: bool = Field(
        default=False,
        description="Always false; protected values are excluded from this tool.",
    )


STRICT_CSP = {
    "connectDomains": [],
    "resourceDomains": [],
    "frameDomains": [],
}

RESOURCE_META = {
    "ui": {
        "csp": STRICT_CSP,
        "domain": WIDGET_DOMAIN,
        "prefersBorder": True,
    },
    "openai/widgetDomain": WIDGET_DOMAIN,
    "openai/widgetDescription": "Shows evidence-backed Sovereign swarm, control-plane and Draft PR status.",
    "openai/widgetCSP": {
        "connect_domains": [],
        "resource_domains": [],
        "frame_domains": [],
        "redirect_domains": [],
    },
}

TOOL_META = {
    "ui": {
        "resourceUri": WIDGET_URI,
        "visibility": ["model", "app"],
    },
    "openai/ui": {"entrypoints": [{"type": "global"}, {"type": "thread"}]},
    "openai/outputTemplate": WIDGET_URI,
    "openai/toolInvocation/invoking": "Sovereign Nervensystem prüft reale Runtime-Evidence…",
    "openai/toolInvocation/invoked": "Sovereign Runtime-Evidence wurde geladen.",
}

WIDGET_MANIFEST = {
    "schema": 1,
    "agentCount": 8,
    "agents": [
        {"index": 0, "role": "dispatcher", "name": "The Dispatcher"},
        {"index": 1, "role": "data_storage", "name": "Data & Storage Node"},
        {"index": 2, "role": "business_core", "name": "Business & Core Logic Node"},
        {"index": 3, "role": "endpoint_bridge", "name": "Endpoint & Bridge Node"},
        {"index": 4, "role": "chat_cognitive", "name": "Functional Chat & Cognitive Action Node"},
        {"index": 5, "role": "ui_accessibility", "name": "UI, CSS & Accessibility Node"},
        {"index": 6, "role": "predictive_qa", "name": "Predictive Build Nervous System & QA Node"},
        {"index": 7, "role": "judge", "name": "The Judge"},
    ],
    "doubleLoop": [
        "dispatcher_plan",
        "worker_pass_one",
        "judge_checkpoint_one",
        "worker_refinement_pass_two",
        "judge_final_verdict",
    ],
    "releaseMode": "draft_pr_only",
    "autoMerge": False,
    "runtimeTruthRequired": True,
}

WIDGET_HTML = r'''<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Sovereign Cognitive Dashboard</title>
  <style>
    :root { color-scheme: light dark; font-family: system-ui, sans-serif; }
    body { margin: 0; padding: 16px; background: Canvas; color: CanvasText; }
    main { display: grid; gap: 14px; max-width: 900px; margin: 0 auto; }
    section { border: 1px solid color-mix(in srgb, CanvasText 18%, transparent); border-radius: 14px; padding: 14px; }
    h1, h2 { margin: 0 0 10px; }
    h1 { font-size: 1.15rem; }
    h2 { font-size: 1rem; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 10px; }
    .card { border: 1px solid color-mix(in srgb, CanvasText 14%, transparent); border-radius: 10px; padding: 10px; }
    .label { font-size: .78rem; opacity: .72; }
    .value { font-weight: 700; overflow-wrap: anywhere; }
    .muted { opacity: .72; font-size: .82rem; margin: 12px 0 6px; }
    ul { margin: 0; padding-left: 20px; }
    .run-list { display: grid; gap: 8px; }
    .run-list li { overflow-wrap: anywhere; }
    button { min-height: 48px; border-radius: 10px; border: 1px solid currentColor; padding: 0 16px; font: inherit; font-weight: 700; }
    input { min-height: 44px; max-width: 100%; box-sizing: border-box; font: inherit; margin: 8px; }
    button:focus-visible, input:focus-visible { outline: 3px solid Highlight; outline-offset: 3px; }
    button:disabled { opacity: .48; cursor: not-allowed; }
    #message { min-height: 1.3em; }
  </style>
</head>
<body>
<main aria-labelledby="title">
  <section>
    <h1 id="title">Sovereign Cognitive Architecture</h1>
    <div id="message" role="status" aria-live="polite">Warte auf echte Runtime-Evidence.</div>
  </section>
  <section aria-labelledby="runtime-title">
    <h2 id="runtime-title">Runtime</h2>
    <div class="grid">
      <div class="card"><div class="label">Control Plane</div><div class="value" id="control-plane">unbekannt</div></div>
      <div class="card"><div class="label">Agents SDK</div><div class="value" id="agents-sdk">unbekannt</div></div>
      <div class="card"><div class="label">Release-Modus</div><div class="value" id="release-mode">unbekannt</div></div>
      <div class="card"><div class="label">Double Loop</div><div class="value" id="double-loop">unbekannt</div></div>
    </div>
  </section>
  <section aria-labelledby="agents-title">
    <h2 id="agents-title">Acht Rollen</h2>
    <ul id="agents"></ul>
  </section>
  <section aria-labelledby="runs-title">
    <h2 id="runs-title">Persistierte Agents-SDK-Läufe</h2>
    <div class="grid">
      <div class="card"><div class="label">Letzter Status</div><div class="value" id="latest-run-status">nicht belegt</div></div>
      <div class="card"><div class="label">Run-ID</div><div class="value" id="latest-run-id">nicht belegt</div></div>
      <div class="card"><div class="label">Aktiver Agent</div><div class="value" id="latest-agent">nicht belegt</div></div>
      <div class="card"><div class="label">Nächste Aktion</div><div class="value" id="latest-next-action">nicht belegt</div></div>
    </div>
    <div class="muted">Aktuelle Agentenaktivität</div>
    <ul id="run-events" class="run-list" aria-live="polite"><li>Keine persistierte Agentenaktivität geladen.</li></ul>
    <div class="muted">Letzte Läufe</div>
    <ul id="recent-runs" class="run-list"><li>Keine persistierten Läufe geladen.</li></ul>
    <button id="refresh-runs" type="button" aria-label="Persistierte Agents-SDK-Läufe erneut laden">Runs aktualisieren</button>
  </section>
  <section aria-labelledby="evidence-title">
    <h2 id="evidence-title">Evidence und Draft PR</h2>
    <div id="draft-pr">Kein belegter Draft PR.</div>
    <button id="approve" type="button" disabled aria-label="Belegten Draft PR zur Prüfung an ChatGPT übergeben">PR prüfen</button>
  </section>
  <section aria-labelledby="repository-title">
    <h2 id="repository-title">Repository und Release-Evidence</h2>
    <label for="workspace-id">Bestehende Workspace-ID</label>
    <input id="workspace-id" type="text" maxlength="84" placeholder="job-…" autocomplete="off">
    <button id="load-repository" type="button">Revisionen lesen</button>
    <ul id="repository-evidence"><li>Keine Repository-Evidence geladen.</li></ul>
    <h3>Deployment-Nachweise</h3>
    <ul id="deployment-evidence"><li>Keine Deployment-Evidence geladen.</li></ul>
    <label for="pr-number">PR-Nummer</label>
    <input id="pr-number" type="text" inputmode="numeric" maxlength="9" autocomplete="off">
    <button id="load-pr" type="button">PR und CI lesen</button>
    <ul id="pr-evidence"><li>Keine PR-Evidence geladen.</li></ul>
    <p class="muted">Repository, CI und Deployment benötigen jeweils eigene Nachweise.</p>
  </section>
</main>
<script>
(() => {
  'use strict';
  const byId = (id) => document.getElementById(id);
  const state = { draftPr: null };

  function text(value, fallback = 'unbekannt') {
    return typeof value === 'string' && value.trim() ? value.trim() : fallback;
  }

  function render(payload) {
    const data = payload && typeof payload === 'object' ? payload : {};
    if (data.ok !== true) {
      state.draftPr = null;
      byId('approve').disabled = true;
      byId('message').textContent = 'Status blockiert oder unvollständig. Evidence ist nicht aktualisiert.';
      byId('control-plane').textContent = text(data.status, 'nicht belegt');
      return;
    }
    const manifest = data.manifest && typeof data.manifest === 'object' ? data.manifest : {};
    const control = data.controlPlane && typeof data.controlPlane === 'object' ? data.controlPlane : {};
    byId('control-plane').textContent = text(control.status || data.status);
    byId('agents-sdk').textContent = text(data.agentsSdkState, 'nicht belegt');
    byId('release-mode').textContent = text(manifest.releaseMode, 'draft_pr_only');
    byId('double-loop').textContent = Array.isArray(manifest.doubleLoop) ? manifest.doubleLoop.join(' → ') : 'nicht belegt';

    const list = byId('agents');
    list.replaceChildren();
    const agents = Array.isArray(manifest.agents) ? manifest.agents : [];
    for (const agent of agents) {
      const item = document.createElement('li');
      item.textContent = `${agent.index}: ${text(agent.name)} — ${text(agent.role)}`;
      list.appendChild(item);
    }

    const controller = data.controllerRuns && typeof data.controllerRuns === 'object' ? data.controllerRuns : {};
    const latest = controller.latestRun && typeof controller.latestRun === 'object' ? controller.latestRun : {};
    const latestRun = latest.run && typeof latest.run === 'object' ? latest.run : {};
    const events = Array.isArray(latest.events) ? latest.events : [];
    const tasks = Array.isArray(latest.tasks) ? latest.tasks : [];
    const activity = events.length ? events : tasks;
    const newestActivity = activity.length ? activity[activity.length - 1] : {};
    byId('latest-run-status').textContent = text(latestRun.status, text(controller.status, 'nicht belegt'));
    byId('latest-run-id').textContent = text(latestRun.runId, 'nicht belegt');
    byId('latest-agent').textContent = text(newestActivity.agentId, 'nicht belegt');
    byId('latest-next-action').textContent = text(latestRun.nextAction || newestActivity.nextAction, 'nicht belegt');

    const eventList = byId('run-events');
    eventList.replaceChildren();
    const visibleActivity = activity.slice(-10).reverse();
    if (!visibleActivity.length) {
      const item = document.createElement('li');
      item.textContent = 'Keine persistierte Agentenaktivität belegt.';
      eventList.appendChild(item);
    }
    for (const event of visibleActivity) {
      const item = document.createElement('li');
      const actor = text(event.agentId, 'runtime');
      const status = text(event.status || event.type, 'Status unbekannt');
      item.textContent = `${actor}: ${status} — ${text(event.summary, 'Keine Zusammenfassung.')}`;
      eventList.appendChild(item);
    }

    const recentList = byId('recent-runs');
    recentList.replaceChildren();
    const runs = Array.isArray(controller.runs) ? controller.runs : [];
    if (!runs.length) {
      const item = document.createElement('li');
      item.textContent = 'Keine persistierten Agents-SDK-Läufe belegt.';
      recentList.appendChild(item);
    }
    for (const run of runs) {
      const item = document.createElement('li');
      item.textContent = `${text(run.status)} — ${text(run.runId)} — ${text(run.nextAction, 'keine nächste Aktion')}`;
      recentList.appendChild(item);
    }

    const draftPr = data.draftPr && typeof data.draftPr === 'object' ? data.draftPr : null;
    const verified = draftPr && draftPr.ready === true && Number.isInteger(draftPr.number) && typeof draftPr.headSha === 'string' && /^[0-9a-f]{40}$/.test(draftPr.headSha) && draftPr.number > 0;
    state.draftPr = verified ? draftPr : null;
    byId('draft-pr').textContent = verified
      ? `Draft PR #${draftPr.number}, Head ${draftPr.headSha}`
      : 'Kein belegter Draft PR.';
    byId('approve').disabled = !verified;
    byId('message').textContent = text(data.summary, 'Status empfangen; Runtime-Verifikation ist separat erforderlich.');
  }

  const pending = new Map();
  let sequence = 0;
  let bridgeReady = false;
  function rpc(method, params) {
    return new Promise((resolve, reject) => {
      const id = 'sovott-ui-' + (++sequence);
      const timer = setTimeout(() => {
        pending.delete(id);
        reject(new Error('Host-Antwort fehlt.'));
      }, 90000);
      pending.set(id, { resolve, reject, timer });
      window.parent.postMessage({ jsonrpc: '2.0', id, method, params }, '*');
    });
  }
  function resultData(result) {
    if (!result || result.isError === true || !result.structuredContent ||
        typeof result.structuredContent !== 'object' || Array.isArray(result.structuredContent)) {
      throw new Error('Kein gültiges strukturiertes Tool-Ergebnis.');
    }
    return result.structuredContent;
  }
  const allowedTools = new Set(['sovereign_cognitive_architecture_status', 'repository_revision_resolve', 'repository_pr_status']);
  async function callTool(name, args) {
    if (!bridgeReady || !allowedTools.has(name)) throw new Error('Host-Verbindung noch nicht bereit.');
    return resultData(await rpc('tools/call', { name, arguments: args }));
  }
  function acceptToolResult(event) {
    const message = event && event.data;
    if (!event || event.source !== window.parent || !message || message.jsonrpc !== '2.0') return;
    if (Object.prototype.hasOwnProperty.call(message, 'id') && pending.has(message.id)) {
      const request = pending.get(message.id);
      pending.delete(message.id);
      clearTimeout(request.timer);
      if (message.error) request.reject(new Error('Host-Aufruf abgelehnt.'));
      else if (Object.prototype.hasOwnProperty.call(message, 'result')) request.resolve(message.result);
      else request.reject(new Error('Ungültige Host-Antwort.'));
      return;
    }
    if (message.method === 'ui/notifications/tool-result') {
      try {
        const data = resultData(message.params);
        if (data.ok === false || (data.manifest && data.controlPlane)) render(data);
      } catch (_) {
        state.draftPr = null;
        byId('approve').disabled = true;
        byId('message').textContent = 'Tool-Ergebnis fehlerhaft. Evidence ist nicht aktualisiert.';
      }
    }
  }

  window.addEventListener('message', acceptToolResult);
  if (window.openai && window.openai.toolOutput) render(window.openai.toolOutput);
  if (window.parent !== window) {
    rpc('ui/initialize', {
      protocolVersion: '2026-01-26',
      appInfo: { name: 'Sovott Evidence Dashboard', version: '2.1.0' },
      appCapabilities: {}
    }).then((host) => {
      if (!host || host.protocolVersion !== '2026-01-26') throw new Error('MCP-App-Protokoll nicht unterstützt.');
      bridgeReady = true;
      window.parent.postMessage({ jsonrpc: '2.0', method: 'ui/notifications/initialized', params: {} }, '*');
    }).catch(() => {
      byId('message').textContent = 'Host-Verbindung nicht verfügbar. Evidence ist nicht aktualisiert.';
    });
  }
  async function action(button, work) {
    button.disabled = true;
    try { await work(); }
    catch (error) {
      state.draftPr = null;
      byId('approve').disabled = true;
      byId('message').textContent = error.message + ' Evidence ist nicht aktualisiert.';
    } finally { button.disabled = button.id === 'approve' && !state.draftPr; }
  }
  byId('refresh-runs').addEventListener('click', () => action(byId('refresh-runs'), async () => {
    if (bridgeReady) render(await callTool('sovereign_cognitive_architecture_status', {}));
    else if (window.openai && typeof window.openai.sendFollowUpMessage === 'function') {
      await window.openai.sendFollowUpMessage({
        prompt: 'Rufe sovereign_cognitive_architecture_status erneut auf und zeige die aktuelle persistierte Agents-SDK-Run- und Agenten-Evidence im bestehenden Sovereign Widget.'
      });
      byId('message').textContent = 'Aktualisierung angefragt; Evidence steht noch aus.';
    } else throw new Error('Keine Host-Verbindung verfügbar.');
  }));
  function showEvidence(id, data, fields) {
    const list = byId(id);
    list.replaceChildren();
    for (const key of fields) {
      const value = data[key];
      const item = document.createElement('li');
      item.textContent = key + ': ' + (typeof value === 'string' ? value.slice(0, 240) :
        typeof value === 'boolean' ? String(value) : 'nicht belegt');
      list.appendChild(item);
    }
  }
  byId('load-repository').addEventListener('click', () => action(byId('load-repository'), async () => {
    const workspace = byId('workspace-id').value.trim();
    byId('repository-evidence').replaceChildren();
    byId('deployment-evidence').replaceChildren();
    if (!/^job-[a-z0-9-]{1,80}$/.test(workspace)) throw new Error('Gültige Workspace-ID erforderlich.');
    const data = await callTool('repository_revision_resolve', {
      workspace_id: workspace, include_ci: true, include_deployed_mcp: true
    });
    if (data.ok === true && data.workspaceId !== workspace) throw new Error('Workspace-Evidence gehört zu einem anderen Scope.');
    showEvidence('repository-evidence', data, ['status', 'workspaceHeadSha', 'currentBaseHeadSha', 'prHeadSha', 'worktreeClean']);
    showEvidence('deployment-evidence', data.deployedMcpEvidence || {}, ['status', 'revision', 'revisionVerified', 'digestVerified']);
    byId('message').textContent = data.ok === true ? 'Repository-Evidence gelesen. Deployment-Nachweise separat prüfen.' : 'Repository-Evidence unvollständig oder blockiert.';
  }));
  byId('load-pr').addEventListener('click', () => action(byId('load-pr'), async () => {
    const raw = byId('pr-number').value.trim();
    byId('pr-evidence').replaceChildren();
    if (!/^[1-9][0-9]{0,8}$/.test(raw)) throw new Error('Positive PR-Nummer erforderlich.');
    const data = await callTool('repository_pr_status', { pr_number: Number(raw) });
    if (data.ok === true && data.pr_number !== Number(raw)) throw new Error('PR-Evidence gehört zu einem anderen Scope.');
    showEvidence('pr-evidence', data, ['status', 'head_sha', 'state', 'draft', 'mergeable']);
    const checks = data.checks && typeof data.checks === 'object' ? data.checks : {};
    const bound = /^[0-9a-f]{40}$/.test(data.head_sha || '') && checks.head_sha === data.head_sha;
    const rows = bound && Array.isArray(checks.checks) ? checks.checks.slice(0, 60) : [];
    const list = byId('pr-evidence');
    const summary = document.createElement('li');
    summary.textContent = bound ? 'CI an PR-Head gebunden; Einzelprüfungen:' : 'CI-Head fehlt oder weicht ab. CI nicht verifiziert.';
    list.appendChild(summary);
    for (const check of rows) {
      const item = document.createElement('li');
      item.textContent = text(check.name) + ': ' + text(check.status) + ' / ' + text(check.conclusion, 'kein Ergebnis');
      list.appendChild(item);
    }
    byId('message').textContent = data.ok === true ? 'PR-Readback gelesen; keine Merge-Freigabe erteilt.' : 'PR-Readback blockiert oder unvollständig.';
  }));

  byId('approve').addEventListener('click', () => action(byId('approve'), async () => {
    const pr = state.draftPr;
    if (!pr || !window.openai || typeof window.openai.sendFollowUpMessage !== 'function') {
      throw new Error('Belegter PR und ChatGPT-Nachrichtenpfad erforderlich.');
    }
    await window.openai.sendFollowUpMessage({
      prompt: 'Prüfe Draft PR #' + pr.number + ' mit erwartetem Head-SHA ' + pr.headSha +
        '. Prüfe zuerst repository_pr_status. Führe keine Merge-Aktion ohne eine weitere ausdrückliche Bestätigung aus.'
    });
  }));
})();
</script>
</body>
</html>'''


def register_sovereign_cognitive_widget(
    mcp: FastMCP,
    *,
    read_only_annotations: types.ToolAnnotations,
    status_provider: Callable[[], dict[str, Any]],
) -> None:
    @mcp.resource(
        WIDGET_URI,
        name="Sovereign Cognitive Dashboard",
        description="Evidence-only dashboard for the eight-role Sovereign cognitive architecture.",
        mime_type=WIDGET_MIME_TYPE,
        meta=RESOURCE_META,
    )
    def sovereign_cognitive_dashboard() -> str:
        return WIDGET_HTML

    @mcp.tool(
        name="sovereign_cognitive_architecture_status",
        description="Use this when the user wants the current evidence-backed Sovereign swarm and control-plane status.",
        annotations=read_only_annotations,
        meta=TOOL_META,
        structured_output=True,
    )
    def sovereign_cognitive_architecture_status() -> Annotated[
        types.CallToolResult,
        SovereignCognitiveStatusOutput,
    ]:
        payload = {"manifest": WIDGET_MANIFEST, **status_provider()}
        summary = str(payload.get("summary") or "Sovereign cognitive architecture status loaded.")
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=summary)],
            structuredContent=payload,
            _meta={
                "widget": "sovereign-cognitive-dashboard",
                "sensitiveValuesIncluded": False,
            },
        )
