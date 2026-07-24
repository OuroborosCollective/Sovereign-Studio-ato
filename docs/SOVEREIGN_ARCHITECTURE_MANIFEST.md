# Sovereign Studio ATO — Architektur- und Projektmanifest

**Status:** Lebendes Architekturhandbuch  

**Evidence-Stand:** 23. Juli 2026

**Issue-Nachtrag vom 24. Juli 2026:** Der Vertrag `historical-schema-ownership` aus GitHub-Issue #876 ist durch PR #973, den installierten MCP-Readback und den versionierten Closure-Record `docs/architecture/SOVEREIGN_MANIFEST_ISSUE_CLOSURE_876_2026-07-24.json` abgeschlossen. Die übrigen Manifestpunkte bleiben von diesem gezielten Nachtrag unberührt.

**Verbindliche LLM-Routing-Aktualisierung:** Die aktuelle Transport-, Schlüssel-, Zustands- und Operatorwahrheit steht in [`LLM_ROUTING_TRUTH_AND_HANDOFF.md`](./LLM_ROUTING_TRUTH_AND_HANDOFF.md). Paid läuft ausschließlich direkt über OpenRouter, Free ausschließlich direkt über FreeLLM. LiteLLM ist nur noch deaktivierte historische Evidence und kein aktivierbarer Produkt- oder Rollbacktransport. Ältere LiteLLM-Belege in diesem Manifest sind historische Provenance.

- **Audit-Baseline dieses Manifest-Updates:** `246e701f5b2d8ce94c21c001b26bf4aee216239c`
- **Produktive MCP-Revision:** `246e701f5b2d8ce94c21c001b26bf4aee216239c`
- **Produktives MCP-Image:** `sha256:25f00872bf26c6702cf0a04f0a7dcccc6bfd3e025a2081ee40bbae4bba137c1b`
- **Manifest-/Issue-Reconciliation:** PR #868 wurde als reiner Dokumentations-/Workflow-Merge `27e96907c4c95b94a5722b2530804dbf88d9ea51` übernommen. Der owner-gated Issue-Workflow `29767947369` lief auf exakt dieser Revision erfolgreich und erzeugte beziehungsweise bestätigte für alle zwölf stabilen Marker je ein eigenes Issue.
- **Backend-Releasezustand:** Code und immutable Image für `246e701f5b2d8ce94c21c001b26bf4aee216239c` sind vorhanden; der produktive Backend-Container läuft noch auf dem Stand vor PR #867. Deployment, Migration `028` und Live-Readback bleiben offen.

**Repository:** `OuroborosCollective/Sovereign-Studio-ato`  
**Produkt:** Android-first NoCode-/AI-Service- und Agentenplattform  
**Kanonische Regel:** Die Runtime erzeugt Wahrheit. Die UI zeigt diese Wahrheit nur an.

---

## 0. Leseregel und Wahrheitsklassen

Dieses Dokument trennt jeden Architekturpunkt in drei Klassen:

- **BELEGT:** im aktuellen Repository, in einer Migration, einem Runtime-Vertrag oder durch echte Control-Plane-Evidence nachgewiesen.
- **TEILWEISE:** wesentliche Verträge sind vorhanden, aber mindestens ein Produktions-, Paritäts- oder Betriebsbeweis fehlt.
- **BLOCKIERT:** die Arbeit ist begonnen, kann wegen eines realen fehlgeschlagenen Gates aber nicht als erledigt gelten.
- **ZIEL:** beschlossene Zielarchitektur, noch nicht vollständig produktiv belegt.
- **OFFEN:** fehlende Evidence, noch zu implementierender Vertrag oder ungeprüfter Betriebszustand.

Ein geplanter Container, Endpoint oder Ablauf wird niemals als produktiv bezeichnet, solange Runtime-Evidence fehlt.

---

# 1. Projektvision

Sovereign Studio ATO ist eine Android-first Entwicklungs- und Automationsplattform, die natürliche Sprache in kontrollierte, nachvollziehbare technische Arbeit übersetzt.

Der Nutzer arbeitet primär in einem ruhigen Chat. Sovereign analysiert den Auftrag, ermittelt den benötigten Kontext, wählt eine erlaubte Route und führt nur solche Aktionen aus, deren Voraussetzungen und Berechtigungen durch die Runtime bestätigt sind.

Das Produkt soll insbesondere:

- Repositorys verstehen und bearbeiten,
- Fehler und Fehlerfamilien analysieren,
- Patches erzeugen und prüfen,
- Tests und Builds anstoßen,
- Dokumente einlesen und erzeugen,
- Agenten koordinieren,
- Runtime-Evidence speichern,
- maximal einen Draft PR als kontrollierten Ausgang erzeugen.

Sovereign ist kein UI-Dashboard, das Aktivität simuliert. Es ist eine Runtime mit einer schlichten Chat-Oberfläche.

## 1.1 Produktgrundsätze

1. Runtime erzeugt Wahrheit.
2. UI zeigt nur belegte Wahrheit.
3. Kein Fake-Erfolg.
4. Kein harter Prozentfortschritt ohne reale Berechnung.
5. Keine Mocks, Stubs oder Fassaden im Live-Pfad.
6. Kein unautorisierter oder gate-loser Auto-Merge.
7. Der Standardpfad endet bei einem Draft PR. Der private owner-scoped Operator darf einen PR nur nach ausdrücklicher Owner-Freigabe, exakter Head-SHA-Bindung, bestätigter Mergefähigkeit und relevanten grünen Gates mergen.
8. Jede Aktion erzeugt ein Ergebnis.
9. Jedes Ergebnis erzeugt einen gespeicherten Zustand.
10. Jeder Zustand erlaubt oder blockiert die nächste Aktion.
11. Evidence schlägt Vermutung.
12. Secrets erscheinen niemals im Frontend, in Logs, im Chat oder im Repository.

---

# 2. Wichtigste Architekturänderung: Sprache gehört dem Online-LLM

## 2.1 Verbindlicher Grundsatz

**Natürliche Sprache wird ausschließlich durch das online angebundene LLM verstanden.**

Runtime, Executor, MCP, Router und Backend interpretieren keine freie Sprache als fachliche Wahrheit. Sie verarbeiten ausschließlich strukturierte, validierbare Intent- und Action-Evidence.

## 2.2 Verantwortungsgrenze

### Online-LLM

Das Online-LLM darf:

- natürliche Sprache verstehen,
- Gesprächskontext erfassen,
- Bedeutung und Nutzerziel ableiten,
- eine Assistant-Antwort formulieren,
- strukturierten Intent erzeugen,
- strukturierte Action-Evidence vorschlagen,
- Unsicherheit und fehlenden Kontext kennzeichnen.

Das Online-LLM darf nicht:

- Berechtigungen erfinden,
- Tool-Verfügbarkeit behaupten,
- Runtime-Erfolg erzeugen,
- Tests als bestanden markieren,
- einen Draft PR als erstellt melden, bevor die Runtime ihn belegt,
- Provider-, Credit- oder GitHub-Zustände mutieren.

### Runtime, Backend, Router, MCP und Executor

Diese Schichten übernehmen:

- Schema- und Vertragsvalidierung,
- Berechtigungen,
- Sicherheitsgrenzen,
- Gatekeeping,
- Tool Contracts,
- Zustandsautomat,
- Executor-Auswahl,
- Retry und Recovery,
- Evidence-Erzeugung,
- Speicherung,
- Audit,
- Abrechnung.

Sie betreiben **kein Sprachverständnis**.

## 2.3 Strukturierter Übergabevertrag

```text
User Text
  → Online-LLM
  → Assistant Response
  → IntentEvidence
      intentType
      target
      requestedOutcome
      requiredCapabilities
      riskClass
      confidence/uncertainty
      proposedActions[]
  → Runtime Validation
  → Allowed | Blocked | Needs Owner Input
  → Tool Execution
  → Result Evidence
  → Stored State
  → Next Allowed Action
```

## 2.4 Offline-Fallback

Ein Offline-Fallback ist nur zulässig, wenn er:

- klar als Offline-Fallback markiert ist,
- keine Online-Sprachverständnisqualität vortäuscht,
- keine Schreibaktion automatisch freigibt,
- keine Runtime-Wahrheit erzeugt,
- nur begrenzte, deterministische Hilfsfunktionen ausführt.

---

# 3. Gesamtarchitektur

## 3.1 Kanonischer Hauptpfad

```text
User
  ↓
Android/Web Frontend
  ↓
Sovereign Backend
  ↓
PostgreSQL-gebundener Route Resolver
  ↓
OpenRouter Paid direkt | FreeLLM Free direkt
  ↓
Provider beziehungsweise FreeLLM-Pool
  ↓
LLM-Antwort + strukturierte Intent-Evidence
  ↓
Sovereign Runtime
  ↓
Tool-/Agent-/Executor-Ausführung
  ↓
Result Evidence
  ↓
Persistierter State
  ↓
UI-Anzeige und nächste erlaubte Aktion
```

## 3.2 Schichten

1. **Frontend:** Chat, Eingabe, kompakte Statusanzeige, Inspektionsflächen.
2. **Backend:** Auth, Credits, Admin, LLM-Route, Toolchain, Persistenz.
3. **LLM-Transporte:** OpenRouter Paid direkt und FreeLLM Free direkt; LiteLLM ausschließlich als deaktivierte historische Evidence.
4. **Runtime Library:** Verträge, Gates, State Machine, Evidence, Recovery.
5. **Executor Layer:** interne Agent Runtime, MCP, GitHub, Workspaces, Tests.
6. **Storage:** PostgreSQL, pgvector/Knowledge, Audit, Learning Candidates.
7. **Operations:** Docker, Control Plane, Broker, Health, immutable Deployments.

---

# 4. Frontend

## 4.1 Zentrale Arbeitsfläche

Der kanonische sichtbare Live-Pfad ist Chat-first. Die zentrale Arbeitsfläche liegt im bestehenden Produktpfad und darf nicht durch eine zweite Workbench oder ein Dashboard ersetzt werden.

Standardmäßig sichtbar:

- Chat-Timeline,
- Texteingabe,
- kleine Thinking-/Statushinweise,
- kompakte Runtime-Lampen,
- ruhiger Tool-Launcher,
- echte Blocker und nächste erlaubte Aktion.

## 4.2 Bereiche

### Chat

Primäre Oberfläche für:

- Fragen,
- Repository-Aufträge,
- Analyse,
- Code- und Dokumentaufträge,
- Draft-PR-Aufträge,
- Runtime-Erklärungen.

### Builder

Bezeichnung für die zentrale Arbeitsoberfläche und deren Runtime-gebundene Interaktionen. Builder darf keine eigene fachliche Wahrheit erzeugen.

### Admin

Backend-gebundene Inspektions- und Verwaltungsfläche für Owner/Admins. Keine Provider-Secrets im Browserzustand.

### Repo

Zeigt belegten Repository-Kontext, Branch, Dateien, Snapshot-Status und Zugriffsgates.

### Settings

Zeigt konfigurierbare, nicht geheime Produkt- und Sessioneinstellungen. Serverkritische Einstellungen bleiben Backend-/Admin-Verträge.

### Evidence

Zeigt Resultate, Toolaufrufe, Tests, Runtime-Gates, Blocker und Provenance.

### Runtime

Inspektionsfläche für State Machine, aktuelle Aktion, Result, gespeicherten Zustand und nächste Aktion.

### Mobile, Android und Tablet

