# LLM Routing Truth, FreeLLM Failure Model und Operator-Handoff

Stand: 23. Juli 2026

## 1. Zweck und Verbindlichkeit

Dieses Dokument ist die kanonische technische Wahrheit für alle LLM-Routen im Sovereign Studio ATO. Es ist zugleich Übergabeprotokoll, Fehleranalyse, Betriebsanweisung und Schutz gegen erneute Architekturdrift.

Bei Widersprüchen zwischen älteren Texten, UI-Beschriftungen, historischen Migrationen oder Legacy-Werkzeugen und diesem Dokument gilt:

1. Produktionsausführung und persistierte Runtime-Evidence haben Vorrang.
2. Paid und Free sind getrennte Transporte.
3. LiteLLM ist ein optionaler Legacy-/Rollback-Transport und kein globales Produktions-Gate.
4. Kein Zustand wird allein aufgrund eines Namens, eines Katalogeintrags oder einer Konfiguration als grün dargestellt.
5. Eine Route ist nur aktiv, wenn aktuelle, persistierte und transportgerechte Evidence vorliegt.

## 2. Kanonische Transportarchitektur

### 2.1 Paid

Paid-Ausführung läuft direkt über OpenRouter:

- Transport: `openrouter`
- API-Basis: `https://openrouter.ai/api/v1`
- Schlüsseldatei: `/opt/sovereign-owner-managed/openrouter_api_key.txt`
- Schlüssel wird nicht in PostgreSQL gespeichert.
- Aktivierung benötigt geschützte Owner-Eingabe, Katalog-Readback, verifizierte Preise, Agentenparameter-Eignung und echten Completion-Canary.
- Standard-Markup ist mindestens Faktor 4; höhere Werte können im Admin gespeichert werden.
- Paid-Routen dürfen niemals als Free-Routen kategorisiert werden.

### 2.2 Free

Free-Ausführung läuft direkt über die verwaltete FreeLLM-API beziehungsweise den verwalteten FreeLLM-Pool:

- Transport: `freellm`
- API-Basen:
  - `http://freellmapi:3001/v1`
  - `http://freellmpool:8080/v1`
- interne Schlüsseldateien:
  - `/opt/sovereign-owner-managed/freellmapi_unified_key.txt`
  - `/opt/sovereign-owner-managed/freellmpool_proxy_key.txt`
- Ausführungsprofil: `free_single_agent`
- maximal ein Vordergrundagent, keine Hintergrundagenten
- kein automatischer Wechsel von Free zu Paid
- Nullkosten-Evidence und zwei echte Completion-Canaries sind Voraussetzung für Aktivierung

### 2.3 Legacy LiteLLM

LiteLLM bleibt für historische Providerkonfiguration, Rollback, ältere Evidenz und spezielle Operatorwerkzeuge erhalten. Es ist jedoch nicht mehr:

- alleiniger Provider-Router,
- Pflichtbestandteil des globalen Backend-Healthchecks,
- Eigentümer aller aktiven Online-Routen,
- Standardausführung von `/api/llm/chat`,
- korrekte Beschriftung für OpenRouter- oder FreeLLM-Routen.

Jede Oberfläche, die LiteLLM erwähnt, muss ausdrücklich `Legacy`, `Rollback` oder einen tatsächlich LiteLLM-spezifischen Werkzeugkontext nennen.

### 2.4 Agents-SDK- und Swarm-Grenze

Der produktive REST-, A2A-, Start- und Resume-Pfad beginnt in `agent_runtime/cognitive_swarm_routes.py` und muss vor jedem Modellaufruf `load_execution_resolution(...)` ausführen. Danach gelten harte Verträge:

- Paid-Swarm: `main_route` und `agent_route` sind datenbankaufgelöste direkte OpenRouter-Routen.
- Free-Profil: genau eine datenbankaufgelöste direkte FreeLLM-Route und keine Hintergrundagenten.
- `execute_persisted_swarm(...)` übergibt die aufgelösten Routen ausdrücklich an `run_cognitive_swarm(...)`.
- Ein produktiver Run darf `run_cognitive_swarm(...)` niemals ohne Route aufrufen.

In `agent_runtime/cognitive_swarm_agents.py` verbleiben `_ensure_litellm_runtime_key`, `ensure_openai_runtime_key`, `DEFAULT_MODEL`, historische LiteLLM-Aliasnamen und der No-Route-Zweig ausschließlich als begrenzte Legacy-Test-/Operator-Kompatibilität. Diese Symbole sind kein Beweis für einen aktiven LiteLLM-Produktpfad. Das Flask-Routenmodul importiert oder verwendet den Legacy-Key-Helfer nicht mehr.

