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
git push --set-upstream origin "$BRANCH"  # then open a Draft PR
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

## Skill: Backend Agent Tool erstellen

### When to Use
- Neues Tool für Agent Runtime hinzufügen
- Python-Funktionen als LLM-Tools verfügbar machen

### Pattern
```python
# backend/agent_runtime/tools/my_tool.py
from typing import Any
from dataclasses import dataclass

@dataclass
class ToolResult:
    ok: bool
    output: str = ""
    error: str = ""
    metadata: dict[str, Any] = None

class MyTool:
    name: str = "my_tool"
    description: str = "Does something useful"
    
    def __init__(self, workspace_path: str):
        self.workspace_path = workspace_path
    
    def execute(self, **params) -> ToolResult:
        try:
            return ToolResult(ok=True, output="success")
        except Exception as e:
            return ToolResult(ok=False, error=str(e))

# Registry
TOOL_REGISTRY = {"my_tool": MyTool}
```

### Test Pattern
```python
# backend/tests/test_agent_my_tool.py
import pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from agent_runtime.tools.my_tool import MyTool, ToolResult

class TestMyTool:
    def test_success(self):
        tool = MyTool("/workspace")
        result = tool.execute(param="value")
        assert result.ok is True
    
    def test_failure(self):
        tool = MyTool("/workspace")
        result = tool.execute(param="")
        assert result.ok is False
```

---

## Skill: VPS Migration via stdin

### When to Use
- PostgreSQL Migration auf Container anwenden
- `docker exec -f` nicht verfügbar

### Pattern
```python
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("HOST", username="root", password="PASS")

# SQL via stdin senden
transport = ssh.get_transport()
channel = transport.open_session()
channel.exec_command("docker exec -i supabase-db psql -U postgres -d postgres")

channel.send(migration_sql.encode())
channel.shutdown_write()

# Output lesen
stdout = b""
while True:
    if channel.recv_ready():
        stdout += channel.recv(1024)
    if channel.exit_status_ready():
        break

print(stdout.decode())
```

### Migration Template
```sql
-- scripts/sovereign-backend/migrations/XXX_name.sql
-- Migration: XXX_name

ALTER TABLE table_name ADD COLUMN IF NOT EXISTS col TYPE;

CREATE TABLE IF NOT EXISTS new_table (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid()
);

CREATE INDEX IF NOT EXISTS idx_name ON table_name(column);

DO $$
BEGIN
    RAISE NOTICE 'Migration XXX completed';
END $$;
```

---

## Skill: MagicMock defensiv testen

### When to Use
- Python Tests mit unittest.mock
- MagicMock gibt None oder False statt echter Werte

### Problem
```python
# Problem: mock_request.branch = None → MagicMock
if not branch:  # Immer False wegen MagicMock!
    branch = generate_branch()
```

### Lösung
```python
# Explizite None/Empty Prüfung
if branch is None or (isinstance(branch, str) and len(branch) == 0):
    branch = generate_branch()

# Oder für Any-Typen
if not branch or not isinstance(branch, str) or len(str(branch)) == 0:
    branch = generate_branch()
```

### Alternative: Real Mock Values
```python
mock_request.branch = ""  # Empty string statt None
result = my_function(mock_request)
assert result is not None
```

---

## Skill: Python Type-Hints für Cross-Module

### When to Use
- Import-Fehler zwischen Modulen
- Zirkuläre Imports
- Fehlende Klassen

### Pattern
```python
# Problem: ImportError von WorkspaceProvisioner
# from .workspace import WorkspaceProvisioner  # ❌ Fail

# Lösung: Any mit Kommentar
from typing import Any

class EvidenceGate:
    def __init__(self, workspace: Any):  # WorkspaceProvisioner | GitWorkspace
        self.workspace = workspace
```

### Vorteile
- Kompiliert erfolgreich
- Dokumentation bleibt erhalten
- Flexibel für verschiedene Implementierungen

---

## Skill: Tool Signal Integration

### When to Use
- Frontend Tools mit Predictive Layer verbinden
- Signal-basierte Lern-Integration

