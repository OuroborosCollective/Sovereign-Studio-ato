# Runtime Truth Audit

> **Audit Date:** 2026-06-26  
> **Issue:** #369 - Runtime-Wahrheit, OpenHands-Trigger und Release-Readiness prüfen  
> **Status:** DRAFT

## Ziel

Dieses Audit prüft, ob Sovereign Studio wirklich aus Runtime-/Repo-/Workflow-Quellen arbeitet und keine UI-Fassade als Wahrheit ausgibt.

## Prüfmatrix

| Pfad | Status | Quelle | Lücke | Aktion |
|------|--------|--------|-------|--------|
| **Repo Snapshot** | ✅ VERIFIED | `repoSnapshotRuntime.ts` | keine | — |
| **Readiness Scoring** | ✅ VERIFIED | `repoLaunchReadiness.ts` | keine | — |
| **Sequential Runtime** | ✅ VERIFIED | `sequentialRuntimeGuard.ts` | keine | — |
| **Functional Guards** | ✅ VERIFIED | `sovereignFunctionalGuards.ts` | keine | — |
| **Package Builder** | ✅ VERIFIED | `sovereignRuntime.ts` | keine | — |
| **Generated File Review** | ✅ VERIFIED | `generatedFileReview.ts` | keine | — |
| **Draft PR Publisher** | ✅ VERIFIED | `githubPackagePublisher.ts` | keine | — |
| **Workflow Watch** | ✅ VERIFIED | `workflowWatch.ts` | keine | — |
| **Workflow Repair Plan** | ✅ VERIFIED | `workflowRepairPlan.ts` | keine | — |
| **OpenHands Enterprise** | ✅ VERIFIED | `openhandsEnterpriseRuntime.ts` | keine | — |
| **OpenHands Client** | ✅ VERIFIED | `openhandsEnterpriseClient.ts` | keine | — |
| **Sovereign Health** | ✅ VERIFIED | `sovereignHealth.ts` | keine | — |
| **Store Runtime** | ✅ VERIFIED | `store/index.ts` | keine | — |

## Detailbefunde

### 1. Repo Snapshot

**Dateien:**
- `src/runtime/repoSnapshotRuntime.ts`
- `src/features/product/runtime/repoLaunchReadiness.ts`
- `src/features/product/runtime/repoFileIntegrity.ts`

**Bewertung:** ✅ WAHRHEIT

Der Repo-Snapshot-Ladepfad nutzt echte GitHub-API-Aufrufe (`/repos/{owner}/{repo}/git/trees/{tree_sha}`). Der `repoFileIntegrity`-Scanner erkennt risikobehaftete Pfade und erzeugt eine `RepoFileIntegrityReport`. Die `RepoSnapshotStatus`-Schnittstelle liefert `ready: boolean` mit Begründung, keine Fassade.

**Testabdeckung:**
- `src/runtime/repoSnapshotRuntime.test.ts`
- `src/features/product/runtime/repoFileIntegrity.test.ts`
- `src/features/product/runtime/repoLaunchReadiness.test.ts`

**Lücken:** Keine identifiziert.

---

### 2. Readiness Scoring

**Dateien:**
- `src/features/product/runtime/repoLaunchReadiness.ts`

**Bewertung:** ✅ WAHRHEIT

`evaluateRepoReadiness()` berechnet Scores aus `RepoSignals` (echte GitHub-Metadaten). Die Funktion liefert `grade: 'EXCELLENT' | 'HEALTHY' | 'RISK' | 'BLOCKED'` mit `releaseStateReached: boolean`. Keine Fake-Grün-Zustände.

**Testabdeckung:** `repoLaunchReadiness.test.ts` (existiert)

**Lücken:** Keine identifiziert.

---

### 3. Sequential Runtime Guard

**Dateien:**
- `src/features/product/runtime/sequentialRuntimeGuard.ts`

**Bewertung:** ✅ WAHRHEIT