- Android-first Layout,
- Zielbreite ab 360 dp,
- Touch-Ziele mindestens 48 dp,
- keine Desktop-only Pflichtinteraktion,
- WebView-/Browser-Fallback,
- verständliche Fehlerflächen,
- keine versteckten kritischen Zustände.

---

# 5. Sovereign Backend

## 5.1 Aufgaben

Das Backend ist die kanonische Serverinstanz für:

- Authentifizierung und Sessions,
- Nutzer- und Adminzugriffe,
- Credit-Reservierung und Settlement,
- PostgreSQL-Persistenz,
- providerneutrales LLM-Routing über direkte OpenRouter-/FreeLLM-Transporte,
- MCP-/Toolchain-Bridges,
- GitHub- und Draft-PR-Verträge,
- Agent-Job-Persistenz,
- Runtime-/Audit-Evidence,
- Provider- und Modellverwaltung.

## 5.2 Kanonische Betriebsinstanz

Die Admin-Backend-Instanz unter
`https://sovereign-backend.arelorian.de/admin`
ist der vorgesehene kanonische Backend-/Admin-Livepfad.

**BELEGT:** Die produktive Backend-Anwendung besitzt eine eindeutige kanonische Quelle: `scripts/sovereign-backend/app.py`. Das immutable Backend-Image wird ausschließlich aus diesem Deploymentbaum gebaut. Eine zweite Datei `backend/app.py` existiert nicht; nur ausgewählte Supportmodule besitzen weiterhin bytegleich geprüfte Analyse-/Kompatibilitätsspiegel.

**BELEGT:** Die tatsächlich gespiegelten Agent-Runtime-, A2A-, ARE-, Knowledge-, Security-, LiteLLM-, `knowledge_library.py`- und `r2_storage.py`-Dateien sind im Architektur-Snapshot bytegleich. Der produktive R2-Adapter verwendet die vollständige fail-closed Implementierung einschließlich Pfad-, MIME-, Hash-, Evidence- und 33-MiB-PDF-Grenzen.

**BELEGT — Code auf `main`:** PR #867 ersetzte die ausgelieferte `/admin`-Wahrheit durch `scripts/sovereign-backend/enterprise_admin_ui.py` und ergänzte die persistierbare Standing-Owner-Policy in Migration `028_owner_learning_policy.sql`. Das immutable Backend-Image für Revision `246e701f5b2d8ce94c21c001b26bf4aee216239c` wurde erfolgreich als Digest `sha256:629a694d67c4789053da81656cbc7523a084b8ac52877ff2083aa0325453ae18` gebaut.

**TEILWEISE — produktive Aktivierung:** Der laufende Backend-Container wurde vor diesem Merge gestartet. `owner_learning_policies` fehlt im Live-Schema und Migration `028` ist nicht registriert. Die neue Adminoberfläche und die Standing-Learning-Policy sind daher code- und image-belegt, aber noch nicht produktiv readback-verifiziert.

---

# 6. Admin Backend

Das Admin Backend verwaltet keine bloßen UI-Listen, sondern serverseitige Verträge und persistierte Zustände.

## 6.1 Benutzer

- Nutzerliste,
- Rollen und Status,
- Sperren/Entsperren,
- Session-/Security-Policies,
- user-scoped Jobs und Evidence.

## 6.2 Credits und Preise

- Credit Ledger,
- Credit Adjustments,
- Pakete,
- Zahlungstransaktionen,
- provider-finanzierte Credits aus echten Käufen,
- Reservierung vor Provider-Ausführung,
- Settlement aus direkten Providerkosten und Usage-Evidence,
- Refund bei belegtem Fehlschlag,
- Admin-Statistiken.

**BELEGT:** Das Datenmodell besitzt jetzt eine getrennte `provider_funded_credits`-Spalte, damit Bonus-, Admin- oder Testgutschriften nicht automatisch externe Providerkosten auslösen dürfen. Migration `022` wurde aus der unveränderten Repository-Quelle mit SHA-256 `7c08cf8f92dafe264171d62a19cd6bbc5accf1264574a00ad7f468c7323bdfa4` angewendet. Der anschließende Live-Readback bestätigte den Ledger-Eintrag `022`, alle sieben neuen Constraints, `0` ungültige provider-finanzierte Balances und `0` aktive Routen mit ungeprüfter Preisgrundlage.

## 6.3 Modelle, Provider und Routen

- Provider Registry,
- getrennte OpenRouter-Paid- und FreeLLM-Free-Modellkataloge,
- drei Kostenkategorien,
- Modellinventar,
- Modellalias,
- Preis-Metadaten,
- Route-Status,
- Canary- und Health-Evidence,
- Aktivierung nur nach vollständigem Gate.

Die drei Kostenkategorien sind verbindlich:

1. `free`: nur direkte FreeLLM-Revolver-Routen mit bestätigtem Nullkostenvertrag und zwei echten Completion-Canaries.
2. `standard`: bezahlte Standardrouten mit mindestens `×4` auf echte Providerkosten.
3. `premium`: Premiumrouten mit mindestens `×8` auf echte Providerkosten.

Ein höherer Multiplikator ist zulässig; ein niedrigerer Multiplikator wird durch Backend-Policy und Datenbank-Constraint abgelehnt.

## 6.4 Statistiken

- Usage,
- Kosten,
- Fehlerraten,
- Provider-/Modellzustand,
- Agent- und Toolausführungen,
- Audit.

## 6.5 Runtime, MCP und GitHub

- Control-Plane-Status,
- MCP-Vertrag,
- Brokerzustand,
- GitHub-OAuth-/Access-State,
- Draft-PR-Evidence,
- Workflow- und Release-Gates.

---

# 7. Neue Providerverwaltung — Zielarchitektur

## 7.1 Ziel

Ein Admin trägt ausschließlich einen neuen Provider-Key über einen geschützten Owner-Kanal ein. Danach übernimmt die Runtime den vollständigen, belegbaren Onboardingprozess.

## 7.2 Automatischer Ablauf

```text
Protected Owner Input
  → Provider identifizieren
  → Credential-Metadaten speichern, Secret selbst verborgen
  → Modelle abrufen
  → Provider validieren
  → Preise abrufen oder Admin-Ergänzung anfordern
  → Modellaliase planen
  → Datenbankeinträge erzeugen
  → passenden Direkttransport und PostgreSQL-Route aktualisieren
  → transportgerechte Readiness prüfen
  → Canary je Alias ausführen
  → passende Backend-Routen atomar aktivieren
  → Runtime-Evidence speichern
```

## 7.3 Aktivierungsregel

Keine Route wird aktiviert, solange eines fehlt:

- Provider-Credential vorhanden,
- Inventar bestätigt,
- Modellalias deployt,
- transportgerechte OpenRouter- oder FreeLLM-Readiness und Completion-Evidence grün,
- Completion-Canary grün,
- Preis-/Credit-Regel vorhanden,
- passender Datenbankeintrag vorhanden.

Ein normaler Nutzerrequest darf niemals Provider- oder Routentabellen reparieren oder aktivieren.

---

# 8. LLM-Transporte: OpenRouter, FreeLLM und Legacy LiteLLM

## 8.1 Aktuelle Aufgabe

Der PostgreSQL-gebundene Resolver trennt zwei aktive direkte Transportklassen:

- `openrouter` für bezahlte Standard-/Premium-Ausführung,
- `freellm` für kostenfreie, quota-bewusste Einzelagent-Ausführung.

LiteLLM ist kein aktiver Produkttransport mehr. Historische Datensätze bleiben deaktiviert lesbar, dürfen aber weder aktiviert, gecanaryt noch als Readiness-Ersatz verwendet werden.

## 8.2 Aktuelle Architektur

```text
Sovereign Backend
  → PostgreSQL-Route + Billing-/Canary-/Quota-Evidence
  → direkter OpenRouter-Transport für Paid
     oder direkter FreeLLM-Transport für Free
  → externer Provider beziehungsweise verwalteter FreeLLM-Pool
```

Frontend, Android und Agents SDK erhalten niemals echte Provider- oder Service-Keys.

## 8.3 Modelle und Aliase

Produktcode verwendet stabile Sovereign-Routenaliase, nicht hartcodierte Providerbezeichnungen. Der historische Datenbankfeldname `litellm_alias` ist kein Transportbeweis.

Beispiel:

- `sovereign-fast`
- `sovereign-balanced`
- `sovereign-code`
- `sovereign-reasoning`

Providerwechsel erfolgen hinter dem Alias.

## 8.4 Preisberechnung

Der jeweilige Direkttransport liefert Usage- und, sofern verfügbar, Providerkosten-Evidence. Sovereign Backend führt das Nutzer-Creditkonto.

```text
Request
  → Route, Transport und Kostenkategorie bestimmen
  → transportgerechte Preis-/Nullkosten-Evidence prüfen
  → provider-finanzierte Credits bei Paid atomar reservieren
  → direkter OpenRouter- oder FreeLLM-Aufruf
  → echte Usage/Cost Evidence
  → Settlement
  → Differenz erstatten oder endgültig verbuchen
```

**BELEGT:** Die Backend-Policy trennt `free`, `standard` und `premium`. `standard` verlangt mindestens `×4`, `premium` mindestens `×8`, und `free` ist nur mit verifizierten Nullkosten zulässig. Kosten werden in Micro-USD berechnet und dann in Credits übersetzt. Provider-finanzierte Credits werden vor dem Provideraufruf reserviert und nach echter Usage-Evidence abgerechnet.

**BELEGT:** Agents-SDK-Aufrufe benötigen vor jeder Ausführung einen datenbankaufgelösten direkten Route-`RunConfig`. Paid-Swarms akzeptieren ausschließlich OpenRouter; Free-Single-Agent-Läufe ausschließlich FreeLLM. `sovereign-fast` und `sovereign-balanced` sind nur UI-Leistungstarife und werden vor dem Request auf aktuelle aktive OpenRouter-Routen aufgelöst.

**BELEGT:** Sowohl die sichtbare Swarm-Route als auch die owner-scoped Controller-Bridge erzeugen für Start und Resume denselben `AgentStageBilling`-Vertrag. Ein fehlender Alias oder ungeprüfter Preis wird als persistierter `BLOCKED`-Zustand mit konkreter `nextAction` zurückgegeben; bei Resume wird dabei die bereits beanspruchte Lease gebunden und freigegeben. Die Runtime-Contracts prüfen zusätzlich, dass in diesem Blockerpfad keine Usage-Reservation und damit keine Provider-Ausführung begonnen wurde.

## 8.5 Canary und Readiness

- Liveliness beweist nur Prozessleben.
- Readiness beweist Proxy-/DB-Bereitschaft.
- Completion-Canary beweist einen echten Modellpfad.
- Route-Aktivierung erfordert die vollständige Kette.

## 8.6 Schlüsselgrenzen

Erlaubte produktive Schlüsselklassen sind OpenRouter-Key, FreeLLM-Unified-Key, FreeLLM-Upstream-Provider-Keys und Keyless-Marker. Sie bleiben serverseitig in exakt allowlisteten 0600-Dateien; Rohwerte erscheinen weder in PostgreSQL noch in UI, Logs oder Chat. Direkte OpenAI- und LiteLLM-Master-Key-Ziele sind aus dem Owner-Input-Vertrag entfernt.

## 8.7 Historischer LiteLLM-Betriebsbeweis

Die folgenden Absätze dokumentieren historische LiteLLM-/OpenAI-Provenance. Sie ersetzen nicht die aktuelle direkte Transportwahrheit aus `LLM_ROUTING_TRUTH_AND_HANDOFF.md`.

