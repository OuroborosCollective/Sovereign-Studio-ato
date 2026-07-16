"""Secure ChatGPT Apps SDK widget for one-time owner-controlled inputs."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP


WIDGET_URI = "ui://sovereign/owner_input.html"
WIDGET_MIME_TYPE = "text/html;profile=mcp-app"
WIDGET_DOMAIN = "https://sovereign-backend.arelorian.de"
OWNER_BACKEND_ORIGIN = WIDGET_DOMAIN

STRICT_CSP = {
    "connectDomains": [OWNER_BACKEND_ORIGIN],
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
        "Accepts one protected owner value directly into the Sovereign backend. "
        "The value is never returned to ChatGPT or MCP."
    ),
    "openai/widgetCSP": {
        "connect_domains": [OWNER_BACKEND_ORIGIN],
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
    <label for="adminKey">Sovereign Admin-Zugang</label>
    <input id="adminKey" type="password" autocomplete="off" spellcheck="false">

    <label for="protectedValue" id="valueLabel">Geschützter Wert</label>
    <input id="protectedValue" type="password" autocomplete="new-password" spellcheck="false">

    <label for="comment">Optionaler Kommentar ohne Zugangsdaten</label>
    <textarea id="comment" maxlength="1000"></textarea>

    <div class="row">
      <button id="submit" type="button">Sicher eintragen</button>
      <button id="deny" type="button">Ablehnen</button>
    </div>
    <p class="muted">Der geschützte Wert wird direkt per HTTPS an Sovereign übertragen. ChatGPT und MCP erhalten ihn nicht.</p>
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

  function clearSensitiveInputs() {
    byId('adminKey').value = '';
    byId('protectedValue').value = '';
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
    byId('valueLabel').textContent = clean(request.fieldLabel, 'Geschützter Wert');
    setStatus(request.status === 'pending' ? 'Bereit zur sicheren Eingabe.' : `Status: ${clean(request.status, 'unbekannt')}`);
  }

  async function resolve(decision) {
    if (state.busy || !state.request) return;
    const adminKey = byId('adminKey').value.trim();
    const comment = byId('comment').value.trim();
    const rawValue = decision === 'yes' ? byId('protectedValue').value : '';
    if (!adminKey) {
      setStatus('Admin-Zugang fehlt.', 'danger');
      return;
    }
    if (decision === 'yes' && !rawValue) {
      setStatus('Geschützter Wert fehlt.', 'danger');
      return;
    }

    state.busy = true;
    byId('submit').disabled = true;
    byId('deny').disabled = true;
    setStatus('Direkte geschützte Übertragung läuft…');
    const encoded = new TextEncoder().encode(rawValue);
    const url = BACKEND + '/api/admin/owner-input/requests/'
      + encodeURIComponent(state.request.id)
      + '/resolve?decision=' + encodeURIComponent(decision)
      + '&comment=' + encodeURIComponent(comment);
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Authorization': 'Bearer ' + adminKey,
          'Content-Type': 'application/octet-stream'
        },
        body: encoded,
        cache: 'no-store',
        credentials: 'omit'
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(clean(data.error, 'Sichere Eingabe fehlgeschlagen.'));
      byId('comment').value = '';
      byId('formSection').hidden = true;
      setStatus(decision === 'yes' ? 'Sicher gespeichert. Der Eingabepuffer wurde geleert.' : 'Anfrage wurde abgelehnt.', 'success');
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Sichere Eingabe fehlgeschlagen.', 'danger');
    } finally {
      encoded.fill(0);
      clearSensitiveInputs();
      state.busy = false;
      byId('submit').disabled = false;
      byId('deny').disabled = false;
    }
  }

  function acceptToolResult(event) {
    const message = event && event.data;
    if (!message || message.method !== 'ui/notifications/tool-result') return;
    const result = message.params && message.params.result;
    render(result && result.structuredContent ? result.structuredContent : result);
  }

  window.addEventListener('message', acceptToolResult);
  if (window.openai && window.openai.toolOutput) render(window.openai.toolOutput);
  byId('submit').addEventListener('click', () => resolve('yes'));
  byId('deny').addEventListener('click', () => resolve('no'));
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
