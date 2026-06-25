#!/bin/bash
# Sovereign Studio V3 - OpenHands Setup Script
# This script runs automatically when starting an OpenHands conversation

set -e

echo "=========================================="
echo "Sovereign Studio V3 - Session Setup"
echo "=========================================="

cd "$(dirname "$0")/.." 2>/dev/null || cd "$(git rev-parse --show-toplevel)" 2>/dev/null || { echo "Error: Could not find repository root"; exit 1; }

echo ""
echo "Repository: $(basename $(pwd))"
echo "Branch: $(git branch --show-current)"
echo ""

echo "Pulling latest from main..."
git fetch origin main 2>/dev/null || true
LOCAL=$(git rev-parse @)
REMOTE=$(git rev-parse origin/main 2>/dev/null || echo "$LOCAL")
if [ "$LOCAL" = "$REMOTE" ]; then
    echo "   OK: Already up to date"
else
    echo "   Warning: Remote has new commits. Consider running 'git pull' manually."
fi

echo ""
echo "Running release gates..."

gate_failed=0

echo ""
echo "   1. TypeScript check..."
if pnpm run type-check > /tmp/type-check.log 2>&1; then
    echo "      OK: TypeScript passed"
else
    echo "      FAIL: TypeScript errors found"
    tail -5 /tmp/type-check.log | sed 's/^/         /'
    gate_failed=1
fi

echo ""
echo "   2. Running tests..."
if pnpm run test:run > /tmp/test-run.log 2>&1; then
    echo "      OK: Tests passed"
else
    echo "      FAIL: Tests failed"
    grep -E "(FAIL|PASS|Tests:)" /tmp/test-run.log | tail -3 | sed 's/^/         /' || true
    gate_failed=1
fi

echo ""
echo "   3. Building..."
if pnpm run build:web > /tmp/build.log 2>&1; then
    echo "      OK: Build passed"
else
    echo "      FAIL: Build failed"
    grep -E "(error|Error|ERROR)" /tmp/build.log | head -3 | sed 's/^/         /' || true
    gate_failed=1
fi

echo ""
echo "   4. Static audit..."
if pnpm run audit:sovereign > /tmp/audit.log 2>&1; then
    echo "      OK: Audit passed"
else
    echo "      FAIL: Audit failed"
    grep -E "(audit|error|Error|ERROR|warning|Warning|violation)" /tmp/audit.log | head -5 | sed 's/^/         /' || true
    gate_failed=1
fi

echo ""
echo "=========================================="
if [ "$gate_failed" -ne 0 ]; then
    echo "Setup blocked: one or more release gates failed."
    echo "Fix the failing gate output above before starting a release or agent fix cycle."
    exit 1
fi

echo "Setup complete."
echo ""
echo "Quick commands:"
echo "  pnpm run dev"
echo "  pnpm run test:run"
echo "  pnpm run build:web"
echo "  pnpm run audit:sovereign"
echo ""
echo "Key files:"
echo "  AGENTS.md"
echo "  docs/SOVEREIGN_READER.md"
echo "  docs/SOVEREIGN_RUNTIME.md"
echo "=========================================="