Auch Dateinamen und Datenbankspalten wie `sovereignLiteLlmIntentRuntime.ts` oder `litellm_alias` können aus Kompatibilitätsgründen historisch bleiben. Transportwahrheit entsteht ausschließlich aus der aufgelösten Route und ihrer Runtime-Evidence, niemals aus einem alten Symbolnamen.

## 3. Vier verschiedene Schlüsselklassen

Die frühere Fehlinterpretation entstand unter anderem dadurch, dass verschiedene Schlüsselarten begrifflich vermischt wurden.

### 3.1 FreeLLMAPI Unified Service Key

Dieser Schlüssel authentifiziert Sovereign Backend gegenüber der internen FreeLLMAPI. Er ist nicht gleichbedeutend mit einem Schlüssel für jeden sichtbaren Upstream-Provider oder jedes Modell.

Er entsteht beziehungsweise wird verwaltet durch den FreeLLMAPI-Registrierungs-/Bootstrap-Prozess. Falls dieser Prozess unterbrochen wurde, müssen Dateiexistenz, Berechtigungen, Fingerprint und erfolgreicher authentifizierter `/models`-Readback geprüft werden. Ein Unified Key beweist nur den Zugang zur internen API, nicht die Verfügbarkeit aller Upstreams.

### 3.2 FreeLLM Upstream-Provider-Keys

FreeLLMAPI kann Provider wie OVH, Kilo, OpenRouter, Cloudflare, NVIDIA, Groq und weitere im Katalog führen. Viele davon benötigen einen eigenen Provider-Key. Ein Katalogeintrag bedeutet nicht, dass ein solcher Key aktuell aktiviert und gesund ist.

Provider-Keys liegen ausschließlich in:

`/opt/sovereign-owner-managed/freellm-provider-keys`

Der FreeLLM-Bootstrap importiert nur veränderte Fingerprints. Rohwerte werden nicht geloggt oder an PostgreSQL zurückgegeben.

### 3.3 FreeLLM Keyless Marker

Einige Provider dürfen kontrolliert ohne eigenen API-Key aktiviert werden. Die aktuell begrenzte Allowlist ist bewusst klein und muss im Codevertrag geprüft werden. Ein Keyless-Marker ist eine geschützte 0600-Datei und keine Behauptung, dass der Upstream jederzeit verfügbar ist.

Keyless bedeutet:

- kein benutzereigener Provider-Key erforderlich,
- aber weiterhin Quota, Rate-Limits, Provider-Cooldowns und zeitweise Nichtverfügbarkeit möglich,
- weiterhin echte Completion-Canaries erforderlich.

### 3.4 OpenRouter Paid Key

Der OpenRouter-Key ist ausschließlich für den direkten bezahlten Transport bestimmt. Er darf nicht als FreeLLM-Unified-Key, FreeLLM-Upstream-Key oder LiteLLM-Master-Key interpretiert werden.

## 4. Entdeckte Hauptursache

Der FreeLLM-Katalog beschreibt mögliche Poolrouten. Die bisherige Sovereign-Logik behandelte jedoch jeden sichtbaren Alias wie eine dauerhaft eigenständig ausführbare Providerroute.

Ein FreeLLM-Canary konnte beispielsweise mit folgenden realen Ursachen scheitern:

- kein aktuell aktivierter und gesunder Provider-Key für die Plattform,
- keyloser Provider in Cooldown,
- Rate-Limit,
- zeitweiser Upstream-Ausfall,
- Modell derzeit nicht über einen gesunden Provider erreichbar,
- Timeout oder Gatewayfehler.

Diese temporären Verfügbarkeitszustände wurden pauschal als:

`status='blocked'` und `last_error_code='free_provider_canary_failed'`

gespeichert. Damit wurden vier verschiedene Wahrheiten unzulässig vermischt:

1. Modell wurde nur entdeckt und noch nicht geprüft.
2. Modell ist Nullkosten-verifiziert, hat aber gerade keinen verfügbaren Upstream.
3. Modell ist temporär rate-limitiert oder in Cooldown.
4. Modell verletzt tatsächlich Credential-, Kosten-, Evidence- oder Sicherheitsregeln.

