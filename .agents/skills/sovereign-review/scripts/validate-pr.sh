#!/bin/bash
# PR Validation Script for Sovereign Studio
# Usage: ./scripts/validate-pr.sh

set -e

echo "=== Sovereign Studio PR Validation ==="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASS=0
FAIL=0

check() {
    local name="$1"
    local cmd="$2"
    echo -n "Checking: $name... "
    if eval "$cmd" > /dev/null 2>&1; then
        echo -e "${GREEN}PASS${NC}"
        ((PASS++))
        return 0
    else
        echo -e "${RED}FAIL${NC}"
        ((FAIL++))
        return 1
    fi
}

check_output() {
    local name="$1"
    local cmd="$2"
    local expected="$3"
    echo -n "Checking: $name... "
    output=$(eval "$cmd" 2>&1 || true)
    if echo "$output" | grep -q "$expected"; then
        echo -e "${GREEN}PASS${NC}"
        ((PASS++))
        return 0
    else
        echo -e "${RED}FAIL${NC}"
        echo "  Expected: $expected"
        echo "  Got: $output"
        ((FAIL++))
        return 1
    fi
}

# Check TypeScript
check "TypeScript compiles" "npx tsc --noEmit"

# Check for artifacts
ARTIFACTS=$(git diff --name-only origin/main...HEAD 2>/dev/null | grep -E "(\.apk|\.aab|\.aar|\.gradle|android/|dist/|build/|node_modules/)" || true)
if [ -z "$ARTIFACTS" ]; then
    echo -e "Checking: No artifacts in diff... ${GREEN}PASS${NC}"
    ((PASS++))
else
    echo -e "Checking: No artifacts in diff... ${RED}FAIL${NC}"
    echo "  Found: $ARTIFACTS"
    ((FAIL++))
fi

# Check for unused states in BuilderContainer
UNUSED=$(grep -n "const \[.*\].*= useState" src/features/product/containers/BuilderContainer.tsx 2>/dev/null | wc -l || true)
if [ "$UNUSED" -gt 0 ]; then
    echo -e "Checking: Minimal state variables... ${YELLOW}REVIEW${NC}"
    echo "  Found $UNUSED useState declarations - verify they're all used"
    # Don't fail, just warn
fi

# Check tests exist
check "ChatMarkdown tests exist" "test -f src/features/product/components/ChatMarkdown.test.tsx"
check "WorkerBlockerCard tests exist" "test -f src/features/product/components/WorkerBlockerCard.test.tsx"
check "Intent detector tests exist" "test -f src/features/product/runtime/workerIntentDetector.test.ts"

# Run tests
echo ""
echo "=== Running Tests ==="
if npx vitest run \
    src/features/product/components/ChatMarkdown.test.tsx \
    src/features/product/components/DraftPrCard.test.tsx \
    src/features/product/components/WorkerBlockerCard.test.tsx \
    src/features/product/runtime/workerIntentDetector.test.ts \
    src/features/product/runtime/chatExportRuntime.test.ts \
    2>&1 | tee /tmp/test-output.txt; then
    echo -e "Tests: ${GREEN}PASS${NC}"
    ((PASS++))
else
    echo -e "Tests: ${RED}FAIL${NC}"
    ((FAIL++))
fi

# Check retry pattern
if grep -q "retrySubmit" src/features/product/containers/BuilderContainer.tsx && \
   grep -q "_processSubmit" src/features/product/containers/BuilderContainer.tsx; then
    echo -e "Checking: Real retry pattern... ${GREEN}PASS${NC}"
    ((PASS++))
else
    echo -e "Checking: Real retry pattern... ${RED}FAIL${NC}"
    echo "  retrySubmit or _processSubmit not found"
    ((FAIL++))
fi

# Check intent detection in runtime module
if grep -q "from '../runtime/workerIntentDetector'" src/features/product/containers/BuilderContainer.tsx 2>/dev/null; then
    echo -e "Checking: Intent detection in runtime module... ${GREEN}PASS${NC}"
    ((PASS++))
else
    echo -e "Checking: Intent detection in runtime module... ${RED}FAIL${NC}"
    ((FAIL++))
fi

echo ""
echo "=== Summary ==="
echo -e "Passed: ${GREEN}$PASS${NC}"
echo -e "Failed: ${RED}$FAIL${NC}"

if [ $FAIL -eq 0 ]; then
    echo ""
    echo -e "${GREEN}PR is ready for review!${NC}"
    exit 0
else
    echo ""
    echo -e "${RED}PR has issues that need fixing.${NC}"
    exit 1
fi
