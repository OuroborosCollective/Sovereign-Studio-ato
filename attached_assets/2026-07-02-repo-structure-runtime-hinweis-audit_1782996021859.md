# Repo Structure & Runtime Hinweis-Audit

Datum: 2026-07-02  
Projekt: NOCODESTUDIO / Sovereign Studio ATO  
Repo: OuroborosCollective/Sovereign-Studio-ato  
Audit-Art: Hinweis-/Aussage-Audit auf Basis bereitgestellter Analyse-Nachrichten

## 1. Zweck

Dieses Dokument sammelt belastbare Hinweise aus den bereitgestellten Analyse-Nachrichten und ordnet sie nach Beweisgrad, Risiko und naechster erlaubter Aktion.

Es ist bewusst kein finales Runtime-Wahrheits-Audit. Die Quelle dieses Dokuments sind Aussagen, Analyseprotokolle und beobachtete Indikatoren. Harte Wahrheit entsteht erst durch direkten Code-, Test-, Workflow- oder Runtime-Nachweis.

Projektregel fuer dieses Audit:

> Baue niemals eine UI, die Wahrheit erzeugt. Baue eine Runtime, die Wahrheit erzeugt. Die UI darf diese Wahrheit nur anzeigen.

## 2. Beweisgrad-Skala

- **Belegt im Analyseprotokoll**: Die bereitgestellten Nachrichten nennen konkrete Dateien, Zahlen, Pfade oder Code-Eigenschaften.
- **Plausibel**: Mehrere Hinweise zeigen in dieselbe Richtung, aber ein erneuter direkter Repo-Check ist sinnvoll.
- **Verdacht**: Moegliches Risiko, noch nicht ausreichend belegt.
- **Entkraeftet**: Urspruenglicher Verdacht wurde durch die Analyse selbst ausgeraeumt.
- **Offen**: Nicht aus dem Repo allein entscheidbar, z. B. Cloudflare-Secret-Konfiguration.

## 3. Executive Summary

Das Repo wirkt nicht wie ein kleines Prototyp-Projekt, sondern wie ein stark gewachsenes Android-first NoCode-/AI-Service-Tool mit breiter Runtime-, Worker-, GitHub-, Memory- und Agent-Schicht.

Positive Befunde:

- Die Runtime-Schicht ist umfangreich und offenbar bewusst testnah aufgebaut.
- Streaming wurde laut Analyse bereits als echter SSE-Pfad implementiert und im BuilderContainer verdrahtet.
- Viele Runtime-Module besitzen direkte Tests; die Testdisziplin im Runtime-Ordner wirkt hoch.
- Der vorhandene GitHub-Write-Proxy ist bereits sicherheitsbewusst aufgebaut, aber noch auf Full-File-Write ausgelegt.

Hauptprobleme:

- `BuilderContainer.tsx` ist ein massiver God-Component-Kandidat mit sehr vielen Zustandsquellen, UI-Subkomponenten und Business-/Runtime-Helfern in einer Datei.
- Memory-/Remote-/External-Namensraeume sind konzeptionell feinkoernig, aber sprachlich verwirrend und koennen Drift verursachen.
- Ein sicherer `/git/patch`- oder SEARCH/REPLACE-Pfad fehlt laut Analyse noch im Repo, obwohl der Bedarf durch grosse Dateien klar gegeben ist.
- Cloudflare AI Proxy hat ein Sicherheitsrisiko, falls `PROXY_API_KEY` in der echten Worker-Umgebung nicht gesetzt ist.
- Rate-Limiting im Worker ueber In-Memory-Map ist fuer Cloudflare Workers nur begrenzt belastbar.

## 4. Befund A: BuilderContainer.tsx ist zu gross fuer dauerhafte sichere Entwicklung

**Beweisgrad:** Belegt im Analyseprotokoll  
**Risiko:** Hoch  
**Betroffene Regel:** Keine grossen Live-Pfad-Dateien blind ersetzen. Runtime erzeugt Wahrheit; UI zeigt sie nur an.

### Beobachtung

Die Analyse meldet:

