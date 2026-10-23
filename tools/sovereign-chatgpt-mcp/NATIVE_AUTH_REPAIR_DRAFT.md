# Native-Auth-Reparatur — unvollständiger Repository-Entwurf

Basis: `9341b5151b9476e95186a03e6ee3deb5fd8cdfa9`, 23.10.2026.
Status: **PARTIAL**, keine produktiv nutzbare Reparaturaktion.

`aurion_native_auth.py` enthält den fokussierten Datei-/Schlüsselvertrag und
den Operationskoordinator. Es gibt noch keinen Host-Adapter, keine Toolregistrierung
und keine authentifizierte HTTP-Freigaberoute. Der Code erweitert weder die
SSH-Freigabe noch die Compose-Allowlist und wird nicht vom Broker aufgerufen.

Der Koordinator bindet Freigaben an den vollständigen Plan einschließlich
Container, Image, Revision, Metadaten- und Konfigurationsfingerprint. Er schreibt
den dauerhaften Intent vor dem Freigabeverbrauch und vor Effekten. Unklare
Ausgänge sperren weitere Mutationen; erneute Zustellung liest ausschließlich.
Der Adapter muss die wirklichen Prüfungen und Effekte implementieren. Seine
Testsimulation belegt weder Schema-Parität noch eine Docker-Same-Image-Garantie.

Der Dateivertrag lehnt mehrdeutiges dotenv, Duplikate, ungültige vorhandene
Schlüssel, ungeschützte Dateien, Hardlinks und Symlinks ab. Gültige Schlüssel
werden wiederverwendet. Neuanlage benötigt eine konkrete Planfreigabe.
Atomarer Dateiaustausch prüft vorher Inhalt und Inode und synchronisiert Datei
und Verzeichnis. Der Aufrufer muss das Verzeichnis rootgeschützt öffnen und die
Operationssperre halten. Andere privilegierte Writer müssen dieselbe Sperre
beachten; eine systemweite Dateisystem-CAS-Garantie besteht nicht.

## Tatsächliche lokale Prüfung

```sh
python -m unittest discover -s tools/sovereign-chatgpt-mcp/tests -p 'test_aurion_native_auth_*.py' -v
git diff --check
```

33 Tests bestanden. Root-Metadaten werden am OS-Adapter simuliert; Datei-I/O,
Inode-Tausch, Symlinks, `flock`, Persistenz und Wiederanlauf benutzen echte
temporäre Dateien. Docker, HTTP und Datenbank werden nicht ausgeführt.
`pytest` und Flask sind lokal nicht vorhanden; nichts wurde installiert.

## Offene Integration

- Den tatsächlichen Vertrag der Migration
  `drizzle/0075_aurion_native_auth_sessions.sql`, der aktiven
  `docker-compose.traefik.yml`, der Deployment-Receipts und der erforderlichen
  SHA-/Digest-Variablen revisionsgebunden lesen. Diese Quellen fehlen in diesem
  Repository. Eine eng begrenzte externe Leseprüfung wurde angefragt.
- Einen festen Host-Adapter für Container/Healthz/Receipts, beide festen env-Dateien,
  `SELECT 1`, Tabellen/Spalten/Indizes, Backup, Konfigurationsprüfung,
  ausschließlich Same-Image-Aurion-Neuerzeugung und unabhängige Rücknahme implementieren.
- Owner-authentifizierte Plananzeige und Einmalfreigabe an die vorhandene
  Owner-Input-Grenze anbinden; keine MCP-Behauptung darf die Freigabe erzeugen.
- Genau eine mutationsfähige Aktion im Command-Contract; Dispatch, Registry,
  benötigte Mirrors und deren Regressionen ergänzen. Installation und produktiver
  Einsatz benötigen weiterhin eigene Freigaben.
- Echte HTTP-/Queue-/Host-Adaptertests, Aggregate-Gates und unveränderte Head-CI.

Runtime, Browser-/Android-Callback, Tokenaustausch, Zonenticket, WebSocket,
Welcome und Welt-Snapshot bleiben **UNVERIFIED**.
