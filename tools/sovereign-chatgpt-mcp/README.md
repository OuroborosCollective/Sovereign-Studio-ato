# Sovereign ChatGPT Operator MCP

Privater Operator für `OuroborosCollective/Sovereign-Studio-ato`. Er macht die vorhandene Sovereign-Code- und Runtime-Arbeit für ChatGPT als klar begrenzte MCP-Tools zugänglich.

## Was ChatGPT damit bearbeiten kann

- Backendfehler in Python-Dateien finden und per exaktem Search/Replace reparieren
- neue Backendmodule, Tests und Migrationen anlegen
- React-/TypeScript-Komponenten und neue Menüs bauen
- bestehende große Live-Dateien ohne blindes Komplettüberschreiben patchen
- Abhängigkeiten mit dem committed Lockfile installieren
- Python-Compile, Pytest, TypeScript, Vitest, Sovereign-Audit und Web-Build ausführen
- Git-Diff und reale Check-Ergebnisse lesen
- Änderungen committen und ausschließlich einen Draft-PR öffnen
- allowlistete Docker-Container inspizieren und begrenzte Logs lesen
- Postgres- und pgvector-Canaries ausführen
- Migrationen gegen eine separate Preview-Datenbank ausführen und immer zurückrollen
- ein Backend-Image anhand des vollständigen Commit-SHA auflösen und dessen unveränderlichen Digest prüfen
- nach expliziter Aktivierung und exakter Digest-/SHA-Bestätigung deployen oder rollbacken

## Harte Grenzen

- kein Direkt-Push nach `main`
- kein Merge und kein Auto-Merge
- kein generisches Shell-Tool
- kein generisches SQL-Tool
- keine `.env`-, Schlüssel-, Credential- oder Git-Interna
- bestehende Dateien nur über exakte, einmalige Search/Replace-Blöcke
- Pythonänderungen benötigen gezielte Pytest-Evidence
- UI-/Menüänderungen benötigen gezielte Vitest-Evidence sowie Typecheck, Audit und Build
- produktive DB-Writes und Deploys standardmäßig deaktiviert
- destruktive Migrationen besitzen einen zweiten, separat deaktivierten Schalter
- kein OpenAI-API-Key im MCP-Server nötig; der Server ruft selbst kein Modell auf

## Werkzeugfluss für einen Backendfehler

1. `workspace_prepare`
2. `repository_search_text` und `repository_read_file`
3. `repository_apply_search_replace` oder `repository_write_new_file`
4. gezielten Backendtest über `repository_run_check(check="pytest", target="...")` ausführen
5. weitere passende Gates ausführen
6. `repository_diff`
7. `repository_create_draft_pr`

## Werkzeugfluss für ein neues Menü

1. echten Menü-/Navigationspfad im Workspace suchen
2. bestehende Komponente mit SHA lesen
3. neue Komponente über `repository_write_new_file` anlegen
4. vorhandene Navigation exakt patchen
5. relevante Vitest-Datei ergänzen oder patchen
6. `repository_install_dependencies`
7. gezieltes `vitest`; beim Draft-PR folgen zusätzlich Typecheck, Audit und Build
8. Diff prüfen und Draft-PR erstellen

## Docker- und VPS-Trennung

Der MCP-Container erhält **keinen Docker-Socket**. Dadurch kann ein Fehler im MCP-Prozess nicht unmittelbar beliebige Host-Container starten.

```text
ChatGPT
  -> privater MCP-Container
      -> Unix-Socket /run/sovereign-chatgpt-broker/operator.sock
          -> root Host-Broker mit exakt vier Docker-Aktionsfamilien
```

Der Broker akzeptiert nur:

- Containerstatus
- begrenzte Containerlogs
- Auflösen eines revisionsgebundenen Backend-Images
- verifizierter Deploy beziehungsweise Rollback

Ein Action-Name wie `shell` wird geblockt.

## Unveränderliche Backend-Images

`.github/workflows/sovereign-backend-image.yml` baut den echten Backend-Docker-Kontext. Auf `main` wird das Image so veröffentlicht:

```text
ghcr.io/ouroboroscollective/sovereign-backend:<vollständiger-commit-sha>
```

