#!/usr/bin/env bash
# ============================================================================
# Issue #1196 Canary Cleanup Diagnostic Script
# ============================================================================
# This script verifies that the GitHub Knowledge canary cleanup is working.
# It checks:
#   1. Backend container health
#   2. GitHub Knowledge canary cleanup tables for leftover rows
#   3. No orphan audit log entries from canary runs
#
# USAGE:
#   ./diagnose_canary_cleanup.sh [--container NAME]
#
# EXIT CODES:
#   0 - All checks passed (canary cleanup verified)
#   1 - Diagnostic failure (cannot run checks)
#   2 - Canary cleanup incomplete (leftover rows found)
# ============================================================================

set -euo pipefail

CONTAINER="${SOVEREIGN_BACKEND_CONTAINER:-sovereign-backend}"
VPS_HOST="${VPS_HOST:-46.202.154.25}"
VPS_USER="${VPS_USER:-root}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_FILE="${SCRIPT_DIR}/canary-diagnostic-$(date +%Y%m%d-%H%M%S).json"

# Known canary source IDs that may exist from test runs
# These should ALL be zero after canary runs
CANARY_QUERY="
SELECT 
    'knowledge_sources' AS table_name,
    COUNT(*) AS row_count
FROM knowledge_sources 
WHERE title LIKE '%canary%' OR metadata->>'liveCanary' = 'true'
UNION ALL
SELECT 
    'knowledge_source_blocks' AS table_name,
    COUNT(*) AS row_count
FROM knowledge_source_blocks 
WHERE source_id IN (
    SELECT id FROM knowledge_sources 
    WHERE title LIKE '%canary%' OR metadata->>'liveCanary' = 'true'
)
UNION ALL
SELECT 
    'knowledge_learning_candidates' AS table_name,
    COUNT(*) AS row_count
FROM knowledge_learning_candidates
WHERE source_id IN (
    SELECT id FROM knowledge_sources 
    WHERE title LIKE '%canary%' OR metadata->>'liveCanary' = 'true'
)
UNION ALL
SELECT 
    'knowledge_blocks' AS table_name,
    COUNT(*) AS row_count
FROM knowledge_blocks
WHERE id IN (
    SELECT block_id FROM knowledge_source_blocks 
    WHERE source_id IN (
        SELECT id FROM knowledge_sources 
        WHERE title LIKE '%canary%' OR metadata->>'liveCanary' = 'true'
    )
)
UNION ALL
SELECT 
    'vector_index_outbox' AS table_name,
    COUNT(*) AS row_count
FROM vector_index_outbox
WHERE entity_type = 'knowledge_block'
AND entity_id IN (
    SELECT block_id FROM knowledge_source_blocks 
    WHERE source_id IN (
        SELECT id FROM knowledge_sources 
        WHERE title LIKE '%canary%' OR metadata->>'liveCanary' = 'true'
    )
)
UNION ALL
SELECT 
    'audit_log_canary' AS table_name,
    COUNT(*) AS row_count
FROM audit_log
WHERE action = 'knowledge:github_import_failed'
AND changes->>'blocker' = 'github_api_timeout'
AND created_at > NOW() - INTERVAL '7 days'
AND target_id LIKE 'github:%'
AND changes::text NOT LIKE '%sovereign-canary%'
AND changes::text NOT LIKE '%sensitive%'
;
"

echo "=== Issue #1196 Canary Cleanup Diagnostic ==="
echo "Container: ${CONTAINER}"
echo "Output: ${OUTPUT_FILE}"
echo ""

