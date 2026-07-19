# Sovereign ChatGPT Operator MCP

Privater Operator für `OuroborosCollective/Sovereign-Studio-ato`. Er macht die vorhandene Sovereign-Code- und Runtime-Arbeit für ChatGPT als klar begrenzte MCP-Tools zugänglich.

## Was ChatGPT damit bearbeiten kann

- Backendfehler in Python-Dateien finden und per exaktem Search/Replace reparieren
- neue Backendmodule, Tests und Migrationen anlegen
- React-/TypeScript-Komponenten und neue Menüs bauen
- bestehende große Live-Dateien ohne blindes Komplettüberschreiben patchen
- Python-Compile und Pytest lokal ausführen; Node-/Web-Gates revisionsgebunden an GitHub Actions delegieren
- Git-Diff und reale Check-Ergebnisse lesen
- Änderungen committen und genau einen Draft-PR pro aktivem Auftrag öffnen
- im explizit aktivierten privaten Owner-Modus einen mergefähigen PR nur am bestätigten Head und nach den konfigurierten Check-Gates freigeben und mergen
- allowlistete Docker-Container inspizieren und begrenzte Logs lesen
- Postgres- und pgvector-Canaries ausführen
- PatchMon-Container, Docker-Netze, Datenbankschema, Flottenzustand, Updates, Patch-Läufe, Warnungen und Compliance secret-sicher korrelieren
- PatchMon-Dry-Runs, Freigabevorlagen, Approval, Validierungs-Retries und Stop-Anfragen über zustandsgebundene Plan-Hashes steuern
- Migrationen gegen eine separate Preview-Datenbank ausführen und garantiert zurückrollen
- bestätigte Migrationen nach erneuter Host-Broker-Prüfung produktiv anwenden
- ein Backend-Image anhand des vollständigen Commit-SHA auflösen und dessen unveränderlichen Digest prüfen
- nach expliziter Aktivierung und exakter Digest-/SHA-Bestätigung deployen oder rollbacken

## Harte Grenzen

- Direkt-Push nach `main` und PR-Merge sind außerhalb des explizit aktivierten privaten Owner-Modus gesperrt
- kein Auto-Merge; der exakte PR-Head und alle relevanten terminalen Checks werden unmittelbar vor einem Merge erneut geprüft
- kein generisches Shell-Tool
- kein generisches SQL-Tool
- keine `.env`-, Schlüssel-, Credential- oder Git-Interna
- bestehende Dateien nur über exakte, einmalige Search/Replace-Blöcke
- Pythonänderungen benötigen gezielte Pytest-Evidence
- UI-/Menüänderungen benötigen gezielte Vitest-Evidence sowie Typecheck, Audit und Build
- produktive DB-Writes und Deploys bleiben durch feste Gates, exakte Hashes und Preview-Evidence begrenzt
- `UPDATE`-Backfills besitzen einen eigenen Schalter
- `DROP`-, `DELETE`- und andere destruktive Migrationen besitzen einen zweiten, separat deaktivierten Schalter
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

## Backend- und Systemarchitekturwerkzeuge

Die sechs zusätzlichen Werkzeuge sind read-only, idempotent und liefern strukturierte Ergebnisse mit expliziten Evidenzgrenzen:

- `backend_engineering_tool_inventory`: Werkzeugkarte, Reihenfolge und harte Grenzen
- `backend_architecture_assess`: begrenzte, secret-sichere statische Architektur-, Technologie- und Risikoevidence
- `backend_stack_select`: nachvollziehbare Stackbewertung aus Repository-Evidence und expliziten Betriebsanforderungen
- `backend_delivery_plan`: test-, migrations- und rollback-gegateter Fahrplan für Greenfield, Modernisierung oder eine TSX-Prototyp-zu-Plattform-Migration
- `backend_api_security_plan`: Threat-/Control-/Verifikationsvertrag für Identity, Autorisierung, Tenancy, dynamische Endpunkte, Plugins, Abuse und DevSecOps
- `repository_revision_resolve`: getrennte Auflösung von Workspace-Head, aktuellem Base-Head, PR-Head/-Base, Merge-SHA, CI-Head und deployter MCP-Revision