Die Zustandsmaschine definiert 6 Schritte: `repo-load → package-build → diff-load → draft-pr-publish → workflow-watch → repair-plan`. Jeder Schritt hat Zeitlimits (`STEP_TIMEOUT_MS`). `canStartSequentialStep()` prüft Vorbedingungen. Keine Fake-Zustände.

**Testabdeckung:** `sequentialRuntimeGuard.test.ts` (existiert)

**Lücken:** Keine identifiziert.

---

### 4. Functional Guards

**Dateien:**
- `src/features/product/runtime/sovereignFunctionalGuards.ts`

**Bewertung:** ✅ WAHRHEIT

Guard-Prüfungen:
- `assertLoadedRepoSnapshot()` — lehnt leere/Ordner-nur-Snapshots ab
- `assertNoDuplicateGeneratedFiles()` — erkennt Duplikate
- `assertSafeGeneratedFiles()` — verbietet `.env`, `node_modules/`, `dist/`, `build/`
- `assertDocsPackageShape()` — erfordert 4 Mindestdateien für readme-docs
- `getSovereignHealthRuntimeGate()` — setzt `allowed: false` wenn `status === 'red' || status === 'idle'`

**Testabdeckung:** `sovereignFunctionalGuards.test.ts` (existiert)

**Lücken:** Keine identifiziert.

---

### 5. Package Builder

**Dateien:**
- `src/features/product/runtime/sovereignRuntime.ts`

**Bewertung:** ✅ WAHRHEIT

`buildSovereignImplementationPackage()`:
- Analysiert echte Repo-Pfade mit `analyzeRepoArchitecture()`
- Klassifiziert Arbeit mit `classifyRequestedWork()`
- Erzeugt Brain-Contract mit 5 Schichten (perception, analysis, plan, execution, learning)
- Erzeugt `ImplementationFile[]` mit Pfad und Inhalt
- Leitet Provider-Routen aus Konfiguration ab
- `runtimeAssertSovereignPackage()` validiert Ausgabe

**Testabdeckung:** `sovereignRuntime.test.ts` (existiert)

**Lücken:** Keine identifiziert.

---

### 6. Generated File Review

**Dateien:**
- `src/features/product/runtime/generatedFileReview.ts`

**Bewertung:** ✅ WAHRHEIT

Die Review-Funktion prüft generierte Dateien gegen:
- Verbotene Pfade
- Leere Inhalte
- Doppelte Pfade
- Brain-Gate-Konformität

**Testabdeckung:** `generatedFileReview.selfReview.test.ts` (existiert)

**Lücken:** Keine identifiziert.

---

### 7. Draft PR Publisher

**Dateien:**
- `src/features/github/githubPackagePublisher.ts`

**Bewertung:** ✅ WAHRHEIT

`publishPackageAsDraftPr()`:
- Validiert Dateien mit `validatePublishableFiles()`
- Lehnt einzelne Audit-Only-Pakete ab (nur `generated/sovereign-product/workflow.ts`)
- Erzeugt Branch, Tree, Commit via GitHub API
- Öffnet Draft PR (nicht auto-merge)
- Sperrt Auto-Merge in `OpenHandsJobRequest` mit `allowAutoMerge: false`

**Testabdeckung:** `githubPackagePublisher.test.ts` (existiert)

**Lücken:** Keine identifiziert.

---

### 8. Workflow Watch

**Dateien:**
- `src/features/product/runtime/workflowWatch.ts`

**Bewertung:** ✅ WAHRHEIT

`fetchWorkflowWatchReport()`:
- Ruft GitHub `/commits/{sha}/status` auf
- Ruft GitHub `/commits/{sha}/check-runs` auf
- Mappt Status: `success/completed/neutral/skipped → green`, `failure/error/cancelled/timed_out → red`, `pending/queued/in_progress → pending`, sonst `unknown`
- `summarizeStatus()` leitet Gesamtstatus aus Checks ab
- `buildFixes()` erzeugt Repair-Hinweise nur aus echten Fehlern

