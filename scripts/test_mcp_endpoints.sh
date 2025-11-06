#!/bin/bash
# Comprehensive MCP endpoint testing script

set -e

BASE_URL="http://localhost:8003"
PASSED=0
FAILED=0

echo "========================================="
echo "AOP MCP Server Endpoint Test Suite"
echo "========================================="
echo ""

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

test_endpoint() {
    local test_name="$1"
    local method="$2"
    local params="$3"
    local expected_check="$4"
    
    echo -n "Testing $test_name... "
    
    local response=$(curl -s -X POST "$BASE_URL/mcp" \
        -H 'Content-Type: application/json' \
        -d "{
            \"jsonrpc\": \"2.0\",
            \"id\": $RANDOM,
            \"method\": \"$method\",
            \"params\": $params
        }")
    
    if echo "$response" | jq -e "$expected_check" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ PASSED${NC}"
        ((PASSED++))
        return 0
    else
        echo -e "${RED}✗ FAILED${NC}"
        echo "Response: $response"
        ((FAILED++))
        return 1
    fi
}

# Test 1: Health endpoint
echo -n "Testing health endpoint... "
if curl -s "$BASE_URL/health" | jq -e '.status == "ok"' > /dev/null; then
    echo -e "${GREEN}✓ PASSED${NC}"
    ((PASSED++))
else
    echo -e "${RED}✗ FAILED${NC}"
    ((FAILED++))
fi

# Test 2: Initialize handshake
test_endpoint "initialize" "initialize" \
    '{"protocolVersion": "2025-03-26", "clientInfo": {"name": "test", "version": "1.0"}, "capabilities": {}}' \
    '.result.protocolVersion == "2025-03-26" and .result.serverInfo.name == "AOP MCP Server"'

# Test 3: Initialized notification
test_endpoint "initialized" "initialized" '{}' \
    '.result == {}'

# Test 4: Tools list
test_endpoint "tools/list" "tools/list" '{}' \
    '.result.tools | length == 12'

# Test 5: Prompts list
test_endpoint "prompts/list" "prompts/list" '{}' \
    '.result.prompts | type == "array"'

# Test 6: Tool call - search_aops
test_endpoint "tools/call (search_aops)" "tools/call" \
    '{"name": "search_aops", "arguments": {"text": "liver", "limit": 1}}' \
    '.result.content[0].type == "text"'

# Test 7: Tool call - get_applicability
test_endpoint "tools/call (get_applicability)" "tools/call" \
    '{"name": "get_applicability", "arguments": {"species": "human", "sex": "male", "life_stage": "adult"}}' \
    '.result.content[0].type == "text"'

# Test 8: Invalid method
echo -n "Testing invalid method (should fail gracefully)... "
response=$(curl -s -X POST "$BASE_URL/mcp" \
    -H 'Content-Type: application/json' \
    -d '{"jsonrpc": "2.0", "id": 999, "method": "invalid_method", "params": {}}')
if echo "$response" | jq -e '.error.code == -32601' > /dev/null; then
    echo -e "${GREEN}✓ PASSED${NC}"
    ((PASSED++))
else
    echo -e "${RED}✗ FAILED${NC}"
    ((FAILED++))
fi

# Test 9: Invalid tool name
echo -n "Testing invalid tool name (should fail gracefully)... "
response=$(curl -s -X POST "$BASE_URL/mcp" \
    -H 'Content-Type: application/json' \
    -d '{"jsonrpc": "2.0", "id": 998, "method": "tools/call", "params": {"name": "nonexistent_tool", "arguments": {}}}')
if echo "$response" | jq -e '.error.code == -32601' > /dev/null; then
    echo -e "${GREEN}✓ PASSED${NC}"
    ((PASSED++))
else
    echo -e "${RED}✗ FAILED${NC}"
    ((FAILED++))
fi

echo ""
echo "========================================="
echo "Test Results"
echo "========================================="
echo -e "Passed: ${GREEN}$PASSED${NC}"
echo -e "Failed: ${RED}$FAILED${NC}"
echo "Total: $((PASSED + FAILED))"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed.${NC}"
    exit 1
fi