- `src/features/product/containers/BuilderContainer.tsx` hat ca. 4.682 Zeilen.
- Die eigentliche Komponentenfunktion startet erst ca. bei Zeile 3.099.
- Vorher liegen rund 3.000 Zeilen Typen, Konstanten, Hilfsfunktionen und UI-Subkomponenten.
- Es wurden 38 `useState`-Aufrufe und 13 `useEffect`-Aufrufe in einer zentralen Komponente beobachtet.
- Es existieren viele interne UI-Subkomponenten in derselben Datei, z. B. TopBar, StatusPanel, FileBadge, ThoughtBubble, Bubble, ThinkingDots, OutcomeHints, WelcomeScreen, ModuleScreen, RuntimeSheet, SideDrawer, Composer, BottomTabBar.
- Kommentare wie `BuilderContainer v3`, `verbatim`, Issue-Patches und PAL-Zusatz weisen auf eine Additionshistorie hin.

### Bewertung

Das wirkt nicht wie schlampiger Code, sondern wie ein bewusst konservativer Wachstumsstil: vorhandene grosse Datei nicht zerbrechen, sondern neue Issue-Fixes additiv danebenbauen.

Diese Strategie war kurzfristig sicher, ist aber jetzt selbst ein Risiko:

- kleine Patches werden schwer eindeutig zu platzieren,
- Testfixes werden breiter als noetig,
- UI-/Runtime-Grenzen verschwimmen,
- neue Helfer landen eher im Container als in `runtime/**`,
- grosse Full-File-Replaces werden wahrscheinlicher und damit riskanter.

### Naechste erlaubte Aktion

Kein Full-File-Replace.

Empfohlene Reihenfolge:

1. Neue Tests/Contracts vor Extraktion schreiben.
2. Reine Hilfsfunktionen aus BuilderContainer nach `src/features/product/runtime/**` verschieben.
3. UI-Subkomponenten in kleine, reine Komponenten unter `src/features/product/components/**` verschieben.
4. Zustaende mit einer kleinen State-Machine oder `useReducer` schrittweise gruppieren.
5. Jede Extraktion nur per kleinem SEARCH/REPLACE-Patch oder PR.

## 5. Befund B: Runtime-Modul-Landschaft ist stark fragmentiert, aber nicht pauschal redundant

**Beweisgrad:** Belegt im Analyseprotokoll  
**Risiko:** Mittel  
**Betroffene Regel:** Jeder Schritt muss aus vorherigem Ergebnis logisch ableitbar sein.

### Beobachtung

Die Analyse nennt ca. 116 Dateien unter `src/features/product/runtime/`. Ein erster Namensverdacht auf Redundanz wurde teilweise entkraeftet.

Insbesondere Memory/Pattern-Dateien bilden offenbar mehrere Schichten:

- Persistenz: `solutionPatternPersistence`, `sovereignSessionMemory`
- Domaenenmodell/Runtime: `solutionPatternMemory`, `patternMemoryRuntime`, `sovereignLearningMemory`
- Container-Bindung: `patternMemoryContainerRuntime`, `patternMemoryProposalRuntime`
- Matching/Anwendung: `patternReusePlanner`
- Remote-/External-Sync: `externalMemorySync`, `externalMemorySyncPreview`, `externalMemoryMonitoring`, `remoteMemoryContainerRuntime`, `remoteMemoryGatewayBridge`, `remoteMemoryProductionReadiness`, `remoteMemoryUpdateIntake`

### Bewertung

Das ist feinkoernig und teilweise fachlich sinnvoll. Es sollte nicht pauschal zusammengelegt werden.

Das Problem liegt eher in der Sprache:

- `solution pattern`, `learned pattern`, `learning memory pattern` klingen aehnlich,
- `external memory` und `remote memory` scheinen laut Analyse denselben Gateway-/Sync-Komplex zu beschreiben,
- neue Agenten koennen dadurch falsche Zusammenlegungen oder doppelte Features bauen.

### Naechste erlaubte Aktion

1. Ein kleines `docs/architecture/memory-boundaries.md` anlegen.
2. Begriffe verbindlich definieren:
   - Solution Pattern
   - Learned Pattern
   - Learning Memory Node
   - Remote Memory Gateway
   - External Sync
3. Keine funktionale Zusammenlegung, bevor Imports und Tests pro Datei kartiert sind.
4. Bei neuen Dateien ein Namenspraefix waehlen und alte Praefixe nicht weiter vermehren.

## 6. Befund C: `externalMemory*` und `remoteMemory*` bezeichnen offenbar denselben Sync-Komplex

