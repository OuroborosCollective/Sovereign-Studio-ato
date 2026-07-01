# Sovereign Studio - LLM Tools

## 🎯 Verfügbare Tools

### 1. Custom GPT (Automatisch)
**Für:** ChatGPT App (Android/iOS)

→ Siehe `CUSTOM_GPT_INSTRUCTIONS.md`

### 2. Python Script (Code Interpreter)
**Für:** ChatGPT/Claude mit Code Interpreter

→ Siehe `scripts/sovereign_git_patch.py`

### 3. Cloudflare Worker API
**Für:** Direkte API Calls, eigene Apps

```
POST https://sovereign-studio-worker.projectouroboroscollective.workers.dev/git/patch
```

---

## Schnell-Referenz

### Custom GPT Prompt

```
DU BIST Sovereign Code Patcher.

REGELN:
1. IMMER SEARCH/REPLACE Blöcke
2. SEARCH = exakter Code zum Ersetzen
3. Bei 0 oder >1 Treffern = Fehler
4. IMMER Draft PR erstellen

WORKFLOW:
1. User: "Mach X in Datei Y"
2. Du: Lade Code, baue SEARCH/REPLACE
3. Du: Rufe sovereign_patch auf
4. Du: Zeige PR Link
```

### Python Usage

```python
from sovereign_git_patch import sovereign_patch

# Einzelner Block
result = sovereign_patch(
    path="src/App.tsx",
    search="alter code",
    replace="neuer code",
    message="fix: beschreibung"
)

# Mehrere Blöcke
from sovereign_git_patch import sovereign_patch_multi
result = sovereign_patch_multi(
    path="src/test.tsx",
    blocks=[
        {"search": "block1", "replace": "neu1"},
        {"search": "block2", "replace": "neu2"},
    ],
    message="fix: mehrere änderungen"
)

print(result)
# ✅ → {"ok": True, "prUrl": "https://github.com/..."}
# ❌ → {"ok": False, "error": "string not found"}
```

### Direkter API Call

```bash
curl -X POST \
  https://sovereign-studio-worker.projectouroboroscollective.workers.dev/git/patch \
  -H "Content-Type: application/json" \
  -d '{
    "owner": "OuroborosCollective",
    "repo": "Sovereign-Studio-ato",
    "path": "src/App.tsx",
    "message": "fix: beschreibung",
    "blocks": [
      {"search": "alter code", "replace": "neuer code"}
    ]
  }'
```

---

## Dateien

| Datei | Beschreibung |
|-------|-------------|
| `CUSTOM_GPT_INSTRUCTIONS.md` | Komplette Anleitung für Custom GPT |
| `scripts/sovereign_git_patch.py` | Python Tool für Code Interpreter |
| `cloudflare-worker/` | Worker Source Code |
| `AGENTS.md` | Agent Regeln (Sovereign Studio intern) |

---

## Security

- ✅ GITHUB_TOKEN als Cloudflare Secret gesetzt
- ✅ Keine Token in Environment Variables
- ✅ Keine Token in Code/Config
- ✅ Nur Draft PRs (kein direkter Merge)