Die zwei real aktiven Routen `auto` und `fusion` waren keine Beweise für zwei alte LiteLLM-Modellschlüssel. Sie sind FreeLLM-Poolprofile. Live-Logs belegten erfolgreiche Ausführungen über OVH und Kilo.

## 5. Verbindliches Zustandsmodell

### 5.1 `discovered`

Bedeutung: Katalog- und Nullkosten-Evidence ist vorhanden, aber eine aktuelle erfolgreiche Doppel-Canary fehlt.

Hierzu gehören auch temporäre Verfügbarkeitsfehler:

- `freellm_rate_limited`
- `freellm_timeout`
- `freellm_upstream_unavailable`
- historische generische `free_provider_canary_failed`, sofern kein härterer Beweis vorliegt
- HTTP-4xx/5xx eines Pool-Alias, wenn dies lediglich fehlende Upstream-Verfügbarkeit bedeutet

Folgen:

- Route bleibt deaktiviert.
- Zustand wird in der UI gelb als `wartet auf Upstream` beziehungsweise `erneut prüfbar` gezeigt.
- Er darf nicht als endgültiger Modellfehler behauptet werden.
- Ein späterer Recheck darf die Route aktivieren, sobald beide Canaries erfolgreich sind.

### 5.2 `ready`

Voraussetzungen:

- Providerquelle aktiviert,
- authentifizierter Katalog HTTP 200,
- Free-/Nullkostenvertrag bestätigt,
- Pricing-Evidence aktuell,
- zwei echte Completion-Canaries erfolgreich,
- kein positiver Providerkostenwert,
- Route in `llm_routes` vorhanden und `disabled=false`,
- Transport `freellm`,
- Profil `free_single_agent`,
- eigene gültige Quota-Scope,
- kein aktiver Block oder Cooldown.

Nur `ready` darf ausgeführt werden.

### 5.3 `blocked`

Dieser Zustand ist für harte Beweise reserviert, zum Beispiel:

- Credential abgelehnt,
- Rohschlüssel-/Dateivertrag ungültig,
- positiver Kostenwert bei einer als kostenlos behaupteten Route,
- unvollständige oder widersprüchliche Doppel-Canary-Evidence,
- Modell fehlt aus dem aktuellen Katalog,
- ungültige oder zu große Providerantwort,
- verbotener Transport, API-Endpunkt oder Redirect,
- Policy- oder Sicherheitsverletzung.

Folgen:

- Route bleibt deaktiviert.
- UI zeigt rot `hart blockiert`.
- Reaktivierung verlangt die zur Fehlerfamilie passende neue Evidence.

### 5.4 `disabled`

Die gesamte Providerquelle wurde bewusst ausgeschaltet. Alle zugehörigen Routen bleiben deaktiviert. Ein erneutes Einschalten aktiviert keine Route automatisch; Discovery und Canaries müssen erneut durchgeführt werden.

## 6. Warum 61 oder 93 Modelle nicht 61 oder 93 ausführbare Routen bedeuten

Folgende Zählungen sind getrennt darzustellen:

- `model_count`: im Katalog sichtbare Modelle
- `free_verified_count`: Modelle, deren Preis-/Quota-Vertrag als Nullkostenvertrag akzeptiert ist
- `discovered/deferred`: Nullkostenkandidat ohne aktuelle erfolgreiche Doppel-Canary
- `ready_count`: aktuell ausführbare Routen
- `blocked_count`: harte Policy-/Credential-/Evidence-Verstöße

Die Oberfläche darf `free_verified_count` niemals als `aktive Free-Routen` bezeichnen.

## 7. Datenbank-Wahrheit

Relevante Tabellen:

- `llm_revolver_provider_sources`
- `llm_revolver_provider_models`
- `llm_revolver_provider_checks`
- `llm_routes`
- `llm_route_revolver_state`
- `llm_route_attempts`
- `llm_usage_settlements`
- `llm_provider_deployments`
- `schema_migrations`

Wichtige Regeln:

- `llm_revolver_provider_models.litellm_alias` ist ein historischer Spaltenname. Der Wert ist heute ein Sovereign-Routenalias und kein Beweis, dass die Ausführung durch LiteLLM läuft.
- Transportwahrheit wird aus `runtime_kind`, `provider`, `config.transport`, `base_url` und dem aktuellen Routevertrag gemeinsam bestimmt.
- `disabled=false` allein reicht nicht. Pricing, Canary, Profil, Quota und Transportvertrag müssen ebenfalls stimmen.
- Migrationen werden bei Deployments wiederholt abgespielt. Jede neue Migration muss idempotent sein und darf historische Migrationen nicht unbemerkt wieder falsche Zustände setzen lassen.

