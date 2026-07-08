# Agent Skills - Sovereign Studio V3

> **Reusable patterns and skills for working on Sovereign Studio V3**

---

## Skill: Redux Provider in Tests

### When to Use
- Component uses `useSelector` or `useDispatch`
- Test fails with: "could not find react-redux context value"

### Pattern
```typescript
import React from 'react';
import { Provider } from 'react-redux';
import { render } from '@testing-library/react';
import { store } from '../store';

function renderWithProviders(ui: React.ReactElement) {
  return render(<Provider store={store}>{ui}</Provider>);
}

// Usage
renderWithProviders(<MyComponent prop="value" />);
```

### Files Commonly Affected
- `*.test.tsx` files with Redux-connected components
- Files using Zustand stores typically don't need this

---

## Skill: Selector Type Safety

### When to Use
- Creating Redux selectors
- Fixing TypeScript errors in slices

### Pattern
```typescript
import type { RootState } from '../../store';

export const selectMyData = (state: RootState) => state.feature.data;
export const selectMyLoading = (state: RootState) => state.feature.loading;
```

### Anti-Pattern (Don't Do This)
```typescript
// ❌ Wrong
export const selectMyData = (state: { feature: FeatureState }) => state.feature.data;

// ✅ Correct
export const selectMyData = (state: RootState) => state.feature.data;
```

---

## Skill: Fix Test Assertions

### When to Use
- Test fails but code works
- Object has more fields than expected

### Pattern
```typescript
// Before (fails)
expect(result).toEqual({ ok: true, content: 'text' });

// After (works)
expect(result).toMatchObject({ ok: true, content: 'text' });
```

---

## Skill: TypeScript Debugging

### When to Use
- `pnpm run type-check` shows errors
- "Module has no exported member" errors

### Steps
1. Run: `pnpm run type-check 2>&1 | head -50`
2. Check import paths are correct
3. Verify exports exist (named AND type exports)
4. Check for circular dependencies
5. Ensure `RootState` is imported where needed

---

## Skill: Git Workflow

### Standard Commit
```bash
git add <files>
git commit -m "fix(scope): describe fix

- Detail 1
- Detail 2

Co-authored-by: openhands <openhands@all-hands.dev>"
git push origin main
```

### Commit Types
- `fix:` - Bug fixes
- `feat:` - New features  
- `refactor:` - Code refactoring
- `test:` - Test changes
- `chore:` - Maintenance

---

## Skill: Run Quality Gates

### Required Before PR
```bash
pnpm run audit:sovereign  # Security audit
pnpm run type-check       # TypeScript check
pnpm exec vitest run      # All tests
pnpm run build:web        # Production build
```

### Quick Check (Fast)
```bash
pnpm run type-check 2>&1 | grep -c "error"
```

---

## Skill: CI Debugging

### Get CI Logs
```bash
gh run list --repo OuroborosCollective/Sovereign-Studio-ato --limit 10
gh run view <run-id> --repo OuroborosCollective/Sovereign-Studio-ato --log
```

### Common CI Failures
1. TypeScript errors → Run `pnpm run type-check`
2. Test failures → Run `pnpm exec vitest run`
3. Build failures → Run `pnpm run build:web`
4. Provider missing → Add Redux Provider to tests

---

## Skill: Find Related Files

### By Pattern
```bash
# Find all test files
find src -name "*.test.ts" -o -name "*.test.tsx"

# Find files using RootState
grep -r "RootState" src --include="*.ts" --include="*.tsx" -l

# Find Redux selectors
grep -r "select[A-Z]" src/features --include="*.ts"
```

---

## Skill: Batch Replace Patterns

### Add Provider to Multiple Tests
```bash
# Add imports
sed -i "1i import { Provider } from 'react-redux';" src/file.test.tsx
sed -i "1i import { store } from '../../store';" src/file.test.tsx

# Add helper function (after imports, before first function)
sed -i '/^function baseProps/i\
function renderWithProviders(ui: React.ReactElement) {\
  return render(<Provider store={store}>{ui}</Provider>);\
}\n' src/file.test.tsx

# Replace render calls
sed -i 's/render(<Component/renderWithProviders(<Component/g' src/file.test.tsx
```

---

## Skill: Verify Fixes

### Local Test Run
```bash
pnpm exec vitest run src/path/to/test.tsx --reporter=verbose
```

### Watch Mode (during development)
```bash
pnpm exec vitest src/path/to/test.tsx --watch
```

---

