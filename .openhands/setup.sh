#!/bin/bash
# Sovereign Studio V3 - OpenHands Setup Script
# This script runs automatically when starting an OpenHands conversation

set -e  # Exit on error

echo "=========================================="
echo "🚀 Sovereign Studio V3 - Session Setup"
echo "=========================================="

# Navigate to repository root
cd "$(dirname "$0")/.." 2>/dev/null || cd "$(git rev-parse --show-toplevel)" 2>/dev/null || { echo "Error: Could not find repository root"; exit 1; }

echo ""
echo "📂 Repository: $(basename $(pwd))"
echo "🌿 Branch: $(git branch --show-current)"
echo ""

# Pull latest from main
echo "📥 Pulling latest from main..."
git fetch origin main 2>/dev/null || true
LOCAL=$(git rev-parse @)
REMOTE=$(git rev-parse origin/main 2>/dev/null || echo "$LOCAL")
if [ "$LOCAL" = "$REMOTE" ]; then
    echo "   ✅ Already up to date"
else
    echo "   ⚠️  Remote has new commits. Consider running 'git pull' manually."
fi

echo ""
echo "📋 Running Green Gates..."

# Run quality gates
echo ""
echo "   1️⃣  TypeScript check..."
if pnpm run type-check > /tmp/type-check.log 2>&1; then
    echo "      ✅ TypeScript OK"
else
    echo "      ❌ TypeScript errors found"
    tail -5 /tmp/type-check.log | sed 's/^/         /'
fi

echo ""
echo "   2️⃣  Running tests..."
if pnpm run test:run > /tmp/test-run.log 2>&1; then
    echo "      ✅ Tests passed"
else
    echo "      ⚠️  Some tests failed"
    grep -E "(FAIL|PASS|Tests:)" /tmp/test-run.log | tail -3 | sed 's/^/         /'
fi

echo ""
echo "   3️⃣  Building..."
if pnpm run build:web > /tmp/build.log 2>&1; then
    echo "      ✅ Build successful"
else
    echo "      ⚠️  Build failed"
    grep -E "(error|Error|ERROR)" /tmp/build.log | head -3 | sed 's/^/         /'
fi

echo ""
echo "   4️⃣  Static audit..."
if pnpm run audit:sovereign > /tmp/audit.log 2>&1; then
    echo "      ✅ Audit passed"
else
    echo "      ⚠️  Audit warnings found"
    grep -E "(warning|Warning|violation)" /tmp/audit.log | head -3 | sed 's/^/         /' || true
fi

echo ""
echo "=========================================="
echo "✅ Setup complete!"
echo ""
echo "Quick commands:"
echo "  pnpm run dev           # Start dev server"
echo "  pnpm run test:run      # Run all tests"
echo "  pnpm run build:web     # Production build"
echo "  pnpm run audit:sovereign # Run static audit"
echo ""
echo "Key files:"
echo "  AGENTS.md              # Agent rules"
echo "  docs/SOVEREIGN_READER.md # Tool documentation"
echo "  docs/SOVEREIGN_RUNTIME.md # Runtime truth path"
echo "=========================================="
