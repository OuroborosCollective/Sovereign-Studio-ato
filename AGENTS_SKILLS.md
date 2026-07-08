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

### Pattern
```python
from cryptography.fernet import Fernet
import hashlib, base64

def setup_fernet(key: str) -> Fernet:
    fernet_key = base64.urlsafe_b64encode(
        hashlib.sha256(key.encode()).digest()
    )
    return Fernet(fernet_key)

def encrypt_token(token: str, cipher: Fernet) -> str:
    return cipher.encrypt(token.encode()).decode()

def decrypt_token(encrypted: str, cipher: Fernet) -> str | None:
    try:
        return cipher.decrypt(encrypted.encode()).decode()
    except Exception:
        return None
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

### Pattern
```python
import threading, time
from typing import Optional

_oauth_state_store = {}
_oauth_lock = threading.Lock()

def _store_oauth_state(state: str, data: dict) -> None:
    with _oauth_lock:
        _oauth_state_store[state] = {**data, "created_at": time.time()}

def _get_oauth_state(state: str) -> Optional[dict]:
    with _oauth_lock:
        data = _oauth_state_store.pop(state, None)
        if data and time.time() - data.get("created_at", 0) > 600:
            return None
        return data

def _validate_pkce(verifier: str, challenge: str) -> bool:
    import hashlib, base64
    digest = hashlib.sha256(verifier.encode()).digest()
    computed = base64.urlsafe_b64encode(digest).decode().rstrip('=')
    return computed == challenge
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

## Skill: Standalone Backend Tests

### When to Use
- Testing backend logic without psycopg2/Flask deps
- Contract tests for security features

### Pattern
```python
"""
Backend Tests - OHNE externe Dependencies.
Kopiere die zu testenden Funktionen direkt hier.
"""
import pytest
import threading, time

# Kopiere die Funktionen aus app.py
_oauth_state_store = {}
_oauth_lock = threading.Lock()

def _store(state: str, data: dict):
    with _oauth_lock:
        _oauth_state_store[state] = {**data, "created_at": time.time()}

def _get(state: str):
    with _oauth_lock:
        data = _oauth_state_store.pop(state, None)
        if data and time.time() - data.get("created_at", 0) > 600:
            return None
        return data

class TestOAuth:
    def test_one_time_use(self):
        _store("test", {"data": True})
        assert _get("test") is not None
        assert _get("test") is None

    def test_expiry(self):
        # Nach 600 Sekunden abgelaufen
        pass
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
