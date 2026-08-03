# Repository Intelligence & Evidence Lane v1

## Zweck

Diese Lane überführt rechtlich unbedenkliche Architekturprinzipien aus der statischen Untersuchung von JetBrains-Plugins in eine eigenständige Sovereign-Studio-ATO-Implementierung. Es wird kein fremder Binärcode, kein proprietärer Prompt, kein eingebetteter Schlüssel und kein Anbieter-Telemetriepfad übernommen.

Die Lane erweitert die vorhandene Architektur-Sensorik. Sie ersetzt weder `deterministic_architecture_inventory`, `repository_architecture_snapshot`, `repository_architecture_drift_report` noch `backend_architecture_assess` und erzeugt keine konkurrierende Wahrheitsschicht.

## Werkzeuge

- `repository_intelligence_index_build`: revisionsgebundener lokaler SQLite-FTS5-Index mit deterministischer Token-Hash-Projektion. Der Index liegt ausschließlich im privaten Git-Verzeichnis des isolierten Workspaces.
- `repository_intelligence_search`: kombinierte lexikalische und lokale Projektion mit Git-Blob- und Inhalts-Hash-Readback.
- `repository_capability_scope_create`: SHA-256-adressierter, revisionsgebundener Capability-Scope für ein Subjekt, erlaubte Werkzeuge, Effekte und Pfadmuster.
- `repository_hash_bound_replace`: exakter Search/Replace-Patch nur bei passendem Repository-SHA, Blob-SHA, Scope und eindeutiger Trefferzahl.
- `repository_hash_bound_restore`: Wiederherstellung aus einem exakten Git-Ref und bestätigten Quell-/Ziel-Blob-SHAs.
- `managed_toolchain_verify`: allowlist-basierte Versions- und Executable-Digest-Prüfung ohne Installation.
- `repository_schema_diagnostics`: Duplicate-Key-, OpenAPI-, JSON-Schema-, Workflow- und Compose-Diagnostik.
- `deployment_evidence_session_capture`: Git-private Evidence-Session mit Revision, Toolchain, Schema- und optionalem Docker-Readback.
- `sovereign_resource_explorer`: begrenzter Graph Repository → CI → Compose → DB-Verträge → MCP → PatchMon → Container.
- `repository_context_drift_watch`: Readback gegen erwartete Revision, Branch, Docker-Kontext und immutable Image-Digest.

## Wahrheitsgrenzen

1. Der Index ist ein Side-Channel. Kanonische Wahrheit bleiben die getrackte Datei, der konkrete Git-Blob und die gebundene Repository-Revision.
2. Die deterministische lokale Projektion ist kein neuronales Modell und keine semantische Wahrheitsinstanz.
3. Ein Capability-Scope ersetzt nicht das fail-closed Operating Profile oder eine notwendige Owner-Freigabe.
4. Patch und Restore ändern nur den isolierten Working Tree. Commit, PR, Merge, Image, Deployment und Runtime-Erfolg müssen separat belegt werden.
5. Nicht verfügbare Runtime-, Docker-, Registry-, Datenbank- oder PatchMon-Evidence wird niemals als grün interpretiert.
6. Datenbanktabellen werden vom Ressourcen-Explorer nicht gelesen. Er meldet ausschließlich vorhandene Migrations- und Vertragsflächen.

## Ausschlüsse

- keine Priset- oder Google-Cloud-Code-Binärdateien;
- keine Reverse-Engineering-Artefakte oder proprietären Implementierungsdetails;
- keine eingebetteten API-Schlüssel;
- keine Telemetrie oder Geräteidentifikation;
- keine direkten Gemini-, OpenAI- oder Anthropic-Routen;
- kein LiteLLM;
- keine Installation unbekannter Toolchains;
- kein Mock-, Stub- oder Snapshot-Pfad als Runtime-Wahrheit.

## Persistenz und Datenschutz

Index, Scopes und Evidence-Sessions werden unter dem durch `git rev-parse --git-dir` aufgelösten privaten Git-Verzeichnis gespeichert. Sie werden nicht als Repositorydateien getrackt. Geheimnisartige Zeilen werden vor der Indexierung vollständig redigiert. Rückgaben enthalten keine erkannten Secret-Werte.

## Abnahme

- Modul und Tests kompilieren unter Python 3.12.
- Die fokussierte Suite prüft Registrierungsgrenzen, Secret-Redaktion, FTS-/Projektionssuche, hashgebundenes Patch/Restore, Schemafindings, Toolchain-/Ressourcen-Readback und Git-private Evidence.
- Der vollständige MCP-Testlauf, Output-Schema-Vertrag, Continuity-Gate und Release-Gate müssen am exakten PR-Head bestehen.
- Nach Merge muss ein immutable MCP-Image die exakte Main-Revision tragen.
- Ein Self-Update gilt erst nach Revision-, Digest-, Container-, Registry-, MCP-Protokoll- und PatchMon-Readback als abgeschlossen.