### Pattern
```typescript
// src/features/feature/toolIntegration.ts
import { emitToolSignal, registerToolNode } from '@/predictive/toolPredictiveBridge';

export async function executeTool(config: ToolConfig) {
    const startTime = performance.now();
    registerToolNode(config.name, 'feature');

    try {
        const result = await doWork(config);
        emitToolSignal({
            toolName: config.name,
            toolType: 'feature',
            status: 'success',
            durationMs: performance.now() - startTime,
            parameters: config.params,
        });
        return { success: true, result };
    } catch (error) {
        emitToolSignal({
            toolName: config.name,
            toolType: 'feature',
            status: 'error',
            durationMs: performance.now() - startTime,
        });
        return { success: false, error };
    }
}
```

---

## Skill: VPS Production Debugging

### When to Use
- Debugging running backend services on VPS
- Investigating stuck jobs or failed deployments
- Verifying fixes in production containers

### Pattern: VPS SSH + Paramiko
```python
import os
import paramiko

client = paramiko.SSHClient()
client.load_system_host_keys()
client.set_missing_host_key_policy(paramiko.RejectPolicy())
client.connect(
    os.environ['VPS_HOST'],
    username=os.environ['VPS_USER'],
    key_filename=os.environ['VPS_SSH_KEY_FILE'],
    timeout=30,
)

# Execute commands in container
stdin, stdout, stderr = client.exec_command('docker exec sovereign-backend python3 -c "..."')

# Copy file to container (use SFTP for binary files)
sftp = client.open_sftp()
with sftp.open('/app/fixed.py', 'wb') as f:
    f.write(file_content.encode())
sftp.close()
client.exec_command('docker restart sovereign-backend')

# Fetch file from container
stdin, stdout, stderr = client.exec_command('docker exec sovereign-backend cat /app/file.py')
content = stdout.read().decode()

client.close()
```

### Pattern: Multi-File Transfer
```python
files = {
    '/app/agent_runtime/sovereign_local_runner.py': '/tmp/copy.py',
    '/app/agent_runtime/tools/git_tool.py': '/tmp/git.py',
}
for src, dst in files.items():
    stdin, stdout, stderr = client.exec_command(f'docker exec sovereign-backend cat {src}')
    with open(dst, 'w') as f:
        f.write(stdout.read().decode())
```

### Pattern: DB Query from Container
```python
script = '''#!/usr/bin/env python3
import os, psycopg2
conn = psycopg2.connect(
    host=os.getenv("POSTGRES_HOST","supabase-db"),
    port=int(os.getenv("POSTGRES_PORT","5432")),
    database=os.getenv("POSTGRES_DB","postgres"),
    user=os.getenv("POSTGRES_USER","postgres"),
    password=os.getenv("POSTGRES_PASSWORD","")
)
cur = conn.cursor()
cur.execute("SELECT job_id, status FROM sovereign_agent_jobs LIMIT 5")
for r in cur.fetchall():
    print(r)
conn.close()'''

with open('/tmp/query.py', 'w') as f:
    f.write(script)
with open('/tmp/query.py', 'rb') as f:
    content = f.read()
sftp = client.open_sftp()
with sftp.open('/tmp/sovereign_backend/query.py', 'wb') as f:
    f.write(content)
sftp.close()
client.exec_command('docker cp /tmp/sovereign_backend/query.py sovereign-backend:/tmp/query.py')
stdin, stdout, stderr = client.exec_command('docker exec sovereign-backend python3 /tmp/query.py')
print(stdout.read().decode())
```

### Pattern: Container Verification
```python
# Check runner alive
cmd = "docker exec sovereign-backend python3 -c \"import sys; sys.path.insert(0,'/app'); import app; rd=app._runner_daemon; print('OK' if rd and rd.is_alive() else 'DOWN')\""
stdin, stdout, stderr = client.exec_command(cmd)
print(stdout.read().decode())

# Check health
stdin, stdout, stderr = client.exec_command('docker exec sovereign-backend python3 -c "import urllib.request; print(urllib.request.urlopen(\'http://127.0.0.1:8787/health\').read().decode())"')

# Syntax check
stdin, stdout, stderr = client.exec_command('docker exec sovereign-backend python3 -m py_compile /app/filename.py')
```

