# Sovereign Universal Toolchain – eingebettete Integration

## Ziel

Die bereitgestellte **Sovereign Universal Toolchain 2** wird nicht als zweiter
FastAPI-/SQLite-/GitHub-Dienst neben Sovereign Studio betrieben. Der
policy-guarded Kern läuft eingebettet im vorhandenen Flask-/PostgreSQL-Backend.
Ausführung, Dateischreibvorgänge, Tests und Draft-PR-Erstellung bleiben Eigentum
des bestehenden Sovereign-Agent-Runtimes.

Damit gilt weiterhin:

- Die Runtime erzeugt Wahrheit; die UI zeigt sie nur an.
- Kein direkter Push auf `main`.
- Kein beliebiger Shell-Befehl aus dem Chat.
- Keine GitHub-Tokens, API-Keys oder Rohlogs in Antworten oder Evidence-Tabellen.
- Write-Aktionen laufen nur über bestehende Agent-Tools und deren Evidence-Gates.
- Das maximale GitHub-Ergebnis ist ein Draft PR.

## Herkunft und geprüfte Archive

Die bereitgestellte Toolchain-Datei wurde vor der Analyse gegen die beigefügte
SHA-256-Datei geprüft.

```text
sovereign_universal_toolchain_policy_guarded_integrated.zip
SHA-256: 26faab25a4877ec6ad4ec0d1edf56f5acfaffb062dcfb6ae1b2884e8fdd5fa9a
```

Das Archiv enthielt keine Pfadtraversalen oder Symlinks. Die separat gelieferten
7z-Teile enthalten lokale Dependency-/Playwright-Daten. Sie werden nicht in das
Repository, das Backend-Image oder die APK kopiert. Abhängigkeiten werden stets
aus dem committed Lockfile reproduzierbar installiert.

## Backend-Komponenten

### Eingebetteter Runtime-Kern

```text
backend/agent_runtime/universal_toolchain.py
scripts/sovereign-backend/agent_runtime/universal_toolchain.py
```

Er stellt bereit:

- `runtime_failure_diagnose`
- `policy_guarded_rollback_preview`
- `agent_toolchain_handoff`
- einen read-only Manifest- und Briefing-Vertrag
- Erkennung bekannter Fehlerfamilien
- genau vier logisch benachbarte Runtime-Risiken
- SHA-256-Evidence statt reflektierter Rohlogs

### HTTP-Routen

Read-only Universal-Routen:

```text
GET  /api/toolchain/universal/status
GET  /api/toolchain/universal/manifest
GET  /api/toolchain/universal/briefing
POST /api/toolchain/universal/invoke
```

Der Invoke-Endpunkt akzeptiert nur die eingebetteten read-only Werkzeuge.
Ausführung wird nicht über diesen Endpunkt freigeschaltet.

Authentifizierte Agent-Routen:

```text
GET  /api/user/agent/toolchain/manifest
POST /api/user/agent/toolchain/diagnose
POST /api/user/agent/toolchain/rollback-preview
POST /api/user/agent/toolchain/handoff
```

Der Handoff erstellt einen normalen Sovereign-Agent-Job. Die späteren
Draft-PR-Schritte bleiben getrennt:

```text
POST /api/user/agent/jobs/<job_id>/draft-pr/prepare
POST /api/user/agent/jobs/<job_id>/draft-pr/create
```

## PostgreSQL-Installation

Migration:

```text
scripts/sovereign-backend/migrations/015_universal_toolchain_runtime.sql
```

Das bestehende Backend-Image kopiert das komplette Verzeichnis `migrations`.
`auto-migrate.sh` sortiert alle SQL-Dateien und führt Migration 015 beim Start
des neuen Backend-Images aus.

Die Migration ist additiv und idempotent. Sie erzeugt:

```text
sovereign_toolchain_incidents
sovereign_toolchain_handoffs
```

Gespeichert werden ausschließlich:

- User-ID
- Mission-SHA-256
- Evidence-SHA-256
- klassifizierte Fehlerfamilien
- vier Folgeprognosen
- Policy-Snapshot
- zugehörige Agent-Job-ID, Repository und Branch

Rohlogs, Shell-Befehle und Secrets werden nicht gespeichert.

### Manuelle Vorschau ohne Produktionswrite

Die Migration muss vor einem Deployment in der isolierten Preview-Datenbank
transaktional geprüft werden. Eine Vorschau darf immer vollständig zurückrollen.

### Verifikation nach einem bestätigten Deployment

```sql
SELECT to_regclass('sovereign_toolchain_incidents');
SELECT to_regclass('sovereign_toolchain_handoffs');

SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = current_schema()
  AND table_name IN (
    'sovereign_toolchain_incidents',
    'sovereign_toolchain_handoffs'
  )
ORDER BY table_name, ordinal_position;
```

Die Tabellen dürfen erst nach einem ausdrücklich bestätigten Produktionsdeploy
beschrieben werden.

## Frontend-Integration

### Automatisches Laden

`useToolchainStore.loadTools()` lädt parallel:

- vorhandene Sovereign-App-Tools
- das eingebettete Universal-Manifest

`getToolContext()` stellt der Chat-KI anschließend Version, sichere Werkzeuge und
Guardrails bereit. Die KI kann bei Bedarf die read-only Diagnose aufrufen.

### Predictive Übergabe

`SovereignAgentClient.startToolchainJob()` ruft den Handoff-Endpunkt auf. Die
Oberfläche erhält danach:

- echten Agent-Job
- diagnostizierte Fehlerfamilien
- genau vier benachbarte Runtime-Risiken
- persistierte Agent-Events

### Draft-PR-Übergabe

`App.tsx` startet beim Klick auf „Draft PR“ keinen zweiten Agent-Job mehr.
Stattdessen läuft die belegte Sequenz:

1. vorhandene Job-ID prüfen
2. `draft-pr/prepare`
3. Changed-Files, Diff, Tests und Branch-Evidence validieren
4. `draft-pr/create`
5. GitHub-Draft-PR-URL aus der Runtime übernehmen
6. Job erneut laden und den finalen Zustand anzeigen

## Lokales reproduzierbares Test-Setup

```bash
corepack enable
corepack prepare pnpm@9.12.2 --activate
pnpm install --frozen-lockfile
pnpm run type-check
pnpm exec vitest run src/features/product/runtime/sovereignAgentClient.test.ts
pnpm run build:web
```

Playwright-Browser werden passend zur Lockfile-Version installiert:

```bash
pnpm exec playwright install --with-deps chromium
pnpm run test:e2e
```

Die gelieferten 7z-Dependency-Caches sind optionales lokales Material und keine
Quelle der Paketwahrheit. CI und Backend-Build verwenden ausschließlich
`package.json`, `pnpm-lock.yaml` und die zentralen Python-Requirements.

## Runtime-Fluss

```text
Chat-Eingabe
  → Intent und Repository-Evidence
  → Universal Toolchain Diagnose
  → Fehlerfamilien + vier Folgefehler
  → Sovereign-Agent-Handoff
  → isolierter Workspace
  → erlaubte Agent-Tools
  → Changed Files + Diff + Tests
  → Draft-PR-Vorbereitung
  → GitHub Draft PR
  → persistierter finaler Jobzustand
```

Ein Erfolg darf erst angezeigt werden, wenn die jeweilige Runtime-Antwort die
Evidence bestätigt. Ein fehlender Schritt bleibt als Blocker sichtbar.