**Beweisgrad:** Belegt im Analyseprotokoll  
**Risiko:** Mittel  
**Betroffene Regel:** Kein Drift; jede neue Logik braucht klare Runtime-Checks und Validierung.

### Beobachtung

Die Analyse berichtet, dass `remoteMemoryGatewayBridge` und `remoteMemoryContainerRuntime` direkt aus `externalMemorySync*` importieren.

### Bewertung

Das ist kein zwingender Laufzeitfehler, aber ein Architektur-Drift-Risiko. Zwei Praefixe fuer denselben fachlichen Komplex erschweren:

- Suche,
- Tests,
- Onboarding,
- Agent-Auftraege,
- spaetere Refactors.

### Naechste erlaubte Aktion

1. Einen kanonischen Begriff festlegen: wahrscheinlich `remoteMemory` fuer Gateway/Sync.
2. Neue Dateien nur noch unter einem Praefix anlegen.
3. Optional spaeter Alias-Dateien mit Deprecation-Kommentar nutzen.
4. Erst nach Tests und Importkarte umbenennen.

## 7. Befund D: `repoLaunchReadiness` vs. `repoLaunchReadinessFromFiles` ist kein Duplikat

**Beweisgrad:** Entkraeftet durch Analyse  
**Risiko:** Niedrig  
**Betroffene Regel:** Keine falschen Vorwuerfe, kein blinder Cleanup.

### Beobachtung

Die Analyse beschreibt `repoLaunchReadinessFromFiles.ts` als Adapter von `RepoFile[]` zu `RepoSignals`, der aus `repoLaunchReadiness.ts` importiert.

### Bewertung

Das ist eine sinnvolle Trennung von Modell/Logik und Adapter. Kein Refactor notwendig.

### Naechste erlaubte Aktion

Nicht anfassen, solange keine Tests oder echte Fehler dagegen sprechen.

## 8. Befund E: Sicherer `/git/patch`-Pfad fehlt noch

**Beweisgrad:** Belegt im Analyseprotokoll  
**Risiko:** Hoch  
**Betroffene Regel:** Keine grossen Full-File-Replaces; bei grossen Dateien SEARCH/REPLACE mit eindeutiger Trefferzahl.

### Beobachtung

Die Analyse meldet keinen Treffer fuer `/git/patch`.

Gleichzeitig wurde beschrieben, dass `GitHubWriteProxyPayloadFile` nur folgendes Modell hat:

```ts
path: string;
content: string;
```

Das bedeutet: Der bestehende Write-Pfad arbeitet mit vollstaendigen Datei-Inhalten, nicht mit Patch-/Diff-/SEARCH-REPLACE-Bloecken.

### Bewertung

Fuer kleine Dateien ist Full-File-Replace akzeptabel. Fuer `BuilderContainer.tsx`, `App.tsx` und andere grosse Live-Pfad-Dateien ist das zu riskant.

Ein sicherer Patch-Endpunkt passt sehr gut zur vorhandenen Sicherheitslogik, wenn diese laut Analyse bereits Pfadvalidierung, Secret-Detection und Groessenlimits enthaelt.

### Naechste erlaubte Aktion

Route/Worker-Funktion fuer `/git/patch` oder gleichwertigen Tool-Pfad bauen:

- Auth-Secret erforderlich
- Repo-Allowlist
- Branch-Allowlist
- `dryRun: true` zuerst
- `expectedSha`
- max file size
- max block count
- max replacement size
- exakte SEARCH-Trefferzahl pruefen
- 0 Treffer blockieren
- >1 Treffer blockieren
- bei exakt 1 Treffer ersetzen
- keine Secrets in Logs
- optional Draft PR statt direktem Main-Write

## 9. Befund F: Streaming ist bereits implementiert und verdrahtet

**Beweisgrad:** Belegt im Analyseprotokoll  
**Risiko:** Niedrig  
**Betroffene Regel:** Keine veralteten Erinnerungen als Wahrheit behandeln.

### Beobachtung

Die Analyse stellt fest:

- `streamDevChatWorkerReply` existiert als Async Generator mit SSE-Parsing.
- `BuilderContainer.tsx` nutzt den Streaming-Pfad aktiv mit `for await`.
- `fetchDevChatWorkerReply` bleibt als Fallback-Pfad vorhanden.

### Bewertung