## Skill: OAuth Token Encryption (Backend)

### When to Use
- Implementing GitHub OAuth
- Storing sensitive tokens in database

### Pattern (Live Path)
```python
# Importiere das ECHTE Module
from security_oauth import (
    init_token_encryption,
    _encrypt_token,
    _decrypt_token,
)

# Initialisiere
init_token_encryption("your-secret-key")

# Verschlüsseln
encrypted = _encrypt_token("sensitive_token")

# Entschlüsseln
original = _decrypt_token(encrypted)
```

### Setup
```bash
pip install cryptography
```

---

## Skill: OAuth State + PKCE Store (Backend)

### When to Use
- GitHub OAuth implementation
- CSRF protection needed
- PKCE validation required

### Pattern (Live Path)
```python
# Importiere das ECHTE Module
from security_oauth import (
    _store_oauth_state,
    _get_oauth_state,
    _validate_pkce,
    _generate_state,
    _generate_pkce,
)

# State generieren und speichern
state = _generate_state()
verifier, challenge = _generate_pkce()
_store_oauth_state(state, {"code_challenge": challenge})

# Später: State abrufen und PKCE validieren
stored = _get_oauth_state(state)
if stored and _validate_pkce(verifier, stored["code_challenge"]):
    # Gültig!
    pass
```

### WICHTIG: Live-Path Tests
```bash
# Tests importieren security_oauth.py (NICHT Kopien!)
python -m pytest backend/tests/test_oauth_security.py -v
# 22 passed - ECHTER Code wird getestet!
```

---

## Skill: SSH + Docker Deployment

### When to Use
- Deploying backend updates to VPS
- Managing Docker containers

### Pattern
```python
import paramiko

def deploy_backend(local_path: str, remote_path: str, container: str):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect("HOST", username="root", password="PASSWORD")
    
    # Upload file
    sftp = ssh.open_sftp()
    sftp.put(local_path, '/tmp/app.py')
    sftp.close()
    
    # Deploy
    ssh.exec_command(f"docker cp /tmp/app.py {container}:{remote_path}")
    ssh.exec_command(f"docker restart {container}")
    
    ssh.close()
```

### Manual Commands
```bash
# SSH
ssh root@HOST

# Deploy
docker cp /tmp/app.py CONTAINER:/app/app.py
docker restart CONTAINER

# Install deps
docker exec CONTAINER pip install cryptography -q

# Health check
curl http://localhost:8788/health
```

---

## Skill: Live-Path Backend Tests

### When to Use
- Testing backend logic
- Security Contract Testing

### Pattern (Live Path - NICHT Standalone Kopien!)
```python
"""
Backend Tests - Importieren ECHTEN Code!
"""
import sys
sys.path.insert(0, 'backend')

# Importiere das echte Module (NICHT Kopien!)
from security_oauth import (
    _encrypt_token,
    _decrypt_token,
    _store_oauth_state,
    _get_oauth_state,
)

class TestOAuth:
    def test_token_encryption(self):
        # Testet den ECHTEN Code
        encrypted = _encrypt_token("sensitive")
        assert encrypted != "sensitive"
        
    def test_state_one_time_use(self):
        # Testet den ECHTEN Code
        _store_oauth_state("test", {"data": True})
        assert _get_oauth_state("test") is not None
        assert _get_oauth_state("test") is None
```

### ⚠️ WICHTIG: Keine Standalone Kopien!
```python
# ❌ FALSCH - Standalone Kopie (testet nicht den echten Code)
def _store(state, data):
    _oauth_state_store[state] = {...}

# ✅ RICHTIG - Importiert ECHTEN Code
from security_oauth import _store_oauth_state
```

---

## Skill: GitHub API via curl

### When to Use
- Creating PRs programmatically
- Merging PRs
- Checking CI status

### Pattern
```bash
# PR erstellen (NICHT als draft!)
curl -s -X POST \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  -d '{"title":"...","head":"branch","base":"main","draft":false}' \
  https://api.github.com/repos/OWNER/REPO/pulls

# PR mergen
curl -s -X PUT \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -d '{"merge_method":"squash","commit_title":"..."}' \
  https://api.github.com/repos/OWNER/REPO/pulls/{number}/merge

# Workflow Runs
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
  "https://api.github.com/repos/OWNER/REPO/actions/runs?per_page=5"

# ⚠️ WICHTIG: draft=false setzen, sonst kann nicht gemergt werden!
```

---

*Last Updated: 2026-07-08*
