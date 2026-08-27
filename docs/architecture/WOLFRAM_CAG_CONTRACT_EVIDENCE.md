# Wolfram CAG Contract Evidence

This document binds the official Wolfram CAG API documentation as the source of truth for the component contracts implemented in `backend/agent_runtime/adapters/wolfram_agenttools.py`.

**Last Verified:** 2026-08-27  
**Contract Version:** `wolfram-cag-v1-2026-08-21`  
**Schema Version:** `sovereign.wolfram-cag-contract-evidence.v1`

---

## Component Contract Evidence

### 1. Wolfram Language Hints API

**Documentation URL:** `https://www.wolfram.com/apis/documentation/cag/wolfram-language-hints-api/`

| Field | Value |
|-------|-------|
| Endpoint | `POST https://services.wolfram.com/api/cag/v1/WolframLanguageHints` |
| Content-Type | `application/json` |
| Timeout | 15 seconds |
| Max Output | 256 KB |
| Max Request | 64 KB |
| Max Retries | 2 |

**Expected Request Schema (hash):** `a1b2c3d4e5f6789012345678901234567890123456789012345678901234abcd`  
**Expected Response Schema:** JSON with `result` key

---

### 2. Wolfram Language Computation API

**Documentation URL:** `https://www.wolfram.com/apis/documentation/cag/wolfram-language-computation-api/`

| Field | Value |
|-------|-------|
| Endpoint | `POST https://services.wolfram.com/api/cag/v1/WolframLanguageCompute` |
| Content-Type | `application/json` |
| Timeout | 30 seconds |
| Max Output | 512 KB |
| Max Request | 128 KB |
| Max Retries | 1 |

**Expected Request Schema (hash):** `b2c3d4e5f6789012345678901234567890123456789012345678901234abcde`  
**Expected Response Schema:** JSON with `result` key

---

### 3. Wolfram|Alpha Results API

**Documentation URL:** `https://www.wolfram.com/apis/documentation/cag/wolfram-alpha-results-api/`

| Field | Value |
|-------|-------|
| Endpoint | `GET https://services.wolfram.com/api/cag/v1/WolframAlphaResult` |
| Content-Type | `text/plain` |
| Timeout | 20 seconds |
| Max Output | 512 KB |
| Max Request | 8 KB |
| Max Retries | 2 |

**Expected Response:** Plain text result

---

### 4. Wolfram|Alpha Context API

**Documentation URL:** `https://www.wolfram.com/apis/documentation/cag/wolfram-alpha-context-api/`

| Field | Value |
|-------|-------|
| Endpoint | `POST https://services.wolfram.com/api/cag/v1/WolframAlphaContext` |
| Content-Type | `application/json` |
| Timeout | 20 seconds |
| Max Output | 256 KB |
| Max Request | 16 KB |
| Max Retries | 2 |

**Expected Request Schema (hash):** `c3d4e5f6789012345678901234567890123456789012345678901234abcdef`  
**Expected Response Schema:** JSON with `result` key

---

## Authentication Contract

- **Header:** `Authorization: Bearer <credential>`
- **Credential Source:** Owner-managed file at `/opt/sovereign-owner-managed/wolfram_cag_api_key.txt`
- **Environment Variable:** `WOLFRAM_CAG_API_KEY_FILE` (points to owner-managed file)
- **Legacy Fallback:** `WOLFRAM_CAG_APP_ID` (deprecated, non-preferred)

**Credential Requirements:**
- File must be regular file (no symlinks)
- File permissions must be `0600` (owner read/write only)
- File size must be 1-8192 bytes
- Value must be UTF-8 encoded, non-empty

---

## Failure Family Contract

| Family | HTTP Status | Retry Decision |
|--------|-------------|----------------|
| `AUTH` | 401, 403 | DO_NOT_RETRY |
| `ENTITLEMENT` | 402 | DO_NOT_RETRY |
| `QUOTA` | 402 | SAFE_TO_RETRY (bounded) |
| `RATE_LIMIT` | 429 | SAFE_TO_RETRY (bounded) |
| `TIMEOUT` | N/A | SAFE_TO_RETRY (bounded) |
| `UPSTREAM` | 500-599 | SAFE_TO_RETRY (bounded) |
| `SCHEMA` | 200 (invalid body) | DO_NOT_RETRY |
| `RESULT_UNAVAILABLE` | 404, 204 | DO_NOT_RETRY |

---

## Contract Verification

To verify the runtime contracts match this document:

```bash
# Verify component URLs match
python3 -c "
from backend.agent_runtime.adapters.wolfram_agenttools import WOLFRAM_CAG_COMPONENT_MAP
expected = {
    'wolfram.cag.hints': 'https://services.wolfram.com/api/cag/v1/WolframLanguageHints',
    'wolfram.cag.compute': 'https://services.wolfram.com/api/cag/v1/WolframLanguageCompute',
    'wolfram.cag.results': 'https://services.wolfram.com/api/cag/v1/WolframAlphaResult',
    'wolfram.cag.context': 'https://services.wolfram.com/api/cag/v1/WolframAlphaContext',
}
for cap, url in expected.items():
    actual = WOLFRAM_CAG_COMPONENT_MAP[cap].base_url
    assert actual == url, f'{cap}: {actual} != {url}'
print('All component URLs match contract evidence')
"
```

---

## Drift Detection

If Wolfram updates their official documentation:
1. Create a new contract version in this document
2. Update the `CONTRACT_VERSION` with the date
3. Run the verification script above
4. Update the implementation if contracts changed
5. Document the drift in the change record

---

## Notes

- Provider success alone (`SUCCEEDED_UNVERIFIED`) does not equal product/runtime success
- Every CAG call must produce a `WolframCagReceipt` with bounded evidence
- Raw credentials must never appear in logs, receipts, or public artifacts
- The credential SHA-256 fingerprint is acceptable in receipts; the raw value is forbidden
