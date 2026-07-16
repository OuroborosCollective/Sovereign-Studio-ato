# LLM Language / Runtime Action Boundary

## Verbindlicher Architekturgrundsatz

**Das Online-LLM versteht und formuliert Sprache. Die Runtime handelt.**

Ein online erreichbares LLM ist die primäre Instanz für:

- natürliche Sprache und Mehrdeutigkeit,
- Gesprächskontext und implizite Verweise,
- Fragen, Erklärungen und Rückfragen,
- die semantische Einordnung eines User-Wunsches,
- eine strukturierte Intent-Evidence für mögliche Aktionen.

Die Runtime und ihre Tools sind ausschließlich zuständig für:

- Berechtigungen und Owner-Grenzen,
- Repository-, Branch-, Workspace- und Pfadgrenzen,
- Tool- und Routenverträge,
- Sicherheits- und Secret-Gates,
- Zustandsübergänge,
- Ausführung und Wiederaufnahme,
- Runtime-, Patch-, Test-, Commit- und Draft-PR-Evidence,
- die Entscheidung, ob ein Erfolg wirklich belegt ist.

## Harte Grenze

Das LLM darf eine gewünschte Aktion **beschreiben oder als Intent melden**. Es darf die Aktion nicht selbst als ausgeführt oder erfolgreich behaupten.

Die Runtime darf dem LLM **belegte Fakten** bereitstellen, zum Beispiel:

```text
repo_ready=true
branch=main
github_write_ready=false
agent_state=running
changed_files=2
draft_pr_ready=false
```

Die Runtime darf daraus jedoch keine eigene Gesprächsantwort oder semantische Interpretation erzeugen. Sie zeigt eigene Meldungen ausschließlich als `system`-/Evidence-Zustand, niemals als `assistant`-Aussage.

## Zulässiger Ablauf

```text
User-Text
  -> Online-LLM versteht Sprache und liefert strukturiertes Intent-Schema
  -> Runtime validiert Intent-Schema
  -> Runtime prüft Capability, Berechtigung, Scope und Safety
  -> Tool führt die erlaubte Aktion aus
  -> Runtime speichert echte Evidence
  -> LLM formuliert auf Basis der belegten Fakten die Gesprächsantwort
```

## Offline-Fallback

Lokale Wort-/Regelklassifizierung ist ausschließlich zulässig, wenn die Online-Sprachroute nachweislich nicht verfügbar ist oder der User eine explizite lokale UI-/Slash-Aktion ausgelöst hat.

Jede solche Entscheidung muss:

1. als `offline_fallback` oder `explicit_runtime_action` markiert sein,
2. im Action Stream sichtbar sein,
3. keine LLM-Antwort vortäuschen,
4. keine Erfolgsbehauptung erzeugen,
5. weiterhin alle Runtime-Gates durchlaufen.

## Sechs blockierte Fehlerfamilien

### 1. Capability Router interpretiert Rohtext

**Verboten:** `decideSovereignCapabilityRoute()` erhält User-Text und sucht selbst Wörter.

**Erlaubt:** Der Router erhält ausschließlich `SovereignLanguageIntentEvidence`.

### 2. Internal Operator deutet Sprache erneut

**Verboten:** Dokument-/Code-Wortlisten im Internal Operator.

**Erlaubt:** Der Operator erhält `intent` und `taskComplexity` aus bereits validierter Evidence.

### 3. Executor klassifiziert beim Start erneut

**Verboten:** `interpretedIntent ?? classify(userText)`.

**Erlaubt:** Ein Executor-Start ist nur mit explizit übergebener Intent-Evidence möglich.

### 4. Bestätigter Draft fällt auf Rohtext zurück

**Verboten:** Bei fehlendem Mapping den ursprünglichen User-Text erneut klassifizieren.

**Erlaubt:** Fehlende oder ungültige Intent-Evidence führt fail-closed zu `unknown`/Blocker.

### 5. Composertext beeinflusst Runtime vor Submit

**Verboten:** Unfertigen Eingabetext semantisch klassifizieren und damit Executor-Zustände ändern.

**Erlaubt:** Erst Submit oder eine explizite Tool-Schaltfläche erzeugt eine Aktion.

### 6. Runtime spricht als LLM

**Verboten:** Route-, Gate-, Retry-, GitHub-, Patch- oder Executor-Meldungen mit `role: assistant`.

**Erlaubt:** Runtime-Meldungen verwenden `role: system` beziehungsweise den Evidence-/Action-Stream. Nur echte Provider-/LLM-Ausgabe verwendet `role: assistant`.

## Erfolg und Lernen

Eine Modellantwort ist niemals Erfolgsevidence. Lernen aus Online-Beobachtungen beginnt als `pending_evidence`. Eine Promotion ist erst nach belegtem Runtime-Ergebnis zulässig, beispielsweise:

- validierter Patch/Diff,
- erfolgreiche Tests,
- bestätigter Commit,
- echte Draft-PR-URL,
- akzeptierte Runtime-Evidence.

Kein LLM-Text, kein UI-Text und keine lokale Klassifizierung darf diese Evidence ersetzen.