**BELEGT — Inventar:** Der geschützte OpenAI-/LiteLLM-Inventarpfad lieferte 92 sichtbare Modelle und bestätigte `gpt-5.4-mini` als verfügbares Provider-Modell. Provider-Identität und Projektzugriff wurden ohne Secret-Ausgabe bestätigt.

**BELEGT — Kostenarchitektur:** Das Repository enthält jetzt einen dreistufigen Kostenvertrag: `free` für Revolver-/Nullkostenrouten, `standard` mit mindestens `×4`, `premium` mit mindestens `×8`. Die Live-Datenbank besitzt die neuen Spalten und Constraints für provider-finanzierte Credits, Usage-Settlement, Billing-Kategorie, Multiplikator, Trace-/Stage-Evidence und Provider-Pricing-Metadaten. Die exakte Migration `022` wurde mit dem Repository-Hash `7c08cf8f92dafe264171d62a19cd6bbc5accf1264574a00ad7f468c7323bdfa4` angewendet und als Version `022` rückgelesen; alle sieben Constraints sind vorhanden, ungültige provider-finanzierte Balances und aktive ungeprüfte Routen stehen jeweils auf `0`.

**BLOCKIERT — aktueller Modellpfad:** Die Aktivierung von `sovereign-fast` und `sovereign-balanced` auf `gpt-5.4-mini` wurde am 19. Juli 2026 erneut gegen das geschützte Inventar `2fcb9285b7ee898910238d9b83cdf570c98bc870ab25853a0770fbc3e6633ef5` versucht. LiteLLM-Readiness, Datenbankverbindung und beide Aliase waren erreichbar, aber beide echten Completion-Canaries erhielten vom OpenAI-Upstream HTTP `429` mit `code=insufficient_quota`. Die Aktivierung wurde deshalb nicht als grün übernommen und der Rollbackpfad ausgelöst. Agents-SDK läuft code-seitig nur über `sovereign-fast` und bleibt fail-closed blockiert, bis Provider-Billing beziehungsweise verfügbares Kontingent hergestellt und ein neuer echter Completion-Canary bestanden ist.

**TEILWEISE:** Der Admin-Pfad für LiteLLM-Modellkatalog, Modellauswahl, Kostenkategorie, Multiplikator und owner-gated Provider-Key-Onboarding ist im Codevertrag vorhanden. Ein vollständiger grüner Produktionsbeweis mit aktivierter `gpt-5.4-mini`-Route fehlt noch.

---

# 9. MCP Docker und ChatGPT Operator

## 9.1 Zweck

Der private Sovereign ChatGPT MCP verbindet ChatGPT mit kontrollierten Repository- und VPS-Fähigkeiten.

## 9.2 Belegter Control-Plane-Stand

**BELEGT:** Die Control Plane meldet `BROKER_READY`. Die produktive MCP-Revision und die dabei geprüfte Produktcode-Baseline stehen auf `246e701f5b2d8ce94c21c001b26bf4aee216239c`; der revisionsgebundene Self-Update-Readback bestätigt Container-Health, Host-Command-Worker, Broker-RPC, MCP-Protokoll-Handshake, Cross-Runtime-Parität und KappaPos `1_000_000`. Repository-`main` enthält danach zusätzlich ausschließlich den Dokumentations-/Workflow-Merge `27e96907c4c95b94a5722b2530804dbf88d9ea51`, der keinen MCP-Self-Update erforderte. Immutable Image-Referenz und Image-ID sind `sha256:25f00872bf26c6702cf0a04f0a7dcccc6bfd3e025a2081ee40bbae4bba137c1b`; der Runtime-Evidence-Hash ist `1d0fe00f2b344d584bbf7c46320cc2b171191c9533efae192272db7cec431af2`. Direkte eingehende Mutationen, generische Shell und ein Docker-Socket im MCP bleiben verboten.

Die Runtime-Grenzen schreiben unter anderem vor:

- keine freie generische Shell im privaten MCP-Wahrheitspfad,
- keine Secrets im Modellpfad,
- Host-Mutationen nur über validierte Queue und Host Worker,
- Node-Builds und Dependency-Installationen über GitHub Actions,
- Draft PR als normaler Releaseausgang,
- optionaler owner-scoped Merge nur nach ausdrücklicher Freigabe, exakter PR-Head-SHA und relevanten grünen Gates.

**BELEGT:** Persistierte Agents-SDK-Runs enthalten Dispatcher-, sechs Worker- und Judge-Evidence, Tasks, Events, Tool Calls, Blocker und Statusprojektionen. Aktuelle und historische Tasks werden getrennt ausgewiesen; ein früherer blockierter Task erzeugt keinen globalen Rot- oder Grünstatus. Fehlende Runtime-Evidence führt weiterhin fail-closed zu `BLOCKED`.

## 9.3 Fähigkeiten

- isolierter Workspace,
- Repository lesen und exakt patchen,
- Diff,
- Tests/Checks delegieren,
- Draft PR,
- owner-scoped PR-Status und SHA-/Gate-gebundener Merge,
- Workflowstatus,
- Runtime-/Container-Evidence,
- PostgreSQL-/Vector-Canaries,
- immutable Backend-Deployment,
- begrenzte statische Backend-/Architekturevidence,
- constraints-basierte Stackauswahl,
- test-, migrations- und rollback-gegatete Delivery-Roadmaps,
- threat-getriebene API-Sicherheitspläne,
- getrennte Auflösung von Workspace-, Base-, PR-, Merge-, CI- und deployter MCP-Revision.

## 9.4 Enterprise-Backend- und Revisionswerkzeuge

**BELEGT — Code-/Schema-Vertrag:** `enterprise_backend_tools.py` registriert sechs strukturierte MCP-Werkzeuge:

1. `backend_engineering_tool_inventory`,
2. `backend_architecture_assess`,
3. `backend_stack_select`,
4. `backend_delivery_plan`,
5. `backend_api_security_plan`,
6. `repository_revision_resolve`.

Alle sechs sind read-only, nicht-destruktiv und idempotent. Nur der Revisionsresolver besitzt `openWorldHint=true`, weil er aktuelle GitHub-Base-, PR- und Check-Evidence liest. Eingaben sind durch Enums, Längen, Zahlenbereiche, Allowlisten und exakte 40-stellige SHA-Verträge begrenzt; Ergebnisse besitzen strukturierte Output-Schemas.

Die fünf Backendwerkzeuge analysieren nur versionierte Repository-Dateien innerhalb harter Datei-, Einzeldatei-, Gesamtbyte- und Evidence-Grenzen. Secret-ähnliche Literale werden ausschließlich als Fundklasse und Pfad gemeldet; Werte werden nie ausgegeben. Stackbewertungen sind deterministische Empfehlungen aus beobachteter Repository-Evidence und expliziten Constraints. Ein modularer Monolith ist der Standard; Microservices, Event-Broker, Kubernetes, NoSQL, Cache oder dynamische Erweiterungen benötigen jeweils messbare Betriebs- und Ownership-Gates. Metadaten dürfen keine ausführbaren Routen oder SQL-Fragmente enthalten. Plugins laufen nur über signierte Capability-Manifeste in separaten Prozessen, Containern oder Wasm-Sandboxes.

`repository_revision_resolve` trennt und vergleicht:

- aktuellen Workspace-Head und Dirty-Tree,
- gefetchten aktuellen Base-Head und Merge-Base,
- PR-Head, PR-Base, Draft-/Mergezustand und Merge-SHA,
- Check-Run-Head sowie terminale Failure-/Pending-Evidence,
- vom Broker belegte deployte MCP-Revision.

Revision, immutable Image-Referenz, Digest, Image-ID, Runtime-Evidence-Hash sowie MCP-/Container-/Broker-Readiness werden aus dem revisionsgebundenen Self-Update-Status getrennt rückgelesen; fehlende oder ungültige Werte bleiben als Evidence-Gap sichtbar. Dirty Tree, Remote-/Base-/PR-/Expected-SHA-Mismatch oder nicht auflösbare Authority führen zu `REVISION_CONFLICT` und `stop_and_resolve_revision_conflicts`. Das Tool behauptet bewusst keinen relevanten Grünstatus allein aus einer Check-Run-Liste und führt weder Merge, Deploy noch andere fachliche Mutation aus.

**BELEGT — lokale Verträge:** Acht gezielte Modultests belegen Registrierung, FastMCP-Schemas, Sicherheitsannotationen, Secret-Redaktion, Stackauswahl, TSX-/Tenancy-/Plugin-/Release-Roadmap, Threat-Control-Plan sowie Revisionserfolg und fail-closed Dirty-/Mismatch-Pfade. Weitere 17 Installer-/Docker-Vertragstests belegen Packaging, Launcher-Registrierung und Runtime-Import-Canaries. Die vollständige lokal ausführbare MCP-Suite bestand mit `264 passed`; zwei unveränderte Broker-Tests wurden ausschließlich wegen des Sandbox-Verbots für Unix-Socket-Erzeugung lokal nicht ausgeführt und bleiben für GitHub Actions verpflichtend.

**BELEGT — Runtime:** Dockerfile, Launcher, Installer, Releasearchiv-Check und GitHub-Workflow sind verdrahtet. PR #854 bestand am unveränderten Head `380d1c34a1a8205e90d7a6fe53181128ee29f75b` alle 18 Checkläufe ohne Fehler und wurde als Squash-Commit `11016a246af0a1f866c1814178f4fed7f82746c8` übernommen. Nach PR #867 wurde die produktive MCP-Runtime revisionsgebunden auf `246e701f5b2d8ce94c21c001b26bf4aee216239c` aktualisiert. Der aktuelle Readback bestätigt Digest `sha256:25f00872bf26c6702cf0a04f0a7dcccc6bfd3e025a2081ee40bbae4bba137c1b`, Evidence-Hash `1d0fe00f2b344d584bbf7c46320cc2b171191c9533efae192272db7cec431af2`, KappaPos `1_000_000`, Container-Health, Host Worker, Broker-RPC, MCP-Handshake und Cross-Runtime-Parität.

## 9.5 A2A-Adapter

**BELEGT:** Der Backendvertrag enthält eine AgentCard unter `/.well-known/agent-card.json`, A2A-Nachrichten-, Streaming-, Task-, Subscribe- und Cancel-Routen sowie owner-scoped Service-Authentisierung. Der Adapter startet und liest dieselbe persistierte Agents-SDK-Truth-Chain wie die direkten Swarm-Routen; er ist kein zweiter fachlicher Orchestrator.

**BELEGT:** Ein authentifizierter Produktions-Canary bestätigte AgentCard, Protokollversion 1.0, Owner-Scope, persistierten Run, `contextId`, identische Task-/Controller-Identität, Streaming, Resume und übereinstimmende Endstatusprojektion. A2A ist damit nicht mehr nur statisch oder CI-belegt, sondern für diesen Livepfad runtime-verifiziert.

---

# 10. GPT-Tools Docker

## 10.1 Browserless

Zweck:

- echte Browser- und UI-Evidence,
- mobile Viewports,
- Screenshots und Traces,
- Konsole und Netzwerk,
- Accessibility und Touch-Ziele.

Browserless darf keine frei erfundene Erfolgsmeldung erzeugen.

## 10.2 Apache Tika

Zweck:

- MIME-Erkennung,
- PDF-, Office-, HTML- und Text-Extraktion,
- Metadaten,
- Input für Indexierung und semantischen Import.

