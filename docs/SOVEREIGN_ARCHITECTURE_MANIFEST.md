# Sovereign Studio ATO — Architektur- und Projektmanifest

**Status:** Lebendes Architekturhandbuch  

**Evidence-Stand:** 18. Juli 2026

**Baseline-Revision:** `b828e3b84367dda85d0b22cdec76de3bda1d78e2`

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
6. Kein Auto-Merge.
7. Maximal Draft PR, sofern ausdrücklich beauftragt.
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
LiteLLM
  ↓
Provider
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
3. **LiteLLM:** Providerabstraktion, Modellalias, Kosten- und Nutzungsdaten.
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
- LLM-Routing über LiteLLM,
- MCP-/Toolchain-Bridges,
- GitHub- und Draft-PR-Verträge,
- Agent-Job-Persistenz,
- Runtime-/Audit-Evidence,
- Provider- und Modellverwaltung.

## 5.2 Kanonische Betriebsinstanz

Die Admin-Backend-Instanz unter
`https://sovereign-backend.arelorian.de/admin`
ist der vorgesehene kanonische Backend-/Admin-Livepfad.

**TEILWEISE:** Die produktiven Agent-Runtime-, A2A-, ARE-, Knowledge-, Security- und LiteLLM-Module sind zwischen `backend/` und `scripts/sovereign-backend/` überwiegend bytegleich. Der aktuelle Architektur-Snapshot weist jedoch noch zwei nicht bytegleiche Spiegelpaare aus: `backend/app.py` gegenüber `scripts/sovereign-backend/app.py` sowie `backend/r2_storage.py` gegenüber `scripts/sovereign-backend/r2_storage.py`. Bis Eigentümerschaft und Deploymentquelle dieser Abweichungen geklärt und vereinheitlicht sind, ist die doppelte Backend-Wahrheit nicht vollständig beseitigt.

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
- Reservierung,
- Settlement,
- Refund bei belegtem Fehlschlag,
- Admin-Statistiken.

## 6.3 Modelle, Provider und Routen

- Provider Registry,
- Modellinventar,
- Modellalias,
- Preis-Metadaten,
- Route-Status,
- Canary- und Health-Evidence,
- Aktivierung nur nach vollständigem Gate.

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
  → LiteLLM-Konfiguration aktualisieren
  → Readiness prüfen
  → Canary je Alias ausführen
  → passende Backend-Routen atomar aktivieren
  → Runtime-Evidence speichern
```

## 7.3 Aktivierungsregel

Keine Route wird aktiviert, solange eines fehlt:

- Provider-Credential vorhanden,
- Inventar bestätigt,
- Modellalias deployt,
- LiteLLM readiness grün,
- Completion-Canary grün,
- Preis-/Credit-Regel vorhanden,
- passender Datenbankeintrag vorhanden.

Ein normaler Nutzerrequest darf niemals Provider- oder Routentabellen reparieren oder aktivieren.

---

# 8. LiteLLM

## 8.1 Aufgabe

LiteLLM ist der private Provider-Router. Es abstrahiert externe Anbieter, Modelle und Kostenmetadaten hinter einem internen OpenAI-kompatiblen Vertrag.

## 8.2 Architektur

```text
Sovereign Backend
  → interner LiteLLM Service Key
  → LiteLLM im privaten Docker-Netz
  → Provider Credential nur im LiteLLM-Prozess
  → externer Provider
```

Frontend, Android und Agents SDK erhalten niemals den echten Provider-Key.

## 8.3 Modelle und Aliase

Produktcode verwendet stabile Aliase, nicht hartcodierte Providerbezeichnungen.

Beispiel:

- `sovereign-fast`
- `sovereign-balanced`
- `sovereign-code`
- `sovereign-reasoning`

Providerwechsel erfolgen hinter dem Alias.

## 8.4 Preisberechnung

LiteLLM liefert Nutzungs- und Kostenmetadaten. Sovereign Backend führt das Nutzer-Creditkonto.

```text
Request
  → maximale Credits reservieren
  → LiteLLM-Aufruf
  → echte Usage/Cost Evidence
  → Settlement
  → Differenz erstatten oder endgültig verbuchen