Streaming sollte nicht mehr als offenes Feature gefuehrt werden. Das ist ein positiver Befund.

### Naechste erlaubte Aktion

1. Streaming in Audit/README als erledigt markieren.
2. Nur noch Stabilisierung pruefen:
   - Fehlendes SSE-Body
   - Nicht-SSE-Antwort
   - Worker 4xx/5xx
   - Abbruch/Timeout
   - leere Antwort

## 10. Befund G: Runtime-Testdisziplin wirkt hoch, aber CI-Abdeckung sollte gemappt werden

**Beweisgrad:** Belegt/Plausibel im Analyseprotokoll  
**Risiko:** Mittel  
**Betroffene Regel:** Keine Fake-Erfolge; CI-gruen nur behaupten, wenn geprueft.

### Beobachtung

Die Analyse nennt:

- Nur ca. 9 von 116 Runtime-Dateien ohne direkte 1:1-Testdatei.
- `package.json` enthaelt mehrere Gate-Skripte, u. a. `verify`, `test:release-gate`, `test:smoke`, `test:integration`, `test:all`.
- CI nutzt laut Analyse nicht nur `test:smoke`, sondern `test:release-gate`.
- Trotzdem koennten manche Testdateien nur ueber `test:all` oder `verify` laufen.

### Bewertung

Das ist keine schlechte Testlage. Im Gegenteil: Die Tests wirken relativ reif.

Offene Luecke ist nicht `Tests fehlen`, sondern: Welche Tests laufen wirklich in welchem Gate?

### Naechste erlaubte Aktion

1. Script `scripts/audit-test-coverage-map.mjs` bauen.
2. Alle `*.test.ts`, `*.test.tsx`, `*.spec.ts`, `e2e/**` sammeln.
3. Gegen `package.json`-Skripte und `.github/workflows/**` mappen.
4. Report erzeugen:
   - laeuft in release gate
   - laeuft nur in verify
   - laeuft nur manuell
   - laeuft gar nicht automatisch

## 11. Befund H: Cloudflare AI Proxy kann offen sein, wenn `PROXY_API_KEY` nicht gesetzt ist

**Beweisgrad:** Belegt im Analyseprotokoll, Deployment-Status offen  
**Risiko:** Kritisch, falls Secret nicht gesetzt  
**Betroffene Regel:** Keine Secrets in Logs; keine offenen Live-Pfade mit serverseitigem Token.

### Beobachtung

Die Analyse beschreibt:

- Worker nutzt serverseitige Provider-Secrets wie `CF_AI_TOKEN`.
- `PROXY_API_KEY` ist optional typisiert.
- Auth-Pruefung gibt offenbar `true` zurueck, wenn `env.PROXY_API_KEY` nicht gesetzt ist.

### Bewertung

Wenn `PROXY_API_KEY` in der echten Cloudflare-Umgebung fehlt, waere der Worker fuer jeden mit URL nutzbar und koennte Kosten/Kontingent gegen serverseitige Provider-Secrets erzeugen.

Nicht aus dem Repo beweisbar: ob `PROXY_API_KEY` in Produktion tatsaechlich gesetzt ist.

### Naechste erlaubte Aktion

1. Worker hard-failen lassen, wenn `PROXY_API_KEY` fehlt.
2. Health-Endpunkt darf nur `configured: false` melden, aber keine Secrets offenlegen.
3. Tests fuer drei Faelle:
   - Secret fehlt => 503/blocked
   - Secret gesetzt, Header fehlt => 401
   - Secret gesetzt, Header korrekt => allow
4. Android/Web-App muss den Client-Key nicht im Repo hart kodieren.

## 12. Befund I: Worker-Rate-Limit ueber In-Memory-Map ist fuer Cloudflare nur schwach

**Beweisgrad:** Belegt im Analyseprotokoll  
**Risiko:** Mittel bis Hoch  
**Betroffene Regel:** Runtime erzeugt Wahrheit; UI darf keine harte Limit-Wahrheit behaupten, wenn Runtime sie nicht global garantiert.

### Beobachtung

Die Analyse beschreibt Rate-Limiting ueber eine In-Memory `Map` im Cloudflare Worker.

### Bewertung

Cloudflare Workers laufen ueber Edge-Isolate. Eine In-Memory-Map ist nicht global konsistent und kann pro warmer Isolat-Instanz separat sein.