## 10.3 Gotenberg

Zweck:

- HTML-zu-PDF,
- Evidence-Reports,
- Testberichte,
- Dokumentvorschau.

Ein erzeugtes PDF beweist nur die erfolgreiche Dokumenterzeugung.

## 10.4 Dozzle

Zweck:

- menschliche Logansicht.

Dozzle ist keine Runtime-Wahrheitsquelle und kein Orchestrator.

## 10.5 Aktueller Betriebsstand

**BELEGT:** Browserless, Tika, Gotenberg, Dozzle, Code Server, LiteLLM, LiteLLM-PostgreSQL, PatchMon und Milvus besitzen aktuelle Prozess-, Health- oder Fachcanary-Evidence. Der private Gotenberg→Tika-End-to-End-Canary ist unter 12.1 belegt.

**BELEGT — Remote Memory:** Das hash-bestätigte Managed-Compose-Bundle `780c5844cc9f8949fba63f2fed1e63a8ae1f53d5930ebdd71366ce8163fef6fa` bestätigte Milvus-, Etcd- und MinIO-Health, das isolierte Gateway-Netz mit ausschließlich `milvus-standalone` und `sovereign-memory-gateway`, keine veröffentlichten Milvus-Ports und einen erfolgreichen Gateway-TCP-Pfad. Der fachliche Canary erzeugte anschließend eine zufällige flüchtige Collection, schrieb einen Marker, bestätigte Query-Readback und Vektorsuche und löschte die Collection im `finally`-Pfad. Der Markerinhalt wurde nicht ausgegeben; als Receipt wurde ausschließlich SHA-256 `f918ac924f0bf5a4bd2ca4f99463d8b5ded8f5e1b3bb65eb6dd1fb3200234d04` zurückgegeben. PostgreSQL/pgvector bleibt die kanonische Learning-Wahrheit; Milvus bleibt optionale Indexprojektion.

---

# 11. Code-Server Docker

## Zielnutzen

- Browser-IDE,
- Remote-Bearbeitung,
- Android-first Zugriff ohne Desktop-PC,
- Inspektion isolierter Agent-Workspaces,
- manuelle Owner-Korrektur,
- Download und Review von Diffs und Artefakten.

Code Server ist keine gemeinsame unkontrollierte Arbeitsmappe. Pro Agent/Job wird ein isolierter Workspace verwendet.

**BELEGT — gehärteter Runtimepfad:** Das hash-bestätigte Managed-Compose-Bundle `828f9bdee7def79ef4731fefffa0234232c9c0456d493a9668211ff9d30ec41d` verwendet den immutable Image-Digest `lscr.io/linuxserver/code-server@sha256:dfc5e74083f43f3cb217fedfead149f32b319ee663744351c001bdc5e4245441`, bindet Port `32782` ausschließlich an `127.0.0.1`, übernimmt die bestehende Authentisierung in eine root-only `.env` mit Modus `0600` und verwendet unverändert das persistente Volume `code-server-46bq_code-server-config` an `/config`. Der Runtime-Canary bestätigte HTTP `200`, Git-Verfügbarkeit, Schreibbarkeit unter `/config/workspace`, einen echten flüchtigen Clone von `OuroborosCollective/Sovereign-Studio-ato@main` auf Revision `11016a246af0a1f866c1814178f4fed7f82746c8` sowie die anschließende Entfernung des Test-Clones. Repository-Inhalt und Secretwerte wurden nicht zurückgegeben.

---

# 12. Tika- und Gotenberg-Dokumentfluss

```text
Upload
  → Dateityp-/Größenvalidierung
  → Malware-/Policy-Gate
  → Tika Text + Metadaten
  → optionale OCR-Stufe
  → sichere Segmentierung
  → Knowledge Blocks
  → Embeddings
  → PostgreSQL/pgvector
  → Retrieval-Kontext
```

Für Dokumenterzeugung:

```text
Runtime Evidence / Report Data
  → HTML-/Dokumenttemplate
  → Gotenberg
  → PDF-Artefakt
  → Hash + Metadaten
  → Evidence Store
  → Download/Preview
```

OCR darf nur als gekennzeichnete Extraktionsstufe auftreten. Extrahierter Text ist keine automatisch verifizierte fachliche Wahrheit.

## 12.1 Aktueller Live-Status

**BELEGT — produktiver Fachcanary:** PR #827 bestand am unveränderten Head `0e3bc930132cb8f4c57ef991cae1a0e6655f8b71` alle acht relevanten Workflows und wurde als Squash-Commit `7cdb4d2f1d9a39881ae4b0a3d61f2c5118d8b117` gemergt. Die offizielle Post-Merge-Kette installierte das revisions- und digestverifizierte immutable Image `sha256:9c9ae2101ff4930f6ecf68f1e7a4fd99b4e769656db9c51787d411e20aa9ee76`. Der danach auf exakt dieser Runtime ausgeführte Fachcanary lieferte `DOCUMENT_PIPELINE_LIVE_CANARY_VERIFIED`: Gotenberg antwortete authentisiert mit HTTP `200`, `application/pdf`, `16.244` PDF-Bytes und SHA-256 `8e3342b5fa36e119ff69c0e7275d50b84a4cad1810c1cceda904ebf30c5c702b`; Tika antwortete mit HTTP `200`, extrahierte `72` Zeichen und bestätigte den eindeutigen Marker.

**BELEGT — Sicherheitsgrenzen:** Der Host-Broker wertet aus dem bereits service- und containerverifizierten Gotenberg-Objekt ausschließlich die zwei benannten Basic-Auth-Werte für den flüchtigen Authorization-Header aus. Werte, Header, übrige Container-Umgebung und Dokumentinhalt werden weder ausgegeben noch persistiert; die lokale Headerstruktur wird nach dem Request geleert. Fehlende, nur teilweise vorhandene, übergroße oder kontrollzeichenhaltige Werte blockieren fail-closed. Der private Pfad bleibt speicherlos und größenbegrenzt und verwendet weder generische Shell, `docker exec`, veröffentlichte Hostports noch Netzwerkmutation. Vierzehn gezielte Tests, die lokal ausführbare MCP-Suite mit `268 passed, 2 deselected`, acht grüne PR-Workflows und der erfolgreiche Livecanary bilden die vollständige Evidence-Kette.

---

# 13. SQL-Datenbank

## 13.1 Tabellenfamilien im Repository

Die Migrationen belegen unter anderem folgende Familien:

### Admin und Sicherheit

- `admin_api_keys`
- `owner_input_requests`
- `owner_learning_policies` — in Migration `028` definiert, live noch nicht angewendet
- `user_passkeys`
- `user_account_keys`
- `user_security_policies`
- `auth_challenges`
- `step_up_approvals`
- `github_oauth_states`

### Credits und Billing

- `credit_ledger`
- `credit_receipts`
- `credit_packages`
- `transactions`
- `payment_methods`
- `llm_usage_settlements`

### LLM und Provider

- `llm_routes`
- `llm_provider_deployments`

### Runtime und Agenten

- `sovereign_agent_jobs`
- `sovereign_agent_events`
- `agent_runs`
- `agent_tasks`
- `agent_handoffs`
- `agent_events`
- `agent_tool_calls`
- `agent_evidence`
- `agent_artifacts`
- `agent_approvals`
- `agent_failures`

### Knowledge und Learning

- `knowledge_sources`
- `knowledge_blocks`
- `knowledge_source_blocks`
- `sovereign_agent_pattern_candidates`
- `sovereign_agent_pattern_vectors`
- `knowledge_learning_candidates`
- `vector_index_outbox`

### Toolchain und Audit

- `toolchain_tools`
- `sovereign_toolchain_incidents`
- `sovereign_toolchain_handoffs`
- `user_skills`
- `audit_log`

## 13.2 Datenbankregel

Jede Migration muss fail-closed laufen, Preview/Rollback-Evidence liefern und darf historische Schemadrift nicht durch ein blindes `CREATE TABLE IF NOT EXISTS` verschleiern.

---

# 14. Vektordatenbank und Knowledge Memory

## 14.1 Aktueller Live- und Importvertrag

**BELEGT:** Die produktive PostgreSQL-/pgvector-Instanz enthält aktuell 37 `ready`-Quellen mit zusammen 400 verknüpften Wissensblöcken. Alle 400 Blöcke besitzen Embeddings; es wurden `0` fehlende Embeddings und `0` verwaiste Source-Block-Links gemessen.

**BELEGT:** Der frühere Import mit `0` Chunks im Zustand `processing` wurde durch den fail-closed Reconciliation-Vertrag aus Revision `feae19e0965ff276eadc97e95fb2b5aadd046463` als `blocked` mit `knowledge_import_interrupted` klassifiziert. Der aktuelle Live-Readback enthält 37 `ready`-Quellen und eine `blocked`-Quelle; kein `processing`-Datensatz bleibt aktiv. Ein Importfehler nach dem Processing-Commit wird weiterhin als begrenzte Fehlerfamilie persistiert; interne Exception-Texte werden nicht als Blocker gespeichert.

**BELEGT:** GitHub-Wissensimporte trennen öffentliche und private Lesepfade. Kanonische öffentliche `github.com`-Repository- und Datei-URLs werden zuerst ohne Server-Credential read-only über die GitHub API gelesen. Nur wenn das Repository öffentlich nicht auflösbar ist, darf einmal ein vorhandener serverseitiger Lesezugang versucht werden. Abgelehnte Credentials können öffentliche Repositories damit nicht mehr vergiften. Private Repositories, Rate-Limits, ungültige Antworten und nicht erlaubte Raw-Download-Hosts erzeugen getrennte, operator-sichere Blocker.

## Aufgaben

- semantische Suche,
- Code Knowledge,
- Dokumentwissen,
- verifizierte Learn Patterns,
- Retrieval-Kontext,
- ähnliche Fehlerfamilien,
- Runtime-Evidence-Verknüpfung.

## Trennung

- Vector Store speichert Repräsentationen und Referenzen.
- PostgreSQL hält kanonische Metadaten, Status und Provenance.
- Vektortreffer sind Kandidaten, keine Wahrheit.
- Ein Pattern wird erst nach akzeptierter Runtime-Evidence aktiv.

---

# 15. Learning Database

## 15.1 Was gespeichert werden darf

- anonymisierte oder owner-gebundene technische Muster,
- Fehlerfamilie,
- betroffene Technologie und Dateityp,
- belegte Lösung,
- Test-/Build-Evidence,
- erfolgreiche und fehlgeschlagene Nutzung,
- Provenance,
- Version und Gültigkeitsbereich,
- Contributor-ID bei nutzerbezogenen Einträgen.

## 15.2 Was niemals gespeichert werden darf

- API-Keys,
- Tokens,
- Passwörter,
- private Schlüssel,
- vollständige `.env`-Inhalte,
- personenbezogene Chatdaten ohne Zweck und Einwilligung,
- unbestätigte Modellbehauptungen als aktive Lösung,
- proprietärer Code ohne erlaubten Scope,
- UI-erfundene Erfolge.

## 15.3 Gateway-Regel

Contributor-Submissions und shared-derived-pattern bleiben getrennt. User-Erasure entfernt nur owner-/contributor-gebundene Inhalte; geteilte, nicht personenbezogene abgeleitete Muster bleiben nach dem definierten Gateway-Vertrag bestehen.

