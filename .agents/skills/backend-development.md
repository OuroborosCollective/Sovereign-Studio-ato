# Backend Development Best Practices

## Sovereign Studio Backend Conventions

This document captures best practices learned from working with the Sovereign Studio backend (Flask + PostgreSQL).

---

## 1. Database Column Types

### Critical Rule: Check Before Casting
**Never assume a column type. Always verify before using type casts.**

```python
# WRONG - assuming uuid type
query("SELECT * FROM table WHERE id = %s::uuid", (id,))

# CORRECT - no cast needed if id is TEXT
query("SELECT * FROM table WHERE id = %s", (id,))
```

### llm_routes Table
| Column | Type | Notes |
|--------|------|-------|
| id | TEXT | UUID stored as text, NOT UUID type |
| model_id | TEXT | UNIQUE constraint |
| model_name | TEXT | Friendly name |
| provider | TEXT | Provider name |
| base_url | TEXT | Optional, nullable |
| api_key | TEXT | Optional, nullable |

### admin_users Table
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | Use `::uuid` cast |
| email | TEXT | |
| role | TEXT | admin, superadmin, user |
| credits | NUMERIC | |

---

## 2. Worker AI Integration

### Centralized Fetch Helper
Always use the centralized `fetch_worker_ai()` function for Worker AI API calls:

```python
# Define at module level
WORKER_AI_BASE = os.getenv(
    "WORKER_AI_PROXY_URL", 
    "https://sovereign-llm-proxy.projectouroboroscollective.workers.dev"
)
WORKER_AI_TIMEOUT = 15  # seconds

def _worker_headers() -> dict:
    """Standard headers for Worker AI API calls."""
    headers = {"Content-Type": "application/json"}
    api_key = os.getenv("WORKER_AI_PROXY_KEY", "")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers

def fetch_worker_ai(path: str, method: str = "GET", json_data: dict = None) -> tuple[requests.Response | None, str]:
    """
    Centralized Worker AI fetch with consistent base URL, headers, timeout, and error handling.
    Returns (response, error_message). If error_message is empty, response is valid.
    """
    url = f"{WORKER_AI_BASE.rstrip('/')}/{path.lstrip('/')}"
    try:
        if method == "GET":
            resp = requests.get(url, headers=_worker_headers(), timeout=WORKER_AI_TIMEOUT)
        elif method == "POST":
            resp = requests.post(url, headers=_worker_headers(), json=json_data, timeout=WORKER_AI_TIMEOUT)
        else:
            return None, f"Unsupported method: {method}"
        return resp, ""
    except requests.exceptions.Timeout:
        return None, f"Request to Worker AI timed out after {WORKER_AI_TIMEOUT}s"
    except requests.exceptions.ConnectionError as e:
        return None, f"Cannot connect to Worker AI: {e}"
    except Exception as e:
        return None, f"Worker AI request failed: {e}"
```

### Usage Pattern
```python
# GOOD - centralized
resp, err = fetch_worker_ai("v1/models")
if err:
    return jsonify({"error": err}), 500

# BAD - inconsistent, hard to maintain
resp = requests.get(f"{worker_url}/v1/models", headers={"Authorization": f"Bearer {api_key}"}, timeout=10)
```

---

## 3. Error Handling Patterns

### Consistent Error Response Format
```python
def some_endpoint():
    try:
        result = do_something()
        return jsonify({"ok": True, "data": result})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500
```

### Database Error Handling
```python
try:
    result = query("SELECT ...", params, write=True)
except psycopg2.errors.UniqueViolation:
    return jsonify({"error": "Duplicate entry"}), 409
except psycopg2.errors.ForeignKeyViolation:
    return jsonify({"error": "Referenced entity not found"}), 400
except Exception as e:
    return jsonify({"error": str(e)}), 500
```

---

## 4. Health Check Endpoints

### System Health Pattern
```python
@app.route("/api/admin/system/health", methods=["GET"])
@require_admin
def admin_system_health():
    """Comprehensive system health check."""
    health = {
        "ok": True,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "components": {},
    }
    
    # Check database
    try:
        start = time.time()
        result = query("SELECT 1 as test, NOW() as now", one=True)
        db_time = int((time.time() - start) * 1000)
        health["components"]["database"] = {
            "status": "healthy",
            "responseTimeMs": db_time,
        }
    except Exception as e:
        health["ok"] = False
        health["components"]["database"] = {
            "status": "unhealthy",
            "error": str(e)[:100],
        }
    
    # Add more components...
    
    return jsonify(health)
```