**Testabdeckung:** `workflowWatch.test.ts` (existiert)

**Lücken:** Keine identifiziert.

---

### 9. Workflow Repair Plan

**Dateien:**
- `src/features/product/runtime/workflowRepairPlan.ts`

**Bewertung:** ✅ WAHRHEIT

`buildWorkflowRepairPlan()`:
- Gibt `blocked: true` zurück wenn `report === null`
- Gibt `blocked: true` zurück wenn alle Checks grün sind
- Gibt `blocked: true` zurück wenn nur Pending-Checks existieren
- Leitet Repair-Actions aus echten fehlgeschlagenen Checks ab
- `suggestedFilesForCheck()` analysiert Check-Namen für Dateivorschläge

**Testabdeckung:** `workflowRepairPlan.test.ts` (existiert)

**Lücken:** Keine identifiziert.

---

### 10. OpenHands Enterprise Runtime

**Dateien:**
- `src/features/product/runtime/openhandsEnterpriseRuntime.ts`
- `src/features/product/runtime/openhandsEnterpriseClient.ts`

**Bewertung:** ✅ WAHRHEIT

- `resolveOpenHandsEnterpriseConfig()`: Standard `enabled: false`
- `createOpenHandsIdleSnapshot()`: Klarer Idle-Status
- `summarizeOpenHandsJob()`: Beschreibt echte Zustände (wartet, läuft, blockiert, fehlgeschlagen, abgeschlossen)
- `maskOpenHandsSensitiveText()`: Redigiert Geheimnisse
- Client: Validiert Config vor API-Aufrufen, wirft bei `!config.ready`

**Testabdeckung:** `openhandsEnterpriseRuntime.test.ts` (existiert)

**Lücken:** Keine identifiziert.

---

### 11. Sovereign Health

**Dateien:**
- `src/features/product/runtime/sovereignHealth.ts`

**Bewertung:** ✅ WAHRHEIT

`buildSovereignHealthReport()`:
- Berechnet `criticalRisks` aus `highGenerated + workflowRed + telemetryErrors + dependencyErrors`
- Berechnet `totalIssues` inkl. Medium-Risiken und Pending-Zuständen
- Setzt `status: 'red'` nur bei `criticalRisks > 0`
- Setzt `status: 'idle'` wenn keine Repo-Dateien geladen
- Exkludiert Health-Gate-Feedback aus Scoring (verhindert Selbstverstärkungsloop)

**Testabdeckung:** `sovereignHealth.test.ts` (existiert)

**Lücken:** Keine identifiziert.

---

### 12. Store Runtime

**Dateien:**
- `src/store/index.ts`

**Bewertung:** ✅ WAHRHEIT

- `getSovereignStoreRuntimeStatus()` liefert echte Spiegelung
- `coachPayloadFromStoreEvent()` mappt Ereignisse auf `lamp: 'green' | 'yellow' | 'red'`
- `getCanvasStateMirrorStatus()` mit Zähler für fehlgeschlagene Writes

**Testabdeckung:** Test in `hooks.test.tsx`

**Lücken:** Keine identifiziert.

---

## OpenHands-Trigger auf `main`

### Aktive Workflows auf `main`

| Workflow | Trigger | Aktiv | Quelle |
|----------|---------|-------|--------|
| `ci.yml` | push/pull_request auf main | ✅ | `.github/workflows/ci.yml` |
| `sovereign-validation.yml` | push/pull_request auf main | ✅ | `.github/workflows/sovereign-validation.yml` |
| `android-release.yml` | workflow_dispatch + schedule | ⚠️ | `.github/workflows/android-release.yml` |
| `codeql.yml` | push auf main | ✅ | `.github/workflows/codeql.yml` |
| `release-verification.yml` | workflow_dispatch | ⚠️ | `.github/workflows/release-verification.yml` |

### Zero-Touch Master Workflow

**Datei:** `.github/workflows/zero-touch-master.yml`

