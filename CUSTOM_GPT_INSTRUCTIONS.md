# Sovereign Git Patch - Custom GPT Setup

## Schnellstart

### 1. Erstelle Custom GPT

1. Öffne ChatGPT → Create → Create a GPT
2. Name: `Sovereign Code Patcher`
3. Description: `Präziser Code-Patcher für GitHub. Erstelle SEARCH/REPLACE Blöcke und publiziere als Draft PR.`

### 2. Instructions (kopieren)

```
DU BIST Sovereign Code Patcher - ein präziser GitHub-Code-Patcher.

REGELN:
1. IMMER exakte SEARCH/REPLACE Blöcke erstellen
2. SEARCH muss exakt dem Code entsprechen der ersetzt wird
3. Bei 0 oder >1 Treffern: Fehler erklären
4. IMMER Draft PR erstellen

WORKFLOW:
1. User beschreibt gewünschte Änderung
2. Du analysierst das Repository und den Code
3. Du baust exakte SEARCH/REPLACE Blöcke
4. Du rufst sovereign_patch Action auf
5. Bei Erfolg: Draft PR Link zeigen
6. Bei Fehler: Problem erklären und Korrektur vorschlagen

BEISPIEL DIALOG:
User: "Mach den async test in BuilderContainer.test.tsx"

Du:
1. Lade Datei von GitHub
2. Finde den Test
3. Erstelle Block:
   search: "it('submits', () => {"
   replace: "it('submits', async () => {"
4. Rufe sovereign_patch auf
5. Zeige PR Link
```

### 3. Actions - OpenAPI Schema

Kopiere dies in "Create new action":

```json
{
  "openapi": "3.1.0",
  "info": {
    "title": "Sovereign Git Patch",
    "description": "Apply SEARCH/REPLACE blocks to GitHub files and create Draft PR",
    "version": "1.0"
  },
  "servers": [
    {
      "url": "https://sovereign-studio-worker.projectouroboroscollective.workers.dev"
    }
  ],
  "paths": {
    "/git/patch": {
      "post": {
        "operationId": "applyPatch",
        "summary": "Apply SEARCH/REPLACE blocks and create Draft PR",
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "properties": {
                  "owner": {
                    "type": "string",
                    "description": "GitHub repository owner"
                  },
                  "repo": {
                    "type": "string",
                    "description": "GitHub repository name"
                  },
                  "path": {
                    "type": "string",
                    "description": "File path in repo, e.g. src/App.tsx"
                  },
                  "message": {
                    "type": "string",
                    "description": "Commit message"
                  },
                  "blocks": {
                    "type": "array",
                    "description": "SEARCH/REPLACE blocks",
                    "items": {
                      "type": "object",
                      "properties": {
                        "search": {
                          "type": "string",
                          "description": "EXACT code to replace (must appear exactly once)"
                        },
                        "replace": {
                          "type": "string",
                          "description": "New code to insert"
                        }
                      },
                      "required": ["search", "replace"]
                    }
                  }
                },
                "required": ["owner", "repo", "path", "message", "blocks"]
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Success - Draft PR created",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "ok": {"type": "boolean"},
                    "branch": {"type": "string"},
                    "commit": {"type": "string"},
                    "pr": {"type": "integer"},
                    "prUrl": {"type": "string"}
                  }
                }
              }
            }
          },
          "422": {
            "description": "Patch failed - search string not found or ambiguous"
          }
        }
      }
    }
  }
}
```

### 4. Privacy Policy

Trage ein: `https://sovereign-studio.dev/privacy` (oder eigene URL)

### 5. Testen

Im GPT Builder → "Create" → Test Panel:

```
Frage: Mach den ersten Test in src/App.tsx async
```

---

## Verfügbare Repositories

| Owner | Repo | Beschreibung |
|-------|------|-------------|
| OuroborosCollective | Sovereign-Studio-ato | Haupt-Repository |
| (alle) | (alle) | Jedes öffentliche Repository |

---

## Troubleshooting

### "search string not found"
- Der Code existiert nicht in dieser Form
- Prüfe Leerzeichen, Tabs, Zeilenumbrüche
- Lade die Datei neu von GitHub

### "found X times (expected exactly 1)"
- Der SEARCH-String kommt mehrfach vor
- Mache den String eindeutiger (mehr Kontext)

### "Token nicht gesetzt"
- Das GITHUB_TOKEN Secret ist auf dem Worker gesetzt
- Das Tool braucht keinen extra Token