**BELEGT:** PR #802 erzwingt im sichtbaren Pattern-Memory-Pfad, dass ausschließlich akzeptierte serverseitige Learning-Evidence mit Candidate-ID und gespeichertem Vector den Zustand „gelernt“ erzeugen darf. Der zunächst rote Head enthielt einen einzelnen Test-Scope-Fehler (`PR_URL is not defined`); nach kausaler Reparatur bestand Head `c5b4668c13da592a370853815b1f14d6c0fb1f0b` sämtliche Typecheck-, Test-, Build-, Runtime-/UX-, Security-, Release- und Android-Gates und wurde SHA-gebunden als Squash-Commit `c81af1ef295d102a887211e738e4b30ac4788944` nach `main` gemergt.

**BELEGT — aktueller Codevertrag:** PR #867 ergänzt eine persistierte Owner-Policy. Ohne frische Einzelanfrage darf `apply_proven_learning` nur dann automatisch speichern, wenn exakt eine aktive `owner_learning_policies`-Zeile für einen Admin oder Superadmin existiert. Null oder mehrere aktive Policies blockieren fail-closed. Plan-Hash, Secretblocker, Content-Idempotenz, pgvector-Readback und Milvus-Outbox bleiben unverändert verpflichtend.

**TEILWEISE — Livebetrieb:** Migration `028` ist noch nicht produktiv angewendet; die Standing-Owner-Policy ist daher im aktuellen Backendbetrieb noch nicht aktiv belegt.

---

# 16. Runtime Library

Die Runtime Library ist das fachliche Rückgrat.

## 16.1 Bestandteile

- Runtime Contracts,
- Intent-/Action-Schemas,
- Capability Gates,
- Validation,
- Executor Contracts,
- Evidence Model,
- State Machine,
- Retry/Recovery,
- Circuit Breaker,
- Audit,
- Predictive Advisory Layer,
- Inference Layer.

## 16.2 Zustandskette

```text
Input
  → Structured Intent
  → Route Decision
  → Capability Validation
  → Tool Call
  → Tool Result
  → Evidence Validation
  → Stored State
  → Next Action
```

Jeder Übergang muss validiert und testbar sein.

## 16.3 Beispielzustände

- `RECEIVED`
- `SCOPING`
- `PLANNED`
- `QUEUED`
- `RUNNING`
- `WAITING_FOR_TOOL`
- `WAITING_FOR_OWNER`
- `VERIFYING`
- `BLOCKED`
- `FAILED_RECOVERABLE`
- `FAILED_FINAL`
- `READY_FOR_DRAFT_PR`
- `DRAFT_PR_CREATED`
- `COMPLETED`

`COMPLETED` ist nur zulässig, wenn alle erforderlichen Evidence-Gates erfüllt sind.

---

# 17. Predictive Engine

## Zweck

Die Predictive Engine priorisiert mögliche Fehlerfamilien, Risiken und nächste Prüfungen.

Sie darf:

- Wahrscheinlichkeiten und Risikosignale berechnen,
- benachbarte Fehlerfamilien vorschlagen,
- Prüfungen priorisieren,
- Warnungen erzeugen.

Sie darf niemals:

- Erfolg erzeugen,
- einen Gate-Status überschreiben,
- eine Schreibaktion autorisieren,
- eine Prediction als Result Evidence speichern,
- eine UI-Lampe ohne Runtime-State auf grün setzen.

**Prediction ist Wahrscheinlichkeit, niemals Wahrheit.**

---

# 18. Inference Layer

Der Inference Layer arbeitet ausschließlich auf strukturierten Runtime-Daten:

- Tool Results,
- Test Evidence,
- Logs,
- State Transitions,
- Failure Families,
- Health Snapshots,
- Provenance.

Er interpretiert keine freie Nutzersprache. Sprachverständnis bleibt beim Online-LLM.

Inference-Ausgaben sind Kandidaten oder Empfehlungen und müssen durch Runtime-Verträge validiert werden.

**BELEGT:** PR #800 hat den aktiven ARE-Inferenzpfad auf Kappa-Fixed-Point-Material mit `1_000_000` als Skala umgestellt. Schwellen, Sortierung, Revisionen und State-Hashes verwenden kanonische Integerwerte; Dezimalwerte bleiben nur rückwärtskompatible API-Projektionen. Die zugehörigen Backend-, Typecheck-, Android-, Security-, Release- und Runtime-Gates wurden grün abgeschlossen.

---

# 19. SD-Card-System — Zielarchitektur

Geplante Nutzung auf Android-Geräten:

- lokaler Workspace,
- sichere Downloads,
- große Modelle oder Assets,
- lokaler Wissenscache,
- temporäre Artefakte,
- Offline-Fallback,
- exportierte Evidence und Reports.

## Regeln

- keine unverschlüsselten Secrets,
- klare Trennung permanent/temporär,
- Hash- und Größenprüfung,
- Berechtigungsprüfung,
- kein stilles Ausführen heruntergeladener Dateien,
- Offlinezustand sichtbar kennzeichnen,
- Synchronisierung nur über explizite Runtime-Aktion.

---

# 20. Docker-Landschaft

## Containerrollen

### Frontend

Web-/Android-Artefakt; spricht nur mit dem Sovereign Backend.

### Sovereign Backend

Auth, Credits, Runtime-API, Admin, Toolchain, LLM-Bridge und Persistenz.

### OpenRouter Paid

Direkter bezahlter Providertransport; kein öffentlicher Clientzugriff und keine Secrets im Frontend.

### FreeLLM Free

Direkter verwalteter Free-Pooltransport; kein öffentlicher Clientzugriff, nur doppelt gecanaryte Nullkostenrouten aktiv.

### Historische LiteLLM-Evidence

Deaktivierte Alt-Datensätze und Receipts; kein Router, kein Rollbackpfad, kein Canary und kein globales Produktions-Gate.

### PostgreSQL

Kanonische Produkt-, Runtime-, Audit-, Billing- und Knowledge-Daten.

### MCP / ChatGPT Operator

Kontrollierte Repository- und VPS-Operationen.

### Memory Gateway

Optionale Synchronisationsschicht zur Trennung von Contributor-Daten und geteilten abgeleiteten Mustern. PostgreSQL und die lokale Knowledge-/Pattern-Provenance bleiben kanonisch. Ein gesunder Gateway-Prozess ohne erreichbares Vector-Backend ist kein funktionsfähiger Memorypfad.

### GPT Tools

Browserless, Tika, Gotenberg und Dozzle.

### Code Server

Browser-IDE und optionaler Workspace-Inspector.

### Redis

Optionale Queue-, Cache- oder Sessionunterstützung; nicht als alleinige Wahrheit für langlebige Zustände.

### Soketi

Optionale Echtzeitübertragung; Events zeigen persistierte Runtime-Zustände, erzeugen sie nicht.

---

# 21. Endpoint-Übersicht

Die folgenden Familien sind im Backendvertrag belegt oder als kanonische Gruppen vorgesehen.

## 21.1 Health und Readiness

- `/health`
- `/health/live`
- `/health/ready`
- `/api/admin/system/health`
- `/api/admin/runtime/health`

## 21.2 Auth

- `/api/auth/register`
- `/api/auth/login`
- `/api/auth/me`
- `/api/auth/logout`
- `/api/auth/google`
- `/api/auth/github`
- `/api/auth/github/init`
- `/api/auth/github/callback-context`

## 21.3 LLM

- `/api/llm/chat`
- `/api/llm/routes`
- `/api/llm/routes/<route_id>`
- `/api/llm/auto-route`

## 21.4 Admin LLM und Provider

- `/api/admin/llm/routes`
- `/api/admin/llm/routes/<id>`
- `/api/admin/llm/routes/<id>/healthcheck`
- `/api/admin/llm/provider-presets`
- `/api/admin/llm/provider-deployments`
- `/api/admin/llm/provider-deployments/prepare`
- `/api/admin/llm/provider-deployments/<id>/activate`
- `/api/admin/llm/model-catalog`
- `/api/admin/llm/model-catalog/attach`
- `/api/admin/llm/gateway/providers`
- `/api/admin/llm/gateway/sync`
- `/api/admin/llm/worker-ai/status`
- `/api/admin/llm/worker-ai/models`
- `/api/admin/llm/worker-ai/sync`

Die Gateway- und Worker-AI-Endpunkte bleiben als Legacy-Tombstones sichtbar. Produktive Paid-Modelle laufen direkt über OpenRouter, produktive Free-Routen direkt über FreeLLM; LiteLLM bleibt ausschließlich deaktivierte historische Evidence.

## 21.5 Admin Benutzer, Credits und Billing

- `/api/admin/users`
- `/api/admin/users/<id>`
- `/api/admin/users/<id>/credit-adjustment`
- `/api/admin/transactions`
- `/api/admin/billing/stats`
- `/api/admin/payment-methods`
- `/api/admin/credit-packages`
- `/api/billing`
- `/api/billing/credits`
- `/api/billing/deduct`
- Zahlungs- und Webhook-Endpunkte

## 21.6 Toolchain und GitHub

- `/api/toolchain/user-tools`
- `/api/toolchain/github/read-file`
- `/api/toolchain/github/list-directory`
- `/api/toolchain/github/list-branches`
- `/api/toolchain/github/search-code`
- `/api/toolchain/preview-patch`
- `/api/toolchain/apply-patch-worker`
- `/api/toolchain/create-draft-pr`
- `/api/toolchain/sandbox-plan`
- `/api/toolchain/audit-log`

## 21.7 Skills und universelle Toolchain

- `/api/toolchain/skills/scan`
- `/api/toolchain/skills/read`
- `/api/toolchain/skills/adapt`
- `/api/toolchain/skills/install`
- `/api/toolchain/skills/list`
- `/api/toolchain/universal/status`
- `/api/toolchain/universal/manifest`
- `/api/toolchain/universal/briefing`
- `/api/toolchain/universal/invoke`

## 21.8 Agent Runtime und A2A

**BELEGT:** Agent-Job-, Event-, Evidence-, Toolcall-, Approval- und Failure-Verträge sind persistiert. Der aktuelle Code-Snapshot belegt unter anderem:

- `/api/user/agent/swarm/manifest`
- `/api/user/agent/swarm/run`
- `/api/user/agent/swarm/runs/<run_id>`
- `/api/user/agent/swarm/runs/<run_id>/resume`
- `/api/user/agent/swarm/runs/resumable`
- `/.well-known/agent-card.json`
- `/a2a/v1/message:send`
- `/a2a/v1/message:stream`
- `/a2a/v1/tasks`
- A2A-Task-, Subscribe- und Cancel-Unterpfade

**BELEGT:** Die deterministische Architekturreferenz wird aus dem aktuellen Repositorycode erzeugt. Die produktive Endpoint-Wahrheit stammt ausschließlich aus `scripts/sovereign-backend/app.py` sowie den registrierten Runtime-/Protokollmodulen. Der aktuelle Snapshot auf Revision `246e701f5b2d8ce94c21c001b26bf4aee216239c` enthält 167 kanonische Backendverträge, `0` aktive unmatched Frontend-Calls und den Referenzhash `4338121167f1eaa8ad14a4df620da166a2545c3f1ddd8092e27f66b3dee11d9f`.

Vier weiterhin sichtbare Altflächen werden nicht verborgen, sondern getrennt ausgewiesen: `/api/ai/gemini` als `legacy-unreferenced` sowie `/api/vps/connect`, `/api/vps/disconnect` und `/api/vps/exec` als `disabled-launcher`. Statische Routenerkennung bleibt Orientierung; produktive Funktionsaussagen benötigen zusätzlich Live-Evidence.