## 8. Runtime-Ausführung

### 8.1 Öffentlicher Produktpfad

`/api/llm/chat` muss providerneutral arbeiten und nur aktive direkte Transporte akzeptieren:

- OpenRouter Paid
- FreeLLM Free

Der Pfad darf nicht mehr ausschließlich auf `provider='litellm'` filtern.

### 8.2 Fallback-Regel

- Paid darf im automatischen Modus auf eine verifizierte FreeLLM-Route zurückfallen, wenn keine Provider-Nutzung stattgefunden hat und der Fehler retryfähig ist.
- Free darf niemals automatisch auf Paid/OpenRouter wechseln.
- Nach nachweisbarer Provider-Nutzung darf kein blinder Retry auf einen anderen Provider erfolgen; zuerst muss Settlement erfolgen.

### 8.3 Netzwerkgrenzen

Direkte Requests müssen:

- Proxy-Environment ignorieren (`trust_env=false`),
- Redirects ablehnen,
- Antwortgrößen begrenzen,
- feste Timeouts verwenden,
- nur die erlaubten API-Basen und Schlüsseldateien akzeptieren,
- keine Rohantworten oder Schlüssel persistieren.

## 9. Admin-Oberfläche und Statuslampen

### 9.1 Paid-Bereich

Beschriftung: `OpenRouter Paid`

Nicht erlaubt:

- `LiteLLM Paid`, wenn die Route `runtime_kind='openrouter'` hat,
- OpenRouter-Route ohne geschützten Key/Katalog/Preis/Canary als aktiv darstellen,
- Free-Kategorie auf OpenRouter-Paid-Routen.

### 9.2 Free-Bereich

Getrennte Zahlen und Lampen:

- grün: aktive, aktuelle, doppelt gecanaryte Free-Routen
- gelb: Nullkosten bestätigt, wartet auf verfügbaren Upstream oder erneute Canary
- rot: harter Blocker
- neutral: nur katalogisiert oder Evidence abgelaufen

### 9.3 Enterprise Control Center

Pflichtintegration ist `llm-routing`, nicht `litellm`.

Evidence muss mindestens enthalten:

- `freellmReadyRoutes`
- `openrouterReadyRoutes`
- `legacyLiteLlmActiveRoutes`
- Routing-Policy

Ein optionaler LiteLLM-Completion-Canary muss sichtbar als Legacy-Canary bezeichnet werden und darf den direkten Produktionspfad nicht repräsentieren.

## 10. PatchMon- und Operatorpflicht

Bei jeder zukünftigen LLM-Routenänderung sind folgende Werkzeuge zu verwenden:

1. `patchmon_runtime_inventory(include_fleet=true)`
2. `patchmon_brain_snapshot(include_fleet=true)`
3. Containerstatus und begrenzte Logs für:
   - `sovereign-backend`
   - `sovereign-freellmapi`
   - `sovereign-litellm` nur bei Legacy-Fragen
4. PostgreSQL-Readback der Quellen, Modelle, Routen, Cooldowns und Attempts
5. exakte Repository-/PR-/CI-/Deployment-Revision
6. immutable Backend-Image-Digest
7. `/health/live` und `/health/ready` nach Deployment

PatchMon darf nicht durch UI-Anzeigen ersetzt werden. Eine grüne Lampe ist keine Runtime-Evidence.

## 11. Revisions- und Deploymentvertrag

Vor Merge:

- Workspace muss sauber und auf aktuellem `main` basieren.
- Python-Compile, fokussierte Backendtests, Provider-/Resolvertests und Frontend-Typecheck müssen grün sein.
- Migration muss im Preview-DB-Transaction erfolgreich laufen und zurückgerollt werden.
- Secret-Triage und Architektur-Inventar müssen keine neuen kritischen Befunde zeigen.
- PR-Head, CI-Head und erwartete Merge-Revision müssen eindeutig sein.

Nach Merge:

- Backend-Image ausschließlich für den exakten Merge-SHA auflösen.
- Revision-Label und immutable Digest prüfen.
- Genau diesen Digest deployen.
- `/health/live` muss denselben Source-SHA und Digest melden.
- `/health/ready` darf LiteLLM nur dann prüfen, wenn aktive Legacy-LiteLLM-Routen existieren.
- PostgreSQL muss Migration 038 und die neue Zustandsverteilung zeigen.

