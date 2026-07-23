# Übergabeprotokoll: technisch erzwungenes Sovereign-MCP-Betriebsprofil

## 1. Ziel

Dieses Protokoll übergibt den dauerhaften Betriebsvertrag für die optimale Nutzung des privaten Sovereign ChatGPT MCP-Servers. Die Regeln dürfen nicht nur aus Chat-Erinnerung oder einer Modellinstruktion stammen. Sie werden deshalb gleichzeitig als versioniertes Repository-Profil, Skill, Runtime-Statuswerkzeug, Missions-Preflight, automatischer Mutations-Wrapper, Testvertrag, Image-Inhalt und VPS-Installationsgate geführt.

Das Ziel gilt erst als vollständig erreicht, wenn dieselbe gemergte Revision als unveränderliches MCP-Image auf dem VPS läuft und der Live-Status `OPERATING_PROFILE_ENFORCED` meldet.

## 2. Autoritative Pfade

| Zweck | Pfad | Autorität |
|---|---|---|
| Maschinenlesbarer Betriebsvertrag | `tools/sovereign-chatgpt-mcp/config/sovereign-mcp-operating-profile.json` | Primäre fachliche Policy |
| Runtime-Enforcement | `tools/sovereign-chatgpt-mcp/operating_profile.py` | Technische Durchsetzung |
| Wiederverwendbarer Skill | `tools/sovereign-chatgpt-mcp/skills/sovereign-mcp-optimal-operation/SKILL.md` | Menschlich und agentisch lesbarer Ablauf |
| MCP-Startverdrahtung | `tools/sovereign-chatgpt-mcp/launcher.py` | Registrierung, Output-Verträge, Wrapper-Installation |
| Modell-/Serverinstruktion | `tools/sovereign-chatgpt-mcp/server.py` | Sichtbarer Arbeitsauftrag an den Agenten |
| Containervertrag | `tools/sovereign-chatgpt-mcp/Dockerfile` | Aufnahme von Profil, Skill und Runtime-Modul ins Image |
| VPS-Live-Gates | `tools/sovereign-chatgpt-mcp/deploy/install-on-vps.sh` | Fail-closed Installations- und Runtime-Prüfung |
| Regressionstests | `tools/sovereign-chatgpt-mcp/tests/test_operating_profile.py` | Nachweis von Profil, Preflight und Blockierung |
| Governance-Inventar | `tools/sovereign-chatgpt-mcp/operational_governance_tools.py` | Auffindbarkeit im Skill-/Tool-Inventar |
| Dieses Übergabeprotokoll | `docs/SOVEREIGN_MCP_OPERATING_PROFILE_HANDOFF.md` | Betriebs- und Wartungsanweisung |

Chat-Memory darf auf diese Pfade und Regeln hinweisen, ist aber niemals technische Autorität.

## 3. Verhaltensanweisung für jede zukünftige Arbeit

### 3.1 Vor mehrstufiger oder mutierender Arbeit

1. Exakte Repository-, Workspace-, PR-, CI- und installierte MCP-Revision auflösen.
2. `sovereign_operating_profile_status` lesen.
3. Bei einem anderen Status als `OPERATING_PROFILE_ENFORCED` stoppen. Keine direkte Toolwahl als Umgehung verwenden.
4. Die Mission in strukturierte Capabilities, erlaubte Effect-Klassen und erforderliche Evidence übersetzen.
5. `sovereign_mission_preflight` ausführen.
6. Nur bei `MISSION_PREFLIGHT_VALID` mit dem ersten separat geregelten Toolaufruf fortfahren.
7. Nach jedem Schritt den tatsächlichen Effekt aus der autoritativen Quelle zurücklesen.
8. Bei Revisionsdrift, neuer Fehlerfamilie, geänderter Tool-Schema-Version, fehlender Evidence oder fehlendem Owner-Gate stoppen und neu planen.

### 3.2 Während der Ausführung

