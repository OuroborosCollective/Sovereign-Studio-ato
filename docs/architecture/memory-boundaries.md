# Memory & Sync — Begriffsgrenzen

**Befund B/C (Audit 2026-07-02)**

Dieses Dokument legt verbindliche Begriffe für die Memory/Sync-Schicht fest.
Neue Dateien dürfen nur noch unter diesen kanonischen Präfixen angelegt werden.
Vor einer Zusammenlegung vorhandener Dateien müssen Imports und Tests vollständig
kartiert sein.

---

## Kanonische Begriffe

### Solution Pattern

**Was es ist:** Ein konkret gelerntes Code- oder Lösungsmuster aus einem
abgeschlossenen Agenten-Durchlauf. Ein Pattern ist fachlich spezifisch: es
beschreibt, wie eine bestimmte Klasse von Aufgaben gelöst wurde.

**Kanonische Dateien:**
- `solutionPatternMemory.ts` — Domänenmodell + Runtime-Logik
- `solutionPatternPersistence.ts` — Persistenz (Capacitor Preferences)
- `patternReusePlanner.ts` — Matching: welches Pattern passt auf eine neue Aufgabe?

**Nicht dasselbe wie:** Learning Memory (weiter unten).

---

### Learned Pattern / Pattern Memory

**Was es ist:** Die laufende In-Memory-Repräsentation der gesammelten Solution
Patterns plus Container-Bindung. "Pattern Memory" ist die Store-Schicht.

**Kanonische Dateien:**
- `patternMemoryRuntime.ts` — Store + CRUD
- `patternMemoryContainerRuntime.ts` — Anbindung an BuilderContainer
- `patternMemoryProposalRuntime.ts` — Vorschlagspfad für neue Patterns

---

### Learning Memory

**Was es ist:** Der Lernzyklus des Agenten — nicht die gespeicherten Patterns
selbst, sondern der Prozess, neue Patterns aus Durchläufen zu destillieren.

**Kanonische Datei:**
- `sovereignLearningMemory.ts`

---

### Remote Memory Gateway

**Was es ist:** Synchronisation von Pattern Memory mit einem externen Backend
(z. B. sovereign-backend). Alles, was Daten über ein Netzwerk schickt oder
empfängt, gehört hierher.

**Kanonischer Präfix:** `remoteMemory*`

**Kanonische Dateien:**
- `remoteMemoryGatewayBridge.ts` — Netzwerk-Adapter
- `remoteMemoryContainerRuntime.ts` — Container-Anbindung für Remote-Sync
- `remoteMemoryProductionReadiness.ts` — Health/Readiness-Prüfung
- `remoteMemoryUpdateIntake.ts` — Eingehende Updates verarbeiten

**Nicht dasselbe wie:** External Sync (unten).

---

### External Sync (Deprecated-Präfix)

**Was es ist:** Älterer Präfix für dieselbe Gateway/Sync-Schicht. Die Dateien
`externalMemorySync.ts`, `externalMemoryMonitoring.ts` und
`externalMemorySyncPreview.ts` verwenden denselben fachlichen Komplex wie die
`remoteMemory*`-Dateien.

**Handlungsregel:**
- Keine neuen Dateien mit dem Präfix `externalMemory*` anlegen.
- Der Präfix `remoteMemory*` ist kanonisch für alle neuen Gateway/Sync-Dateien.
- Bestehende `externalMemory*`-Dateien werden erst umbenannt, wenn:
  1. alle Imports kartiert sind,
  2. alle betroffenen Tests laufen,
  3. Umbenennung per kleinem SEARCH/REPLACE-PR erfolgt.

---

## Namensregel für neue Dateien

| Fachlicher Bereich        | Erlaubter Präfix       | Verbotener Präfix         |
|---------------------------|------------------------|---------------------------|
| Gespeichertes Muster      | `solutionPattern*`     | `learnedPattern*`         |
| Pattern-Store/Runtime     | `patternMemory*`       | –                         |
| Lernzyklus                | `sovereignLearning*`   | –                         |
| Remote/Netzwerk-Sync      | `remoteMemory*`        | `externalMemory*` (neu)   |
| Sitzungs-Persistenz       | `sovereignSession*`    | –                         |

---

## Audit-Hinweis

Quelle: `docs/audit/2026-07-02-repo-structure-runtime-hinweis-audit.md`
Befunde B und C: Memory-Namespace-Drift, `externalMemory*` vs. `remoteMemory*`.
