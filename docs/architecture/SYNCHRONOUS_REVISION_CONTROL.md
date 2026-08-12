# Synchrone Revisionskontrolle für Backend und MCP

Die Revisionskontrolle verhindert eine Promotion, bei der Backend, MCP, CI-Evidence und Runtime unterschiedliche Git-Revisionen vertreten. Sie verwendet keinen „latest“-Tag und akzeptiert keine Check-Runs eines anderen Heads.

## CI-Kette

| Stufe | Verbindliche Identität | Fail-closed Bedingung |
|---|---|---|
| Pull Request | Quell-Head des PR | Der `Synchronous Revision Contract` prüft Gate- und Workflow-Verträge. |
| Main-Image-Build | `github.sha` auf `main` | Backend und MCP veröffentlichen jeweils eine JSON-Evidence mit OCI-Revision-Label und Digest. |
| Synchrones Image-Gate | Ein exakter Main-Head | Der Gate-Workflow sucht nur erfolgreiche Backend- und MCP-Workflow-Runs mit identischem `head_sha`, lädt deren Evidence und validiert beide Digests. |
| Release-Readback | Derselbe Main-Head und dieselben zwei Digests | Ein Release-Dispatch benötigt zusätzlich einen Backend-/MCP-/Broker-Runtime-Readback. |

> Ein erfolgreiches Einzelimage, ein `latest`-Tag, ein anderer erfolgreicher Workflow-Run oder ein gesunder Container ohne passende OCI-Revision sind keine ausreichende Promotion-Evidence.

## Betriebsregel

Verwende für eine revisionsgleiche Release-Evidence den Workflow **Synchronous Revision Control** mit `release_mode=true`, der exakten `source_revision` und einem redigierten Runtime-Readback. Das Readback-Dokument muss `sovereign.coordinated-runtime-readback.v1` verwenden und für Backend sowie MCP Quelle, Image-Repository, Digest, Health, Ready und Readback-Bestätigung enthalten. Der Broker muss `BROKER_READY` und `mcpProtocolReady=true` liefern.

Der Workflow blockiert insbesondere in den folgenden Fällen: fehlendes Component-Image, anderer Git-Head, fehlendes oder ungültiges OCI-Label, fehlende Runtime-Evidence, abweichender Container-Digest, ungesunder Service oder nicht bereiter Broker.

## Nachweisartefakte

Die Image-Workflows erzeugen je Main-Head unveränderliche Artefakte mit den Namen `sovereign-backend-immutable-image-evidence-<sha>` und `sovereign-mcp-immutable-image-evidence-<sha>`. Das synchrone Gate erzeugt danach `synchronous-revision-gate-<sha>`. Dieses Artefakt ist die bindende CI-Evidence für die Image-Synchronität; es ersetzt keinen nachgelagerten Runtime-Readback.