- Nur den kleinsten geeigneten registrierten Werkzeugsatz verwenden.
- Toolnamen, Parameter und Output-Schemas aus der Live-Registry beziehen, nicht aus Erinnerung oder Dokumentation ableiten.
- Eine Toolchain ist ein nicht-ausführender Plan. Jeder echte Toolaufruf bleibt eine getrennte, kontrollierte Aktion.
- Keine automatische Rekursion, kein unbeschränktes Retry und kein Wechsel der Fehlerfamilie ohne neue Evidence.
- Keine Secrets im Chat, in MCP-Argumenten, Logs, Repository oder Datenbank speichern.
- Owner-geschützte Werte ausschließlich über die authentifizierte Owner-Oberfläche erfassen.
- FreeLLM und Paid OpenRouter/LiteLLM als getrennte Routen behandeln. Kein stiller Fallback in irgendeine Richtung.
- Keine UI-Anzeige, kein Mock, Stub, Facade-Ergebnis oder ungeprüfter Funktionsreturn als Live-Erfolg melden.

### 3.3 Nach der Ausführung

- Repository-Erfolg: exakte Diff-, Test- und PR-Head-Evidence.
- CI-Erfolg: erforderliche Checks auf exakt demselben Head-SHA grün.
- Release-Erfolg: gemergte Revision, unveränderlicher Image-Digest und passendes Revision-Label.
- Deployment-Erfolg: Container-Readback zeigt exakt Revision und Digest.
- MCP-Erfolg: Container gesund, MCP initialize/tools-list erfolgreich, Broker-RPC bereit.
- Fachlicher Erfolg: ursprünglicher Fehler oder gewünschter Ablauf durch einen echten Runtime-Canary belegt.
- Learning erst danach erzeugen; geheimnisfrei, begrenzt, revisionsgebunden und mit der nachgewiesenen Fehlerfamilie sowie Lösung verknüpft.

## 4. Technische Durchsetzung

### 4.1 Persistentes Profil

Das JSON-Profil definiert:

- fail-closed Enforcement;
- LLM-/Runtime-Verantwortungsgrenze;
- verpflichtenden Missions-Preflight;
- erforderliche Governance-Tools;
- Evidence- und Completion-Regeln;
- Secret-Policy;
- Free-/Paid-Routentrennung;
- verbotene generische Ausführungsflächen;
- autoritative Persistenzpfade.

Der SHA-256 des tatsächlich geladenen Profilinhalts wird bei jedem Status- und Preflight-Aufruf ausgegeben. Der Profil-Digest ist an die unveränderliche Repository-/Image-Revision zu binden.

### 4.2 Statuswerkzeug

`sovereign_operating_profile_status` prüft live:

- Profil kann geladen und strukturell validiert werden;
- Enforcement-Modus ist weiterhin `fail-closed`;
- automatisches Mutationsgate ist aktiviert;
- alle verpflichtenden Governance-Tools sind registriert;
- keine exakt verbotenen generischen Toolnamen sind registriert;
- alle MCP-Tools besitzen ein explizites Output-Schema;
- jeder mutierende Toolvertrag wurde vom Betriebsprofil-Wrapper erfasst;
- Registry-Snapshot und Profil-Digest sind verfügbar.

Erfolg: `OPERATING_PROFILE_ENFORCED`.

Blockiert: `OPERATING_PROFILE_BLOCKED` mit einer oder mehreren P0-Familien.

### 4.3 Missions-Preflight

`sovereign_mission_preflight`:

1. verlangt zuerst ein grünes Betriebsprofil;
2. rankt den kleinsten geeigneten Werkzeugsatz aus der Live-Registry;
3. kompiliert eine nicht-ausführende Toolchain;
4. bindet sie an den aktuellen Registry-Snapshot;
5. validiert Graph, Toolverträge, Effekte, Output-Schemas und Hashes;
6. gibt keine automatische Ausführungsfreigabe und führt kein vorgeschlagenes Tool aus.

Erfolg: `MISSION_PREFLIGHT_VALID`.

Blockiert: `MISSION_PREFLIGHT_BLOCKED` oder `MISSION_PREFLIGHT_BLOCKED_BY_OPERATING_PROFILE`.

### 4.4 Automatisches Mutationsgate

Nach Registrierung aller Tools und Installation aller Output-Verträge wird jede Funktion mit `readOnlyHint=false` automatisch umschlossen.

Vor Aufruf der ursprünglichen Funktion wird geprüft:

- Betriebsprofil ist grün;
- Zieltool existiert weiterhin in der Live-Registry;
- aktueller Toolvertrag und Effekt stimmen;
- ein Ein-Knoten-Vertragsgraph validiert gegen denselben Registry-Snapshot;
- das Ziel besitzt ein Output-Schema;
- `owner_approved` ist wahr, sofern dieser Parameter im External-Write-Vertrag existiert;
- vorhandene Revisionsfelder enthalten einen vollständigen 40-stelligen Git-SHA;
- erforderliche Bestätigungsfelder sind nicht leer;
- Argumente enthalten keine erkannten Secret-Formen wie OpenAI-/GitHub-Token, Bearer-Token, Private Keys oder JWTs.

Bei einem Fehler wird vor der Originalfunktion `OperatingProfileBlocked` ausgelöst. Damit wird kein Brokerjob, keine Repository-Mutation, kein Deploy, keine Datenbankänderung und keine Provideraktivierung gestartet.

## 5. Fehlerfamilien und Reaktion

| Fehlerfamilie | Bedeutung | Pflichtreaktion |
|---|---|---|
| `OPERATING_PROFILE_REQUIRED_TOOL_MISSING` | Governance-Werkzeug fehlt | Registry-/Registrierungsfehler reparieren, neu bauen, nicht mutieren |
| `OPERATING_PROFILE_FORBIDDEN_TOOL_REGISTERED` | Verbotene generische Ausführungsfläche vorhanden | Tool entfernen oder durch eng begrenzten Vertrag ersetzen |
| `OPERATING_PROFILE_OUTPUT_SCHEMA_MISSING` | Mindestens ein Tool ohne explizites Schema | Output-Vertrag ergänzen, tools/list erneut testen |
| `OPERATING_PROFILE_MUTATION_GATE_NOT_INSTALLED` | Wrapper nicht aktiviert | Launcher-Reihenfolge reparieren; Release blockieren |
| `OPERATING_PROFILE_MUTABLE_TOOL_UNENFORCED` | Neues/verspätet registriertes Mutationstool umgeht Wrapper | Registrierung vor Wrapper-Installation verschieben oder erneut installieren |
| `OPERATING_PROFILE_OWNER_APPROVAL_REQUIRED` | External-Write mit vorhandenem Owner-Parameter ohne Freigabe | Nur mit gültiger ausdrücklicher Owner-Freigabe erneut aufrufen |
| `OPERATING_PROFILE_EXACT_REVISION_MISSING` | Pflichtrevision fehlt | Exakte SHA aus autoritativer Quelle auflösen |
| `OPERATING_PROFILE_EXACT_REVISION_INVALID` | Revisionswert ist kein voller SHA | Nicht raten; Revision neu lesen |
| `OPERATING_PROFILE_CONFIRMATION_MISSING` | Zustandsgebundene Bestätigung fehlt | Plan/Preview erneut lesen und exakten Hash verwenden |
| `OPERATING_PROFILE_SECRET_SHAPED_ARGUMENT_BLOCKED` | Mögliches Secret in Toolargumenten | Wert entfernen und Owner-Input-Pfad verwenden |
| `TOOLCHAIN_REGISTRY_SNAPSHOT_DRIFT` | Registry änderte sich zwischen Planung und Prüfung | Toolchain verwerfen und frisch kompilieren |
| `TOOLCHAIN_TOOL_CONTRACT_DRIFT` | Einzelvertrag änderte sich | Neue Schema-/Vertragsprüfung durchführen |

Dieselben generischen Reparaturen dürfen nicht wiederholt werden, solange die vorherige Fehlerfamilie nicht durch ihre Post-Checks als behoben belegt wurde.

## 6. Wann etwas als erledigt gilt

### 6.1 Repository-Implementierung erledigt

Nur wenn:

- Profil, Skill, Runtime-Modul, Launcher-, Docker-, Installer- und Teständerungen committed sind;
- `git diff --check` grün ist;
- Python-Compile grün ist;
- gezielte Tests für Profil und Governance grün sind;
- alle vorhandenen MCP-Tests grün sind;
- Draft-PR auf einem exakten Head-SHA existiert.

Das ist noch kein Live-Erfolg.

### 6.2 PR/CI erledigt

Nur wenn:

- der PR-Head unverändert bestätigt ist;
- alle erforderlichen GitHub-Checks auf exakt diesem Head grün sind;
- keine relevante Review-Anforderung offen ist;
- Mergefähigkeit belegt ist.

Das ist noch kein Live-Erfolg.

### 6.3 Merge erledigt

Nur wenn:

- exakt der bestätigte PR-Head gemergt wurde;
- die Main-/Merge-Revision neu aufgelöst wurde;
- kein Base-Advance oder abweichender Merge-Commit unbemerkt blieb.

Das ist noch kein Live-Erfolg.

### 6.4 MCP-Release live erledigt

Nur wenn dieselbe gemergte Revision:

- als unveränderliches GHCR-Image mit passendem Revision-Label vorliegt;
- über den Self-Update-/Installerpfad installiert wurde;
- im laufenden Container denselben Image-Digest und dieselbe Revision zeigt;
- `launcher.OUTPUT_CONTRACT_INSTALLATION.ok == true` meldet;
- `launcher.OPERATING_PROFILE_ENFORCEMENT.ok == true` meldet;
- `sovereign_operating_profile_status().status == OPERATING_PROFILE_ENFORCED` meldet;
- alle mutierenden Tools als umschlossen ausweist;
- MCP-Protokoll-, Broker- und Container-Canaries besteht.

Erst dann darf „technisch live und persistent“ behauptet werden.

### 6.5 Gesamtauftrag erledigt

Der Auftrag ist abgeschlossen, wenn zusätzlich ein echter negativer Canary belegt, dass ein mutierendes Tool mit fehlender Owner-Freigabe oder ungültiger Revision vor Broker-/Hostausführung blockiert wird, und ein read-only Missions-Preflight erfolgreich gegen die Live-Registry kompiliert und validiert.

## 7. Änderungs- und Wartungsregeln

- Jede Profiländerung erhöht `profileVersion` nach SemVer.
- Jede neue mutierende Toolregistrierung muss vor `install_enforcement` stattfinden.
- Neue Mutationstools benötigen ein explizites Output-Schema und korrekte `ToolAnnotations`.
- Neue Revisions-/Bestätigungsparameter sind in die Argumentvalidierung aufzunehmen.
- Neue Secret-Transportwege sind verboten; nur der Owner-Input-Pfad darf geschützt Werte annehmen.
- Registry- oder Toolvertragänderungen erfordern Aktualisierung der Tests und einen frischen MCP-Live-Canary.
- Das Profil darf niemals „fail-open“ werden, um einen Release durchzubekommen.
- Das Betriebsprofil ersetzt keine fachlichen Auth-, Broker-, Datenbank-, CI- oder Deployment-Gates; es ergänzt und erzwingt deren korrekte Nutzung.

## 8. Rollback

Bei fehlgeschlagenem Rollout:

1. Keine Mutation auf der neuen Revision fortführen.
2. Exakten letzten grünen MCP-Image-Digest aus Runtime-Evidence ermitteln.
3. Kontrollierten MCP-Self-Update-/Rollbackpfad verwenden.
4. Container-, MCP-Protokoll- und Broker-Readback erneut prüfen.
5. Betriebsprofilstatus der zurückgerollten Revision dokumentieren.
6. Fehlerfamilie und fehlgeschlagenen Revisions-/Digest-Tupel im PR oder Incident festhalten.
7. Kein Learning als erfolgreiche Lösung speichern.

## 9. Live-Evidence-Abschnitt

Dieser Abschnitt wird erst nach Merge und echtem VPS-Rollout mit den autoritativen Werten aktualisiert:

- PR-Nummer und finaler PR-Head
- gemergte Main-Revision
- MCP-Image-Referenz und Digest
- installierte Revision
- Registry-Snapshot-SHA-256
- Profil-SHA-256
- Anzahl registrierter und umschlossener mutierender Tools
- CI-Checkliste
- MCP initialize/tools-list Ergebnis
- Broker- und Containerstatus
- positiver Missions-Preflight-Canary
- negativer Mutationsblock-Canary

Bis diese Werte eingetragen und durch Runtime-Evidence belegt sind, lautet der Status: **Repository-Implementierung in Arbeit, noch nicht live abgeschlossen.**
