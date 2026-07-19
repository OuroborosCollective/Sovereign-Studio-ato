# Sovereign Studio ATO — Architektur- und Projektmanifest

**Status:** Lebendes Architekturhandbuch  

**Evidence-Stand:** 19. Juli 2026

**Baseline-Revision vor diesem Manifest-Update:** `25d49ca85d9ab2072bddff620a0da650670f3e76`

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

**BELEGT:** Die produktive Backend-Anwendung besitzt eine eindeutige kanonische Quelle: `scripts/sovereign-backend/app.py`. Das immutable Backend-Image wird ausschließlich aus diesem Deploymentbaum gebaut. `backend/app.py` bleibt als nicht deployte Kompatibilitäts-/Analysequelle sichtbar, ist aber weder Endpoint-Wahrheit noch bytegleichheitspflichtiger Produktionsspiegel.

**BELEGT:** Die tatsächlich gespiegelten Agent-Runtime-, A2A-, ARE-, Knowledge-, Security-, LiteLLM-, `knowledge_library.py`- und `r2_storage.py`-Dateien sind im Architektur-Snapshot bytegleich. Der produktive R2-Adapter verwendet die vollständige fail-closed Implementierung einschließlich Pfad-, MIME-, Hash-, Evidence- und 33-MiB-PDF-Grenzen.

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
- Settlement aus LiteLLM-/Providerkosten und Usage-Evidence,
- Refund bei belegtem Fehlschlag,
- Admin-Statistiken.

**BELEGT:** Das Datenmodell besitzt jetzt eine getrennte `provider_funded_credits`-Spalte, damit Bonus-, Admin- oder Testgutschriften nicht automatisch externe Providerkosten auslösen dürfen. Migration `022` wurde aus der unveränderten Repository-Quelle mit SHA-256 `7c08cf8f92dafe264171d62a19cd6bbc5accf1264574a00ad7f468c7323bdfa4` angewendet. Der anschließende Live-Readback bestätigte den Ledger-Eintrag `022`, alle sieben neuen Constraints, `0` ungültige provider-finanzierte Balances und `0` aktive Routen mit ungeprüfter Preisgrundlage.

## 6.3 Modelle, Provider und Routen

- Provider Registry,
- LiteLLM-Modellkatalog,
- drei Kostenkategorien,
- Modellinventar,
- Modellalias,
- Preis-Metadaten,
- Route-Status,
- Canary- und Health-Evidence,
- Aktivierung nur nach vollständigem Gate.

Die drei Kostenkategorien sind verbindlich:

1. `free`: nur Revolver-/Free-Routen mit von LiteLLM bestätigten Providerkosten von exakt `0`.
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
  → Route und Kostenkategorie bestimmen
  → echte Providerpreise aus LiteLLM-Modellinfo prüfen
  → provider-finanzierte Credits atomar reservieren
  → LiteLLM-Aufruf
  → echte Usage/Cost Evidence
  → Settlement
  → Differenz erstatten oder endgültig verbuchen