Ein Limit wie `60` waere dadurch eher `60 pro Isolat/Region/Warm-Kontext` als globaler Schutz.

### Naechste erlaubte Aktion

1. Limit-Anzeige nicht als harte globale Wahrheit darstellen.
2. Fuer echten Schutz Cloudflare Durable Objects oder KV-basierte Rate-Limit-Schicht pruefen.
3. Tests fuer Rate-Limit-Entscheidung isolieren.
4. Dokumentieren: In-Memory-Limit ist nur Best-Effort.

## 13. Befund J: Bestehendes Audit vom 26.06.2026 nicht duplizieren

**Beweisgrad:** Belegt im Analyseprotokoll  
**Risiko:** Niedrig  
**Betroffene Regel:** Keine redundanten Dokumente; keine falschen Scope-Vermischungen.

### Beobachtung

Im Repo existiert laut Analyse bereits ein Audit vom 26.06.2026, dessen Scope auf Runtime-Verhalten echt oder Fassade fuer Issue #369 begrenzt war.

### Bewertung

Dieses neue Dokument ersetzt das alte nicht. Es erweitert den Blick auf Struktur, Runtime-Architektur, GitHub-Write-Pfad, Worker-Sicherheit und Test-Gates.

### Naechste erlaubte Aktion

1. Dieses Dokument als Struktur-/Runtime-Hinweis-Audit behandeln.
2. Vor spaeteren Audits eine `docs/audit/README.md` oder Index-Datei anlegen.
3. Audits nach Scope benennen, nicht chronologisch allein.

## 14. Priorisierte Maßnahmen

### P0 — Sicherheits-/Kostenrisiko

- Cloudflare AI Proxy muss blockieren, wenn `PROXY_API_KEY` fehlt.
- Auth- und Secret-Status nicht in Logs oder UI als Rohwert ausgeben.

### P1 — Sicheres Arbeiten an grossen Dateien

- `/git/patch` oder gleichwertigen SEARCH/REPLACE-Patch-Endpoint bauen.
- Dry-run/Preview vor Apply erzwingen.
- Branch/PR bevorzugen, besonders bei `BuilderContainer.tsx` und `App.tsx`.

### P2 — BuilderContainer stabilisieren

- Reine Runtime-Helfer aus Container extrahieren.
- UI-Subkomponenten aus Datei auslagern.
- State-Gruppen schrittweise in Reducer/Runtime-State ueberfuehren.
- Keine visuelle Dashboard-Erweiterung als Loesung bauen.

### P3 — Memory-/Remote-Namenskonvention klaeren

- Begriffe dokumentieren.
- Ein Praefix fuer Remote/External Memory festlegen.
- Keine grosse Umbenennung ohne Importkarte und Tests.

### P4 — Test-Gate-Mapping

- Automatisches Mapping aller Testdateien zu CI-/Verify-Skripten erzeugen.
- Keine Aussage `alles getestet`, solange nicht klar ist, welches Gate welche Testdatei ausfuehrt.

## 15. Nicht-Empfehlungen

Diese Aktionen sind nach aktuellem Hinweisstand nicht sinnvoll:

- `repoLaunchReadinessFromFiles` mit `repoLaunchReadiness` zusammenwerfen.
- Streaming erneut als offenes Hauptfeature behandeln.
- Memory-Dateien nur anhand aehnlicher Namen pauschal zusammenlegen.
- `BuilderContainer.tsx` komplett ersetzen.
- UI-Dashboard bauen, um Runtime-Komplexitaet sichtbar zu machen.

## 16. Abschlussbewertung

Das Repo zeigt hohe Ambition und bereits viel Runtime-Disziplin. Die groessten Risiken liegen nicht darin, dass alles Fassade waere, sondern darin, dass die Integration zu gross und zu schwer sicher patchbar geworden ist.

Der naechste Produktgewinn entsteht nicht durch mehr sichtbare Oberflaeche, sondern durch:

1. sichere Patch-Runtime,
2. strengere Worker-Auth,
3. kleinere Container-Grenzen,
4. klare Memory-Begriffe,
5. nachvollziehbare Test-Gate-Wahrheit.

Dieses Audit sollte als Startpunkt fuer kleine, sichere PRs verwendet werden, nicht als Auftrag fuer einen grossen Umbau.