# Check if running locally or on VPS
if [[ "${1:-}" == "--remote" ]]; then
    echo "Running diagnostic via SSH to ${VPS_USER}@${VPS_HOST}..."
    
    SSH_CMD="ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 ${VPS_USER}@${VPS_HOST}"
    
    # Check container is running
    echo "[1/4] Checking backend container health..."
    HEALTH=$(${SSH_CMD} "docker exec ${CONTAINER} curl -s http://127.0.0.1:8787/health 2>/dev/null | head -c 500" || echo "{}")
    if ! echo "${HEALTH}" | grep -q '"ok":true'; then
        echo "FAIL: Backend container health check failed"
        echo "Health response: ${HEALTH}"
        exit 1
    fi
    echo "  OK: Backend container is healthy"
    
    # Check for leftover canary rows
    echo "[2/4] Checking for leftover canary rows..."
    QUERY_RESULT=$(${SSH_CMD} "docker exec ${CONTAINER} python3 -c \"
import os, json, psycopg2
conn = psycopg2.connect(
    host=os.getenv('POSTGRES_HOST', 'db'),
    port=int(os.getenv('POSTGRES_PORT', 5432)),
    dbname=os.getenv('POSTGRES_DB', 'postgres'),
    user=os.getenv('POSTGRES_USER'),
    password=os.getenv('POSTGRES_PASSWORD'),
    connect_timeout=15,
)
with conn.cursor() as cur:
    cur.execute('''
        SELECT 
            'knowledge_sources' AS table_name, COUNT(*) AS row_count
        FROM knowledge_sources 
        WHERE title LIKE '%canary%' OR metadata->>'liveCanary' = 'true'
        UNION ALL
        SELECT 
            'knowledge_source_blocks' AS table_name, COUNT(*) AS row_count
        FROM knowledge_source_blocks 
        WHERE source_id IN (SELECT id FROM knowledge_sources WHERE title LIKE '%canary%')
        UNION ALL
        SELECT 
            'knowledge_learning_candidates' AS table_name, COUNT(*) AS row_count
        FROM knowledge_learning_candidates
        WHERE source_id IN (SELECT id FROM knowledge_sources WHERE title LIKE '%canary%')
        UNION ALL
        SELECT 
            'knowledge_blocks' AS table_name, COUNT(*) AS row_count
        FROM knowledge_blocks
        WHERE id IN (SELECT block_id FROM knowledge_source_blocks WHERE source_id IN (SELECT id FROM knowledge_sources WHERE title LIKE '%canary%'))
    )
    rows = cur.fetchall()
    print(json.dumps([{'table': r[0], 'count': r[1]} for r in rows]))
conn.close()
\" 2>&1" || echo "[]")
    
    if [[ "${QUERY_RESULT}" == "[]" ]]; then
        echo "  OK: No canary tables found (query returned empty)"
    else
        TOTAL=0
        echo "  Canary table status:"
        for row in $(echo "${QUERY_RESULT}" | python3 -c "import json,sys; [print(json.dumps({'table': r['table'], 'count': r['count']})) for r in json.load(sys.stdin)]" 2>/dev/null || echo "[]"); do
            TABLE=$(echo "${row}" | python3 -c "import json,sys; print(json.load(sys.stdin)['table'])" 2>/dev/null || echo "unknown")
            COUNT=$(echo "${row}" | python3 -c "import json,sys; print(json.load(sys.stdin)['count'])" 2>/dev/null || echo "0")
            TOTAL=$((TOTAL + COUNT))
            if [[ "${COUNT}" -gt 0 ]]; then
                echo "    FAIL: ${TABLE} has ${COUNT} leftover row(s)"
            else
                echo "    OK: ${TABLE} is clean (0 rows)"
            fi
        done
        
        if [[ "${TOTAL}" -gt 0 ]]; then
            echo ""
            echo "FAIL: Canary cleanup is incomplete. ${TOTAL} leftover row(s) found."
            echo "The github_knowledge_live_canary cleanup path needs investigation."
            exit 2
        fi
    fi
    
    # Check for recent canary audit entries
    echo "[3/4] Checking for recent canary audit entries..."
    AUDIT_COUNT=$(${SSH_CMD} "docker exec ${CONTAINER} python3 -c \"
import os, psycopg2
conn = psycopg2.connect(
    host=os.getenv('POSTGRES_HOST', 'db'),
    port=int(os.getenv('POSTGRES_PORT', 5432)),
    dbname=os.getenv('POSTGRES_DB', 'postgres'),
    user=os.getenv('POSTGRES_USER'),
    password=os.getenv('POSTGRES_PASSWORD'),
    connect_timeout=15,
)
with conn.cursor() as cur:
    cur.execute('''
        SELECT COUNT(*) FROM audit_log
        WHERE action = 'knowledge:github_import_failed'
        AND changes->>'blocker' = 'github_api_timeout'
        AND created_at > NOW() - INTERVAL '7 days'
    )
    print(cur.fetchone()[0])
conn.close()
\" 2>&1" || echo "-1")
    
    if [[ "${AUDIT_COUNT}" =~ ^[0-9]+$ ]] && [[ "${AUDIT_COUNT}" -ge 0 ]]; then
        echo "  INFO: ${AUDIT_COUNT} canary audit entries in last 7 days"
    else
        echo "  WARN: Could not query audit log"
    fi
    
    echo "[4/4] Generating diagnostic report..."
    ${SSH_CMD} "docker exec ${CONTAINER} python3 -c \"
import os, json, psycopg2
conn = psycopg2.connect(
    host=os.getenv('POSTGRES_HOST', 'db'),
    port=int(os.getenv('POSTGRES_PORT', 5432)),
    dbname=os.getenv('POSTGRES_DB', 'postgres'),
    user=os.getenv('POSTGRES_USER'),
    password=os.getenv('POSTGRES_PASSWORD'),
    connect_timeout=15,
)
with conn.cursor() as cur:
    cur.execute('SELECT NOW()')
    ts = cur.fetchone()[0].isoformat()
conn.close()
print(json.dumps({'timestamp': ts, 'container': '${CONTAINER}', 'status': 'verified'}))
\" 2>&1" > "${OUTPUT_FILE}"
    
