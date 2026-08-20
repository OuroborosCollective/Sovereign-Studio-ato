# TypeScript Contract Pilot v1

## Zweck und Geltungsbereich

Der Pilot unter `contracts/typescript/` untersucht eine isolierte, revisionsgebundene TypeScript-Projektion für drei Verträge: `PermissionReceiptInput`, `WorkflowTransitionPayload` und das ungefährliche, read-only Contract-Catalog-MCP-Tool. Die alleinige kanonische TypeScript-Quellfläche ist `contracts/typescript/src/contracts.ts`. Sämtliche Runtime-Validatoren, JSON-Schema-Projektionen, MCP-Schemas und Contract-Artefakte werden von dieser Quelle durch die gepinnte Typia-/ttsc-Toolchain erzeugt.

| Fläche | Bestehende Wahrheit | Rolle des Piloten |
|---|---|---|
| Python Durable Workflow | `backend/agent_runtime/durable_workflow.py` | Bleibt serverseitige Workflow-, Permission- und Receipt-Wahrheit. |
| Python MCP-Operator | `tools/sovereign-chatgpt-mcp/` | Bleibt bestehende Registry-, Owner-, Capability- und Readback-Grenze. |
| Frontend TypeScript | `src/` | Bleibt außerhalb des isolierten Builds. |
| OpenAPI/JSON-Schema | Bestehende projektspezifische Flächen | Werden nicht ersetzt; der Pilot veröffentlicht nur attestierte Projektionen. |
| TypeScript Contract Pilot | `contracts/typescript/` | Erzeugt strikt validierte, nicht autorisierende Projektionen. |

## Transform- und Evidence-Vertrag

Der Pilot nutzt exakt `typia@14.0.0`, `ttsc@0.28.1` und `typescript@7.0.2`, einschließlich Lockfile-Integrität. Ein normaler `tsc`-Build ohne Transformer muss deterministisch scheitern; `ttsc` erzeugt die ausführbaren Validatoren. Der Artefaktbuilder schreibt nur deterministische Informationen in `artifacts/contracts.json` und `artifacts/manifest.json`: Quellpfad, Quellblob-SHA-256, Repository-Revision, Schema-Version, Toolchain-Versionen, Buildkonfigurationshash sowie Schema- und MCP-Projektionshashes.

> **Strukturelle Validierung bedeutet ausschließlich `STRUCTURALLY_VALID`.** Sie ist weder eine Permission-Entscheidung noch ein Execution- oder Runtime-Readback.

Die kanonische Serialisierung sortiert JSON-Objektschlüssel und weist `NaN`, `Infinity`, negative Null, `undefined`, Funktionen, `BigInt`, `Date`, `Map`, `Set`, Buffer und andere nicht-JSON-Werte zurück. Der erzeugte Snapshot wird vor einer späteren Permission-Anfrage tief eingefroren. Jede semantische Payloadänderung benötigt einen neuen Hash und damit eine neue Permission-Anfrage.

## MCP-Pilotgrenze

`dispatchContractCatalog` ist side-effect-free. Es validiert Input vor Dispatch und Output vor `structuredContent`; fehlerhafte Werte ergeben eine kleine Fehlerstruktur ohne Payload-Echo. Selbst schema-konformer Erfolg trägt ausschließlich `SUCCEEDED_UNVERIFIED`. Dieser Pilot ist keine neue Tool Registry, kein Authentisierungspunkt und kein Ersatz für den serverseitigen Target-Readback aus dem Durable-Workflow-Vertrag.

## Cross-Language- und Drift-Grenze

Die Python-Regression `backend/tests/test_typescript_contract_cross_language.py` lädt das durch TypeScript erzeugte Artefakt und validiert gemeinsame positive sowie negative Fixtures. Sie enthält keine zweite handgeschriebene Schemawahrheit. `pnpm verify` erzwingt Transformer-Typecheck, negativen Stock-tsc-Nachweis, Runtime-Regressionen sowie zwei saubere Builds mit identischen Artefakthashes.

JSDoc ist nur Eigentümerdokumentation im kanonischen Sourcefile. Es enthält keine Secrets, Ownerfreigaben, Runtime-Instructions oder dynamisch ausführbaren Inhalt. Änderungen an JSDoc, Quelltyp, Toolchain, Schema oder Registry-Projektion verändern die attestierte Contract-Artefaktidentität und müssen erneut durch den isolierten Build, Cross-Language-Test und die Projektgates geprüft werden.