Das Image trägt zusätzlich `org.opencontainers.image.revision=<commit-sha>`. `backend_image_resolve` prüft Tag, Revision-Label und Registry-Digest, bevor ein Deploy überhaupt bestätigt werden kann.

## Lokale Validierung

```bash
cd tools/sovereign-chatgpt-mcp
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m py_compile policy.py runtime.py database.py operations.py broker.py broker_client.py server.py tests/*.py
python -m pytest -q
docker build -t sovereign-chatgpt-mcp:local .
```

## VPS-Pfad

```text
/opt/sovereign-chatgpt-tools/
├── .env                 # nur MCP/GitHub/DB
├── .ghcr.env            # optional, nur root installer
├── broker.env           # automatisch erzeugt, ohne GitHub-/DB-Secrets
├── bin/                 # feste Deploy-/Rollback-Gates
├── broker/              # lokaler Host-Broker
├── docker-auth/         # optionales root-only Registry-Login
├── docker-compose.yml
└── workspaces/
```

Installation nach Merge/Checkout auf dem VPS:

```bash
cd /opt/sovereign-studio/tools/sovereign-chatgpt-mcp
sudo bash deploy/install-on-vps.sh
```

Beim ersten Lauf wird bewusst abgebrochen, bis `/opt/sovereign-chatgpt-tools/.env` ausschließlich auf dem VPS angelegt und befüllt wurde.

## Benötigte externe Daten

Diese Werte gehören nur in `/opt/sovereign-chatgpt-tools/.env`:

- ein feingranularer GitHub-Token nur für dieses Repository mit Contents- und Pull-Request-Rechten
- ein read-only Postgres-Benutzer
- ein separater Benutzer und eine separate Datenbank für Migration-Previews
- optional die Aktivierung produktiver Deploy-/DB-Gates

Falls das GHCR-Paket privat bleibt, gehören `GHCR_USERNAME` und ein reiner Package-Read-Token ausschließlich in `/opt/sovereign-chatgpt-tools/.ghcr.env`. Der Installer wandelt diese Angaben in eine lokale Docker-Konfiguration um; sie werden nicht in den MCP-Container oder `broker.env` übernommen.

Keine dieser Angaben gehört in Chat, GitHub-Issues, Commits oder Logs.

## ChatGPT verbinden

Der Compose-Dienst veröffentlicht MCP ausschließlich auf:

```text
http://127.0.0.1:8090/mcp
```

Port `8090` darf nicht direkt öffentlich freigegeben werden. Verwende davor entweder:

- OpenAI Secure MCP Tunnel, oder
- einen authentifizierten TLS-Reverse-Proxy mit einer nur für diesen Operator bestimmten Adresse.

Erst der daraus entstehende HTTPS-MCP-Endpunkt wird in ChatGPT als App/Connector verbunden. Das Verbinden selbst ist ein externer Vertrauensschritt und kann nicht durch einen Commit im Repository ersetzt werden.

## Produktionsaktionen

Standardzustand:

```dotenv
SOVEREIGN_MCP_ENABLE_DB_WRITES=0
SOVEREIGN_MCP_ENABLE_DEPLOY=0
SOVEREIGN_MCP_ALLOW_DESTRUCTIVE_MIGRATIONS=0
```

Auch bei Aktivierung gilt:

- Migration: exakter SHA-256 der Migrationsdatei muss bestätigt sein und Preview muss bestehen.
- Destruktive Migration: benötigt zusätzlich den separaten Destruktiv-Schalter.
- Deploy: vollständiger Image-Digest und vollständiger Git-Commit-SHA müssen übereinstimmen.
- Rollback: vollständiger Ziel-Digest muss bestätigt sein.

Die Tools akzeptieren keine frei formulierten Shell-Befehle für Produktion.

## HAPI MCP Registry und 3Min API

Beide wurden geprüft. Generische Postgres-MCP-Server oder ein zusätzlicher CRUD-Dienst ersetzen diese Integration nicht, weil sie die Sovereign-spezifischen Branch-, Draft-PR-, Evidence-, Preview- und Deployment-Gates nicht automatisch durchsetzen. Sie werden daher nicht in den Live-Wahrheitspfad eingebaut.
