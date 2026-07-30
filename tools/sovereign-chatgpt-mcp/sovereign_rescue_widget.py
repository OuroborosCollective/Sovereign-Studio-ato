"""Read-only ChatGPT Apps SDK entry point for Sovereign Rescue."""

from __future__ import annotations

from typing import Annotated, Any

from mcp import types
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field


WIDGET_URI = "ui://sovereign/rescue.v1.html"
WIDGET_MIME_TYPE = "text/html;profile=mcp-app"
WIDGET_DOMAIN = "https://sovereign-backend.arelorian.de"
RESCUE_APP_URL = "https://chat.arelorian.de/?rescue=1"


class SovereignRescueOfferOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schemaVersion: str = Field(description="Sovereign Rescue offer contract version.")
    product: str = Field(description="Stable product identifier.")
    promise: str = Field(description="User-facing Rescue promise.")
    free: dict[str, Any] = Field(description="Read-only free diagnosis boundary.")
    paid: dict[str, Any] = Field(description="Server-entitled Repair Pack boundary.")
    supportedFailureFamilies: list[str] = Field(description="Exactly supported v1 families.")
    appUrl: str = Field(description="Authenticated external Sovereign Rescue entry URL.")
    mutationPerformed: bool = Field(description="Always false for this read-only offer tool.")
    entitlementGranted: bool = Field(description="Always false; entitlement is backend-only.")
    secretValuesReturned: bool = Field(description="Always false.")


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
        "Shows the Sovereign Rescue free diagnosis and bounded Repair Pack offer. "
        "Authentication, repository access and checkout stay on Sovereign."
    ),
    "openai/widgetCSP": {
        "connect_domains": [],
        "resource_domains": [],
        "frame_domains": [],
        "redirect_domains": ["https://chat.arelorian.de"],
    },
}

TOOL_META = {
    "ui": {
        "resourceUri": WIDGET_URI,
        "visibility": ["model", "app"],
    },
    "openai/outputTemplate": WIDGET_URI,
    "openai/toolInvocation/invoking": "Sovereign Rescue wird vorbereitet …",
    "openai/toolInvocation/invoked": "Sovereign Rescue ist bereit.",
}

OFFER = {
    "schemaVersion": "sovereign.rescue-offer.v1",
    "product": "sovereign-rescue",
    "promise": (
        "Deine App ist kaputt. Sovereign findet die Ursache, repariert sie sicher "
        "und beweist, dass sie wieder funktioniert."
    ),
    "free": {
        "repositoryAndCiAnalysis": True,
        "exactRevision": True,
        "failureFamily": True,
        "affectedFiles": True,
        "riskClass": True,
        "repairProposal": True,
        "repositoryMutation": False,
    },
    "paid": {
        "serverSideEntitlementRequired": True,
        "isolatedWorkspace": True,
        "boundedCodeChange": True,
        "tests": True,
        "draftPr": True,
        "proofPack": True,
        "rollbackPlan": True,
        "autoMerge": False,
    },
    "supportedFailureFamilies": [
        "GitHub Actions / CI",
        "Docker Compose / Container",
        "PostgreSQL Migration / Schema",
    ],
    "appUrl": RESCUE_APP_URL,
    "mutationPerformed": False,
    "entitlementGranted": False,
    "secretValuesReturned": False,
}

