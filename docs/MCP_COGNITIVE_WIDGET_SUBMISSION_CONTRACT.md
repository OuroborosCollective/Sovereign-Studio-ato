# MCP Cognitive Widget Submission Contract und Handoff

Stand: 23. Juli 2026

## 1. Zweck

Dieses Dokument ist die kanonische Übergabe für das ChatGPT-App-Widget
`sovereign_cognitive_architecture_status` und die Resource
`ui://sovereign/dev_dashboard.v2.html`.

Es verhindert zwei konkret entdeckte Fehler:

1. Das Tool hatte wegen eines direkten `CallToolResult` kein eigenes fachliches
   `outputSchema`.
2. Die App-Prüfung meldete für die Widget-Vorlage keine feste Domain, obwohl nur
   das interne Resource-Objekt geprüft wurde und ein alter Template-URI im Cache
   beziehungsweise im Workflow verblieben war.

## 2. Kanonische Dateien

- `tools/sovereign-chatgpt-mcp/sovereign_cognitive_widget.py`
- `tools/sovereign-chatgpt-mcp/test_sovereign_cognitive_widget.py`
- `.github/workflows/sovereign-chatgpt-mcp.yml`
- `tools/sovereign-chatgpt-mcp/output_contracts.py`
- `tools/sovereign-chatgpt-mcp/launcher.py`
- `tools/sovereign-chatgpt-mcp/server.py`

## 3. Verbindlicher Toolvertrag

Toolname:

`sovereign_cognitive_architecture_status`

Der Toolhandler gibt weiterhin einen vollständigen `types.CallToolResult` zurück,
weil das Widget zusätzliches `_meta` benötigt. Der Rückgabetyp muss jedoch als

```python
Annotated[types.CallToolResult, SovereignCognitiveStatusOutput]
```

annotiert sein.

`SovereignCognitiveStatusOutput` ist ein Pydantic-Modell. Das Modell muss
mindestens folgende Felder beschreiben:

- `manifest`
- `ok`
- `status`
- `summary`
- `controlPlane`
- `agentsSdkState`
- `controllerRuns`
- `draftPr`
- `secretsExposed`

Damit erzeugt FastMCP ein echtes tool-spezifisches `outputSchema`. Ein nur
nachträglich eingesetztes generisches `ToolOutputEnvelope` ist für diesen
Widgetvertrag nicht ausreichend, weil App-Prüfungen und Modelle die konkrete
Struktur des kognitiven Status erkennen müssen.

Der Handler muss `structuredContent` liefern, das dem Modell entspricht.
Rohsecrets, geschützte Werte, Browser-Cookies, Provider-Keys und rohe
Providerantworten sind verboten.

## 4. Verbindlicher Resourcevertrag

Aktueller URI:

`ui://sovereign/dev_dashboard.v2.html`

Der alte URI

`ui://sovereign/dev_dashboard.html`

darf nicht mehr registriert oder in CI-/Deploymentverträgen behauptet werden.
Die Versionierung verhindert, dass ein alter Widget-Template-Cache weiterhin
fehlende Metadaten meldet.

MIME-Type:

`text/html;profile=mcp-app`

Feste Widget-Origin:

`https://sovereign-backend.arelorian.de`

Die Domain muss auf der Resource sowohl über den Standardvertrag als auch über
den ChatGPT-Kompatibilitätsvertrag vorhanden sein:

```python
RESOURCE_META = {
    "ui": {
        "domain": "https://sovereign-backend.arelorian.de",
        "csp": {...},
        "prefersBorder": True,
    },
    "openai/widgetDomain": "https://sovereign-backend.arelorian.de",
}
```

Die Domain ist eine Origin ohne Pfad. Sie darf nicht dynamisch pro Request,
User oder Workspace erzeugt werden. Ein zukünftiger Domainwechsel verlangt:

1. bestätigte Domain-/TLS-/Erreichbarkeit,
2. Codeänderung an beiden Metadatenfeldern,
3. neue versionierte `ui://`-URI,
4. vollständige CI,
5. exakten MCP-Self-Update,
6. erneuten App-Scan.

## 5. CSP

Das Widget führt keine externen Fetches, Bilder, Fonts oder Subframes aus.
Deshalb bleibt die CSP fail-closed:

```python
{
    "connectDomains": [],
    "resourceDomains": [],
    "frameDomains": [],
}
```

Auch der Legacy-Kompatibilitätsvertrag
`openai/widgetCSP` bleibt leer und enthält zusätzlich keine Redirect-Domains.
Sobald das Widget später eine externe Domain benötigt, muss die konkrete Origin
explizit allowlistet und durch einen neuen App-Review geprüft werden.

## 6. Pflichtprüfungen

Ein interner Check von `mcp._resource_manager.list_resources()` allein reicht
nicht. Folgende Ebenen müssen alle grün sein:

### 6.1 Toolmanager

- Tool existiert genau einmal.
- `tool.output_schema` ist ein Objekt.
- `properties` enthält mindestens `manifest` und `controllerRuns`.

### 6.2 MCP `tools/list`

- `mcp.list_tools()` serialisiert `outputSchema`.
- Das serialisierte Schema entspricht dem internen Tool-Schema.

### 6.3 Resource-Manager

- URI ist exakt `ui://sovereign/dev_dashboard.v2.html`.
- `meta.ui.domain` entspricht der festen Widget-Domain.
- `meta["openai/widgetDomain"]` entspricht derselben Domain.

### 6.4 MCP `resources/list`

- `mcp.list_resources()` enthält den neuen URI.
- `model_dump(by_alias=True)` enthält:
  - `_meta.ui.domain`
  - `_meta["openai/widgetDomain"]`

### 6.5 MCP `resources/read`

- `mcp.read_resource(...)` liefert den MCP-App-MIME-Type.
- Der gelesene Resource-Inhalt enthält dieselben Domain-Metadaten.

### 6.6 Produktionscontainer

Nach Deployment müssen dieselben Prüfungen innerhalb des tatsächlich laufenden
Containers `sovereign-chatgpt-mcp` wiederholt werden. Ein lokaler Unit-Test ist
kein Produktionsbeweis.

## 7. CI- und Deploymentvertrag

Die Workflowdatei `.github/workflows/sovereign-chatgpt-mcp.yml` muss:

- den neuen URI prüfen,
- das konkrete kognitive `outputSchema` prüfen,
- beide Domain-Metadaten prüfen,
- dieselben Prüfungen im veröffentlichten und installierten Container ausführen.

Nach Merge:

1. exakte Merge-Revision lesen,
2. immutable MCP-Image-Digest für diese Revision prüfen,
3. MCP-Self-Update beziehungsweise Main-Deployment abschließen,
4. installierte Revision und Digest lesen,
5. `mcp_control_plane_status` prüfen,
6. MCP-Initialize-/Tools-/Resources-Protokoll prüfen,
7. ChatGPT-App-Verbindung beziehungsweise Submission-Entwurf neu scannen.

Ein grüner PR allein behebt die Warnung im bereits laufenden MCP nicht. Die
warnende App-Prüfung sieht erst nach Installation und erneutem Scan die neue
Tool- und Resource-Beschreibung.

## 8. Zusammenspiel mit `output_contracts.py`

`output_contracts.py` bleibt als Fallback für ältere Dict- und Widgettools
sinnvoll. Für dieses Tool gilt jedoch:

- Das fachliche Pydantic-Schema ist primär.
- Der globale Installer darf ein bereits striktes Schema nicht ersetzen.
- `missingOutputSchemaCount == 0` ist notwendig, aber nicht hinreichend.
- Zusätzlich muss geprüft werden, dass das Tool-spezifische Schema die
  kognitiven Felder enthält.

## 9. PatchMon- und Runtime-Pflicht

Vor und nach einem MCP-Deployment:

1. `patchmon_runtime_inventory(include_fleet=true)`
2. `patchmon_brain_snapshot(include_fleet=true)`
3. Containerstatus von `sovereign-chatgpt-mcp`
4. begrenzte MCP-Containerlogs bei Fehlern
5. Broker-/Host-Worker-Status
6. Self-Update-Status und installierte Revision

PatchMon ersetzt den MCP-Protokolltest nicht. Der MCP-Protokolltest ersetzt
PatchMon nicht. Beide Evidence-Lanes sind erforderlich.

## 10. Stop-Kriterien

Nicht als behoben melden, wenn:

- `outputSchema` nur generisch ist oder fehlt,
- `structuredContent` nicht gegen das Schema validiert,
- einer der beiden Domain-Metadatenwerte fehlt,
- der alte URI noch registriert wird,
- der laufende Container noch eine ältere Revision verwendet,
- die App-Prüfung nicht neu gescannt wurde,
- Secrets oder geschützte Werte in `structuredContent`, `content` oder `_meta`
  auftauchen,
- nur ein internes Python-Objekt geprüft wurde, aber nicht die serialisierte
  MCP-Antwort.

## 11. Zentrale Erkenntnis

> Ein globaler Fallback-Schema-Check und ein internes Resource-Meta-Objekt sind
> kein ausreichender ChatGPT-App-Vertrag. Das kognitive Tool braucht ein eigenes
> explizites Outputmodell, und die feste Widget-Domain muss in den tatsächlich
> serialisierten `resources/list`- und `resources/read`-Antworten nachweisbar
> sein. Nach jeder Änderung sind URI-Versionierung, immutable MCP-Installation
> und erneuter App-Scan Pflicht.