## 12. Erwarteter Zustand nach der Korrektur

Historische generische `free_provider_canary_failed`-Einträge werden nicht automatisch aktiviert. Sie werden zu `discovered`/`freellm_upstream_availability_unconfirmed` umklassifiziert und bleiben `enabled=false`.

Die bisherigen echten `ready`-Routen bleiben aktiv, sofern ihre Evidence weiterhin gültig ist. Weitere Modelle werden erst nach erfolgreicher Doppel-Canary aktiv.

Damit wird weder Fake-Green erzeugt noch eine funktionierende FreeLLM-Methodik unnötig verworfen.

## 13. Diagnoseabfragen

### Quellenübersicht

```sql
SELECT source.id, source.label, source.api_base, source.auth_mode,
       source.status, source.enabled, source.last_http_status,
       source.last_error_code,
       COUNT(model.id) AS model_count,
       COUNT(model.id) FILTER (WHERE model.free_verified) AS free_verified_count,
       COUNT(model.id) FILTER (
         WHERE model.status='ready' AND model.enabled
       ) AS ready_count,
       COUNT(model.id) FILTER (
         WHERE model.status='discovered'
       ) AS deferred_count,
       COUNT(model.id) FILTER (
         WHERE model.status='blocked'
       ) AS blocked_count
FROM llm_revolver_provider_sources AS source
LEFT JOIN llm_revolver_provider_models AS model
  ON model.source_id=source.id
GROUP BY source.id
ORDER BY source.created_at DESC;
```

### Aktive direkte Routen

```sql
SELECT id, model_id, provider, runtime_kind, disabled,
       config->>'executionProfile' AS execution_profile,
       config->>'pricingVerified' AS pricing_verified,
       config->>'canaryVerified' AS canary_verified,
       config->>'quotaScope' AS quota_scope
FROM llm_routes
WHERE disabled=false
  AND lower(COALESCE(runtime_kind, provider)) IN ('openrouter','freellm')
ORDER BY priority, model_id;
```

### Blockerverteilung

```sql
SELECT status, COALESCE(last_error_code, '<none>') AS blocker,
       COUNT(*) AS models
FROM llm_revolver_provider_models
GROUP BY status, COALESCE(last_error_code, '<none>')
ORDER BY status, models DESC;
```

## 14. Stop-Kriterien

Arbeit sofort als blockiert melden, wenn:

- ein Free-Canary positive Providerkosten meldet,
- OpenRouter ohne verifizierten geschützten Key aktiviert werden soll,
- ein direkter Transport auf eine unbekannte Basis-URL zeigt,
- Source-SHA, Image-Digest und Runtime-Readback nicht übereinstimmen,
- ein Rohschlüssel in Datenbank, Log, PR, UI oder API-Antwort auftaucht,
- Free automatisch auf Paid fällt,
- ein temporärer Upstream-Fehler erneut als endgültiger Modelldefekt gespeichert wird,
- Migrationen beim Replay aktive verifizierte Routen wieder deaktivieren.

## 15. Übergabe an einen frischen Operator oder Chat

Ein neuer Operator darf nicht bei null beginnen. Er muss zuerst:

1. dieses Dokument vollständig lesen,
2. aktuelle `main`-Revision, offene PRs und Deployments auflösen,
3. PatchMon-Inventar und Brain-Snapshot erfassen,
4. Produktions-DB mit den Abfragen aus Abschnitt 13 lesen,
5. Live-Containerstatus und begrenzte FreeLLMAPI-Logs prüfen,
6. zwischen Unified Key, Provider-Key, Keyless-Marker, OpenRouter-Key und LiteLLM-Legacy-Key unterscheiden,
7. keinen Katalogzähler als aktive Routenzahl interpretieren,
8. jede Änderung in isoliertem Workspace mit Tests, Draft PR, CI, Merge und immutable Deployment durchführen,
9. nach erfolgreichem Runtime-Readback ein Proven-Learning-Pattern schreiben.

Die zentrale Erkenntnis lautet:

> FreeLLM ist funktionsfähig. Der Hauptfehler war eine falsche Zustands- und Schlüsselmodellierung im Sovereign Backend sowie verbliebene LiteLLM-Livepfade und Beschriftungen. Temporäre Poolverfügbarkeit muss retryfähig bleiben, während echte Kosten-, Credential- und Policy-Verstöße weiterhin fail-closed blockiert werden.
