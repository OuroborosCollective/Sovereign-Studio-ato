# Repository Agent Rules

This file is mandatory reading for every agent, model, Copilot session, automation, or human contributor working in this repository.

## Project identity

This repository is `NOCODESTUDIO Sovereign Tool / Sovereign-Studio-ato`.

Do not mix it with Areloria, WASD, MMORPG, ARE logic, or unrelated game paths unless the user explicitly asks for that.

## Prime directive

Build a runtime that produces truth.
Do not build a UI that invents truth.
The UI may only display verified runtime state.

## Causal runtime chain

Every workflow must follow this chain:

1. Action starts.
2. Action produces a result.
3. Result creates or updates state.
4. State allows, blocks, or routes the next action.
5. The next action must be logically derivable from that state.

Do not jump because a button was clicked, a text string is visible, or the UI looks ready.

## Approved truth sources

Use real runtime sources:

- `sequentialRuntime`
- `repoSnapshotStatus`
- `repoFiles`
- `scanRegistry`
- `workflowReport`
- `lastPackage`
- `latestGeneratedReview`
- `diffReport`
- `telemetry`
- `solutionPatternStore`
- `remoteMemoryIntake`
- `automationStatus`

Do not use DOM text, page text scraping, static percentages, or visual UI state as the source of truth.

## Progress rule

No hard percentage progress.
No fixed maximum step count.
Progress must be a step plan derived from the real runtime flow.

Correct pattern:

```text
currentStep / totalRuntimeSteps - current runtime action
```

The total must come from the planned runtime flow, not from a hardcoded UI list.

## Placeholder mission rule

Default or vague text must never enter `package-build` as-is.

Examples that must be normalized or blocked before package build:

- `README + Update History`
- `Mach weiter`
- `Fehler`
- `Ideen`
- `Plan`
- `Workflow Fehleranalyse + Runtime Check + Test Plan`

The tool must derive a concrete mission from repo analysis or stop in a safe yellow state with a clear next action.

## Draft PR rule

Draft PRs require real execution patches.

Actionable targets include:

- `src/`
- `tests/`
- `android/`
- `scripts/`
- `.github/workflows/`
- real config files
- `README.md`
- real `docs/`

Plan-only output must not count as actionable work.
A PR containing only `docs/SOVEREIGN_PLAN.md` and generated workflow preview artifacts is not acceptable.

## Sovereign Search/Replace Runner workflow rule

For large files or risky edits, agents must prefer the guarded Search/Replace Runner workflow over blind full-file replacement.

Canonical flow:

1. Read the current file from GitHub and identify exact SEARCH blocks.
2. Create or update a patch file in `scripts/patches/pending/*.json`.
3. The patch file must include `target`, `blocks`, `commit_message`, `pr_title`, and `pr_body`.
4. For non-main integration branches, use `source_ref` and `branch_base_ref` with the exact commit SHA when a branch ref is not resolvable in Actions.
5. Run `Sovereign Search/Replace Runner` with `dry_run=true` first.
6. Only after dry-run validation succeeds, run the same workflow with `dry_run=false`.
7. Inspect the resulting Draft PR and CI before merge.

Patch file shape:

```json
{
  "target": "src/features/product/containers/BuilderContainer.tsx",
  "source_ref": "<branch-or-commit-sha>",
  "branch_base_ref": "<branch-or-commit-sha>",
  "branch": "<target-patch-branch>",
  "expectedSha": "<current-file-blob-sha>",
  "commit_message": "feat(runtime): describe real change",
  "pr_title": "feat(runtime): describe real change",
  "pr_body": "Explain runtime result, validation and user-visible effect.",
  "blocks": [
    {
      "search": "exact existing code",
      "replace": "new code"
    }
  ]
}
```

Runner guardrails:

- max 20 blocks per patch
- each `search` must match exactly once
- max 8 KB per `search` or `replace`
- max 500 KB target file
- optional `expectedSha` blocks stale patches
- dry-run must happen before apply
- workflow uses `secrets.SOVEREIGN_GITHUB_TOKEN`; never put raw tokens into chat, patch files, logs, or code
- runner opens or updates a Draft PR; it must never write directly to `main`

This workflow is the default for `BuilderContainer.tsx`, `App.tsx`, workflow files, and any other large or high-risk file.

## Live-path integrity

No mocks, stubs, facades, fake snapshots, fake success states, or hardcoded green states in the live path.

Test fixtures are allowed only inside tests and must stay clearly separated from production runtime code.

## Runtime validation and tests

Every new runtime route, state transition, guard, memory bridge, repo analysis path, package build path, draft PR path, and workflow repair path needs useful runtime checks and tests.

Minimum expected coverage for new logic:

- success case
- failure case
- invalid input case
- state transition case
- guard behavior case

## Repo Insight rule

Repo Insight is not decoration. It must produce actionable missions from real repo structure, findings, workflow state, telemetry, and memory patterns.

A suggestion button must set an executable mission, not a generic explanation such as `whyUseful`.

