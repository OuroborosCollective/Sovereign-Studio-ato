# Issue #1196 Runtime Verification Plan

## Status: RUNTIME_VERIFICATION_PENDING

Issue: [#1196 - Runtime follow-up: OpenHands proxy targets Browserless and GitHub Knowledge canary cleanup is unverified](https://github.com/OuroborosCollective/Sovereign-Studio-ato/issues/1196)

## A. OpenHands Reverse-Proxy Drift (BLOCKED - REQUIRES VPS ACCESS)

### What
Nginx routing for `openhands.arelorian.de` needs to be verified against the runtime requirements:
- Proxy to Browserless endpoint
- Proxy to MCP endpoints

### Repository Configuration
Location: `scripts/vps-config/setup-nginx.sh`

### Verification Required
1. SSH to VPS: `ssh root@46.202.154.25`
2. Check current nginx configuration
3. Compare against expected routing
4. Validate service endpoints are reachable

### Owner Action Required
This part requires direct VPS access and manual verification by Thomas Markgraf.

---

## B. GitHub Knowledge Canary Cleanup (IMPLEMENTATION_VERIFIED - RUNTIME_UNVERIFIED)

### What
The GitHub Knowledge canary (`github_knowledge_live_canary`) must:
1. Insert a test document into pgvector
2. Verify transport error handling
3. **Clean up ALL canary data in the `finally` block**
4. Return only evidence, not actual data

### Repository Implementation
Location: `tools/sovereign-chatgpt-mcp/github_knowledge_canary.py`

### Cleanup Code Analysis
The `finally` block (lines 324-351) executes:
1. `DELETE FROM audit_log WHERE id=%s::uuid` - removes canary audit entry
2. `DELETE FROM vector_index_outbox` - removes pending vector entries
3. `DELETE FROM knowledge_sources` - removes source record
4. `DELETE FROM knowledge_learning_candidates` - removes candidates
5. `DELETE FROM knowledge_blocks` - removes orphaned blocks only

### Verification Command
```bash
# From the repository root
./scripts/issue-1196-canary-diagnostic/diagnose_canary_cleanup.sh --remote
```

### Expected Result
All canary-related tables should return 0 rows after canary runs:
- `knowledge_sources` with `liveCanary=true` metadata: 0 rows
- `knowledge_source_blocks` for canary source: 0 rows
- `knowledge_learning_candidates` for canary source: 0 rows
- `knowledge_blocks` orphaned from canary: 0 rows
- `vector_index_outbox` for canary blocks: 0 rows
- `audit_log` canary entries: removed

### Verification Evidence Required
Run the diagnostic script and provide:
1. Exit code (0 = pass, 2 = cleanup incomplete)
2. JSON report with timestamp
3. Any leftover row counts

---

## C. Diagnostic Tool Added

A new diagnostic script has been added to verify canary cleanup:
- **Location**: `scripts/issue-1196-canary-diagnostic/diagnose_canary_cleanup.sh`
- **Purpose**: Check for leftover canary rows in database
- **Usage**: `./diagnose_canary_cleanup.sh --remote` (for VPS) or local Docker

---

## Truth Classification

| Component | Status | Evidence |
|------------|--------|----------|
| Repository Implementation | IMPLEMENTED | Code review of `github_knowledge_canary.py` |
| Repository Tests | IMPLEMENTED | `test_github_knowledge_canary.py` passes |
| Cleanup SQL Logic | IMPLEMENTED | `finally` block with 5 DELETE statements |
| Runtime Verification | UNVERIFIED | Cannot verify without VPS/database access |
| VPS Nginx Config | UNVERIFIED | Requires manual VPS access |

---

## Owner Action Items

1. **Run canary diagnostic**:
   ```bash
   ssh root@46.202.154.25
   cd /workspace/project/Sovereign-Studio-ato
   ./scripts/issue-1196-canary-diagnostic/diagnose_canary_cleanup.sh
   ```

2. **Verify nginx routing** for `openhands.arelorian.de`

3. **Update issue** with runtime verification results

---

*Document Version: 1.0 | Date: 2026-08-06 | Author: OpenHands*
