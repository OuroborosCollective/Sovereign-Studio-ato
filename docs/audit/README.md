# Audit Index

Dieses Verzeichnis enthält Audits, die nach **Scope** benannt sind, nicht nur
nach Datum. Vor neuen Audits bitte diesen Index aktualisieren.

## Vorhandene Audits

| Datei | Datum | Scope |
|-------|-------|-------|
| [2026-07-02-repo-structure-runtime-hinweis-audit.md](2026-07-02-repo-structure-runtime-hinweis-audit.md) | 2026-07-02 | Repo-Struktur, Runtime-Architektur, Worker-Sicherheit, Test-Gates |
| [runtime-truth-audit.md](runtime-truth-audit.md) | 2026-06-26 | Runtime-Verhalten echt oder Fassade (Issue #369) |

## Scope-Konventionen

- **Struktur-Audit**: Dateiorganisation, Modul-Grenzen, Namenskonventionen
- **Runtime-Truth-Audit**: Ist ein Feature echt implementiert oder nur UI-Fassade?
- **Sicherheits-Audit**: Auth, Secrets, offene Endpunkte, Klartextdaten in Logs
- **Test-Gate-Audit**: Welche Tests laufen in welchem CI-Gate?

## Hinweise

- Audits ersetzen sich nicht gegenseitig — jeder hat seinen eigenen Scope.
- Findings mit P0/P1 sollten als Issues oder PRs getrackt werden.
- Audit-Ergebnisse die als erledigt gelten: im Audit-Dokument markieren,
  nicht löschen.