```

## 8.5 Canary und Readiness

- Liveliness beweist nur Prozessleben.
- Readiness beweist Proxy-/DB-Bereitschaft.
- Completion-Canary beweist einen echten Modellpfad.
- Route-Aktivierung erfordert die vollständige Kette.

## 8.6 Master Key

Der LiteLLM-Master-Key bleibt serverseitig. Nachgelagerte Services erhalten zweckgebundene interne Keys mit minimalen Rechten.

---

# 9. MCP Docker und ChatGPT Operator

## 9.1 Zweck

Der private Sovereign ChatGPT MCP verbindet ChatGPT mit kontrollierten Repository- und VPS-Fähigkeiten.

## 9.2 Belegter Control-Plane-Stand

**BELEGT:** Die Control Plane meldet `BROKER_READY`. Das private MCP ist auf exakt Revision `b828e3b84367dda85d0b22cdec76de3bda1d78e2` installiert. Revision, Archiv, immutable Image-Digest und Image-ID sind verifiziert; Container, MCP-Protokoll, Broker-RPC und Host-Command-Worker sind bereit. Direkte eingehende Mutationen bleiben verboten. Die Cross-Runtime-Parität zwischen Python- und TypeScript-Vertrag ist revisionsgebunden als `cross_runtime_parity_proven=true` belegt.

Die Runtime-Grenzen schreiben unter anderem vor:

- keine generische Shell,
- keine Secrets im Modellpfad,
- Host-Mutationen nur über kontrollierte Queue,
- Node-Builds und Dependency-Installationen über GitHub Actions,
- Draft-PR-only als normaler Releaseausgang.

**BELEGT:** Der jüngste persistierte Agents-SDK-Lauf `run-1f7ee714872445319bed247506cdd366` ist `COMPLETED`, lief drei Iterationen und endete ohne Repositoryänderung mit `NO_FURTHER_ACTION_REQUIRED`. Ältere blockierte Läufe bleiben als historische Evidence erhalten und werden nicht in einen globalen Grünstatus umgedeutet.

## 9.3 Fähigkeiten

- isolierter Workspace,
- Repository lesen und exakt patchen,
- Diff,
- Tests/Checks delegieren,
- Draft PR,
- Workflowstatus,
- Runtime-/Container-Evidence,
- PostgreSQL-/Vector-Canaries,
- immutable Backend-Deployment.

## 9.4 A2A-Adapter

**BELEGT:** Der Backendvertrag enthält eine AgentCard unter `/.well-known/agent-card.json`, A2A-Nachrichten-, Streaming-, Task-, Subscribe- und Cancel-Routen sowie owner-scoped Service-Authentisierung. Der Adapter startet und liest dieselbe persistierte Agents-SDK-Truth-Chain wie die direkten Swarm-Routen; er ist kein zweiter fachlicher Orchestrator. PR #799 wurde mit vollständigen Backend-, MCP-, Security-, Android-, Build- und Runtime-Gates grün abgeschlossen.

**OFFEN:** In der laufenden Produktionsdatenbank besitzen derzeit `0` von `27` Agent-Runs einen gespeicherten `a2aContextId`. Ein authentifizierter Live-Canary muss noch einen A2A-Run erzeugen, den Task erneut lesen und den Endstatus mit der nativen Controller-Evidence vergleichen. A2A darf bis dahin als implementiert und CI-belegt, aber nicht als produktiv genutzt bezeichnet werden.

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

## 10.5 Aktuell gemeldete Betriebsdaten

Vom Owner wurden laufende Container für Browserless, Tika, Gotenberg, Dozzle, LiteLLM, Code Server, MCP und Memory Gateway gemeldet. Diese Meldung ist kein Ersatz für unabhängige Container- und Health-Evidence.

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

---

# 13. SQL-Datenbank

## 13.1 Tabellenfamilien im Repository

Die Migrationen belegen unter anderem folgende Familien:

### Admin und Sicherheit

- `admin_api_keys`
- `owner_input_requests`
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

**BLOCKIERT:** PR #802 soll den sichtbaren Pattern-Memory-Pfad so ändern, dass nur akzeptierte serverseitige Learning-Evidence den Zustand „gelernt“ erzeugen darf. Der Draft PR ist mergebar, aber seine Head-SHA `88f5d453853be8a789a526ca426547ceeab38809` hat fehlgeschlagene Typecheck-/Test-/Build-, Runtime-/UX-, Android-, Release- und Code-Quality-Gates. Die Aufgabe ist daher nicht erledigt und darf nicht gemergt oder als produktiv behauptet werden.

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

### LiteLLM

Privater Provider-Router; kein öffentlicher Clientzugriff.

### PostgreSQL

Kanonische Produkt-, Runtime-, Audit-, Billing- und Knowledge-Daten.

### MCP / ChatGPT Operator

Kontrollierte Repository- und VPS-Operationen.

### Memory Gateway

Trennung von Contributor-Daten und geteilten abgeleiteten Mustern.

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
- `/api/admin/llm/gateway/providers`
- `/api/admin/llm/gateway/sync`
- `/api/admin/llm/worker-ai/status`
- `/api/admin/llm/worker-ai/models`
- `/api/admin/llm/worker-ai/sync`

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

**OFFEN:** Eine vollständig automatisch generierte, normalisierte Endpoint-Referenz aus dem jeweils aktuellen Backendcode und den Protokollverträgen bleibt ausstehend. Statische Routenerkennung ersetzt keinen authentifizierten Live-Canary.

---

# 22. Runtime-Flows

## 22.1 Chatflow

```text
User Text
  → Backend Session prüfen
  → Creditfähigkeit prüfen
  → Online-LLM über LiteLLM
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
  → Access prüfen
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
  → kein Auto-Merge
