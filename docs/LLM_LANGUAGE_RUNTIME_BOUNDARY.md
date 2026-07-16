# LLM Language / Runtime Action Boundary

## Verbindlicher Architekturgrundsatz

**Das Online-LLM versteht und formuliert Sprache. Die Runtime handelt.**

Ein online erreichbares LLM ist die primäre Instanz für natürliche Sprache, Mehrdeutigkeit, Gesprächskontext, Rückfragen und strukturierte Intent-Evidence.

Runtime und Tools sind ausschließlich zuständig für:

- Berechtigungen und Owner-Grenzen,
- Repository-, Branch-, Workspace- und Pfadgrenzen,
- Tool-, Endpoint- und Routenverträge,
- Safety-, Secret- und Circuit-Boundaries,
- Zustandsübergänge und Wiederaufnahme,
- Ausführung,
- Patch-, Test-, Commit-, Workflow- und Draft-PR-Evidence,
- die Entscheidung, ob Erfolg tatsächlich belegt ist.

## Harte Grenze

Das LLM darf eine gewünschte Aktion verstehen, beschreiben und als strukturierten Intent melden. Es darf die Aktion nicht als ausgeführt oder erfolgreich behaupten.

Die Runtime darf dem LLM belegte Fakten bereitstellen, beispielsweise:

```text
repo_ready=true
github_write_ready=false
agent_state=running
changed_files=2
draft_pr_ready=false
```

Diese Fakten sind keine Gesprächsantwort. Die Runtime zeigt eigene Meldungen ausschließlich als `role: system` oder im Evidence-/Action-Stream. Nur echte Provider-/LLM-Ausgabe verwendet `role: assistant`.

## Zulässiger Online-Ablauf

```text
User-Text
  -> LiteLLM versteht Sprache und liefert ein validiertes Intent-Schema
  -> Runtime prüft Capability, Berechtigung, Scope, Circuit und Safety
  -> Tool führt ausschließlich die erlaubte Aktion aus
  -> Runtime speichert echte Evidence
  -> LLM formuliert auf Basis belegter Fakten die Gesprächsantwort
```

## Offline-Fallback

Lokale Wort- oder Regelklassifizierung ist ausschließlich zulässig, wenn die Online-Sprachroute nachweislich nicht verfügbar ist oder der User eine explizite lokale UI-/Slash-Aktion ausgelöst hat.

Jede solche Entscheidung muss:

1. als `offline_fallback` oder `explicit_runtime_action` markiert sein,
2. im Action Stream sichtbar sein,
3. keine LLM-Antwort vortäuschen,
4. keine Erfolgsbehauptung erzeugen,
5. weiterhin alle Runtime-Gates durchlaufen.

## Sechs blockierte Fehlerfamilien

1. **Capability Router interpretiert Rohtext.** Der Router erhält nur `SovereignLanguageIntentEvidence`.
2. **Internal Operator deutet Sprache erneut.** Er erhält nur `intent` und `taskComplexity`.
3. **Executor klassifiziert beim Start erneut.** Ein Start benötigt explizit übergebene Intent-Evidence.
4. **Bestätigter Draft fällt auf Rohtext zurück.** Fehlende Evidence führt fail-closed zu `unknown`.
5. **Composertext beeinflusst Runtime vor Submit.** Erst Submit oder eine explizite Tool-Schaltfläche erzeugt eine Aktion.
6. **Runtime spricht als LLM.** Route-, Gate-, Retry-, GitHub-, Patch- und Executor-Meldungen sind System-/Evidence-Zustände.

## Predictive, Circuit und Lernen

Predictive- und Runtime-Intelligence-Regeln dürfen Risiken, Health, Wahrscheinlichkeiten und Offline-Diagnostik liefern. Sie dürfen keinen Online-Intent ersetzen und keine Aktion autorisieren.

Ein Half-open Circuit Breaker erlaubt exakt einen Probeaufruf. Parallele Probes werden vor Tool-/Provider-Ausführung abgewiesen.

Eine Modellantwort ist niemals Erfolgsevidence. Neue Beobachtungen beginnen als `pending_evidence`. Eine Promotion ist erst nach kausal zugeordnetem Runtime-Ergebnis zulässig, beispielsweise validierter Patch/Diff, erfolgreiche Tests, bestätigter Commit oder echte Draft-PR-URL. Blocker-Lernen benötigt einen terminalen Runtime-Status plus ein reales Warn-/Fehler-Event.