---

# 22. Runtime-Flows

## 22.1 Chatflow

```text
User Text
  → Backend Session prüfen
  → Creditfähigkeit prüfen
  → Online-LLM über verifizierte direkte OpenRouter-/FreeLLM-Route
  → Assistant Response + IntentEvidence
  → Runtime validiert Intent
  → reine Antwort oder Action Route
  → Result/Evidence speichern
  → Chat zeigt Ergebnis oder Blocker
```

## 22.2 Toolflow

```text
Structured Action
  → Capability Gate
  → Permission Gate
  → Tool Contract
  → Execute
  → Tool Result
  → Evidence Validator
  → State
  → Next Action
```

## 22.3 Repoflow

```text
Repo-URL/Selection
  → kanonische GitHub-URL validieren
  → öffentlichen Read-only-Zugriff zuerst versuchen
  → nur bei nicht öffentlichem Repository bestätigten privaten Lesezugang versuchen
  → Rate-Limit, Credential- und Repo-Blocker getrennt klassifizieren
  → Snapshot/Clone
  → Branch/Revision fixieren
  → relevante Dateien finden
  → Kontext erzeugen
  → Analyse oder isolierter Schreibworkspace
```

## 22.4 Patch- und Draft-PR-Flow

```text
Code Intent
  → isolierter Workspace
  → exakte Dateien lesen
  → Patch erzeugen
  → SEARCH/REPLACE Eindeutigkeit
  → Diff
  → Checks/CI
  → Evidence Gate
  → Draft PR
  → optionaler owner-scoped Merge nur bei expliziter Freigabe,
    exakter Head-SHA, Mergefähigkeit und relevanten grünen Gates
```

## 22.5 Creditflow

```text
Request
  → Route und Maximalverbrauch bestimmen
  → Credits atomar reservieren
  → direkter OpenRouter-/FreeLLM-Aufruf
  → Usage/Cost Evidence
  → Settlement
  → Refund oder endgültige Abbuchung
  → Ledger + Receipt
```

## 22.6 GitHubflow

```text
GitHub Intent
  → URL und Repo-/Branch-Scope validieren
  → öffentliche Reads credential-frei ausführen
  → privaten Access-State nur für nicht öffentliche Reads oder Schreibaktionen verwenden
  → Lesen oder isolierter Workspace
  → Patch/Commit
  → Draft PR
  → Checks beobachten
  → Merge nur bei separater ausdrücklicher Owner-Freigabe,
    exakter Head-SHA und relevanten grünen Gates
```

---

# 23. Harte Projektregeln

1. Runtime erzeugt Wahrheit.
2. UI erzeugt niemals Wahrheit.
3. LLM versteht Sprache.
4. Runtime versteht strukturierte Aktionen.
5. Evidence schlägt Vermutung.
6. Kein unautorisierter oder gate-loser Auto-Merge.
7. Maximal Draft PR im Standardpfad; ein owner-scoped Merge ist nur nach ausdrücklicher Freigabe, exakter Head-SHA, bestätigter Mergefähigkeit und relevanten grünen Gates zulässig.
8. Keine Mocks, Stubs oder Fassaden im Live-Pfad.
9. Keine statischen Provider-Routen im Frontend.
10. Keine hartcodierten Provider wie Pollinations, Groq oder vergleichbare direkte Clientprovider.
11. Provider werden ausschließlich über Backend, Datenbank und den transportgerechten OpenRouter-/FreeLLM-Adminvertrag verwaltet; LiteLLM darf nicht aktivierbar sein.
12. Offline-Fallback muss klar markiert sein.
13. Keine Secrets im Frontend, APK, WebView, Chat, Logs oder Repository.
14. Normale Requests mutieren keine Admin-/Providerkonfiguration.
15. UI-Lampen und Statuskarten benötigen Runtime-Evidence.
16. Große Live-Dateien nur über exakte, kleine SEARCH/REPLACE-Patches ändern.
17. Neue Logik erhält Runtime-Checks, Validierung und Tests.
18. Release nur ohne bekannte P0-Fehler und mit mehrfach belegtem Hauptpfad.
19. Android und Web müssen den Hauptpfad bedienen.
20. Rollback oder Rückfallmöglichkeit muss vorhanden sein.

---

# 24. Roadmap und Aufgabenstatus

## 24.1 Erledigt und belegt

1. **BELEGT — Cross-Runtime-Parität:** Python- und TypeScript-Verträge werden über gemeinsame Vektoren verglichen und revisionsgebunden im immutable MCP-Release geprüft.
2. **BELEGT — A2A-Livepfad:** AgentCard, owner-scoped Authentisierung, Nachrichten-, Task-, Streaming- und Resume-Verträge wurden in einem echten Produktions-Canary mit derselben persistierten Controller-Truth-Chain korreliert.
3. **BELEGT — deterministischer ARE-State:** Hash-, Schwellen- und Sortiermaterial verwendet Kappa-Fixed-Point mit der Skala `1_000_000`.
4. **BELEGT — persistierte Multi-Agent-Runs:** Dispatcher, sechs Worker, Judge, Tasks, Events, Tool Calls, Evidence, Blocker, Failures und Approvals sind persistiert und trennen aktuelle von historischen Zuständen.
5. **BELEGT — kanonische Backend-Ownership:** `scripts/sovereign-backend/app.py` ist die einzige deployte App-Wahrheit; echte Spiegel einschließlich Knowledge und R2 sind bytegleich.
6. **BELEGT — Endpoint-Referenz:** 167 kanonische Backendverträge, `0` aktive unmatched Frontend-Calls und vier offen ausgewiesene nichtaktive Altflächen.
7. **BELEGT — historischer LiteLLM-Kernpfad:** 92 Provider-Modelle wurden inventarisiert; `sovereign-fast` und `sovereign-balanced` bestanden echte Completion-Canaries. Der davon getrennte aktuelle Quota-Blocker wird unter 24.2 geführt.
8. **BELEGT — Android-Releaseartefakte:** APK und AAB, SHA-256, Signaturdiagnose, ein Signer, Zertifikat-Fingerprint und Alignment wurden im Releaseworkflow belegt.
9. **BELEGT — externe Action-Stream-Brücke im Codevertrag:** owner-scoped, idempotente externe Events mit deterministischen IDs und ohne Run-, Task- oder Blockermutation sind über Store, Backendroute, MCP-Client und MCP-Tool verdrahtet und getestet.
10. **BELEGT — MCP-Releasebasis:** PR #854 bestand am unveränderten Head `380d1c34a1a8205e90d7a6fe53181128ee29f75b` alle 18 Checkläufe ohne Fehler und wurde als Squash-Commit `11016a246af0a1f866c1814178f4fed7f82746c8` übernommen. Die aktuelle immutable MCP-Runtime steht auf `246e701f5b2d8ce94c21c001b26bf4aee216239c`; Self-Update, Host Worker, Broker-RPC, MCP-Handshake, Cross-Runtime-Parität und KappaPos `1_000_000` sind grün. Der Live-Readback bestätigte Digest `sha256:25f00872bf26c6702cf0a04f0a7dcccc6bfd3e025a2081ee40bbae4bba137c1b` und Evidence-Hash `1d0fe00f2b344d584bbf7c46320cc2b171191c9533efae192272db7cec431af2`.
11. **BELEGT — GitHub-Knowledge- und Modell-Health-Wahrheit:** PR #818 bestand Release Gate, vollständigen Type-check/Test/Build, Security Audit, alle CodeQL-Pfade, OAuth-Live-Path, E2E Smoke, Android- und Runtime-/UX-Verträge und wurde SHA-gebunden als Squash-Commit `feae19e0965ff276eadc97e95fb2b5aadd046463` gemergt. Öffentliche GitHub-Imports sind credential-frei bevorzugt, verlassene Knowledge-Imports werden fail-closed reconciled und Modell-Health erfordert eine echte Completion statt bloßer Readiness.
12. **BELEGT — dreistufiger LLM-Kostenvertrag im Code und Live-Schema:** `free`, `standard` und `premium` sind als Backend-Policy, Admin-Vertrag, Usage-Settlement-Felder, Provider-Pricing-Felder und PostgreSQL-Constraints abgebildet. Provider-finanzierte Credits trennen bezahlte Kaufkraft von Bonus-/Admin-Gutschriften.
13. **BELEGT — GitHub-Knowledge-Transportvertrag im Code:** GitHub-Antwortstatus und HTTPS-Transportfehler werden getrennt behandelt. Timeout, TLS, Connection/DNS und sonstige `requests`-Fehler liefern sichere `github_*`-Blocker mit passender `502`-/`504`-Semantik. Der Fehlerpfad schreibt Audit-Evidence nur mit einem URL-Fingerprint; rohe URL-, Query-, Credential- oder Exceptiondetails werden weder zurückgegeben noch persistiert.
14. **BELEGT — Enterprise-Backend-/Revisionswerkzeuge in Code und Runtime:** Sechs bounded read-only MCP-Tools decken statische Architekturaufnahme, Stackentscheidung, Projekt-/Modernisierungsfahrplan, API-Sicherheitskonzept und die fail-closed Auflösung der vollständigen Repository-/PR-/CI-/Deployment-Revisionstupel ab. FastMCP-Output-Schemas, Eingabegrenzen und ToolAnnotations sind geprüft; PR #824 war vollständig grün, wurde SHA-gebunden gemergt und ist über den revisions- und digestverifizierten privaten MCP produktiv verfügbar.
15. **BELEGT — Dokumentpipeline:** Der private Gotenberg→PDF→Tika-Pfad ist über zwei SHA-gebundene Reparaturstufen, lokale Tests, acht grüne PR-Workflows, immutable Deployment und einen erfolgreichen Produktionscanary belegt. Marker, PDF-Typ und -Hash sowie beide HTTP-Status wurden geprüft; Dokument- und Secretwerte wurden weder zurückgegeben noch persistiert.
16. **BELEGT — KI-Coach-Integration-Workflow:** PR #828 reparierte den joblosen Konfigurationsfehler durch vier statische `needs.<job>.result`-Prüfungen, ergänzte einen zentralen Regression-Guard und band den Logikcheck an die kanonische Funktion `realStopper`. Am unveränderten Head `e8dbf51ea2330babd10c03c99e7a74f95a5ef604` bestanden neun Workflows; der KI-Coach-Lauf `29668564537` erzeugte und bestand alle sechs Jobs einschließlich Unit-, TypeScript-, Build-, Playwright- und Abschlussreport-Gates. Der Head wurde als Squash-Commit `2892776d6d3710ac5a4d40211e2fc09ee0866db3` übernommen.
17. **BELEGT — Action-Stream-Idempotenz:** Ein owner-scoped Produktionscanary erzeugte beim ersten Append genau ein externes Event und eine Evidence. Der identische zweite Append wurde als Duplikat erkannt; Run-, Task-, Failure- und Blockerstatus blieben unverändert.
18. **BELEGT — Release-Schema-Reconciliation:** Die Migrationen `025` und `026` wurden nach Rollback-Preview mit exakter Quell-SHA angewendet. Die zuvor fehlenden Tabellen `platform_runtime_evidence`, `llm_route_attempts` und `llm_route_revolver_state` sind im Live-Readback vorhanden.
19. **BELEGT — Memory-Transport:** Das hash-bestätigte Managed-Compose-Deployment stellte den internen Gateway→Milvus-Pfad wieder her. Milvus-Health, Netzwerkisolation und TCP-Erreichbarkeit wurden ohne externe Portfreigabe bestätigt.
20. **BELEGT — Memory-Collection-Lifecycle:** Ein echter Gateway-Canary erzeugte eine flüchtige Milvus-Collection, schrieb einen Marker, bestätigte Query und Vektorsuche und löschte die Collection im `finally`-Pfad. Keine Collection-Inhalte oder Secrets wurden zurückgegeben.
21. **BELEGT — Code-Server-Härtung und User-Workspace:** Code Server läuft auf einem immutable Image-Digest, nur noch auf `127.0.0.1:32782`, mit dem bestehenden persistenten `/config`-Volume und erhaltener Authentisierung. Der Runtime-Canary bestätigte HTTP, Git, Schreibbarkeit, echten Clone des aktuellen Runtime-`main` und Cleanup des flüchtigen Workspaces.
22. **BELEGT — PR #867 Code- und MCP-Integration:** PR #867 wurde nach vollständig grünen Gates als Squash-Commit `246e701f5b2d8ce94c21c001b26bf4aee216239c` übernommen. Das produktive MCP läuft auf derselben Revision und dem immutable Digest `sha256:25f00872bf26c6702cf0a04f0a7dcccc6bfd3e025a2081ee40bbae4bba137c1b`. Enterprise-Admin-UI und Standing-Learning-Policy sind code- und image-belegt; Backend-Deployment und Migration `028` bleiben getrennte offene Betriebsaufgaben.
23. **BELEGT — aktueller Endpoint-Snapshot:** Revision `246e701f5b2d8ce94c21c001b26bf4aee216239c` enthält 167 kanonische Endpointverträge, `0` aktive unmatched Frontend-Calls und vier weiterhin explizit nichtaktive Altflächen.
24. **BELEGT — historische PostgreSQL-Schema-Ownership / Issue #876:** PR #973 führte das fest allowlistete Manifest `POSTGRES_HISTORICAL_SCHEMA_OWNERSHIP.v1.json` und eine fail-closed Katalogstrukturprüfung ein. Der installierte Reconciler auf Revision `366977a74fea326c3add2af7f727acfa1ae67ec8` ordnet `public.admin_users`, `public.sovereign_agent_draft_pr_events` und `public.sovereign_agent_evidence_log` historisch zu; `unmappedLiveTables`, fehlende historische Tabellen und Schema-Mismatches stehen jeweils auf `0`. Es wurden keine Tabellenzeilen gelesen und keine Datenbankmutation ausgeführt.

