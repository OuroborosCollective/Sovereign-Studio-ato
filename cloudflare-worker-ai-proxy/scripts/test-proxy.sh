#!/bin/bash
# Test script for Sovereign LLM Proxy

set -e

echo "🧪 Sovereign LLM Proxy - Test Script"
echo "===================================="
echo ""

# Configuration
PROXY_URL="${PROXY_URL:-https://sovereign-llm-proxy.your-subdomain.workers.dev}"
URL_SECRET="${URL_SECRET:-test-secret}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Test counter
TESTS_PASSED=0
TESTS_FAILED=0

# Test function
test_endpoint() {
    local name=$1
    local expected_status=$2
    local actual_status=$3
    
    if [ "$actual_status" = "$expected_status" ]; then
        echo -e "${GREEN}✓ $name (Status: $actual_status)${NC}"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}✗ $name (Erwartet: $expected_status, Erhalten: $actual_status)${NC}"
        ((TESTS_FAILED++))
    fi
}

echo "Proxy URL: $PROXY_URL"
echo "URL Secret: ${URL_SECRET:0:10}..."
echo ""

# Test 1: Missing Authorization
echo "Test 1: Missing Authorization Header"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$PROXY_URL/v1/chat/completions" \
    -H "Content-Type: application/json" \
    -d '{"messages":[{"role":"user","content":"Hello"}]}')
STATUS=$(echo "$RESPONSE" | tail -1)
test_endpoint "Missing Auth" "401" "$STATUS"

# Test 2: Invalid Authorization
echo ""
echo "Test 2: Invalid Authorization"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$PROXY_URL/v1/chat/completions" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer invalid-secret" \
    -d '{"messages":[{"role":"user","content":"Hello"}]}')
STATUS=$(echo "$RESPONSE" | tail -1)
test_endpoint "Invalid Auth" "401" "$STATUS"

# Test 3: Invalid Method
echo ""
echo "Test 3: Invalid HTTP Method (GET instead of POST)"
RESPONSE=$(curl -s -w "\n%{http_code}" -X GET "$PROXY_URL/v1/chat/completions" \
    -H "Authorization: Bearer $URL_SECRET")
STATUS=$(echo "$RESPONSE" | tail -1)
test_endpoint "Invalid Method" "405" "$STATUS"

# Test 4: Valid Request (if credentials provided)
echo ""
echo "Test 4: Valid Chat Completion Request"
if [ "$URL_SECRET" != "test-secret" ]; then
    RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$PROXY_URL/v1/chat/completions" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $URL_SECRET" \
        -d '{"model":"@cf/meta/llama-3-8b-instruct","messages":[{"role":"user","content":"Say hello in one word"}]}')
    STATUS=$(echo "$RESPONSE" | tail -1)
    BODY=$(echo "$RESPONSE" | sed '$d')
    
    if [ "$STATUS" = "200" ]; then
        test_endpoint "Valid Request" "200" "$STATUS"
        echo -e "${GREEN}  Response Preview: $(echo $BODY | jq -r '.choices[0].message.content' 2>/dev/null | head -c 100)${NC}"
    else
        test_endpoint "Valid Request" "200" "$STATUS"
        echo -e "${YELLOW}  Response: $BODY${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Übersprungen (URL_SECRET nicht gesetzt)${NC}"
fi

# Summary
echo ""
echo "========================================"
echo "Test Summary"
echo "========================================"
echo -e "${GREEN}Passed: $TESTS_PASSED${NC}"
echo -e "${RED}Failed: $TESTS_FAILED${NC}"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}✅ Alle Tests bestanden!${NC}"
    exit 0
else
    echo -e "${RED}❌ Einige Tests fehlgeschlagen${NC}"
    exit 1
fi
