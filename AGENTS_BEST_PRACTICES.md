# Best Practices - Sovereign Studio V3

> **Guidelines for agents working on Sovereign Studio V3**

---

## Testing Best Practices

### 1. Always Wrap Redux Components in Provider

**Rule:** Any component using `useSelector` or `useDispatch` MUST have a Redux Provider wrapper in tests.

```typescript
// ✅ CORRECT
import { Provider } from 'react-redux';
import { store } from '../../store';

function renderWithProviders(ui: React.ReactElement) {
  return render(<Provider store={store}>{ui}</Provider>);
}

it('renders correctly', () => {
  renderWithProviders(<MyComponent />);
});

// ❌ WRONG - Will fail with context error
it('renders correctly', () => {
  render(<MyComponent />);
});
```

### 2. Use `toMatchObject` for Partial Matching

Prefer `toMatchObject` over `toEqual` when:
- Object has dynamic fields
- Object has more fields than you're testing
- Only specific fields matter

```typescript
// ✅ Better
expect(result).toMatchObject({ ok: true, data: expectedData });

// ❌ Fragile - breaks if any new fields added
expect(result).toEqual({ ok: true, data: expectedData, timestamp: expect.anything() });
```

### 3. Mock Global Functions Properly

```typescript
// ✅ Mock before test
beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});
```

---

## TypeScript Best Practices

### 1. Always Use RootState for Selectors

```typescript
// ✅ CORRECT
import type { RootState } from '../../store';
export const selectData = (state: RootState) => state.feature.data;

// ❌ WRONG
export const selectData = (state: { feature: FeatureState }) => state.feature.data;
```

### 2. Export Both Values and Types

```typescript
// ✅ Complete export
export const myFunction = () => { /* ... */ };
export type MyType = { /* ... */ };

// ❌ Incomplete
export const myFunction = () => { /* ... */ };
// Type not exported - breaks consumers
```

### 3. Check Imports Match Exports

Common mistake:
```typescript
// In module
export const COST_CONFIG = { /* ... */ };

// In consumer - WRONG
import { LEGACY_COST_CONFIG } from './config';  // Doesn't exist!

// CORRECT
import { COST_CONFIG } from './config';
```

---

## Git Best Practices

### 1. Descriptive Commit Messages

```bash
# ✅ Good
git commit -m "fix(billing): resolve TypeScript type errors in selectors
- Add RootState import
- Update all selector signatures
- Add missing exports"

# ❌ Bad
git commit -m "fix stuff"
```

### 2. Include Co-authored-by

```bash
git commit -m "fix(module): describe change

Co-authored-by: openhands <openhands@all-hands.dev>"
```

### 3. Group Related Changes

One commit = one logical change:
- ❌ "fix billing AND add new feature AND refactor store"
- ✅ Three separate commits

---

## Code Organization

### 1. Import Order

```typescript
// 1. React / Core
import React from 'react';

// 2. External libraries
import { Provider } from 'react-redux';

// 3. Internal modules
import { store } from '../../store';
import { selectData } from '../slice';

// 4. Types
import type { MyType } from './types';
```

### 2. Test File Co-location

```
src/features/billing/
├── billingSlice.ts          # Source
├── billingSlice.test.ts      # Tests
└── hooks/
    └── useBilling.ts        # Hook
    └── useBilling.test.ts   # Tests
```

---

## Debugging Workflow

### 1. Reproduce Locally First

```bash
# Run specific test
pnpm exec vitest run src/path/to/test.tsx

# Run with verbose output
pnpm exec vitest run src/path/to/test.tsx --reporter=verbose

# Run in watch mode
pnpm exec vitest src/path/to/test.tsx --watch
```

### 2. Check TypeScript Explicitly

```bash
pnpm run type-check 2>&1 | grep -E "error TS" | head -20
```

### 3. Check CI Logs

```bash
# Find failing run
gh run list --repo OuroborosCollective/Sovereign-Studio-ato --limit 5

# Get logs
gh run view <run-id> --log 2>&1 | tail -100
```

---

## Quality Gates

Always run these before committing:

```bash
# 1. Type check
pnpm run type-check

# 2. Tests
pnpm exec vitest run

# 3. Security audit
pnpm run audit:sovereign

# 4. Build
pnpm run build:web
```

---

## Anti-Patterns to Avoid

### ❌ Don't Skip Tests to "Make CI Pass"
Fix the underlying issue instead.

### ❌ Don't Use `any` to Silence Errors
Use proper types or `unknown` with type guards.

### ❌ Don't Bypass Redux Provider in Tests
Components need their context to render correctly.

### ❌ Don't Hardcode Test Data
Use factories or fixtures for consistent test data.