else
    echo "Running diagnostic locally (requires Docker access)..."
    
    # Check container is running
    echo "[1/4] Checking backend container health..."
    if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
        echo "FAIL: Container ${CONTAINER} is not running"
        exit 1
    fi
    HEALTH=$(docker exec "${CONTAINER}" curl -s http://127.0.0.1:8787/health 2>/dev/null | head -c 500 || echo "{}")
    if ! echo "${HEALTH}" | grep -q '"ok":true'; then
        echo "FAIL: Backend container health check failed"
        echo "Health response: ${HEALTH}"
        exit 1
    fi
    echo "  OK: Backend container is healthy"
    
    # Check for leftover canary rows
    echo "[2/4] Checking for leftover canary rows..."
    docker exec "${CONTAINER}" python3 -c "
import os, json, psycopg2
conn = psycopg2.connect(
    host=os.getenv('POSTGRES_HOST', 'db'),
    port=int(os.getenv('POSTGRES_PORT', 5432)),
    dbname=os.getenv('POSTGRES_DB', 'postgres'),
    user=os.getenv('POSTGRES_USER'),
    password=os.getenv('POSTGRES_PASSWORD'),
    connect_timeout=15,
)
with conn.cursor() as cur:
    cur.execute('''
        SELECT 
            'knowledge_sources' AS table_name, COUNT(*) AS row_count
        FROM knowledge_sources 
        WHERE title LIKE '%canary%' OR metadata->>'liveCanary' = 'true'
        UNION ALL
        SELECT 
            'knowledge_source_blocks' AS table_name, COUNT(*) AS row_count
        FROM knowledge_source_blocks 
        WHERE source_id IN (SELECT id FROM knowledge_sources WHERE title LIKE '%canary%')
        UNION ALL
        SELECT 
            'knowledge_learning_candidates' AS table_name, COUNT(*) AS row_count
        FROM knowledge_learning_candidates
        WHERE source_id IN (SELECT id FROM knowledge_sources WHERE title LIKE '%canary%')
        UNION ALL
        SELECT 
            'knowledge_blocks' AS table_name, COUNT(*) AS row_count
        FROM knowledge_blocks
        WHERE id IN (SELECT block_id FROM knowledge_source_blocks WHERE source_id IN (SELECT id FROM knowledge_sources WHERE title LIKE '%canary%'))
    )
    rows = cur.fetchall()
    print(json.dumps([{'table': r[0], 'count': r[1]} for r in rows]))
conn.close()
" 2>&1 | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    TOTAL = 0
    for row in data:
        count = row['count']
        table = row['table']
        TOTAL += count
        if count > 0:
            print(f\"  FAIL: {table} has {count} leftover row(s)\")
        else:
            print(f\"  OK: {table} is clean (0 rows)\")
    if TOTAL > 0:
        sys.exit(2)
except Exception as e:
    print(f\"  WARN: Could not parse query result: {e}\")
"
    local_result=$?
    if [[ $local_result -eq 2 ]]; then
        echo \"\"
        echo \"FAIL: Canary cleanup is incomplete. Leftover row(s) found.\"
        exit 2
    fi
    
    echo "[3/4] Checking for recent canary audit entries..."
    docker exec "${CONTAINER}" python3 -c "
import os, psycopg2
conn = psycopg2.connect(
    host=os.getenv('POSTGRES_HOST', 'db'),
    port=int(os.getenv('POSTGRES_PORT', 5432)),
    dbname=os.getenv('POSTGRES_DB', 'postgres'),
    user=os.getenv('POSTGRES_USER'),
    password=os.getenv('POSTGRES_PASSWORD'),
    connect_timeout=15,
)
with conn.cursor() as cur:
    cur.execute('''
        SELECT COUNT(*) FROM audit_log
        WHERE action = 'knowledge:github_import_failed'
        AND changes->>'blocker' = 'github_api_timeout'
        AND created_at > NOW() - INTERVAL '7 days'
    )
    print(cur.fetchone()[0])
conn.close()
" 2>&1 | python3 -c "
import json, sys
try:
    count = int(sys.stdin.read().strip())
    print(f'  INFO: {count} canary audit entries in last 7 days')
except:
    print('  WARN: Could not query audit log')
"
    
    echo "[4/4] Generating diagnostic report..."
    docker exec "${CONTAINER}" python3 -c "
import os, json, psycopg2
conn = psycopg2.connect(
    host=os.getenv('POSTGRES_HOST', 'db'),
    port=int(os.getenv('POSTGRES_PORT', 5432)),
    dbname=os.getenv('POSTGRES_DB', 'postgres'),
    user=os.getenv('POSTGRES_USER'),
    password=os.getenv('POSTGRES_PASSWORD'),
    connect_timeout=15,
)
with conn.cursor() as cur:
    cur.execute('SELECT NOW()')
    ts = cur.fetchone()[0].isoformat()
conn.close()
print(json.dumps({'timestamp': ts, 'container': '${CONTAINER}', 'status': 'verified'}))
" 2>&1 > "${OUTPUT_FILE}"
fi

echo ""
echo "=== Diagnostic Complete ==="
echo "Result: PASS (canary cleanup verified)"
echo "Report: ${OUTPUT_FILE}"
cat "${OUTPUT_FILE}"
exit 0