## Pattern Memory rule

Learning patterns may suggest actions, but they never override runtime truth.
A pattern must be validated against current repo state, guards, and tests before it affects output.

## Error handling rule

Failures must route into a repair flow, not into blind retry loops.

A failed action must produce:

1. recorded error result
2. classified state
3. safe next action
4. repair mission or user-visible stop reason

## User-experience rule

The user must not need developer language.
The tool translates vague input such as `Mach weiter` into a safe repo-derived mission or explains the next safe stop in plain language.

## Completion rule

Before claiming work is done, verify:

- the real issue was addressed
- the fix runs in the live path
- tests or validation were added
- no mock/stub/facade entered live code
- no hardcoded UI truth was added
- no plan-only Draft PR path was introduced
- the flow is understandable for a non-developer user

If these checks are not satisfied, report the exact blocker instead of claiming success.

## Required green gate

Before finishing any code change, run or explicitly report why you could not run:

- `pnpm run audit:sovereign`
- `pnpm run type-check`
- `pnpm exec vitest run` (with specific test files)
- `pnpm run build`

Do not stop after fixing only the latest touched file if older failures block the product path.

## Protected product shape

Protect these product rules:

- left side: GitHub file tree and idea/order input
- center: chat, matrix-style file editor and live status
- right side: history log and plain-language analysis
- free-first routing before optional user keys
- visible fix loop on errors
- user confirmation before writing unless autonomous mode is active

## ChatSidebar & Model Selection

The chat interface uses modern ARE-style design with auto-detecting model selection.

### ChatSidebar Component
**Location:** `src/features/product/components/ChatSidebar.tsx`

**Props:**
```typescript
interface ChatSidebarProps {
  chatMessages: ChatMessage[];
  suggestions: Suggestion[];
  isAnalyzing: boolean;
  onSendMessage: (message: string) => void;
  onAcceptSuggestion: (suggestionId: string) => void;
  onDownloadPackage: () => void;
  onClearChat: () => void;
  availableModels?: LlmModelInfo[];      // Auto-detected from adapters
  selectedModel?: string;                  // Currently selected model ID
  onModelChange?: (modelId: string) => void;
}
```

### Kaomoji Thinking Animation 🎉
**DO NOT SIMPLIFY** - The thinking indicator cycles through cute chick emoticons:

```typescript
const THINKING_FRAMES = ['( ^ω^)', '(^_^)', '(^‿^)', '(^o^)', '(^・ω・^)'];
```

- Cycles every 800ms while `isAnalyzing={true}`
- Shows Loader2 spinner + current kaomoji frame
- Preserved for user experience delight

### Model Selection Hook
**Location:** `src/features/product/hooks/useChatModelSelector.ts`

```typescript
import { useChatModelSelector } from '../hooks/useChatModelSelector';

// Extracts available models from LLM adapters
// Prioritizes user-key providers automatically
// Returns: availableModels, selectedModelId, selectedModel, handleModelChange
```

### Chat UI Design Tokens
Uses Sovereign dark/cyan theme:
- Background: `bg-slate-950`, `bg-slate-900/50`
- Borders: `border-cyan-500/20`, `border-cyan-500/30`
- Text: `text-slate-100`, `text-cyan-400`
- Quick actions: pill-style chips with `rounded-full`

## Development Commands & Patterns

### Package Manager
Uses `pnpm` (not npm):
```bash
pnpm install          # Install dependencies
pnpm run dev          # Start dev server (http://localhost:3000)
pnpm run build:web    # Production web build
```

### Quality Gates (required before PR)
```bash
pnpm run type-check           # TypeScript check
pnpm run audit:sovereign      # Custom static audit with NoMock validation
pnpm exec vitest run          # All tests
pnpm run build:web            # Web build
```

### Backend
Python Flask app at `scripts/sovereign-backend/app.py`:
```bash
python3 -m py_compile scripts/sovereign-backend/app.py
```

### Auth Pattern
Backend uses `_get_session_user_id()` to read JWT from HTTP-only cookie. **Never use `X-User-Id` headers** for authentication.

### CORS Pattern
Must use explicit origins list, not `origins="*"`:
```python
CORS(app, origins=CORS_ORIGINS, supports_credentials=True)
```

---

## 📚 Agent Knowledge Files

For patterns, skills, and best practices discovered during development:

| File | Purpose |
|------|---------|
| `AGENTS_KNOWLEDGE.md` | Today's learnings, debugging patterns, file templates |
| `AGENTS_SKILLS.md` | Reusable skill patterns for common tasks |
| `AGENTS_BEST_PRACTICES.md` | Guidelines and anti-patterns to avoid |

**Quick Start:** Read `AGENTS_KNOWLEDGE.md` for the Redux Provider pattern (critical for tests)!

---

## 🔐 Security Best Practices (KRITISCH)

### OAuth Security Contract

Bei GitHub OAuth Implementation MUSS beachtet werden:

1. **Token NIEMALS im Frontend**
   - Access Token bleibt IM Backend
   - Frontend bekommt nur User-Objekt ohne Token
   - Response darf kein `github_access_token`, `githubAccessToken`, `token` enthalten

2. **Token VERSCHLÜSSELT speichern**
   ```python
   # Backend: Fernet encryption
   from cryptography.fernet import Fernet
   import hashlib, base64
   
   key = base64.urlsafe_b64encode(
       hashlib.sha256(ENCRYPTION_KEY.encode()).digest()
   )
   cipher = Fernet(key)
   encrypted = cipher.encrypt(token.encode()).decode()
   ```

3. **State + PKCE Validierung**
   - State für CSRF-Schutz (einmalige Verwendung)
   - PKCE für Code-Interception-Schutz
   ```python
   # State Store (Thread-safe)
   _oauth_state_store: dict = {}
   _oauth_lock = threading.Lock()
   
   def _store_oauth_state(state: str, data: dict) -> None:
       with _oauth_lock:
           _oauth_state_store[state] = {**data, "created_at": time.time()}
   
   def _get_oauth_state(state: str) -> Optional[dict]:
       with _oauth_lock:
           data = _oauth_state_store.pop(state, None)
           if data and time.time() - data.get("created_at", 0) > 600:
               return None  # Ablauf nach 10 min
           return data
   ```

4. **Secrets NIEMALS in Chat teilen**
   - Client Secrets in GitHub Settings regenerieren
   - Environment Variables verwenden
   - GitHub Secrets für CI/CD

### Security Tests ausführen

Security-Tests MÜSSEN in CI laufen:
```bash
pytest backend/tests/test_github_oauth_security.py -v
pytest backend/tests/test_oauth_state_validation.py -v
pytest backend/tests/test_oauth_pkce_validation.py -v
```

---

## 🛠️ Nutzbare Tools & Scripts

### Backend Deployment

```bash
# VPS Backend aktualisieren
ssh root@46.202.154.25
docker cp /tmp/app.py sovereign-backend:/app/app.py
docker restart sovereign-backend
```

### Backend Dependencies installieren

```bash
# Auf VPS
docker exec sovereign-backend pip install cryptography -q
```

### Backend Tests lokal ausführen

```bash
cd backend
pip install pytest cryptography pyjwt -q
python -m pytest tests/ -v
```

### VPS Services

| Service | Port | URL |
|---------|------|-----|
| Backend | 8788 | sovereign-backend |
| Frontend | 3000 | sovereign-frontend |

### Health Check

```bash
curl http://localhost:8788/health
# {"ok":true}
```

---

## 🔑 Wichtige Secrets & Config

### VPS (46.202.154.25)

```bash
# Container anzeigen
docker ps

# Logs anzeigen
docker logs sovereign-backend --tail 50
```

### Environment Variables (Backend)

```bash
GITHUB_CLIENT_ID=xxx
GITHUB_CLIENT_SECRET=xxx      # ⚠️ REGELMÄSSIG ROTIEREN!
GITHUB_TOKEN_ENCRYPTION_KEY=  # Für Token-Verschlüsselung
JWT_SECRET=                  # Für Session Cookies
```

### GitHub Apps / OAuth

- **OAuth App ID**: 4247582
- **OAuth App URL**: https://github.com/settings/applications/4247582

---

## 📝 Coding Patterns

### Backend Tests schreiben (Standalone)

```python
# Backend Tests - Standalone (keine DB deps)
import pytest
import threading, time

_oauth_state_store = {}
_oauth_lock = threading.Lock()

def _store_oauth_state(state: str, data: dict) -> None:
    with _oauth_lock:
        _oauth_state_store[state] = {**data, "created_at": time.time()}

class TestOAuth:
    def test_state_one_time_use(self):
        _store_oauth_state("test", {"data": True})
        first = _get_oauth_state("test")
        assert first is not None
        second = _get_oauth_state("test")
        assert second is None
```

### Frontend API Calls

```typescript
// API Calls immer über Backend
const response = await fetch('/api/auth/me', {
  credentials: 'include'  // Cookie mitsenden
});
```

---

## ⚠️ Häufige Fehler vermeiden

1. **Draft PRs können nicht gemergt werden**
   - Immer `draft:false` setzen oder UI verwenden

2. **TypeScript - test.skip() Signatur**
   ```typescript
   // FALSCH:
   test.skip('message');
   
   // RICHTIG:
   test.skip(true, 'message');
   ```

3. **CI Pipeline läuft nicht**
   - Prüfe ob Dateien in `paths` enthalten sind
   - Workflow Dispatch für manuellen Trigger

---

## 🔄 Workflow für Security Fixes

1. **Branch erstellen**: `git checkout -b security/fix-name`
2. **Tests schreiben**: Tests MÜSSEN zuerst failen
3. **Fix implementieren**: Code ändern bis Tests bestehen
4. **CI prüfen**: Tests müssen in CI laufen
5. **PR erstellen**: Mit detaillierter Beschreibung
6. **Review & Merge**: Draft = false nicht vergessen!