WIDGET_HTML = r'''<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Sovereign Rescue</title>
  <style>
    :root { color-scheme: light dark; font-family: system-ui, sans-serif; }
    body { margin: 0; padding: 16px; background: Canvas; color: CanvasText; }
    main { display: grid; gap: 12px; }
    section { border: 1px solid color-mix(in srgb, CanvasText 18%, transparent); border-radius: 14px; padding: 14px; }
    h1, h2 { margin: 0 0 8px; }
    h1 { font-size: 1.18rem; }
    h2 { font-size: 1rem; }
    p { margin: 6px 0; }
    ul { margin: 6px 0 0; padding-left: 20px; }
    button { width: 100%; min-height: 48px; border-radius: 10px; border: 1px solid currentColor; font: inherit; font-weight: 750; }
    .muted { opacity: .72; font-size: .85rem; }
  </style>
</head>
<body>
<main>
  <section>
    <h1>Sovereign Rescue</h1>
    <p id="promise">Deine App ist kaputt. Sovereign findet die Ursache, repariert sie sicher und beweist, dass sie wieder funktioniert.</p>
  </section>
  <section>
    <h2>Kostenlos</h2>
    <p>Revisionsgenaue Diagnose, Fehlerfamilie, betroffene Dateien, Risiko und Reparaturvorschlag. Keine Repository-Änderung.</p>
  </section>
  <section>
    <h2>Repair Pack</h2>
    <p>Serverseitig autorisierte, begrenzte Reparatur im isolierten Workspace mit Tests, Draft PR, ProofPack und Rollbackplan.</p>
    <ul id="families"></ul>
  </section>
  <button id="open" type="button">Sovereign Rescue öffnen</button>
  <p id="status" class="muted" role="status" aria-live="polite">Anmeldung und GitHub-Zugang erfolgen ausschließlich auf Sovereign.</p>
</main>
<script>
(() => {
  'use strict';
  const APP_URL = 'https://chat.arelorian.de/?rescue=1';
  const families = document.getElementById('families');
  const status = document.getElementById('status');
  function render(payload) {
    const data = payload && typeof payload === 'object' ? payload : {};
    if (typeof data.promise === 'string') document.getElementById('promise').textContent = data.promise;
    families.replaceChildren();
    const values = Array.isArray(data.supportedFailureFamilies) ? data.supportedFailureFamilies : [];
    for (const value of values) {
      const item = document.createElement('li');
      item.textContent = String(value);
      families.appendChild(item);
    }
  }
  window.addEventListener('message', (event) => {
    if (!event || event.source !== window.parent) return;
    const message = event.data;
    if (!message || message.jsonrpc !== '2.0' || message.method !== 'ui/notifications/tool-result') return;
    const result = message.params && message.params.result;
    render(result && result.structuredContent ? result.structuredContent : result);
  });
  if (window.openai && window.openai.toolOutput) render(window.openai.toolOutput);
  document.getElementById('open').addEventListener('click', async () => {
    if (!window.openai || typeof window.openai.openExternal !== 'function') {
      status.textContent = 'Öffne https://chat.arelorian.de und wähle Rescue.';
      return;
    }
    await window.openai.openExternal({ href: APP_URL, redirectUrl: false });
    status.textContent = 'Sovereign Rescue wurde in einem sicheren externen Fenster geöffnet.';
  });
})();
</script>
</body>
</html>'''


def register_sovereign_rescue_widget(
    mcp: FastMCP,
    *,
    read_only_annotations: types.ToolAnnotations,
) -> None:
    @mcp.resource(
        WIDGET_URI,
        name="Sovereign Rescue",
        description="Read-only freemium Rescue entry; protected actions stay on Sovereign.",
        mime_type=WIDGET_MIME_TYPE,
        meta=RESOURCE_META,
    )
    def sovereign_rescue_resource() -> str:
        return WIDGET_HTML

    @mcp.tool(
        name="sovereign_rescue_offer",
        description=(
            "Use this when a user wants Sovereign to diagnose and safely repair a "
            "GitHub Actions/CI, Docker Compose/container, or PostgreSQL migration/schema failure."
        ),
        annotations=read_only_annotations,
        meta=TOOL_META,
        structured_output=True,
    )
    def sovereign_rescue_offer() -> Annotated[
        types.CallToolResult,
        SovereignRescueOfferOutput,
    ]:
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=OFFER["promise"])],
            structuredContent=dict(OFFER),
            _meta={
                "widget": "sovereign-rescue",
                "sensitiveValuesIncluded": False,
            },
        )