---

## 5. VPS Deployment Workflow

### Critical: Container vs Volume Mount
**The Docker container has its own filesystem!**

The container does NOT automatically use files from `/opt/sovereign-backend/` on the host.

Options:
1. **Rebuild image** - `docker-compose up --build`
2. **Direct copy** - `docker cp /tmp/fixed_app.py container:/app/app.py`
3. **Volume mount** - Configure in docker-compose.yml

### Deployment Script Template
```python
import paramiko
import time

def deploy_to_vps(local_file_path: str, remote_path: str):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username="root", password=password, timeout=30)
    
    # Upload file
    sftp = ssh.open_sftp()
    with open(local_file_path, 'rb') as f:
        sftp.open(remote_path, 'wb').write(f.read())
    sftp.close()
    
    # Option A: Rebuild container
    # ssh.exec_command("cd /opt/sovereign-backend && docker-compose up --build -d", timeout=300)
    
    # Option B: Direct copy and restart
    ssh.exec_command("docker cp fixed_app.py container:/app/app.py")
    ssh.exec_command("docker restart container")
    
    time.sleep(25)  # Wait for container to restart
    
    # Verify
    stdin, stdout, stderr = ssh.exec_command("curl -s http://127.0.0.1:8788/health")
    print(stdout.read().decode())
    
    ssh.close()
```

---

## 6. API Key Security

### Do NOT
- ❌ Log API keys
- ❌ Include keys in screenshots
- ❌ Commit keys to git
- ❌ Share keys in chat
- ❌ Store keys in temp files

### Do
- ✅ Store in `.env` on VPS
- ✅ Use environment variables in code
- ✅ Access via `os.getenv()`
- ✅ Rotate keys regularly

---

## 7. Testing Pattern

### E2E Test Template
```python
def test_worker_ai_flow():
    admin_key = os.getenv("ADMIN_API_KEY")
    base = "http://46.202.154.25:8788"
    headers = {"Authorization": f"Bearer {admin_key}"}
    
    # 1. Status check
    resp = requests.get(f"{base}/api/admin/llm/worker-ai/status", headers=headers)
    assert resp.ok and resp.json().get("status") == "healthy"
    
    # 2. Sync
    resp = requests.post(f"{base}/api/admin/llm/worker-ai/sync", headers=headers)
    assert resp.ok
    
    # 3. List routes
    resp = requests.get(f"{base}/api/admin/llm/routes", headers=headers)
    assert resp.ok
    
    # 4. Health check per route
    for route in resp.json().get("routes", [])[:3]:
        rid = route.get("id")
        resp = requests.post(f"{base}/api/admin/llm/routes/{rid}/healthcheck", headers=headers)
        assert resp.ok
    
    # 5. System health
    resp = requests.get(f"{base}/api/admin/system/health", headers=headers)
    assert resp.ok and resp.json().get("ok")
    
    print("✅ All tests passed")
```

---

## 8. Git Workflow

### Commit Message Format
```
<type>: <short description>

<detailed description if needed>

Co-authored-by: openhands <openhands@all-hands.dev>
```

### Types
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation
- `refactor:` - Code refactoring
- `test:` - Tests
- `chore:` - Maintenance

---

## 9. Common Pitfalls

### psycopg2 IN Clause
```python
# WRONG - tuple with single element
ids = ["abc"]
query("SELECT * FROM table WHERE id IN %s", (tuple(ids),))  # Fails

# CORRECT - use list for ALL() 
ids = ["abc"]
query("SELECT * FROM table WHERE id != ALL(%s)", (ids,))
```

### UUID vs TEXT comparison
```python
# WRONG
WHERE id = %s::uuid

# CORRECT if id is TEXT
WHERE id = %s
```

### Request timeout
```python
# Always set timeout to prevent hanging
requests.get(url, timeout=15)  # 15 seconds max
```

---

## 10. Environment Variables Reference

| Variable | Description | Default |
|----------|-------------|---------|
| ADMIN_API_KEY | Admin authentication | - |
| JWT_SECRET | JWT signing key | "supersecretkey-change-me" |
| WORKER_AI_PROXY_URL | Worker AI endpoint | Workers.dev URL |
| WORKER_AI_PROXY_KEY | Worker AI auth | - |
| POSTGRES_HOST | Database host | "db" |
| POSTGRES_PORT | Database port | 5432 |
| OPENHANDS_API_URL | OpenHands API | http://127.0.0.1:3000 |

---

*Document Version: 1.0 | Last Updated: 2026-07-06*
