# Kanonische Proof Envelope und fail-closed Verdict Engine

## Zweck

Der Core in `backend/agent_runtime/proof_verdict.py` ist eine dünne, reine Beweisschicht für riskante Sovereign-Operationen. Er sammelt keine Evidence selbst und ersetzt keine bestehende Wahrheitsquelle. Er bewertet ausschließlich bereits kanonisierte Beobachtungen gegen eine versionierte Anforderungsmenge.

Die einzigen zulässigen Endzustände sind:

- `VERIFIED`
- `CONTRADICTED`
- `BLOCKED_BY_MISSING_EVIDENCE`

## Truth-Boundary

Der Core führt keine Netzwerk-, GitHub-, PatchMon-, Docker-, MCP-, PostgreSQL-, Dateisystem-, Uhrzeit- oder Zufallsoperation aus. Collector und Adapter liegen außerhalb der Verdict-Entscheidung und dürfen kein `VERIFIED` vorgeben.

Bestehende `agent_run_receipts` bleiben kanonische Receipt-Wahrheit. `observation_from_agent_run_receipt` prüft den vorhandenen Receipt-Hash und projiziert nur eine `ProofObservation`. Erst `evaluate_proof` kann aus vollständigen, exakt gebundenen Beobachtungen ein Verdict erzeugen.

## Kanonische Verträge

### `ProofRequirementSet`

Eine Operationsfamilie besitzt eine positive Ganzzahlversion und eine unveränderliche Liste eindeutiger Anforderungen. Jede Anforderung bindet:

- Requirement-ID,
- Evidence-Art,
- zugelassene Quellenklassen,
- Runtime-Pflicht oder statische Zulässigkeit.

Der vollständige Satz wird über UTF-8-NFC-JSON mit sortierten Schlüsseln und SHA-256 identifiziert.

### `ProofEnvelope`

Die Envelope bindet unveränderlich:

- Operationsfamilie und Operation Identity,
- Repository,
- vollständige Git-Revision,
- Input-SHA-256,
- Diff-SHA-256,
- Version und Hash des Requirement Sets,
- vollständige Requirement-ID-Menge.

Eine manipulierte oder veraltete Requirement-Set-Bindung ergibt `CONTRADICTED`.

### `ProofObservation`

Eine Observation ist eine secret-safe kanonische Tatsache mit:

- Requirement- und Evidence-Art,
- Quellenklasse,
- `OBSERVED`, `CONTRADICTED` oder `UNAVAILABLE`,
- exakt derselben Operation-, Revision-, Input- und Diff-Identität,
- Evidence-SHA-256.

Eine statische Candidate-Quelle kann eine Runtime-Anforderung niemals erfüllen.

### `ProofVerdict`

Das Verdict enthält vollständig und getrennt:

- erfüllte Anforderungen,
- fehlende Anforderungen,
- widersprüchliche Anforderungen,
- verwendete Observation-Hashes,
- deterministische Finding-Codes,
- eigenen Verdict-SHA-256.

Ein einziger Widerspruch hat Vorrang vor fehlender Evidence. Ohne Widerspruch, aber mit mindestens einer fehlenden Pflichtbeobachtung bleibt der Vorgang blockiert. Nur eine vollständig erfüllte Anforderungsmenge ohne Widerspruch erzeugt `VERIFIED`.

## Determinismus und Ablehnungsregeln

Der Wahrheitspfad lehnt ab:

- Floats und NaN,
- secret-förmige Felder,
- implizite Zeitfelder wie `now`, `timestamp`, `created_at` oder `epoch`,
- Sets und andere ungeordnete oder nicht unterstützte Typen,
- unvollständige Git- oder SHA-256-Identitäten,
- unbekannte Operationsfamilien als automatische Freigabe.

Golden Vectors liegen in `backend/tests/fixtures/proof_verdict_golden_vectors.v1.json`. Die kanonische Backend-Datei und ihr Deployment-Spiegel müssen bytegleich bleiben.

## Aktuelle Integrationsgrenze

Version 1 registriert ausschließlich `agent_repository_mutation`. Weitere Operationsfamilien und echte Collector werden in den nachgeordneten Issues des Parent-Issues #1097 integriert. Dieser Core schaltet noch keinen produktiven Mutationspfad um und legt keine neue Datenbank oder Migration an.