```

## 22.5 Creditflow

```text
Request
  → Route und Maximalverbrauch bestimmen
  → Credits atomar reservieren
  → LiteLLM-Aufruf
  → Usage/Cost Evidence
  → Settlement
  → Refund oder endgültige Abbuchung
  → Ledger + Receipt
```

## 22.6 GitHubflow

```text
GitHub Intent
  → validierter Access-State
  → Repo-/Branch-Scope
  → Lesen oder isolierter Workspace
  → Patch/Commit
  → Draft PR
  → Checks beobachten
  → Merge nur separate ausdrückliche Owner-Freigabe
```

---

# 23. Harte Projektregeln

1. Runtime erzeugt Wahrheit.
2. UI erzeugt niemals Wahrheit.
3. LLM versteht Sprache.
4. Runtime versteht strukturierte Aktionen.
5. Evidence schlägt Vermutung.
6. Kein Auto-Merge.
7. Maximal Draft PR im Standardpfad.
8. Keine Mocks, Stubs oder Fassaden im Live-Pfad.
9. Keine statischen Provider-Routen im Frontend.
10. Keine hartcodierten Provider wie Pollinations, Groq oder vergleichbare direkte Clientprovider.
11. Provider werden ausschließlich über Backend, Datenbank und LiteLLM verwaltet.
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

1. **BELEGT — Cross-Runtime-Parität:** Python- und TypeScript-Verträge werden über gemeinsame Vektoren verglichen; die erfolgreiche Parität wird seit PR #798 revisionsgebunden im immutable MCP-Release belegt.
2. **BELEGT — A2A-Vertrag und Agents-SDK-Verdrahtung:** AgentCard, owner-scoped Authentisierung, Nachrichten-/Task-Routen und Truth-Chain-Abgleich wurden mit PR #799 implementiert und durch CI-Gates bestätigt.
3. **BELEGT — deterministischer ARE-State:** Hash-, Schwellen- und Sortiermaterial wurde mit PR #800 auf Kappa-Fixed-Point umgestellt.
4. **BELEGT — Release-Ergebnisvalidierung:** PR #801 stärkte die Validierung von Release-Resultaten; alle relevanten Checks waren grün.
5. **BELEGT — persistierte Multi-Agent-Runs:** Agents-SDK-Runs, Tasks, Events und Evidence werden persistiert; der jüngste Run wurde nach drei Iterationen erfolgreich abgeschlossen.
6. **BELEGT — MCP-Control-Plane:** Exact-Revision-, Digest-, Container-, Protokoll-, Broker-, Host-Worker- und Boundary-Evidence ist für die aktuelle Main-Revision vorhanden.

## 24.2 Offen oder teilweise

1. **TEILWEISE — doppelte Backend-Wahrheit:** `app.py` und `r2_storage.py` sind zwischen Quell- und Deploymentbaum noch nicht bytegleich.
2. **OFFEN — A2A-Live-Canary:** Ein authentifizierter Produktionslauf über A2A mit persistiertem `a2aContextId` und anschließendem Task-/Controllervergleich fehlt.
3. **BLOCKIERT — Pattern Memory:** PR #802 muss repariert und vollständig grün werden, bevor „gelernt“ ausschließlich aus akzeptierter Runtime-Evidence entstehen kann.
4. **OFFEN — Provider-Onboarding:** geschützter Key-Input, Inventar, Preise, Aliase, LiteLLM-Readiness, Completion-Canary und atomare Aktivierung/Rollback müssen als eine durchgängige Live-Kette belegt werden.
5. **TEILWEISE — LiteLLM-Runtimekonsolidierung:** Datenbank-, Alias- und Routenkonzepte existieren; der vollständige automatische Provider-Lifecycle ist noch nicht releasebelegt.
6. **OFFEN — vollständige Endpoint-Referenz:** automatisierte Generierung aus aktuellem Code, Protokollverträgen und OpenAPI-/Schemaquellen.
7. **OFFEN — unabhängige Betriebsbeweise:** Browserless, Tika, Gotenberg, Dozzle, Code Server und Memory Gateway benötigen jeweils aktuellen Container-, Health- und Funktionsnachweis.
8. **OFFEN — Android-Releasebeweis:** signiertes APK/AAB, Prüfsumme, Alignment, Signing, Installation und echter Hauptpfad-Smoke auf Android müssen gemeinsam belegt werden.
9. **OFFEN — Dokumentpipeline:** Tika-Ingestion und Gotenberg-Evidence-PDF benötigen einen vollständigen produktiven End-to-End-Nachweis.
10. **OFFEN — einheitlicher Sovereign Action Stream:** alle aktiven Routen müssen auf eine persistierte, idempotente und überprüfbare Aktions-/Ereigniskette konsolidiert werden.

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
- kein Auto-Merge möglich ist,
- Credits serverseitig korrekt reserviert und abgerechnet werden,
- Fehler verständlich sichtbar sind,
- Android und Web den Hauptpfad bedienen,
- eine belegte Rückfall- oder Rollbackmöglichkeit vorhanden ist,
- Provider- und Modellrouten echte Canaries bestanden haben,
- Secrets serverseitig und unsichtbar für LLM/Frontend bleiben,
- Draft-PR- und CI-Evidence gespeichert ist.

## 25.1 Aktuelle Gatebewertung

**BLOCKIERT:** Ein vollständiger Release-Grünstatus wird aktuell nicht behauptet. PR #802 besitzt reale fehlgeschlagene Pflichtchecks. Zusätzlich fehlen der produktive A2A-Live-Canary, die Beseitigung der verbleibenden Backend-Spiegeldrift sowie der signierte Android-Artefakt- und Installationsnachweis.

---

# 26. Aktueller Evidence-Snapshot

Evidence-Stand: 18. Juli 2026, vor diesem Dokumentcommit.

- **BELEGT:** Baseline und installierte MCP-Revision entsprechen `b828e3b84367dda85d0b22cdec76de3bda1d78e2`.
- **BELEGT:** Archiv-SHA, immutable Image-Digest, Image-ID und Revision sind verifiziert; MCP-Container und MCP-Protokoll sind bereit.
- **BELEGT:** Control Plane und Broker melden `BROKER_READY`; Broker-RPC und Host-Command-Worker sind aktiv, eingehende Direktmutationen sind verboten.
- **BELEGT:** Kappa-Skala `1_000_000` und Python-/TypeScript-Cross-Runtime-Parität sind revisionsgebunden bestätigt.
- **BELEGT:** Der jüngste persistierte Agents-SDK-Lauf `run-1f7ee714872445319bed247506cdd366` ist `COMPLETED` und endete mit `NO_FURTHER_ACTION_REQUIRED`.
- **BELEGT:** PRs #798, #799, #800 und #801 wurden mit allen jeweils relevanten Pflichtchecks grün abgeschlossen und sind Bestandteil von `main`.
- **BLOCKIERT:** PR #802 ist offen und besitzt fehlgeschlagene Typecheck-/Test-/Build-, Runtime-/UX-, Android-, Release- und Code-Quality-Gates.
- **TEILWEISE:** A2A ist auf `main` implementiert und CI-belegt; die Produktionsdatenbank zeigt jedoch `0` A2A-Runs bei insgesamt `27` Runs.
- **TEILWEISE:** Die meisten Backendspiegel sind bytegleich; `app.py` und `r2_storage.py` weisen weiterhin Spiegeldrift auf.
- **OFFEN:** Unabhängige Live-Evidence für alle GPT-Tools-/Code-Server-/Memory-Gateway-Funktionen sowie der signierte Android-Releasepfad fehlt.
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
