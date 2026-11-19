# mcp-use: isolierter Metadaten-Pruefstand

**Status: Draft-Pilot.** Kein produktives Deployment, kein zweiter Broker, kein Unity-Editor-Write.

## Aufgabe

Dieser Node-22-Pilot nutzt das offizielle `@mcp-use/client` in Version `2.4.6`. Er verbindet sich nur mit einem expliziten lokalen HTTP-Endpunkt `127.0.0.1:<port>/mcp`. Er ruft ausschliesslich `tools/list` auf und erzeugt einen SHA-256-Fingerprint aus sortierten Namen und Schemas. Kein `tools/call`. Die Berechtigungs-, Execution- und Runtime-Authority verbleibt ausschliesslich beim bestehenden Sovott-Broker.

Der CI-Job prueft die Negativfaelle ohne Endpoint und erstellt einen **noch nicht freigegebenen** NPM-Lockfile-Kandidaten fuer das Review. Abhaengigkeitsversionen und signierte Herkunft muessen vor einer VPS-Installation gegen den Lockfile-Stand gesichert werden. Kein Script-Install im Live-Container.

## Im isolierten Testsystem

```sh
npm ci --ignore-scripts
npm test
MCP_USE_READONLY_ENDPOINT=http://127.0.0.1:10080/mcp npm run probe
```

`10080` ist nur ein Beispiel fuer einen lokalen MCP-Testserver. **Der Unity Accelerator auf demselben Port spricht nicht das MCP-Protokoll und ist kein passendes Testziel.** Der Sovott-Broker hat aktuell keinen hier verifizierten anonymen Loopback-MCP-Endpunkt fuer diesen Piloten; deshalb wird keine Live-Verbindung automatisch versucht.

Das Ergebnis belegt bei erfolgreichem Lauf nur Protokollverbindung und beobachtete Werkzeug-Metadaten. Authentifizierung, Berechtigungen und nicht lesende Operationen werden nicht von MCP-Tool-Annotationen abgeleitet. Erfolgreiche CI beweist kein produktives Runtime-Verhalten.

## Integrationsgrenzen

- Keine neue Server-Instanz und keine Aenderung an `tools/sovereign-chatgpt-mcp/`.
- Kein LLM/Modell, kein SSH, keine Docker-API, keine GitHub-Mutation.
- Nur das bereits vorhandene GitHub-Actions-Runner-Netz; kein VPS-Deploy.
- Unbekannte oder zu grosse Werkzeugkataloge sind ein Fehler statt angenommener Erfolg.
- Unity-6-Asset-/Shader-Cache-Warming wird separat umgesetzt; nie durch eine MCP-Werkzeugliste oder diesen Client als gestartet behauptet.
- Ein echter Broker-Readback erfordert einen bewusst freigegebenen lokalen Endpoint, Authentifizierung und Zielsystem-Receipts.