### ❌ Don't Forget to Unstub Globals
Always clean up in `afterEach`.

---

## Documentation

### When to Update Docs
- New patterns discovered
- Common mistakes identified
- Architecture changes
- New tooling added

### Where to Document
- `AGENTS_KNOWLEDGE.md` - Learned patterns, troubleshooting
- `AGENTS_SKILLS.md` - Reusable skill patterns
- `AGENTS_BEST_PRACTICES.md` - Guidelines and rules
- `docs/` - Architecture documentation
- Code comments - Implementation details

---

## 🔐 Security Best Practices

### ✅ DO: Token NIEMALS im Frontend

```typescript
// ✅ RICHTIG: Backend gibt User-Objekt OHNE Token zurück
{
  "id": "123",
  "email": "user@example.com",
  "githubUsername": "user",
  // KEIN "github_access_token" oder "githubAccessToken"
}

// ❌ FALSCH: Token im Frontend
{
  "githubAccessToken": "gho_xxx"  // ABSOLUT VERBOTEN!
}
```

### ✅ DO: Token Verschlüsseln

```python
# ✅ Backend: Token verschlüsseln
from cryptography.fernet import Fernet
cipher = Fernet(key)
encrypted = cipher.encrypt(token.encode())
```

### ✅ DO: Secrets in Environment Variables

```bash
# ✅ RICHTIG
export GITHUB_CLIENT_SECRET=xxx

# ❌ FALSCH: Hardcoded im Code
GITHUB_CLIENT_SECRET = "hardcoded_secret"
```

### ❌ DON'T: Secrets in Chat/Code

```
⚠️ NIEMALS Secrets in Chat-Nachrichten oder Code-Kommentaren teilen!
```

---

## 🧪 Test Best Practices

### ✅ DO: Tests VOR dem Fix schreiben

```python
# 1. Test schreiben (sollte FAILEN)
def test_token_not_in_response():
    response = auth_endpoint()
    assert "github_access_token" not in response  # FAIL!

# 2. Fix implementieren
def _user_row_to_dict(row):
    return {
        "id": row["id"],
        # Token NICHT hier!
    }

# 3. Test läuft jetzt durch
```

### ✅ DO: Standalone Tests (keine DB deps)

```python
# ✅ Kopiere die Funktionen in die Test-Datei
# statt psycopg2/Flask zu importieren

import threading, time

_oauth_state_store = {}
_oauth_lock = threading.Lock()

def _store(state, data):
    with _oauth_lock:
        _oauth_state_store[state] = {**data, "created_at": time.time()}

class TestState:
    def test_one_time_use(self):
        _store("test", {"data": True})
        assert _get("test") is not None
        assert _get("test") is None  # Bereits verwendet!
```

### ❌ DON'T: Mock-in-Live-Code

```
⚠️ Mocks sind nur in Tests erlaubt, NIEMALS im Production Code!
```

---

## 🔧 CI/CD Best Practices

### ✅ DO: Paths in Workflows definieren

```yaml
# ✅ Workflow nur bei relevanten Änderungen ausführen
on:
  push:
    paths:
      - 'src/**'      # Nur bei Frontend-Änderungen
      - 'backend/**'   # Nur bei Backend-Änderungen
      - '.github/workflows/**'
```

### ✅ DO: Backend Tests in CI

```yaml
# ✅ CI Job für Backend Tests
backend-tests:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/setup-python@v5
    - run: pip install pytest cryptography
    - run: cd backend && pytest tests/ -v
```

---

## 📝 PR Best Practices

### ✅ DO: Klare PR-Beschreibung

```markdown
## Was wurde geändert?
- Fix für OAuth Token Security

## Tests
- 27/27 Backend Tests bestanden
- TypeScript Check bestanden

## Checklist
- [x] Security Tests hinzugefügt
- [x] CI läuft durch
```

### ✅ DO: draft:false für mergbare PRs

```bash
# ✅ RICHTIG
curl -d '{"draft":false}' https://api.github.com/...

# ❌ FALSCH: Draft PRs können nicht gemergt werden!
```

---

## ⚠️ Anti-Patterns (NIEMALS tun!)

1. **Token im Frontend speichern** - Security Risk!
2. **Secrets hardcoden** - Rotieren unmöglich
3. **Draft PRs mergen wollen** - Funktioniert nicht!
4. **Mocks im Live-Code** - Wartbarkeits-Albtraum
5. **Alle Workflows bei jedem Push** - Verschwendet CI-Ressourcen
6. **Ohne Tests mergen** - Regression Risk

---

## 🔄 Workflow Checklist

Vor jedem Merge:

- [ ] Tests schreiben und bestehen
- [ ] `pnpm run type-check` läuft durch
- [ ] `pnpm run build` läuft durch
- [ ] Backend Tests: `pytest backend/tests/ -v`
- [ ] PR ist nicht als Draft markiert
- [ ] Health Check nach Deployment

---

## 🏛️ Causal Runtime Chain

**Immer** dieser Kette folgen:

```
1. Action starts
2. Action produces a result  
3. Result creates or updates state
4. State allows, blocks, or routes the next action
5. Next action is logically derivable from state
```

**Niemals**:
- ❌ Springen weil Button sichtbar ist
- ❌ UI-Text als Logik verwenden
- ❌ DOM-Scraping für Entscheidungen

---

## 🧪 Python Testing Best Practices

### ✅ DO: Live-Path Testing

```python
# ✅ RICHTIG: Importiere echten Code
import sys
sys.path.insert(0, 'backend')
from agent_runtime.tools.file_tool import FileReadTool

class TestFileTool:
    def test_read_success(self):
        tool = FileReadTool("/workspace")
        result = tool.execute(path="test.txt")
        assert result.ok is True

# ❌ FALSCH: Standalone Kopie
def test_read():  # Testet nicht den echten Code!
    assert True  # Immer grün!
```

### ✅ DO: MagicMock defensiv

```python
# ✅ Explizite None-Prüfung
if branch is None or (isinstance(branch, str) and len(branch) == 0):
    branch = generate_branch()

# ❌ MagicMock verhindert None-Prüfung
mock_request.branch = None  # Wird MagicMock!
if not branch:  # Immer False!
    branch = generate_branch()
```

### ✅ DO: Type-Hints für Cross-Module

```python
# ✅ Any mit Kommentar
from typing import Any

class EvidenceGate:
    def __init__(self, workspace: Any):  # WorkspaceProvisioner | GitWorkspace
        self.workspace = workspace
```

---

## 🚀 VPS Deployment Best Practices

### ✅ DO: Container-Ports kennen

```python
# Backend intern: 8787
# Backend extern: 8788 (via Proxy)
# Frontend: 3000
# Database: 5432

curl -s http://127.0.0.1:8788/health  # Extern
curl -s http://127.0.0.1:8787/health  # Intern
```

### ✅ DO: Migration via stdin

```python
# ✅ RICHTIG: stdin statt Datei
channel.exec_command("docker exec -i db psql -U postgres")
channel.send(sql.encode())
channel.shutdown_write()

# ❌ FALSCH: Datei im Container
sftp.put("migration.sql", "/tmp/migration.sql")  # Funktioniert nicht!
```

### ✅ DO: Graceful Restart

```python
# ✅ Stop -> Copy -> Start -> Wait -> Health Check
ssh.exec_command("docker stop backend")
ssh.exec_command("docker cp app.py backend:/app/")
ssh.exec_command("docker start backend")
time.sleep(20)  # Warte auf Start
```

---

## 📦 Modul-Design Best Practices

### ✅ ToolResult Dataclass

```python
@dataclass
class ToolResult:
    ok: bool
    output: str = ""
    error: str = ""
    metadata: dict = None

class MyTool:
    def execute(self, **params) -> ToolResult:
        try:
            return ToolResult(ok=True, output="success")
        except Exception as e:
            return ToolResult(ok=False, error=str(e))
```

### ✅ Workspace-Scoped

```python
class FileTool:
    def __init__(self, workspace_path: str):
        self.workspace_path = workspace_path
    
    def execute(self, **params) -> ToolResult:
        safe_path = self._validate_inside_workspace(params.get("path"))
        ...
```

---

## ⚠️ Anti-Patterns (NIEMALS)

1. **Fake Success State**
```python
# ❌ Hardcoded Green
return {"ok": True, "status": "healthy"}

# ✅ Real Check
return check_real_health()
```

2. **UI als Truth Source**
```python
# ❌ Button-Text als Logik
if "Weiter" in button.text: proceed()

# ✅ Runtime State
if runtime.current_step == "complete": proceed()
```

3. **Blind Retry Loops**
```python
# ❌ Endlos-Retry
while True:
    try: api_call(); break
    except: continue

# ✅ Mit Limit
for attempt in range(3):
    try: return api_call()
    except RetryableError:
        if attempt == 2: return classify_failure()
        wait(exponential_backoff(attempt))
```

4. **Mocks in Production**
```python
# ❌ Mocks in Live-Code
mock_result = {"ok": True}
return mock_result

# ✅ Real Path
return do_real_work()
```

---

*Last Updated: 2026-07-08 (Agent Runtime)*