## 24.2 Offen, teilweise oder blockiert

Die folgenden elf Punkte sind die nach Abschluss von Issue #876 verbleibende operative Open-Point-Liste. Jeder Punkt besitzt einen stabilen Schlüssel im versionierten Ursprungsbundle `docs/architecture/SOVEREIGN_MANIFEST_OPEN_ISSUES.json`. Der owner-gated Workflow `.github/workflows/create-manifest-open-issues.yml` eröffnet daraus marker-idempotent genau ein GitHub-Issue je Schlüssel und öffnet geschlossene Issues nicht automatisch erneut.

1. **BLOCKIERT/TEILWEISE — Provider-Onboarding und `gpt-5.4-mini`-Route** (`provider-onboarding-gpt54-route`): Providerinventar, Projektidentität, LiteLLM-Readiness und Aliasinventar sind belegt; echte Completion-Canaries bleiben fehlgeschlagen. Offen sind verfügbares Kontingent und der vollständige automatische Lifecycle mit Preisvertrag, atomarer Aktivierung und Rollback.
2. **TEILWEISE — Fachcanary-Abdeckung** (`runtime-canary-coverage-matrix`): Mehrere kritische Pfade besitzen Fachcanaries, aber nicht jede produktive Funktionsfamilie ist in einer revisionsgebundenen Canary-Matrix abgedeckt. Prozessleben allein bleibt kein Funktionsbeweis.
3. **TEILWEISE — physischer Android-Geräte-Smoke** (`physical-android-device-smoke`): Repository- und Release-Scan sind ohne statische Blocker; signierte Artefakte und Alignment sind belegt. Installation und Hauptpfad-Smoke auf einem physischen Android-Gerät fehlen.
4. **OFFEN — SHA-gebundene LLM-Boundary-Klassifikation** (`llm-tool-boundary-review-ledger`): Der aktuelle Snapshot meldet 65 heuristische `LLM_TOOL_BOUNDARY`-Kandidaten. Die Treffer sind keine bestätigten Runtimefehler; ihre vollständige, datei-SHA-gebundene Klassifikation fehlt.
5. **TEILWEISE — GitHub-Knowledge-Livecanary** (`github-knowledge-live-canary`): Der sichere Transport- und Auditvertrag ist im Code belegt. Ein realer öffentlicher Import sowie ein kontrollierter Fehlerpfad müssen nach einem revisionsgebundenen Backend-Deployment live bestätigt werden.
6. **TEILWEISE — Enterprise-Admin-Backend deployen** (`deploy-enterprise-admin-backend`): Das immutable Backend-Image für Revision `246e701f5b2d8ce94c21c001b26bf4aee216239c` ist als Digest `sha256:629a694d67c4789053da81656cbc7523a084b8ac52877ff2083aa0325453ae18` gebaut; der laufende Container wurde jedoch vor PR #867 gestartet. `/admin` und die Enterprise-API benötigen einen Digest- und revisionsgebundenen Live-Readback.
7. **BLOCKIERT — Migration `028` und Standing-Owner-Policy** (`apply-owner-learning-policy-migration`): `owner_learning_policies` ist im Repository definiert, fehlt aber live; `schema_migrations` enthält keinen Eintrag `028`. Automatische, idempotente Pattern-Persistenz ohne wiederholte Einzelbestätigung ist daher noch nicht produktiv belegt.
8. **OFFEN — Mirror-Drift der LLM-Kostenpolicy** (`mirror-drift-llm-cost-policy`): `backend/llm_cost_policy.py` und `scripts/sovereign-backend/llm_cost_policy.py` besitzen unterschiedliche Hashes. Die kanonische Deploymentquelle ist bekannt, aber die Analyse-/Testquelle darf keine abweichende Kostenwahrheit behalten.
9. **OFFEN — Mirror-Drift der Proven-Learning-Runtime** (`mirror-drift-proven-learning-runtime`): Der Deploymentpfad enthält die Standing-Owner-Policy, während `backend/proven_learning_runtime.py` noch den früheren Einzelbestätigungspfad abbildet. Semantische und Scanner-Parität fehlen.
10. **BLOCKIERT — GitHub-App-Routenregistrierung** (`github-app-route-registration`): Der produktive Backendstart protokolliert `GitHub App routes registration failed: name 'get_connection' is not defined`. Diese Routenfamilie ist deshalb nicht als produktiv registriert belegt.
11. **OFFEN — toten Legacy-Admin-HTML-Block entfernen** (`remove-dead-legacy-admin-html`): Die Route wird zwar auf `ENTERPRISE_ADMIN_HTML` überschrieben, aber der historische `_ADMIN_PANEL_HTML`-Literalblock verbleibt als reaktivierbare zweite UI-Wahrheit in `scripts/sovereign-backend/app.py`.

## 24.3 Langfristig

1. Vollständige KI-Entwicklungsplattform.
2. Selbstlernende, evidenzgebundene Wissensbasis.
3. Universeller NoCode-/LowCode-Agent.
4. Team-, Mandanten- und Enterprise-Funktionen.
5. Wiederaufnehmbare, isolierte Agent-Workspaces für alle Ausführungsklassen.
6. Policy-gesteuerte Provider-, Tool- und Deployment-Marktplätze.

---

# 25. Release-Gate

Ein erster Release erfolgt nur, wenn:

- keine bekannten P0-Fehler offen sind,
- der Hauptpfad mehrfach erfolgreich belegt wurde,
- kein Fake-Erfolg existiert,
- kein unautorisierter oder gate-loser Merge möglich ist,
- Credits serverseitig korrekt reserviert und abgerechnet werden,
- Fehler verständlich sichtbar sind,
- Android und Web den Hauptpfad bedienen,
- eine belegte Rückfall- oder Rollbackmöglichkeit vorhanden ist,
- Provider- und Modellrouten echte Canaries bestanden haben,
- Secrets serverseitig und unsichtbar für LLM/Frontend bleiben,
- Draft-PR- und CI-Evidence gespeichert ist.

## 25.1 Aktuelle Gatebewertung

**BLOCKIERT/TEILWEISE:** Ein vollständiger Produkt- und Release-Grünstatus wird nicht behauptet. Die historische Schema-Ownership aus Issue #876 ist revisions- und runtimegebunden abgeschlossen. Releasekritisch offen bleiben jedoch die elf Punkte aus Abschnitt 24.2: fehlgeschlagene LiteLLM-Completion-Canaries, unvollständige Canary-Matrix, physischer Android-Smoke, LLM-Boundary-Ledger, GitHub-Knowledge-Livecanary, noch nicht deployte Enterprise-Admin-Wahrheit, nicht angewendete Migration `028`, zwei Mirror-Drifts, fehlgeschlagene GitHub-App-Routenregistrierung und der tote Legacy-Admin-HTML-Block. Ein grüner Gesamtzustand darf erst nach getrenntem Abschluss und revisionsgebundener Manifestaktualisierung dieser verbleibenden Issues behauptet werden.

---

# 26. Aktueller Evidence-Snapshot

Evidence-Stand: 20. Juli 2026. Die geprüfte Produktcode- und produktive MCP-Baseline steht revisionsgebunden auf `246e701f5b2d8ce94c21c001b26bf4aee216239c`. Repository-`main` enthält zusätzlich den danach vollständig grün gemergten Dokumentations-/Workflowstand `27e96907c4c95b94a5722b2530804dbf88d9ea51`. Der aktuelle MCP-Readback, Endpoint-Snapshot, Live-Schema-Readback, Knowledge-Zählung, Android-Repositoryscan und LiteLLM-Zugriff wurden für dieses Update erneut erhoben. Frühere PR- und Releasebelege bleiben historische Provenance und werden nicht als Ersatz für den aktuellen Readback verwendet. Das produktive Backend läuft noch auf dem Stand vor PR #867; Code- und Image-Evidence werden daher ausdrücklich von Live-Evidence getrennt.

