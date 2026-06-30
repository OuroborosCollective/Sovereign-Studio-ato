#!/bin/bash
# Sovereign Studio - Verification Gates Script
# Run this script to execute all required verification checks before pushing to main

set -e

echo "=========================================="
echo "Sovereign Studio - Verification Gates"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Track overall status
ALL_PASSED=true

# Function to run a check
run_check() {
    local name="$1"
    local command="$2"
    
    echo -n "Running: $name... "
    if eval "$command" > /dev/null 2>&1; then
        echo -e "${GREEN}PASSED${NC}"
    else
        echo -e "${RED}FAILED${NC}"
        ALL_PASSED=false
    fi
}

# 1. TypeScript check
run_check "TypeScript (tsc --noEmit)" "npx tsc --noEmit"

# 2. Unit tests (smoke tests)
run_check "Unit tests (vitest run)" "npm test -- --run 2>&1 | grep -q 'Test Files.*passed'"

# 3. Production build
run_check "Production build (vite build)" "npm run build:web 2>&1 | grep -q '✓ built'"

# 4. Static audit
run_check "Static audit" "node scripts/sovereign-static-audit.mjs 2>&1 | grep -q 'passed'"

# Optional: Live path scan (if exists)
if [ -f "scripts/sovereign-live-path-scan.mjs" ]; then
    run_check "Live path scan" "node scripts/sovereign-live-path-scan.mjs 2>&1 | grep -qE '(passed|no issues|keine Probleme)'"
fi

echo ""
echo "=========================================="
if [ "$ALL_PASSED" = true ]; then
    echo -e "${GREEN}All checks passed! Ready to push.${NC}"
    echo "=========================================="
    exit 0
else
    echo -e "${RED}Some checks failed. Please fix before pushing.${NC}"
    echo "=========================================="
    exit 1
fi
