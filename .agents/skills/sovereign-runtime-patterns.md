# Sovereign Studio Runtime Patterns

## Overview

This document captures the established runtime patterns for the Sovereign Studio project, learned through practical implementation.

---

## 1. Worker AI Auto-Discovery System

### Architecture
```
Cloudflare Worker AI → Sovereign LLM Proxy → Auto-Sync → llm_routes DB
                                                        ↓
                                          Admin UI (Status/Sync)
```

### Key Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/admin/llm/worker-ai/status` | GET | Get Worker AI health and available models |
| `/api/admin/llm/worker-ai/sync` | POST | Sync available models to database |
| `/api/admin/llm/worker-ai/models` | GET | List models with DB sync status |
| `/api/admin/llm/routes` | GET | List all configured LLM routes |
| `/api/admin/llm/routes/<id>/healthcheck` | POST | Per-route health check |
| `/api/admin/system/health` | GET | Comprehensive system health |

### Data Model: llm_routes

```sql
CREATE TABLE llm_routes (
    id TEXT PRIMARY KEY,           -- UUID stored as TEXT
    model_id TEXT UNIQUE NOT NULL, -- Worker AI model ID
    model_name TEXT,               -- Friendly display name
    provider TEXT,                 -- 'cloudflare', 'openai', 'mistral', etc.
    base_url TEXT,                 -- Optional custom endpoint
    api_key TEXT,                  -- Optional API key
    credits_per_unit NUMERIC,      -- Cost tracking
    disabled BOOLEAN DEFAULT false,
    priority INTEGER DEFAULT 50,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### Auto-Discovery Flow

1. Worker AI proxy returns available models via `/v1/models`
2. Sync endpoint compares with existing `llm_routes`
3. New models are inserted with defaults
4. Missing models are marked as disabled
5. Admin UI shows sync status per model

### Example: Sync Response
```json
{
  "ok": true,
  "synced": {
    "created": [{"id": "uuid", "model": "@cf/meta/llama-3.1-8b-instruct"}],
    "updated": [],
    "disabled": []
  },
  "totalWorkerModels": 13,
  "totalRoutes": 14
}
```

---

## 2. Admin UI Integration

### JavaScript Pattern

```javascript
// Load LLM routes into UI
async function loadLLMRoutes() {
    const resp = await fetch('/api/admin/llm/routes', {
        headers: { 'Authorization': `Bearer ${getAdminKey()}` }
    });
    const data = await resp.json();
    
    // Display routes with health status
    for (const route of data.routes) {
        const healthResp = await fetch(`/api/admin/llm/routes/${route.id}/healthcheck`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${getAdminKey()}` }
        });
        const health = await healthResp.json();
        displayRoute(route, health);
    }
}

// Worker AI sync
async function syncWorkerAI() {
    const resp = await fetch('/api/admin/llm/worker-ai/sync', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${getAdminKey()}` }
    });
    return resp.json();
}
```

### HTML Structure
```html
<!-- Worker AI Status Card -->
<div class="worker-ai-status">
    <h3>🤖 Worker AI</h3>
    <div class="status-badge" id="wai-status">Checking...</div>
    <div class="model-count" id="wai-models">-</div>
    <button onclick="checkWorkerAIStatus()">🔍 Status prüfen</button>
    <button onclick="syncWorkerAI()">🔄 Worker AI synchronisieren</button>
</div>
```

---

## 3. Health Check Strategy

### Per-Route Health Check

Each LLM route is checked individually:

```python
@app.route("/api/admin/llm/routes/<rid>/healthcheck", methods=["POST"])
def admin_llm_route_healthcheck(rid):
    route = query("SELECT * FROM llm_routes WHERE id = %s", (rid,), one=True)
    
    provider = route.get("provider", "").lower()
    
    if provider == "cloudflare":
        # Use Worker AI proxy
        resp, err = fetch_worker_ai("health")
        # ...
    elif provider == "openai":
        # Direct API check
        resp = requests.get(f"{base_url}/v1/models", timeout=10)
        # ...
    elif provider == "mistral":
        resp = requests.get(f"{base_url}/v1/models", timeout=10)
        # ...
```

### Response Format
```json
{
    "routeId": "uuid",
    "health": "healthy|degraded|unhealthy",
    "responseTimeMs": 42,
    "error": null
}
```

---

## 4. Runtime Truth Sources

### Approved Runtime State Variables
- `sequentialRuntime` - Sequential step execution
- `repoSnapshotStatus` - Git repository state
- `repoFiles` - File tree from repository
- `scanRegistry` - Contract/live scan results
- `workflowReport` - Workflow execution results
- `lastPackage` - Built package artifact
- `diffReport` - Code change analysis
- `telemetry` - Event/metrics stream
- `solutionPatternStore` - Known patterns
- `remoteMemoryIntake` - External memory state
- `automationStatus` - Automation run state

### Do NOT Use
- DOM text or page scraping
- Static percentages
- Visual UI state as truth
- Button click as logic trigger

---

## 5. Causal Runtime Chain

Every workflow must follow:

1. **Action starts** → User or system triggers
2. **Action produces result** → Real data, not UI
3. **Result creates/updates state** → Database or runtime
4. **State routes next action** → Logic from state, not UI
5. **Next action is derivable** → From state, not assumption

---

## 6. Error Classification

| Status | Meaning | Action |
|--------|---------|--------|
| healthy | All good | Continue |
| degraded | Partial failure | Monitor |
| unhealthy | Major failure | Alert |
| timeout | Request timed out | Retry/Escalate |
| unreachable | Cannot connect | Check infrastructure |
| error | Generic error | Log and investigate |

---

## 7. Testing the Flow

### E2E Test Sequence
```bash
# 1. System health
curl -H "Authorization: Bearer $ADMIN_KEY" \
     http://46.202.154.25:8788/api/admin/system/health

# 2. Worker AI status
curl -H "Authorization: Bearer $ADMIN_KEY" \
     http://46.202.154.25:8788/api/admin/llm/worker-ai/status

# 3. Sync models
curl -X POST -H "Authorization: Bearer $ADMIN_KEY" \
     http://46.202.154.25:8788/api/admin/llm/worker-ai/sync

# 4. List routes
curl -H "Authorization: Bearer $ADMIN_KEY" \
     http://46.202.154.25:8788/api/admin/llm/routes

# 5. Health check a route
curl -X POST -H "Authorization: Bearer $ADMIN_KEY" \
     http://46.202.154.25:8788/api/admin/llm/routes/<id>/healthcheck
```

### Expected Results
- System health: `{"ok": true, "components": {...}}`
- Worker AI: `{"status": "healthy", "modelCount": 13}`
- Sync: `{"ok": true, "synced": {...}}`
- Routes: Array of route objects
- Health checks: Individual route status

---

## 8. Common Fixes

### UUID Cast Error
```
psycopg2.errors.UndefinedFunction: operator does not exist: text = uuid
```
**Fix**: Remove `::uuid` cast if column is TEXT type.

### NoneType Iteration
```
'NoneType' object is not iterable
```
**Fix**: Check for empty array before iteration:
```python
if array and len(array) > 0:
    for item in array:
        ...
```

### IN Clause with Single Element
```python
# WRONG
WHERE id IN (('single_value',))  # psycopg2 adds extra parens

# CORRECT
WHERE id != ALL(%s)  # Use ALL() with list
```

---

*Document Version: 1.0 | Last Updated: 2026-07-06*