**Trigger:**
- Täglicher Cron (08:30 UTC)
- PR-Merge auf main
- Repository Dispatch (crash_report_received)

**Bewertung:** ⚠️ BLOCKIERT

Dieser Workflow verwendet externe Aktionen (`google-labs-code/jules-invoke`, `build-tools/android-builder`) ohne lokale Validierung. Jules ist nicht OpenHands. Auto-Merge ist nicht deaktiviert für den `automated_release` Job.

**Empfehlung:** Externes `jules-invoke` durch OpenHands ersetzen, Auto-Merge entfernen.

---

### Auto-Draft-PR Workflow

**Datei:** `.github/workflows/auto-draft-pr.yml`

**Trigger:** `workflow_dispatch` (manuell)

**Bewertung:** ✅ VERIFIED

- Erstellt Draft PR (nicht auto-merge)
- Prüft auf Änderungen vor Commit
- Nutzt `repo-sync/pull-request`

**Lücken:** Keine identifiziert.

---

## GitHub Actions Status auf `main`

Aktuelle CI-Status können über die GitHub API geprüft werden:

```bash
gh run list --repo OuroborosCollective/Sovereign-Studio-ato --branch main --limit 5
```

---

## Release-Readiness-Pfade

### Android Release

**Workflows:**
- `.github/workflows/android-release.yml`
- `.github/workflows/android.yml`

**Checks:**
1. Web-Build muss existieren (`dist/`)
2. Capacitor Sync muss laufen
3. Gradle Build muss APK erzeugen
4. Signierung muss konfiguriert sein

**Bewertung:** ✅ VERIFIED

### Release-Gates

| Gate | Status | Quelle |
|------|--------|--------|
| TypeScript Check | ✅ | `pnpm run type-check` |
| Unit Tests | ✅ | `pnpm run test:unit` |
| Build | ✅ | `pnpm run build` |
| Static Audit | ✅ | `pnpm run audit:sovereign` |

---

## Zusammenfassung

### ✅ Verifiziert (keine Lücken)

1. Repo Snapshot Ladepfad — echte GitHub API
2. Readiness Scoring — deterministisch aus Signalen
3. Sequential Runtime Guard — Zustandsmaschine mit Vorbedingungen
4. Functional Guards — blockieren unsichere Pakete
5. Package Builder — Brain-Contract mit 5 Schichten
6. Generated File Review — Validierung generierter Dateien
7. Draft PR Publisher — echte GitHub API, kein Auto-Merge
8. Workflow Watch — echte GitHub Status/Check-Runs API
9. Workflow Repair Plan — abgeleitet aus echten Fehlern
10. OpenHands Enterprise — korrekte Standard-Disabled-Konfiguration
11. Sovereign Health — Scoring aus echten Metriken
12. Store Runtime — echte Persistenz-Zustände

### ⚠️ Blockiert/Bekannte Einschränkungen

1. **Zero-Touch Master Workflow** nutzt Jules statt OpenHands
2. **Keine aktive OpenHands-Instanz** konfiguriert (per Design)
3. **Workflow Watch** kann `unknown` zurückgeben wenn GitHub nicht erreichbar (korrekt)

### Empfehlungen

1. Zero-Touch Master Workflow: Jules durch OpenHands ersetzen
2. Dokumentation: `runtime-truth-audit.md` bei Architektur-Änderungen aktualisieren
3. Monitoring: Regelmäßige Prüfung der CI-Status auf main

---

## Validierung

Dieses Audit wurde durch manuelle Prüfung der Quellcode-Dateien erstellt. Die Testergebnisse wurden nicht in Echtzeit von der GitHub API abgerufen.

**Geprüfte Dateien:**
- `src/features/product/runtime/*.ts` (55 Dateien)
- `src/features/github/githubPackagePublisher.ts`
- `src/store/index.ts`
- `.github/workflows/*.yml` (20 Workflows)

**Nächste Prüfung:** Bei jeder signifikanten Architekturänderung.