- **BELEGT:** Die produktive MCP- und Produktcode-Baseline steht auf `246e701f5b2d8ce94c21c001b26bf4aee216239c`; Repository-`main` enthält zusätzlich den reinen Manifest-/Issue-Workflow-Merge `27e96907c4c95b94a5722b2530804dbf88d9ea51`.
- **BELEGT:** Für MCP-Release-Revision `246e701f5b2d8ce94c21c001b26bf4aee216239c` bestanden immutable Image-Publish, revisionsgebundener Self-Update, Host Worker, Broker-RPC, MCP-Handshake und Cross-Runtime-Parität. Der Live-Readback bestätigte Digest und Image-ID `sha256:25f00872bf26c6702cf0a04f0a7dcccc6bfd3e025a2081ee40bbae4bba137c1b`, Evidence-Hash `1d0fe00f2b344d584bbf7c46320cc2b171191c9533efae192272db7cec431af2` und KappaPos `1_000_000`; direkte eingehende Mutationen bleiben verboten.
- **BELEGT:** Kappa-Skala `1_000_000` und Python-/TypeScript-Cross-Runtime-Parität sind revisionsgebunden bestätigt.
- **BELEGT:** A2A wurde mit AgentCard, Owner-Scope, persistiertem Run und `contextId`, Streaming, Resume und Controller-/Task-Endstatus live korreliert.
- **BELEGT:** `scripts/sovereign-backend/app.py` ist die kanonische deployte Backend-App. `knowledge_library.py`, `r2_storage.py` und die übrigen echten Spiegel sind bytegleich.
- **BELEGT:** Der generierte Endpoint-Snapshot enthält 167 kanonische Backendverträge, `0` aktive unmatched Frontend-Calls, vier separat klassifizierte nichtaktive Altflächen und den Referenzhash `4338121167f1eaa8ad14a4df620da166a2545c3f1ddd8092e27f66b3dee11d9f`.
- **BELEGT:** Das geschützte LiteLLM-/OpenAI-Inventar enthielt 92 Provider-Modelle und bestätigte `gpt-5.4-mini` als verfügbares Modell. Provider-Identität, Projektzugriff und vorhandener Provider-Key wurden ohne Secret-Ausgabe bestätigt.
- **BELEGT:** Migration `022` wurde exakt aus der Repository-Quelle mit SHA-256 `7c08cf8f92dafe264171d62a19cd6bbc5accf1264574a00ad7f468c7323bdfa4` angewendet. Der Live-Readback bestätigte den Ledger-Eintrag `022`, die neuen Kosten-/Billing-Spalten für `provider_funded_credits`, `llm_usage_settlements` und `llm_provider_deployments`, alle sieben neuen Constraints, `0` ungültige provider-finanzierte User-Balances und `0` aktive Routen mit ungeprüfter Preisgrundlage.
- **BELEGT:** Auf PR-Revision `75e2738594986b32bb41793cd150c56b0bdc5ae1` schlossen alle elf GitHub-Workflowläufe erfolgreich ab. Die gezielten lokalen Verträge bestanden mit `237`, die vollständige Suite unter `scripts/sovereign-backend/tests` mit `113` Tests; zusätzlich bestanden der Agents-SDK-Preflight für zwölf Agenten, Compile-, Mirror- und interne Live-Path-Verträge.
- **BLOCKIERT:** Die Alias-Aktivierung von `sovereign-fast` und `sovereign-balanced` auf `gpt-5.4-mini` bestand die echten Completion-Canaries nicht. Beide Aufrufe erhielten HTTP `429` mit `insufficient_quota`; Readiness, Datenbank und Aliasinventar waren dabei grün. Die Alias-/Route-Aktivierung bleibt fail-closed; ein grüner Agents-SDK-Modellpfad wird nicht behauptet.
- **BELEGT:** PR #818 wurde nach vollständig grünen GitHub-Gates SHA-gebunden gemergt. Der neue Modell-Healthvertrag unterscheidet Quota, Rate-Limit, Credentials, Aliasfehler und Infrastruktur und setzt `completionVerified=true` für Grün voraus.
- **BELEGT:** Der aktuelle Live-Readback enthält 38 Knowledge-Quellen: 37 `ready` und eine `blocked`; es gibt 400 Wissensblöcke, `0` fehlende Embeddings und 400 Source-Block-Links. Der frühere verlassene `processing`-Zustand ist damit nicht mehr aktiv. Ein revisionsgebundener GitHub-Knowledge-Livecanary bleibt dennoch offen.
- **BELEGT — Code/Test:** Der Folgecode klassifiziert GitHub-Timeout, TLS, Connection/DNS und sonstige Transportfehler in sichere Blocker, liefert keine rohen Exceptiondetails und persistiert nur einen URL-Fingerprint. Die vollständige Suite `scripts/sovereign-backend/tests` bestand lokal mit `119 passed`; der GitHub-PR- und Deploybeweis folgt getrennt.
- **BELEGT — Enterprise-Backend-/Revisions-Code und Runtime:** Sechs read-only MCP-Tools sind in Launcher, Dockerfile, VPS-Installer, Releasearchiv-Check, Workflow und Server-Instruktionen integriert. Acht gezielte Tooltests, 17 Installer-/Docker-Vertragstests und die vollständige lokal ausführbare MCP-Suite mit `264 passed` bestanden auf PR #824; GitHub Actions führte auch die zwei lokal sandboxblockierten Unix-Socket-Verträge aus. Alle acht PR-Workflows waren am unveränderten Head grün. Merge-, laufende und Image-Revision sowie immutable Digest stimmen im Produktions-Readback überein.
- **BELEGT:** Öffentliche GitHub-Wissensimporte laufen credential-frei zuerst; private Reads werden nur nach öffentlichem Nichtfund über den bestätigten Serverzugang versucht.
- **BELEGT:** APK- und AAB-Artefakte, Hashes, Signaturdiagnose, genau ein Signer, Zertifikat-Fingerprint und Alignment liegen als Release-Evidence vor.
- **BELEGT:** Browserless, Tika, Gotenberg, Dozzle, Code Server, LiteLLM, LiteLLM-PostgreSQL, PatchMon und Milvus liefen ohne Restart-/OOM-/Exitfehler. Code Server ist zusätzlich auf den immutable Digest `sha256:dfc5e74083f43f3cb217fedfead149f32b319ee663744351c001bdc5e4245441` und ausschließlich `127.0.0.1:32782` gebunden.
- **BELEGT:** Der Dokumentcanary erzeugte über den authentisierten privaten Gotenberg-Pfad ein `16.244` Byte großes PDF, prüfte dessen SHA-256, übergab es an Tika und bestätigte dort HTTP `200` sowie den eindeutigen Marker. Quell- und Ausgabedokument, Dokumentinhalt und Secretwerte wurden nicht persistiert oder zurückgegeben.
- **BELEGT:** Der historische KI-Coach-Push-Run `29666014826` scheiterte vor der Joberzeugung. PR #828 beseitigte nacheinander den dynamischen `needs`-Zugriff und den veralteten Symbolcheck. Am finalen unveränderten Head bestanden neun Workflows; KI-Coach-Run `29668564537` bestand seine sechs erzeugten Jobs. Der SHA-gebundene Squash-Merge ist `2892776d6d3710ac5a4d40211e2fc09ee0866db3`.
- **BELEGT — Action Stream:** Der externe Event `event-external-bc681e7c535a46e4a7579e86b8bc40fd` wurde einmal erzeugt und beim identischen zweiten Append als Duplikat erkannt. Es entstand keine zweite Evidence; Runstatus, Tasks, Failures und aktiver Blocker blieben unverändert.
- **BELEGT — Release-Schema:** Die Migrationen `025` und `026` wurden nach erfolgreicher Rollback-Preview aus ihren unveränderten Quell-SHAs angewendet. Der Live-Readback enthält nun 50 Tabellen einschließlich `platform_runtime_evidence`, `llm_route_attempts` und `llm_route_revolver_state`; die drei vorherigen P1-Missing-Table-Befunde sind geschlossen.
- **BELEGT — Enterprise-Spiegel:** `backend/enterprise_platform/service.py` und `scripts/sovereign-backend/enterprise_platform/service.py` sind wieder bytegleich und prüfen denselben Release-Schema-Vertrag.
- **BELEGT — Memory-Transport und Collection:** Das Managed-Compose-Deployment bestätigte Milvus-Health, isoliertes gemeinsames Netzwerk, Gateway→Milvus-TCP, keine veröffentlichten Milvus-Ports sowie Create, Insert, Query, Vektorsuche und Drop einer flüchtigen Collection. Marker-Receipt: `f918ac924f0bf5a4bd2ca4f99463d8b5ded8f5e1b3bb65eb6dd1fb3200234d04`.
- **BELEGT — Code Server:** Bundle `828f9bdee7def79ef4731fefffa0234232c9c0456d493a9668211ff9d30ec41d`, bestehendes Volume `code-server-46bq_code-server-config`, erhaltene Authentisierung, root-only `.env`, HTTP `200`, Git, Schreibbarkeit, realer Clone und Cleanup sind verifiziert.
- **BELEGT — PR #867 und Backend-Image:** PR #867 wurde als `246e701f5b2d8ce94c21c001b26bf4aee216239c` gemergt. Das immutable Backend-Image wurde erfolgreich als `sha256:629a694d67c4789053da81656cbc7523a084b8ac52877ff2083aa0325453ae18` gebaut. Der laufende Backend-Container startete jedoch bereits am 20. Juli 2026 um 16:37:26 UTC und wurde seitdem nicht revisionsgebunden auf dieses Image umgestellt; ein Live-Erfolg wird nicht behauptet.
- **BLOCKIERT — Migration `028`:** Das Repository definiert `owner_learning_policies`, das Live-Schema enthält bei 50 Tabellen jedoch keine solche Tabelle und `schema_migrations` enthält keinen Eintrag `028`.
- **OFFEN — Architekturdrift:** Der statische Driftreport enthält 67 P1-Kandidaten: 65 heuristische LLM-/Tool-Boundary-Reviews sowie zwei Mirror-Abweichungen für `llm_cost_policy.py` und `proven_learning_runtime.py`. Diese Kandidaten sind keine automatisch bestätigten Runtimefehler, benötigen aber getrennte SHA-gebundene Reviews.
- **BLOCKIERT — GitHub-App-Routen:** Der aktuelle Backend-Startreadback enthält zweimal `GitHub App routes registration failed: name 'get_connection' is not defined`; die betroffene Routenfamilie ist daher nicht produktiv belegt.
- **OFFEN — Admin-Legacycode:** `scripts/sovereign-backend/app.py` enthält weiterhin den historischen `_ADMIN_PANEL_HTML`-Literalblock, obwohl die Variable vor der Route auf `ENTERPRISE_ADMIN_HTML` überschrieben wird. Ausgeliefert wird code-seitig die neue Oberfläche; die tote zweite Quelle bleibt zu entfernen.
- **BELEGT — Issue-Verträge und Eröffnung:** Das Ursprungsbundle versionierte zwölf operative Punkte und der owner-gated Workflow erzeugte marker-idempotent genau ein GitHub-Issue je Schlüssel. Issue #876 (`historical-schema-ownership`) ist durch PR #973 und den Closure-Record vom 24. Juli 2026 abgeschlossen; das Ursprungsbundle bleibt als historische Eröffnungs-Provenance unverändert.
- **TEILWEISE/BLOCKIERT:** Die aktive operative Open-Point-Liste besteht aus den elf Schlüsseln in Abschnitt 24.2. Kein einzelner Sammelstatus darf einen dieser verbleibenden Punkte verdecken.
- Ein vollständig grüner Produkt- und Releasezustand wird daher nicht behauptet.

---

# 27. Pflege dieses Manifests

Dieses Manifest ist kein statisches Marketingdokument.

Bei jeder relevanten Architekturänderung müssen aktualisiert werden:

- Statusklasse BELEGT/ZIEL/OFFEN,
- betroffene Verträge,
- Endpoint-Familien,
- Datenbanktabellen,
- Containerrollen,
- Runtime-Flows,
- Release-Gates,
- Evidence-Snapshot.

Eine spätere 120- bis 200-seitige Langfassung soll aus diesem Manifest modular erzeugt werden, ergänzt um:

- automatisch generierte Endpoint-Referenz,
- vollständiges Datenmodell,
- Sequenzdiagramme,
- Deployment-Runbooks,
- Threat Model,
- Credit-/Pricing-Spezifikation,
- Android- und Web-Testkatalog,
- Recovery- und Rollbackhandbuch,
- Agenten- und Tool-Vertragsreferenz.