Die Planwerkzeuge implementieren nichts selbst und behaupten weder Laufzeiterfolg noch Compliance. Autorisierte Codeänderungen verwenden weiterhin die vorhandenen exakten Repository-Patchwerkzeuge. `repository_revision_resolve` muss vor Arbeit, Review und Merge sowie nach Merge, Rebase, Update-Branch, Force-Push, Branchwechsel oder Base-Advance erneut ausgeführt werden; bei Dirty-Tree- oder SHA-Konflikten lautet das Ergebnis fail-closed.

## PatchMon-Operator

Der PatchMon-Operator bildet einen geschlossenen Wahrnehmungs- und Steuerungspfad für den festen Stack `patchmon-sovereign`:

- `patchmon_tool_inventory` beschreibt Werkzeuge und Grenzen.
- `patchmon_runtime_inventory` liest die vier erwarteten PatchMon-Container, deren Netzwerke, Loopback-Portbindung und begrenzte Metadaten der Docker-Flotte.
- `patchmon_database_inventory` liest nur Schema-, Migrations- und Größenevidence; keine Tabellenzeilen.
- `patchmon_query` bietet ausschließlich die festen Views `fleet_summary`, `hosts`, `pending_updates`, `patch_runs`, `docker_assets`, `alerts` und `compliance`.
- `patchmon_brain_snapshot` korreliert Runtime-, Netzwerk-, Datenbank- und Flottenevidence mit expliziten Risiken.
- `patchmon_patch_action_plan` bindet eine erlaubte Aktion an den aktuellen PatchMon-Datenbankzustand und erzeugt den exakten Bestätigungs-Hash.
- `patchmon_patch_action_apply` wird ausschließlich über die Host-Command-Queue ausgeführt und ruft nur PatchMons fest verdrahtete Loopback-API auf.

`submit_for_approval` legt nur einen `pending_approval`-Lauf an und führt auf dem Zielhost nichts aus. Erst `approve_run` kann einen echten Patch-Lauf anstoßen. Eine erfolgreiche HTTP-Annahme ist ausdrücklich kein Beleg für abgeschlossene Patches; der neue Lauf muss bis zu einem terminalen Datenbankstatus erneut gelesen werden.

Der PatchMon-Admin-JWT liegt ausschließlich als reguläre, root-eigene Datei ohne Gruppen-/Weltrechte unter `/opt/patchmon-sovereign/mcp-admin.jwt`. Er wird weder in den MCP-Container gemountet noch in Tool-Argumenten, Antworten oder Logs ausgegeben. Der MCP-Container erhält weiterhin keinen Docker-Socket; Docker- und PatchMon-Zugriffe erfolgen nur über feste Broker-Aktionen.

## Docker- und VPS-Trennung

Der MCP-Container erhält **keinen Docker-Socket**. Dadurch kann ein Fehler im MCP-Prozess nicht unmittelbar beliebige Host-Container starten oder Produktions-Admin-Zugangsdaten lesen.

```text
ChatGPT
  -> privater MCP-Container
      -> Unix-Socket /run/sovereign-chatgpt-broker/operator.sock
          -> root Host-Broker mit festen, validierten Aktionen
```

Der Broker akzeptiert nur:

- Containerstatus
- begrenzte Containerlogs
- Auflösen eines revisionsgebundenen Backend-Images
- verifizierte Migration mit erneuter Pfad-, Hash-, SQL- und Rollback-Preview-Prüfung
- verifizierter Deploy beziehungsweise Rollback
- feste PatchMon-Runtime-/Datenbankabfragen und zustandsgebundene PatchMon-Aktionen

Ein Action-Name wie `shell` oder ein frei formulierter SQL-Auftrag wird geblockt.

## Datenbank-Sicherheitsmodell

Der MCP-Container behält ausschließlich den read-only Produktionsbenutzer `sovereign_mcp_reader`. Produktive Migrationen werden nicht mit dessen Passwort ausgeführt und erhalten auch kein Admin-Passwort im Container.

Stattdessen gilt:

1. Migration stammt aus einem isolierten Workspace.
2. MCP prüft Pfad, Größe, SQL-Klasse und SHA-256.
3. MCP führt die Migration ohne äußeres `BEGIN`/`COMMIT` in der Preview-Datenbank aus und rollt die Transaktion zurück.
4. Der root-separierte Host-Broker liest dieselbe Datei erneut.
5. Der Broker wiederholt Pfad-, Hash-, SQL- und Preview-Prüfung unabhängig.
6. Erst danach verwendet der Broker die bestehende root-only Backend-Konfiguration für die produktive Anwendung.

`UPDATE`-Backfills können während der aktiven Wissens-/Vektordatenbankentwicklung dauerhaft erlaubt werden. `DELETE`, `DROP TABLE`, `DROP COLUMN`, `DROP SCHEMA` und vollständig gesperrte SQL-Klassen bleiben davon unberührt.

## Unveränderliche Backend-Images

`.github/workflows/sovereign-backend-image.yml` baut den echten Backend-Docker-Kontext. Auf jedem neuen `main`-Commit wird das Image so veröffentlicht:

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
python -m py_compile policy.py runtime.py database.py operations.py broker.py broker_client.py enterprise_backend_tools.py server.py launcher.py tests/*.py
python -m pytest -q
docker build -t sovereign-chatgpt-mcp:local .
```

## VPS-Pfad

```text
/opt/sovereign-chatgpt-tools/
├── .env                 # MCP/GitHub/Reader/Preview; root-only
├── .ghcr.env            # optional, nur root installer
├── broker.env           # automatisch erzeugt; root-only Preview-/Policy-Werte, kein GitHub- oder Backend-Admin-Passwort
├── bin/                 # feste Deploy-/Rollback-Gates
├── broker/              # lokaler Host-Broker
├── docker-auth/         # optionales root-only Registry-Login
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
- die gewünschten produktiven DB-/Deploy-Gates

Das Backend-Admin-Passwort verbleibt ausschließlich in der bestehenden root-only Backend-Konfiguration und wird vom Installer weder in den MCP-Container noch in `broker.env` kopiert.

Falls das GHCR-Paket privat bleibt, gehören `GHCR_USERNAME` und ein reiner Package-Read-Token ausschließlich in `/opt/sovereign-chatgpt-tools/.ghcr.env`. Der Installer wandelt diese Angaben in eine lokale Docker-Konfiguration um; sie werden nicht in den MCP-Container übernommen.

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

Sicherer Standardzustand:

```dotenv
SOVEREIGN_MCP_ENABLE_DB_WRITES=0
SOVEREIGN_MCP_ENABLE_DEPLOY=0
SOVEREIGN_MCP_ALLOW_DATA_BACKFILLS=0
SOVEREIGN_MCP_ALLOW_DESTRUCTIVE_MIGRATIONS=0
```

Für die dauerhafte Entwicklung einer eigenen Wissens- und Vektordatenbank kann folgender begrenzter Modus verwendet werden:

```dotenv
SOVEREIGN_MCP_ENABLE_DB_WRITES=1
SOVEREIGN_MCP_ENABLE_DEPLOY=1
SOVEREIGN_MCP_ALLOW_DATA_BACKFILLS=1
SOVEREIGN_MCP_ALLOW_DESTRUCTIVE_MIGRATIONS=0
```

Auch bei Aktivierung gilt:

- Migration: exakter SHA-256 der Migrationsdatei muss bestätigt sein.
- Preview: MCP und Host-Broker führen jeweils eine rollback-fähige Prüfung aus.
- Daten-Backfill: `UPDATE` benötigt den separaten Backfill-Schalter.
- Destruktive Migration: benötigt weiterhin den separaten Destruktiv-Schalter.
- Deploy: vollständiger Image-Digest und vollständiger Git-Commit-SHA müssen übereinstimmen.
- Rollback: vollständiger Ziel-Digest muss bestätigt sein.

Die Tools akzeptieren keine frei formulierten Shell-Befehle für Produktion.

## HAPI MCP Registry und 3Min API

Beide wurden geprüft. Generische Postgres-MCP-Server oder ein zusätzlicher CRUD-Dienst ersetzen diese Integration nicht, weil sie die Sovereign-spezifischen Branch-, Draft-PR-, Evidence-, Preview- und Deployment-Gates nicht automatisch durchsetzen. Sie werden daher nicht in den Live-Wahrheitspfad eingebaut.
