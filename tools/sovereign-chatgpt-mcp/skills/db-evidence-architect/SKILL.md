---
name: db-evidence-architect
description: Deterministische, revisionsgebundene PostgreSQL-Evidence über den vorhandenen Sovottt-MCP-Wahrheitspfad. Verwenden für Architektur-Inventar, echte read-only Datenbankbelege, rollback-only Migrations-Previews und Receipt-Kettenprüfung.
---

# DB Evidence Architect

Dieser Skill integriert die belastbaren Teile des bereitgestellten DB-Evidence-Architect-Konzepts in die bestehende Sovereign-Architektur. Er baut keinen zweiten Datenbank- oder SQLite-Wahrheitspfad, führt keine simulierten PostgreSQL-/MySQL-Operationen aus und verwendet keine Mock-Telemetrie als Beleg.

## Verbindlicher Ablauf

1. Für Repository-Arbeit zuerst `workspace_prepare` und `repository_revision_resolve` ausführen.
2. Mit `database_evidence_architecture_inventory` die real getrackten Datenbank-, Migrations-, Test- und Konfigurationsflächen erfassen. `.env`-Inhalte werden nicht gelesen.
3. Vor Live-Datenbankzugriff die exakt installierte MCP-Revision aus `mcp_self_update_status` verwenden.
4. Für echte, begrenzte PostgreSQL-Leseoperationen `postgres_evidence_read` verwenden.
5. Für Migrationen ausschließlich `postgres_evidence_migration_preview` auf dem vorhandenen rollback-only Preview-Pfad verwenden. Produktive Anwendung bleibt bei `postgres_migration_apply` mit separatem Bestätigungs-Hash und Owner-Gates.
6. Verkettete Receipts mit `database_evidence_receipt_verify` prüfen.

## Receipt-Vertrag

Der kanonische Receipt-Body enthält:

- vollständigen Git-SHA der installierten MCP-Revision
- feste Operation und gebundene Operationsidentität
- Sequenznummer
- SHA-256 von begrenztem Input und realem Output
- Outcome und Evidence-Gate-Ergebnis
- beobachtete Effect-Klasse
- Hash des vorherigen Receipts

Der Receipt-Hash verwendet `utf8-nfc-json-sorted-no-floats-v1`. Zeitstempel sind absichtlich nicht Teil des kanonischen Hashes, weil eine Uhr Beobachtungsmetadatum und keine ARE-Kausalität ist.

## Wahrheitsschranken

- kein generischer neuer SQL-Endpunkt
- keine SQLite-Zweitwahrheit
- keine simulierten Datenbankerfolge
- keine `.env`-Inhaltsanalyse
- keine Roh-SQL- oder beliebigen Row-Payloads im Receipt
- keine Telemetrieabhängigkeit für PASS
- kein positiver Live-Beleg bei Revisionsdrift
- kein Receipt für produktive Mutation ohne autoritativen Terminal-Readback

## Werkzeugoberfläche

- `database_evidence_skill_inventory`
- `database_evidence_architecture_inventory`
- `postgres_evidence_read`
- `postgres_evidence_migration_preview`
- `database_evidence_receipt_verify`

## Übernommene und verworfene Archivteile

Übernommen wurden Architektur-Scanning, SHA-256-Identitäten, verkettete Receipts und Git-Revisionsbindung. Ersetzt wurden der SQLite-zentrierte Ausführungspfad, simulierte PostgreSQL-/MySQL-Erfolge und die flüchtige In-Memory-Kette. Der Mock-Tracer ist nicht installiert; OpenTelemetry bleibt ein optionaler Side-Channel außerhalb des PASS-Gates.
