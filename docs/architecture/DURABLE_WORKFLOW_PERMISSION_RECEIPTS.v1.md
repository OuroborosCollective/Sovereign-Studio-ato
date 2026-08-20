# Durable Workflow and Permission Receipts v1

> **Status:** Kanonischer Backendvertrag für Issue #1113. Die Dokumentation beschreibt keine produktive Ausführung oder ein Deployment; sie beschreibt die strikt gebundene Zustands- und Receipt-Grenze.

## Zweck

Ein mehrphasiger Agentenablauf wird als revisionsgebundener, append-only Receipt-Strom geführt. Jede mutierende Ausführung benötigt eine server-resolvierte Workflowbindung und eine konkrete Permission für exakt den normalisierten Payload. Tool-Erfolg ist niemals selbst ein Verifikationsnachweis.

| Objekt | Schema | Wahrheitsrolle |
|---|---|---|
| `WorkflowBinding` | `sovereign.durable-workflow.v1` | Bindet Lauf, Owner, Tenant/Organisation, Repository, Workspace, Definition und Basisrevision. |
| `WorkflowStep` | `sovereign.workflow-step.v1` | Deklariert erlaubte Zustände, Capability, Timeout, Versuchslimit, Idempotenz und Pflicht-Readbacks. |
| `PermissionReceipt` | `sovereign.permission-receipt.v1` | Bindet Permission, normalisierten Payload, Effektfläche, Ablaufzeit und Genehmigungsentscheidung. |
| `ExecutionReceipt` | `sovereign.execution-receipt.v1` | Bindet tatsächlichen Versuch, Payloadhash, beobachtete Revision, Effektflächenhash und Readback-Verdikt. |

## Autoritätsgrenze

Die Serverroute oder der Worker muss `WorkflowBinding` ausschließlich aus einem owned Job, Workspace oder einem signierten serverseitigen Scope bilden. Clientfelder für Owner, Repository, Workspace, Revision oder Capability dürfen keine Bindung ersetzen. Credentials werden nicht im Receipt gespeichert.

Ein mutierender Schritt benötigt mindestens einen erlaubten Readback-Typ. Die API oder UI projiziert nur eine vorhandene Permission; sie darf keinen Payload, keine Repositoryidentität, keine Revision oder Wirkfläche nachträglich ändern.

## Zustands- und Verdict-Regeln

| Beobachtung | Zulässiger Zustand/Verdikt |
|---|---|
| Permission fehlt oder ist nicht `APPROVED` | `WAITING_FOR_PERMISSION` oder `BLOCKED` |
| Ausführung endet erfolgreich, aber Readback fehlt | `SUCCEEDED_UNVERIFIED` |
| Passender, unabhängiger Readback auf derselben Repository-/Revisionsbindung | `VERIFIED` |
| Readback widerspricht Repository, Revision oder Effekt | `CONTRADICTED` |
| Ablaufzeit, ungültige Permission oder neue Wirkfläche | `INVALIDATED` oder `BLOCKED` |
| Neustart nach unbestätigter Mutation | `WAITING_FOR_EXTERNAL_EVIDENCE`; niemals Blind-Retry |

## Persistenz

Migration `057_durable_workflow_permission_receipts.sql` schafft die Tabellen `durable_workflow_runs`, `workflow_permission_receipts` und `workflow_execution_receipts`. Alle Tabellen sind append-only: `UPDATE` und `DELETE` werden in PostgreSQL durch Trigger abgelehnt. Jede Zeile enthält nur kanonische, sekretbereinigte Bodies und kryptografische Bindungen.

Die Deployment-Mirror für Runtime und Migration müssen bytegleich sein. Jede produktive Verwendung verlangt zusätzlich einen aktuellen Kontinuitätshandoff, qualifizierte Tests und die üblichen revisionsgebundenen CI-/Runtime-Readbacks.

## Absichtlich ausgeschlossene Quellen

LLM-Ausgabe, Retrieval/Vector Memory, UI-Status, Eventtelemetrie, Tooltext, Returncodes und manuell editierte Statuswerte können weder Permission noch Transition noch `VERIFIED` erzeugen. Externe Toolimporte sind nicht Teil dieses Vertrags und benötigen bei späterer Aktivierung eine getrennte Commit-/Digest-/Registry-Evidence-Kette.
