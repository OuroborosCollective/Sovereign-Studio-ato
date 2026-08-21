# Sovereign GitHub Patch MCP

Ein MCP-Server für ChatGPT/GPT-5.5, der GitHub-ähnliche Lese-Tools mit kontrollierten Schreibaktionen kombiniert.

## Was dieses Projekt macht

Dieses Projekt erstellt **einen eigenen ChatGPT MCP Connector**. Es erweitert **nicht** den offiziellen GitHub-Connector direkt, denn dessen interne Tools sind nicht kopierbar oder modifizierbar.

Enthaltene MCP-Tools:

| Tool | Zweck |
|---|---|
| `github_get_repository` | Repository-Metadaten lesen |
| `github_list_branches` | Branches lesen |
| `github_list_directory` | Ordnerinhalt lesen |
| `github_read_file` | UTF-8-Datei lesen |
| `github_search_code` | Code in einem Repository suchen |
| `github_full_file_replace_pr` | Bestehende Datei vollständig ersetzen und Draft-PR erstellen |
| `github_preview_search_replace_patch` | SEARCH/REPLACE-Blöcke trocken testen |
| `github_apply_search_replace_pr` | SEARCH/REPLACE anwenden, aber GitHub-seitig als Full-file replace in Draft-PR schreiben |
| `apply_patch` | Exakt dein OpenAPI-`applyPatch`: POST an den Sovereign Worker `/git/patch` |

## Warum zwei Patch-Tools?

- `apply_patch` nutzt deinen vorhandenen Worker:
  `https://sovereign-studio-worker.projectouroboroscollective.workers.dev/git/patch`
- `github_apply_search_replace_pr` macht dasselbe Prinzip selbst im MCP-Server:
  Datei lesen → SEARCH/REPLACE anwenden → Datei vollständig per GitHub API ersetzen → Draft PR erstellen.

Damit bleibt die GitHub-Schreibregel sauber: **keine direkten Inline-Edits auf `main`, sondern ein neuer Branch + Draft PR**.

## Setup lokal

```bash
uv sync
cp .env.example .env
# .env ausfüllen
uv run python server.py
```

Healthcheck:

```bash
curl http://localhost:8000/health
```

MCP Endpoint:

```text
http://localhost:8000/mcp
```

## Mit ChatGPT verbinden

Für ChatGPT muss der MCP-Endpoint öffentlich über HTTPS erreichbar sein:

```text
https://deine-domain.example/mcp
```

Danach in ChatGPT:

1. Settings → Apps & Connectors → Advanced settings → Developer mode aktivieren
2. Settings → Connectors / Apps → Create
3. Connector URL setzen:
   `https://deine-domain.example/mcp`
4. Neuen Chat öffnen
5. `+` → More → deinen Connector auswählen

Je nach ChatGPT-Oberfläche erscheint der Connector dann im Tool-/App-Menü. Die native `@GitHub`-Auswahl des offiziellen GitHub-Connectors wird dadurch nicht verändert.

## Sicherheit

Dieses MVP nutzt `GITHUB_TOKEN` serverseitig. Für persönliche Entwicklung ist das praktisch. Für Produktion oder mehrere Nutzer solltest du eine echte OAuth-/GitHub-App-Authentifizierung einbauen.

Wichtige Schutzmaßnahmen im Code:

- Schreib-Tools laufen nur, wenn `ALLOWED_REPOS` gesetzt ist.
- Schreib-Tools erstellen Draft PRs statt direkt auf den Basis-Branch zu schreiben.
- `github_full_file_replace_pr` ersetzt nur existierende Dateien.
- Große Dateien werden blockiert (`MAX_READ_BYTES`, `MAX_WRITE_BYTES`).
- SEARCH/REPLACE-Blöcke müssen eindeutig matchen.

## Erforderliche GitHub-Rechte

Für Fine-grained PATs pro Repository:

- Metadata: read
- Contents: read/write
- Pull requests: read/write

Für `github_search_code` kann GitHub je nach Repository/Plan weitere Search-Einschränkungen haben.

## Beispiel-Prompt in ChatGPT

```text
Nutze Sovereign GitHub Patch. Suche in owner/repo nach "oldFunction", lies die passende Datei,
ersetze nur den exakten Block durch die neue Implementierung und öffne dafür einen Draft PR.
```

## Responses API Beispiel

```bash
curl https://api.openai.com/v1/responses \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5.5",
    "tools": [
      {
        "type": "mcp",
        "server_label": "sovereign_github_patch",
        "server_url": "https://deine-domain.example/mcp"
      }
    ],
    "input": "Lies README.md aus owner/repo und fasse ihn zusammen."
  }'
```

## Dein ursprüngliches OpenAPI-Schema

Das Schema liegt zusätzlich in `docs/openapi-sovereign-git-patch.json`.