### VPS Service Ports (46.202.154.25)
| Service | Port | Access |
|---------|------|--------|
| sovereign-backend | 8788 | 127.0.0.1 only |
| memory-gateway | 8088 | 127.0.0.1 only |
| arelorian-engine | 3001 | 127.0.0.1 (MMORPG, NOT toolchain!) |
| supabase-db | 5432 | Docker network |
| milvus-standalone | 19530 | privates Gateway-Docker-Netz; kein Host-Port |
| milvus-etcd / milvus-minio | 2379 / 9000 | internes `milvus-storage`-Netz; kein Host-Port |

### Docker Commands Reference
```bash
# Container management
docker restart sovereign-backend
docker logs sovereign-backend --tail 50
docker inspect sovereign-backend --format "{{.State.Status}}"
docker exec sovereign-backend python3 -m py_compile /app/file.py

# Port binding
docker inspect sovereign-backend | grep -A2 "PortBindings"
# Should show 127.0.0.1:8788->8787/tcp

# Health check
curl http://localhost:8788/health

# File hash verification
sha256sum /app/agent_runtime/sovereign_local_runner.py
```

### Fix Deployment Pattern
1. Apply fix to local repo files
2. Fetch fixed file from running container (already has fix)
3. Write to local repo at correct path
4. `python3 -m py_compile` to verify syntax
5. `git add && git commit && git push`
6. No rebuild needed for Python-only fixes (container already has fix)

---

## Skill: Job Lifecycle Debugging

### When to Use
- Jobs stuck in provisioning/running
- No tool events appearing
- Runtime not dispatching jobs

### Debug Command Chain
```python
# 1. Check job status
docker exec sovereign-backend python3 -c "
import os, psycopg2
conn = psycopg2.connect(host=os.getenv('POSTGRES_HOST','supabase-db'),port=int(os.getenv('POSTGRES_PORT','5432')),database=os.getenv('POSTGRES_DB','postgres'),user=os.getenv('POSTGRES_USER','postgres'),password=os.getenv('POSTGRES_PASSWORD',''))
cur=conn.cursor()
cur.execute('SELECT job_id, status, blocker FROM sovereign_agent_jobs WHERE status IN (\"provisioning\",\"running\") ORDER BY created_at')
for r in cur.fetchall():
    print(r)
conn.close()"

# 2. Check events
docker exec supabase-db psql -U postgres -d postgres -c "
SELECT stage, message FROM sovereign_agent_events 
WHERE job_id = 'job-id' ORDER BY created_at"

# 3. Check runner daemon
docker exec sovereign-backend python3 -c "
import sys; sys.path.insert(0,'/app')
import app; rd=app._runner_daemon
print('Daemon:', rd)
print('Alive:', rd.is_alive() if rd else False)
print('Jobs:', list(rd._job_threads.keys()) if rd else [])"
```

### Expected Event Sequence
```
1. job_started_by_runner (info)
2. repo_clone_completed (success)
3. repo_snapshot_ready (success) [if applicable]
4. tool_completed OR tool_failed (for each LLM tool call)
...
N. job_completed_by_runner OR job_failed_*
```

### Common Failure Patterns
| Pattern | Cause | Fix |
|---------|-------|-----|
| Only 1-2 events, no tool calls | `_job_events()` crash, git tool missing | Check AttributeError in logs, add GitUniversalTool |
| No job_started event | Runner daemon not started | Check `_runner_daemon.is_alive()` |
| All jobs stuck at provisioning | cloneRepo=false default | Set cloneRepo=true or dispatch manually |
| file_read fails "not found" | Tools got workspace root, not repo path | Change to `repo_path = Path(ws)/job_id/repo` |

### Canary Test Pattern
```python
# Create test job
INSERT INTO sovereign_agent_jobs 
  (job_id, user_id, executor, status, repo_url, branch, mission, workspace_id, 
   draft_pr_only, allow_auto_merge, created_at, updated_at)
VALUES 
  ('canary-' || gen_random_uuid()::text, user_id, 'sovereign-local-runner', 
   'provisioning', 'https://github.com/OWNER/REPO', 'main', 
   'Call done with summary: test', 'canary-' || gen_random_uuid()::text,
   TRUE, FALSE, NOW(), NOW());

# Watch events grow (expect 3+ events within 60s)
SELECT COUNT(*) FROM sovereign_agent_events WHERE job_id = 'canary-...';
```

---

*Last Updated: 2026-07-10 (VPS Production Fix)*
