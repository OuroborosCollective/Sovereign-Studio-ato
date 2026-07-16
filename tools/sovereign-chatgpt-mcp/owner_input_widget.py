"""Secure ChatGPT Apps SDK widget for one-time owner-controlled inputs."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP


WIDGET_URI = "ui://sovereign/owner_input.html"
WIDGET_MIME_TYPE = "text/html;profile=mcp-app"
WIDGET_DOMAIN = "https://sovereign-backend.arelorian.de"
OWNER_BACKEND_ORIGIN = WIDGET_DOMAIN

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
    "openai/widgetDescription": (
        "Opens the authenticated Sovereign owner page for one protected input. "
        "The value is never entered into or returned through ChatGPT or MCP."
    ),
    "openai/widgetCSP": {
        "connect_domains": [],
        "resource_domains": [],
        "frame_domains": [],
        "redirect_domains": [OWNER_BACKEND_ORIGIN],
    },
}

TOOL_META = {
    "ui": {
        "resourceUri": WIDGET_URI,
        "visibility": ["model", "app"],
    },
    "openai/outputTemplate": WIDGET_URI,
    "openai/toolInvocation/invoking": "Geschützte Owner-Eingabe wird vorbereitet…",
    "openai/toolInvocation/invoked": "Geschützte Owner-Eingabe ist bereit.",
}

WIDGET_HTML = r'''<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
  <title>Sovereign geschützte Eingabe</title>
  <style>
    :root { color-scheme: light dark; font-family: system-ui, sans-serif; }
    * { box-sizing: border-box; }
    body { margin: 0; padding: 16px; background: Canvas; color: CanvasText; }
    main { display: grid; gap: 14px; max-width: 620px; margin: 0 auto; }
    section { border: 1px solid color-mix(in srgb, CanvasText 18%, transparent); border-radius: 14px; padding: 16px; }
    h1 { margin: 0 0 8px; font-size: 1.15rem; }
    p { margin: 6px 0; overflow-wrap: anywhere; }
    .muted { opacity: .72; font-size: .86rem; }
    .status { min-height: 1.4em; font-weight: 650; }
    label { display: block; margin: 14px 0 6px; font-size: .86rem; font-weight: 700; }
    input, textarea, button { width: 100%; min-height: 48px; font: inherit; border-radius: 10px; }
    input, textarea { border: 1px solid color-mix(in srgb, CanvasText 24%, transparent); padding: 11px 12px; background: Canvas; color: CanvasText; }
    textarea { min-height: 78px; resize: vertical; }
    button { border: 1px solid currentColor; padding: 10px 14px; font-weight: 750; cursor: pointer; }
    button:disabled { opacity: .48; cursor: not-allowed; }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 14px; }
    .danger { color: #d1242f; }
    .success { color: #1a7f37; }
    @media (max-width: 420px) { .row { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
<main aria-labelledby="title">
  <section>
    <h1 id="title">Geschützte Owner-Eingabe</h1>
    <p id="reason">Warte auf eine bestätigte Anfrage.</p>
    <p class="muted" id="meta"></p>
    <p class="status" id="status" role="status" aria-live="polite"></p>
  </section>
  <section id="formSection" hidden>
    <p>Admin-Zugang und geschützter Wert werden ausschließlich auf der HTTPS-Seite des Sovereign-Backends eingegeben.</p>
    <button id="openOwnerPage" type="button">Sichere Sovereign-Seite öffnen</button>
    <p class="muted"><a id="ownerLink" target="_blank" rel="noopener noreferrer">Direktlink zur sicheren Owner-Seite</a></p>
    <p class="muted">Das Widget nimmt keine Zugangsdaten an und überträgt keine geschützten Werte.</p>
  </section>
</main>
<script>
(() => {
  'use strict';
  const BACKEND = 'https://sovereign-backend.arelorian.de';
  const byId = (id) => document.getElementById(id);
  const state = { request: null, busy: false };

  function clean(value, fallback = '') {
    return typeof value === 'string' && value.trim() ? value.trim() : fallback;
  }

  function setStatus(message, kind = '') {
    const node = byId('status');
    node.textContent = message;
    node.className = `status ${kind}`.trim();
  }

  function requestFrom(payload) {
    const data = payload && typeof payload === 'object' ? payload : {};
    const request = data.request && typeof data.request === 'object' ? data.request : null;
    return request && clean(request.id) ? request : null;
  }

  function render(payload) {
    state.request = requestFrom(payload);
    const request = state.request;
    byId('formSection').hidden = !request || request.status !== 'pending';
    if (!request) {
      byId('reason').textContent = 'Keine auswertbare Owner-Anfrage erhalten.';
      byId('meta').textContent = '';
      setStatus('Nicht bereit.', 'danger');
      return;
    }
    byId('reason').textContent = clean(request.reason, 'Geschützter Serverwert erforderlich.');
    byId('meta').textContent = `${clean(request.targetLabel, 'Owner-Ziel')} · gültig bis ${clean(request.expiresAt, 'unbekannt')}`;
    const ownerUrl = BACKEND + '/owner-approvals?request_id=' + encodeURIComponent(request.id);
    byId('ownerLink').href = ownerUrl;
    setStatus(request.status === 'pending' ? 'Bereit zum Öffnen der sicheren Sovereign-Seite.' : `Status: ${clean(request.status, 'unbekannt')}`);
  }

  async function openOwnerPage() {
    if (state.busy || !state.request) return;
    const button = byId('openOwnerPage');
    const url = BACKEND + '/owner-approvals?request_id=' + encodeURIComponent(state.request.id);
    state.busy = true;
    button.disabled = true;
    setStatus('Sichere Sovereign-Seite wird geöffnet…');
    try {
      if (!window.openai || typeof window.openai.openExternal !== 'function') {
        throw new Error('ChatGPT kann die sichere Seite hier nicht automatisch öffnen. Bitte den Direktlink verwenden.');
      }
      await window.openai.openExternal({ href: url, redirectUrl: false });
      setStatus('Sichere Sovereign-Seite geöffnet. Die Anfrage ist erst nach dortiger Bestätigung abgeschlossen.');
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Sichere Seite konnte nicht geöffnet werden.', 'danger');
    } finally {
      state.busy = false;
      button.disabled = false;
    }
  }

  function acceptToolResult(event) {
    if (!event || event.source !== window.parent) return;
    const message = event.data;
    if (!message || message.jsonrpc !== '2.0' || message.method !== 'ui/notifications/tool-result') return;
    const result = message.params && message.params.result;
    render(result && result.structuredContent ? result.structuredContent : result);
  }

  window.addEventListener('message', acceptToolResult);
  if (window.openai && window.openai.toolOutput) render(window.openai.toolOutput);
  byId('openOwnerPage').addEventListener('click', openOwnerPage);
})();
</script>
</body>
</html>'''


def register_owner_input_widget(mcp: FastMCP) -> None:
    @mcp.resource(
        WIDGET_URI,
        name="Sovereign geschützte Owner-Eingabe",
        description="Direct owner-only credential entry without exposing protected values to ChatGPT or MCP.",
        mime_type=WIDGET_MIME_TYPE,
        meta=RESOURCE_META,
    )
    def sovereign_owner_input_widget() -> str:
        return WIDGET_HTML