```

**BELEGT:** Die Backend-Policy trennt `free`, `standard` und `premium`. `standard` verlangt mindestens `×4`, `premium` mindestens `×8`, und `free` ist nur mit verifizierten Nullkosten zulässig. Kosten werden in Micro-USD berechnet und dann in Credits übersetzt. Provider-finanzierte Credits werden vor dem Provideraufruf reserviert und nach echter Usage-Evidence abgerechnet.

**BELEGT:** Agents-SDK-Aufrufe sind code-seitig auf den Alias `sovereign-fast` beschränkt. Dieser Alias muss auf `gpt-5.4-mini` zeigen, als Standardroute mit mindestens `×4` konfiguriert sein, aktiv sein und verifizierte Preis-Metadaten besitzen. Fehlt eine dieser Bedingungen, blockiert der Agents-SDK-Lauf vor Provider-Ausführung.

**BELEGT:** Sowohl die sichtbare Swarm-Route als auch die owner-scoped Controller-Bridge erzeugen für Start und Resume denselben `AgentStageBilling`-Vertrag. Ein fehlender Alias oder ungeprüfter Preis wird als persistierter `BLOCKED`-Zustand mit konkreter `nextAction` zurückgegeben; bei Resume wird dabei die bereits beanspruchte Lease gebunden und freigegeben. Die Runtime-Contracts prüfen zusätzlich, dass in diesem Blockerpfad keine Usage-Reservation und damit keine Provider-Ausführung begonnen wurde.

## 8.5 Canary und Readiness

- Liveliness beweist nur Prozessleben.
- Readiness beweist Proxy-/DB-Bereitschaft.
- Completion-Canary beweist einen echten Modellpfad.
- Route-Aktivierung erfordert die vollständige Kette.

## 8.6 Master Key

Der LiteLLM-Master-Key bleibt serverseitig. Nachgelagerte Services erhalten zweckgebundene interne Keys mit minimalen Rechten.

## 8.7 Aktueller Betriebsbeweis

**BELEGT — Inventar:** Der geschützte OpenAI-/LiteLLM-Inventarpfad lieferte 92 sichtbare Modelle und bestätigte `gpt-5.4-mini` als verfügbares Provider-Modell. Provider-Identität und Projektzugriff wurden ohne Secret-Ausgabe bestätigt.

**BELEGT — Kostenarchitektur:** Das Repository enthält jetzt einen dreistufigen Kostenvertrag: `free` für Revolver-/Nullkostenrouten, `standard` mit mindestens `×4`, `premium` mit mindestens `×8`. Die Live-Datenbank besitzt die neuen Spalten und Constraints für provider-finanzierte Credits, Usage-Settlement, Billing-Kategorie, Multiplikator, Trace-/Stage-Evidence und Provider-Pricing-Metadaten. Die exakte Migration `022` wurde mit dem Repository-Hash `7c08cf8f92dafe264171d62a19cd6bbc5accf1264574a00ad7f468c7323bdfa4` angewendet und als Version `022` rückgelesen; alle sieben Constraints sind vorhanden, ungültige provider-finanzierte Balances und aktive ungeprüfte Routen stehen jeweils auf `0`.

**BLOCKIERT — aktueller Modellpfad:** Die Aktivierung von `sovereign-fast` und `sovereign-balanced` auf `gpt-5.4-mini` wurde am 19. Juli 2026 erneut gegen das geschützte Inventar `2fcb9285b7ee898910238d9b83cdf570c98bc870ab25853a0770fbc3e6633ef5` versucht. LiteLLM-Readiness, Datenbankverbindung und beide Aliase waren erreichbar, aber beide echten Completion-Canaries erhielten vom OpenAI-Upstream HTTP `429` mit `code=insufficient_quota`. Die Aktivierung wurde deshalb nicht als grün übernommen und der Rollbackpfad ausgelöst. Agents-SDK läuft code-seitig nur über `sovereign-fast` und bleibt fail-closed blockiert, bis Provider-Billing beziehungsweise verfügbares Kontingent hergestellt und ein neuer echter Completion-Canary bestanden ist.

**TEILWEISE:** Der Admin-Pfad für LiteLLM-Modellkatalog, Modellauswahl, Kostenkategorie, Multiplikator und owner-gated Provider-Key-Onboarding ist im Codevertrag vorhanden. Ein vollständiger grüner Produktionsbeweis mit aktivierter `gpt-5.4-mini`-Route fehlt noch.

---

# 9. MCP Docker und ChatGPT Operator

## 9.1 Zweck

Der private Sovereign ChatGPT MCP verbindet ChatGPT mit kontrollierten Repository- und VPS-Fähigkeiten.

## 9.2 Belegter Control-Plane-Stand

**BELEGT:** Die Control Plane meldete `BROKER_READY`. PR #824 wurde vom vollständig grünen Head `7b15d7241597bd40a7f8228733ce5b58f3859545` als Squash-Commit `018e2eee49396a811c9a4539d652053d0d035047` übernommen. PR #825 wurde vom vollständig grünen Head `56564f206ac18a093cd2a101f9df1d6e1f446965` als Squash-Commit `afe3e7fb0415b7de9d201491655e85a7417e4aad` übernommen. PR #826 wurde vom vollständig grünen Head `a5d3fecdb446232149e199c1b2270092bffe0a3a` als Squash-Commit `e2442e4f3c63a1638aa30b7a4339e6a83c2a7f6b` übernommen. PR #827 wurde vom vollständig grünen Head `0e3bc930132cb8f4c57ef991cae1a0e6655f8b71` als Squash-Commit `7cdb4d2f1d9a39881ae4b0a3d61f2c5118d8b117` übernommen. Für die aktuelle Revision bestanden Validation, Veröffentlichung des immutable MCP-Images, Digestprüfung und VPS-Bootstrap. Der Live-Readback meldet dieselbe Revision, den immutable Image-Digest und die Image-ID `sha256:9c9ae2101ff4930f6ecf68f1e7a4fd99b4e769656db9c51787d411e20aa9ee76`, den Archiv-Hash `1be8706177bf96d6771ca6fee5f4e320373f724d1336e96dadd80102afa1228b` sowie den Runtime-Evidence-Hash `cede9cdbb8a7d642c2089934bbfe5b03d48232bf6f9009ee4ce0233cda54f68d`. Container, MCP-Protokoll, Broker-RPC, Host-Command-Worker und Python-/TypeScript-Cross-Runtime-Parität sind revisionsgebunden bereit; direkte eingehende Mutationen bleiben verboten.

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

**BELEGT — Runtime:** Dockerfile, Launcher, Installer, Releasearchiv-Check und GitHub-Workflow sind verdrahtet. Alle acht fachlich relevanten PR-Workflows von PR #824 waren am unveränderten Head grün. Nach dem SHA-gebundenen Merge wurden immutable Image-Publish, Digestprüfung und VPS-Bootstrap über den offiziellen Workflow ausgeführt. Der aktuelle Self-Update- und Control-Plane-Readback bestätigt laufende und Image-Revision `7cdb4d2f1d9a39881ae4b0a3d61f2c5118d8b117` sowie den immutable Digest `sha256:9c9ae2101ff4930f6ecf68f1e7a4fd99b4e769656db9c51787d411e20aa9ee76`. Die sechs Werkzeuge sind damit im privaten MCP produktiv verfügbar; der separate Dokumentpipeline-Fachcanary ist unter 12.1 belegt.

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

**BELEGT:** Browserless, Tika, Gotenberg, Dozzle und Code Server wurden unabhängig als laufende Container ohne Restart-, OOM- oder Exitfehler geprüft. LiteLLM und seine PostgreSQL-Instanz meldeten zusätzlich einen gesunden Healthzustand ohne Failing Streak.

**TEILWEISE:** Prozess- und Health-Evidence beweisen nicht automatisch jede Fachfunktion. Der Gotenberg→Tika-End-to-End-Canary erreicht die laufenden Peer-Container unter der bisherigen Adressierung nicht und wird als eigene Fehlerfamilie in Abschnitt 12 geführt.

**TEILWEISE — Memory-Transport repariert:** Der zuvor mit `EHOSTUNREACH` blockierte Gateway→Milvus-Pfad wurde über das hash-bestätigte Managed-Compose-Bundle `780c5844cc9f8949fba63f2fed1e63a8ae1f53d5930ebdd71366ce8163fef6fa` neu hergestellt. Der Readback bestätigte gesunde Milvus-, Etcd- und MinIO-Container, das isolierte gemeinsame Netzwerk `milvus-kg4i_default`, genau die Mitglieder `milvus-standalone` und `sovereign-memory-gateway`, einen erfolgreichen TCP-Canary vom Gateway zu Milvus sowie keine veröffentlichten Milvus-Ports. Offen bleibt ein separater fachlicher Collection-Read/Write-Canary; Remote Memory bleibt optional und nicht kanonische Produktwahrheit.

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

## 14.1 Aktueller Live- und Importvertrag

**BELEGT:** Die produktive PostgreSQL-/pgvector-Instanz enthält aktuell 37 `ready`-Quellen mit zusammen 400 verknüpften Wissensblöcken. Alle 400 Blöcke besitzen Embeddings; es wurden `0` fehlende Embeddings und `0` verwaiste Source-Block-Links gemessen.

**BELEGT:** Ein weiterer Import steht mit `0` Chunks auf `processing`. Revision `feae19e0965ff276eadc97e95fb2b5aadd046463` führt deshalb einen fail-closed Reconciliation-Vertrag ein: ein länger als 15 Minuten verlassener `processing`-Datensatz ohne verknüpfte Blöcke wird als `blocked` mit `knowledge_import_interrupted` markiert. Ein Importfehler nach dem Processing-Commit wird ebenfalls als begrenzte Fehlerfamilie persistiert; interne Exception-Texte werden nicht als Blocker gespeichert.

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

Die Gateway- und Worker-AI-Endpunkte bleiben als Legacy-Tombstones sichtbar; produktive Online-Modelle dürfen nur über private LiteLLM-Routen laufen.

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

**BELEGT:** Die deterministische Architekturreferenz wird aus dem aktuellen Repositorycode erzeugt. Die produktive Endpoint-Wahrheit stammt ausschließlich aus `scripts/sovereign-backend/app.py` sowie den registrierten Runtime-/Protokollmodulen. Der aktuelle Snapshot enthält 156 kanonische Backendverträge und `0` aktive unmatched Frontend-Calls.

Vier weiterhin sichtbare Altflächen werden nicht verborgen, sondern getrennt ausgewiesen: `/api/ai/gemini` als `legacy-unreferenced` sowie `/api/vps/connect`, `/api/vps/disconnect` und `/api/vps/exec` als `disabled-launcher`. Statische Routenerkennung bleibt Orientierung; produktive Funktionsaussagen benötigen zusätzlich Live-Evidence.

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
  → LiteLLM-Aufruf
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

1. **BELEGT — Cross-Runtime-Parität:** Python- und TypeScript-Verträge werden über gemeinsame Vektoren verglichen und revisionsgebunden im immutable MCP-Release geprüft.
2. **BELEGT — A2A-Livepfad:** AgentCard, owner-scoped Authentisierung, Nachrichten-, Task-, Streaming- und Resume-Verträge wurden in einem echten Produktions-Canary mit derselben persistierten Controller-Truth-Chain korreliert.
3. **BELEGT — deterministischer ARE-State:** Hash-, Schwellen- und Sortiermaterial verwendet Kappa-Fixed-Point mit der Skala `1_000_000`.
4. **BELEGT — persistierte Multi-Agent-Runs:** Dispatcher, sechs Worker, Judge, Tasks, Events, Tool Calls, Evidence, Blocker, Failures und Approvals sind persistiert und trennen aktuelle von historischen Zuständen.
5. **BELEGT — kanonische Backend-Ownership:** `scripts/sovereign-backend/app.py` ist die einzige deployte App-Wahrheit; echte Spiegel einschließlich Knowledge und R2 sind bytegleich.
6. **BELEGT — Endpoint-Referenz:** 156 kanonische Backendverträge, `0` aktive unmatched Frontend-Calls und vier offen ausgewiesene nichtaktive Altflächen.
7. **BELEGT — historischer LiteLLM-Kernpfad:** 92 Provider-Modelle wurden inventarisiert; `sovereign-fast` und `sovereign-balanced` bestanden echte Completion-Canaries. Der davon getrennte aktuelle Quota-Blocker wird unter 24.2 geführt.
8. **BELEGT — Android-Releaseartefakte:** APK und AAB, SHA-256, Signaturdiagnose, ein Signer, Zertifikat-Fingerprint und Alignment wurden im Releaseworkflow belegt.
9. **BELEGT — externe Action-Stream-Brücke im Codevertrag:** owner-scoped, idempotente externe Events mit deterministischen IDs und ohne Run-, Task- oder Blockermutation sind über Store, Backendroute, MCP-Client und MCP-Tool verdrahtet und getestet.
10. **BELEGT — MCP-Releasebasis:** Validation, immutable Image-Publish, Digestprüfung und VPS-Bootstrap bestanden für `7cdb4d2f1d9a39881ae4b0a3d61f2c5118d8b117`; der Live-Readback bestätigte dieselbe Revision und den immutable Digest `sha256:9c9ae2101ff4930f6ecf68f1e7a4fd99b4e769656db9c51787d411e20aa9ee76`.
11. **BELEGT — GitHub-Knowledge- und Modell-Health-Wahrheit:** PR #818 bestand Release Gate, vollständigen Type-check/Test/Build, Security Audit, alle CodeQL-Pfade, OAuth-Live-Path, E2E Smoke, Android- und Runtime-/UX-Verträge und wurde SHA-gebunden als Squash-Commit `feae19e0965ff276eadc97e95fb2b5aadd046463` gemergt. Öffentliche GitHub-Imports sind credential-frei bevorzugt, verlassene Knowledge-Imports werden fail-closed reconciled und Modell-Health erfordert eine echte Completion statt bloßer Readiness.
12. **BELEGT — dreistufiger LLM-Kostenvertrag im Code und Live-Schema:** `free`, `standard` und `premium` sind als Backend-Policy, Admin-Vertrag, Usage-Settlement-Felder, Provider-Pricing-Felder und PostgreSQL-Constraints abgebildet. Provider-finanzierte Credits trennen bezahlte Kaufkraft von Bonus-/Admin-Gutschriften.
13. **BELEGT — GitHub-Knowledge-Transportvertrag im Code:** GitHub-Antwortstatus und HTTPS-Transportfehler werden getrennt behandelt. Timeout, TLS, Connection/DNS und sonstige `requests`-Fehler liefern sichere `github_*`-Blocker mit passender `502`-/`504`-Semantik. Der Fehlerpfad schreibt Audit-Evidence nur mit einem URL-Fingerprint; rohe URL-, Query-, Credential- oder Exceptiondetails werden weder zurückgegeben noch persistiert.
14. **BELEGT — Enterprise-Backend-/Revisionswerkzeuge in Code und Runtime:** Sechs bounded read-only MCP-Tools decken statische Architekturaufnahme, Stackentscheidung, Projekt-/Modernisierungsfahrplan, API-Sicherheitskonzept und die fail-closed Auflösung der vollständigen Repository-/PR-/CI-/Deployment-Revisionstupel ab. FastMCP-Output-Schemas, Eingabegrenzen und ToolAnnotations sind geprüft; PR #824 war vollständig grün, wurde SHA-gebunden gemergt und ist über den revisions- und digestverifizierten privaten MCP produktiv verfügbar.
15. **BELEGT — Dokumentpipeline:** Der private Gotenberg→PDF→Tika-Pfad ist über zwei SHA-gebundene Reparaturstufen, lokale Tests, acht grüne PR-Workflows, immutable Deployment und einen erfolgreichen Produktionscanary belegt. Marker, PDF-Typ und -Hash sowie beide HTTP-Status wurden geprüft; Dokument- und Secretwerte wurden weder zurückgegeben noch persistiert.
16. **BELEGT — KI-Coach-Integration-Workflow:** PR #828 reparierte den joblosen Konfigurationsfehler durch vier statische `needs.<job>.result`-Prüfungen, ergänzte einen zentralen Regression-Guard und band den Logikcheck an die kanonische Funktion `realStopper`. Am unveränderten Head `e8dbf51ea2330babd10c03c99e7a74f95a5ef604` bestanden neun Workflows; der KI-Coach-Lauf `29668564537` erzeugte und bestand alle sechs Jobs einschließlich Unit-, TypeScript-, Build-, Playwright- und Abschlussreport-Gates. Der Head wurde als Squash-Commit `2892776d6d3710ac5a4d40211e2fc09ee0866db3` übernommen.
17. **BELEGT — Action-Stream-Idempotenz:** Ein owner-scoped Produktionscanary erzeugte beim ersten Append genau ein externes Event und eine Evidence. Der identische zweite Append wurde als Duplikat erkannt; Run-, Task-, Failure- und Blockerstatus blieben unverändert.
18. **BELEGT — Release-Schema-Reconciliation:** Die Migrationen `025` und `026` wurden nach Rollback-Preview mit exakter Quell-SHA angewendet. Die zuvor fehlenden Tabellen `platform_runtime_evidence`, `llm_route_attempts` und `llm_route_revolver_state` sind im Live-Readback vorhanden.
19. **BELEGT — Memory-Transport:** Das hash-bestätigte Managed-Compose-Deployment stellte den internen Gateway→Milvus-Pfad wieder her. Milvus-Health, Netzwerkisolation und TCP-Erreichbarkeit wurden ohne externe Portfreigabe bestätigt.

## 24.2 Offen, teilweise oder blockiert

1. **BLOCKIERT/TEILWEISE — Provider-Onboarding und `gpt-5.4-mini`-Route:** Das geschützte Inventar belegt `gpt-5.4-mini`, Provideridentität und vorhandenen Service-Key. Readiness, Datenbank und Aliasinventar sind grün; beide Completion-Canaries enden jedoch reproduzierbar mit OpenAI HTTP `429`, `insufficient_quota`. `sovereign-fast` bleibt deshalb fail-closed inaktiv. Offen bleiben verfügbares Provider-Kontingent sowie der vollständige automatische Lifecycle für beliebige neue Provider inklusive Preisen, atomarer Aktivierung und Rollback.
2. **TEILWEISE — Betriebsbeweise:** Browserless, Tika, Gotenberg, Dozzle, Code Server, LiteLLM, LiteLLM-PostgreSQL, PatchMon und der Milvus-Transport besitzen aktuelle Prozess-, Health- oder Fachcanary-Evidence. Nicht ausdrücklich genannte Fachfunktionen benötigen weiterhin eigene Canaries.
3. **TEILWEISE — Remote Memory:** Der frühere `EHOSTUNREACH`-Transportblocker ist geschlossen und der Gateway→Milvus-TCP-Pfad ist intern verifiziert. Ein fachlicher Collection-Create/Read/Write-/Retrieval-Canary fehlt weiterhin.
4. **TEILWEISE — Android:** Signierte Releaseartefakte und Alignment sind belegt; Installation und Hauptpfad-Smoke auf einem physischen Android-Gerät fehlen.
5. **OFFEN — SHA-gebundene LLM-Boundary-Klassifikation:** Der aktuelle Architektur-Snapshot `86ed7de76e2a301e1ceacdc82b51e5a48fe9c94b10a9afac4b3fc0ed24b952e7` meldet 65 heuristische `LLM_TOOL_BOUNDARY`-Kandidaten. Diese Treffer sind keine Runtimefehler. Die vollständige SHA-gebundene Reviewliste muss noch maschinenlesbar verankert werden, damit jede relevante Dateiänderung den Kandidaten erneut öffnet.
6. **TEILWEISE — GitHub-Knowledge-Livecanary:** Der Codevertrag klassifiziert und auditiert HTTPS-443-Transportfehler sicher. Ein Livecanary nach einem separat freigegebenen immutable Backend-Deployment muss den realen GitHub-Import und den Auditblocker noch bestätigen.
7. **TEILWEISE/BLOCKIERT — Code Server und User-Workspace:** Der Container `code-server-46bq-code-server-1` läuft, aber es ist kein geprüftes Managed-Compose-Template registriert, kein Healthcheck vorhanden und Port `32782` ist aktuell an `0.0.0.0` sowie IPv6 statt ausschließlich Loopback gebunden. Der Container hängt nur in `code-server-46bq_default`; ein user-scoped Clone-/Edit-/Test-/GitHub-Canary und die Anbindung an ein kontrolliertes internes Netzwerk fehlen. Der private MCP-Workspace-Clone ist davon getrennt belegt und funktioniert in isolierten Arbeitsverzeichnissen.
8. **TEILWEISE — Historische Schema-Ownership:** Die P1-Drift für `platform_runtime_evidence`, `llm_route_attempts` und `llm_route_revolver_state` ist geschlossen. Die bereits live vorhandenen Tabellen `admin_users`, `sovereign_agent_draft_pr_events` und `sovereign_agent_evidence_log` besitzen im statischen Migrationsscanner noch keine eindeutig zugeordnete Erzeugerquelle und bleiben P2-Dokumentationsdrift.

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

**BLOCKIERT:** Ein vollständiger Produkt- und Release-Grünstatus wird nicht behauptet. A2A, Backend-Ownership, Endpoint-Referenz, Knowledge-Integrität, signierte Android-Releaseartefakte, die produktive Enterprise-MCP-Werkzeugkette, der Gotenberg→Tika-Produktionscanary, der Action-Stream-Doppel-Append-Canary, die Release-Schema-Tabellen und der interne Milvus-Transport sind belegt. Aktueller harter externer Blocker sind die echten LiteLLM-Completion-Canaries: Beide Aliase erhalten vom OpenAI-Upstream HTTP `429` mit `insufficient_quota`. Zusätzlich fehlen der physische Android-Geräte-Smoke, der fachliche Memory-Collection-Canary, der GitHub-Knowledge-Livecanary, die Code-Server-Härtung samt User-Workspace-Canary sowie die vollständige SHA-gebundene LLM-Boundary-Reviewliste.

---

# 26. Aktueller Evidence-Snapshot

Evidence-Stand: 19. Juli 2026. Aktuelle Repository-Baseline dieser Reparatur ist `25d49ca85d9ab2072bddff620a0da650670f3e76`. Der historische Workflow-Fehler aus Run `29700183253` wurde auf aktuellem `main` durch Run `29701165448` reproduziert und auf den fehlenden fail-closed LiteLLM-Transportblocker eingegrenzt. Zusätzlich wurden Live-Schema-, Memory-Netzwerk-, Action-Stream- und Enterprise-Spiegel-Evidence erneut erhoben. Frühere PR- und Releasebelege bleiben historische Provenance und werden nicht als Ersatz für den heutigen Readback verwendet.

- **BELEGT:** Repository-Baseline für diese Folgearbeit ist `25d49ca85d9ab2072bddff620a0da650670f3e76`. Die produktive MCP-Revision wird davon getrennt über den revisionsgebundenen Self-Update-Readback bewertet.
- **BELEGT:** Für MCP-Release-Revision `7cdb4d2f1d9a39881ae4b0a3d61f2c5118d8b117` bestanden MCP-Validation, immutable Image-Publish, Digestprüfung und VPS-Bootstrap. Der Live-Readback bestätigte Revision, Image-Revision und Image-ID mit Digest `sha256:9c9ae2101ff4930f6ecf68f1e7a4fd99b4e769656db9c51787d411e20aa9ee76`; direkte eingehende Mutationen bleiben verboten.
- **BELEGT:** Kappa-Skala `1_000_000` und Python-/TypeScript-Cross-Runtime-Parität sind revisionsgebunden bestätigt.
- **BELEGT:** A2A wurde mit AgentCard, Owner-Scope, persistiertem Run und `contextId`, Streaming, Resume und Controller-/Task-Endstatus live korreliert.
- **BELEGT:** `scripts/sovereign-backend/app.py` ist die kanonische deployte Backend-App. `knowledge_library.py`, `r2_storage.py` und die übrigen echten Spiegel sind bytegleich.
- **BELEGT:** Der generierte Endpoint-Snapshot enthält 156 kanonische Backendverträge, `0` aktive unmatched Frontend-Calls und vier separat klassifizierte nichtaktive Altflächen.
- **BELEGT:** Das geschützte LiteLLM-/OpenAI-Inventar enthielt 92 Provider-Modelle und bestätigte `gpt-5.4-mini` als verfügbares Modell. Provider-Identität, Projektzugriff und vorhandener Provider-Key wurden ohne Secret-Ausgabe bestätigt.
- **BELEGT:** Migration `022` wurde exakt aus der Repository-Quelle mit SHA-256 `7c08cf8f92dafe264171d62a19cd6bbc5accf1264574a00ad7f468c7323bdfa4` angewendet. Der Live-Readback bestätigte den Ledger-Eintrag `022`, die neuen Kosten-/Billing-Spalten für `provider_funded_credits`, `llm_usage_settlements` und `llm_provider_deployments`, alle sieben neuen Constraints, `0` ungültige provider-finanzierte User-Balances und `0` aktive Routen mit ungeprüfter Preisgrundlage.
- **BELEGT:** Auf PR-Revision `75e2738594986b32bb41793cd150c56b0bdc5ae1` schlossen alle elf GitHub-Workflowläufe erfolgreich ab. Die gezielten lokalen Verträge bestanden mit `237`, die vollständige Suite unter `scripts/sovereign-backend/tests` mit `113` Tests; zusätzlich bestanden der Agents-SDK-Preflight für zwölf Agenten, Compile-, Mirror- und interne Live-Path-Verträge.
- **BLOCKIERT:** Die Alias-Aktivierung von `sovereign-fast` und `sovereign-balanced` auf `gpt-5.4-mini` bestand die echten Completion-Canaries nicht. Beide Aufrufe erhielten HTTP `429` mit `insufficient_quota`; Readiness, Datenbank und Aliasinventar waren dabei grün. Die Alias-/Route-Aktivierung bleibt fail-closed; ein grüner Agents-SDK-Modellpfad wird nicht behauptet.
- **BELEGT:** PR #818 wurde nach vollständig grünen GitHub-Gates SHA-gebunden gemergt. Der neue Modell-Healthvertrag unterscheidet Quota, Rate-Limit, Credentials, Aliasfehler und Infrastruktur und setzt `completionVerified=true` für Grün voraus.
- **BELEGT:** Der aktuelle Live-Readback enthält 38 Knowledge-Quellen: 37 `ready`, eine PDF-Quelle `processing`, 400 verknüpfte Chunks und keine persistierte GitHub-Quelle. In `audit_log` und `sovereign_toolchain_incidents` existiert für den früheren GitHub-443-Fehler keine passende Evidence; der Fehler lag damit vor dem bisherigen Quellen-Commit- und Auditpfad.
- **BELEGT — Code/Test:** Der Folgecode klassifiziert GitHub-Timeout, TLS, Connection/DNS und sonstige Transportfehler in sichere Blocker, liefert keine rohen Exceptiondetails und persistiert nur einen URL-Fingerprint. Die vollständige Suite `scripts/sovereign-backend/tests` bestand lokal mit `119 passed`; der GitHub-PR- und Deploybeweis folgt getrennt.
- **BELEGT — Enterprise-Backend-/Revisions-Code und Runtime:** Sechs read-only MCP-Tools sind in Launcher, Dockerfile, VPS-Installer, Releasearchiv-Check, Workflow und Server-Instruktionen integriert. Acht gezielte Tooltests, 17 Installer-/Docker-Vertragstests und die vollständige lokal ausführbare MCP-Suite mit `264 passed` bestanden auf PR #824; GitHub Actions führte auch die zwei lokal sandboxblockierten Unix-Socket-Verträge aus. Alle acht PR-Workflows waren am unveränderten Head grün. Merge-, laufende und Image-Revision sowie immutable Digest stimmen im Produktions-Readback überein.
- **BELEGT:** Öffentliche GitHub-Wissensimporte laufen credential-frei zuerst; private Reads werden nur nach öffentlichem Nichtfund über den bestätigten Serverzugang versucht.
- **BELEGT:** APK- und AAB-Artefakte, Hashes, Signaturdiagnose, genau ein Signer, Zertifikat-Fingerprint und Alignment liegen als Release-Evidence vor.
- **BELEGT:** Browserless, Tika, Gotenberg, Dozzle und Code Server liefen ohne Restart-/OOM-/Exitfehler; LiteLLM und seine PostgreSQL-Instanz waren healthy.
- **BELEGT:** Der Dokumentcanary erzeugte über den authentisierten privaten Gotenberg-Pfad ein `16.244` Byte großes PDF, prüfte dessen SHA-256, übergab es an Tika und bestätigte dort HTTP `200` sowie den eindeutigen Marker. Quell- und Ausgabedokument, Dokumentinhalt und Secretwerte wurden nicht persistiert oder zurückgegeben.
- **BELEGT:** Der historische KI-Coach-Push-Run `29666014826` scheiterte vor der Joberzeugung. PR #828 beseitigte nacheinander den dynamischen `needs`-Zugriff und den veralteten Symbolcheck. Am finalen unveränderten Head bestanden neun Workflows; KI-Coach-Run `29668564537` bestand seine sechs erzeugten Jobs. Der SHA-gebundene Squash-Merge ist `2892776d6d3710ac5a4d40211e2fc09ee0866db3`.
- **BELEGT — Action Stream:** Der externe Event `event-external-bc681e7c535a46e4a7579e86b8bc40fd` wurde einmal erzeugt und beim identischen zweiten Append als Duplikat erkannt. Es entstand keine zweite Evidence; Runstatus, Tasks, Failures und aktiver Blocker blieben unverändert.
- **BELEGT — Release-Schema:** Die Migrationen `025` und `026` wurden nach erfolgreicher Rollback-Preview aus ihren unveränderten Quell-SHAs angewendet. Der Live-Readback enthält nun 50 Tabellen einschließlich `platform_runtime_evidence`, `llm_route_attempts` und `llm_route_revolver_state`; die drei vorherigen P1-Missing-Table-Befunde sind geschlossen.
- **BELEGT — Enterprise-Spiegel:** `backend/enterprise_platform/service.py` und `scripts/sovereign-backend/enterprise_platform/service.py` sind wieder bytegleich und prüfen denselben Release-Schema-Vertrag.
- **BELEGT — Memory-Transport:** Das Managed-Compose-Deployment bestätigte Milvus-Health, isoliertes gemeinsames Netzwerk und einen erfolgreichen Gateway→Milvus-TCP-Canary ohne veröffentlichte Milvus-Ports.
- **TEILWEISE:** Der fachliche Memory-Collection-Canary, physischer Android-Geräte-Smoke, GitHub-Knowledge-Livecanary, Code-Server-Härtung/User-Workspace-Canary und vollständige SHA-gebundene Klassifikation der 65 LLM-Boundary-Kandidaten bleiben offen.
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
