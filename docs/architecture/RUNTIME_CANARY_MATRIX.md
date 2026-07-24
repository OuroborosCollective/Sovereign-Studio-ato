# Revisionsgebundene Runtime-Canary-Matrix

Die kanonische Matrix liegt in:

`config/architecture/SOVEREIGN_RUNTIME_CANARY_MATRIX.v1.json`

Sie trennt für jede releasekritische Produktfamilie:

- statische Architektur- und Sicherheitsgates,
- CI-Canaries,
- erforderliche Live-Canaries,
- dokumentierte Live-Ausschlüsse,
- Cleanup-, Owner- und Budgetgrenzen,
- verpflichtende Evidence-Felder.

## Wahrheitsgrenze

Die Existenz oder erfolgreiche Strukturprüfung der Matrix ist **kein Live-Funktionsbeweis**. Sie belegt ausschließlich, dass jede releasekritische Familie genau einem überprüfbaren Beweisvertrag oder einem nachvollziehbaren, weiterhin reviewpflichtigen Ausschluss zugeordnet ist.

Ein mutierender Canary ist nur gültig, wenn sein Cleanup als `passed` belegt ist. Ein kostenverursachender Canary benötigt zusätzlich ein bestätigtes Owner- und Budget-Gate. Container-Health, Prozess-Liveness oder ein erfolgreiches Build ersetzen keinen erforderlichen Fachcanary.

## Contract-Modus

Jeder Pull Request prüft die Matrixstruktur und die Validator-Regressionen:

```text
node scripts/runtime-canary-matrix-gate.mjs \
  --mode contract \
  --revision <EXAKTE_PR_HEAD_SHA>

pnpm exec vitest run scripts/runtime-canary-matrix-gate.test.mjs
```

Der Contract-Modus schlägt unter anderem fehl bei:

- doppelten oder unvollständigen Oberflächen,
- fehlender Familienabdeckung,
- mutierenden Canaries ohne Cleanup,
- Kostenpfaden ohne Owner-/Budget-Gate,
- undokumentierten Ausschlüssen,
- fehlenden Pflichtfeldern für revisionsgebundene Receipts.

## Release-Modus

Der manuell ausgelöste Release-Modus benötigt eine separate Evidence-Datei mit Schema `sovereign.runtime-canary-evidence.v1`:

```text
node scripts/runtime-canary-matrix-gate.mjs \
  --mode release \
  --revision <EXAKTE_RELEASE_SHA> \
  --evidence <REPOSITORY_RELATIVE_EVIDENCE_DATEI>
```

Für jede Matrixoberfläche mit `liveCanary.policy = required` muss genau ein Receipt vorliegen. Das Release-Gate akzeptiert nur:

- dieselbe exakte Revision,
- Bindung an den kanonischen Matrix-Hash,
- einen konkreten Workflow-Run,
- Status `passed`,
- einen gültigen Evidence-SHA-256,
- `cleanupStatus = passed` bei Mutation,
- `ownerGateStatus = approved` bei Owner-Gates,
- `budgetGateStatus = passed` bei externen Kosten.

`failed`, `blocked`, fehlende oder veraltete Receipts bleiben release-blockierend.

## Dokumentierte Ausschlüsse

Zwei Oberflächen besitzen bewusst keinen ersatzweise erfundenen Live-Canary:

1. **Release-Revisionsintegrität:** ein CI-/Artefaktbindungsvertrag, keine produktive Fachfunktion.
2. **Physischer Android-Geräte-Smoke:** benötigt reale Installation und Bedienung auf Hardware; Repository-, Emulator- oder Build-Evidence darf diesen Beweis nicht ersetzen. Tracking: Issue #871.

Alle Ausschlüsse bleiben `reviewRequired = true`.
