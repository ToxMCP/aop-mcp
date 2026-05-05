#!/bin/bash
# Modern MCP smoke test script for the live AOP MCP server.

set -uo pipefail

BASE_URL="${BASE_URL:-http://localhost:8003}"
RUN_LIVE_READS="${AOP_MCP_SMOKE_INCLUDE_LIVE_READS:-0}"
DRAFT_ID="${AOP_MCP_SMOKE_DRAFT_ID:-smoke-draft-$(date +%s)}"
ARTIFACT_SUBDIR="${AOP_MCP_SMOKE_SUBDIR:-smoke/$(date -u +%Y%m%d_%H%M%S)}"
ARTIFACT_FILENAME="${AOP_MCP_SMOKE_FILENAME:-scientific_review.md}"

PASSED=0
FAILED=0

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_header() {
    echo "========================================="
    echo "AOP MCP Server Endpoint Smoke Suite"
    echo "========================================="
    echo "Base URL: $BASE_URL"
    echo "Draft ID: $DRAFT_ID"
    echo "Artifact subdirectory: $ARTIFACT_SUBDIR"
    echo ""
}

record_pass() {
    echo -e "${GREEN}✓ PASSED${NC}"
    PASSED=$((PASSED + 1))
}

record_fail() {
    local message="$1"
    echo -e "${RED}✗ FAILED${NC}"
    echo "$message"
    FAILED=$((FAILED + 1))
}

record_skip() {
    local message="$1"
    echo -e "${YELLOW}↷ SKIPPED${NC}"
    echo "$message"
}

rpc() {
    local payload="$1"
    curl -sS -X POST "$BASE_URL/mcp" \
        -H 'Content-Type: application/json' \
        -d "$payload"
}

json_check() {
    local json="$1"
    local expression="$2"
    printf '%s' "$json" | jq -e "$expression" > /dev/null 2>&1
}

json_get() {
    local json="$1"
    local expression="$2"
    printf '%s' "$json" | jq -r "$expression"
}

test_health() {
    echo -n "Testing health endpoint... "
    local response
    if ! response=$(curl -sS "$BASE_URL/health"); then
        record_fail "Could not reach $BASE_URL/health"
        return 1
    fi
    if json_check "$response" '.status == "ok"'; then
        record_pass
        return 0
    fi
    record_fail "Unexpected health payload: $response"
    return 1
}

test_rpc_check() {
    local name="$1"
    local payload="$2"
    local check="$3"

    echo -n "Testing $name... "
    local response
    if ! response=$(rpc "$payload"); then
        record_fail "Request failed"
        return 1
    fi
    if json_check "$response" "$check"; then
        record_pass
        return 0
    fi
    record_fail "Unexpected response: $response"
    return 1
}

print_header

if ! test_health; then
    echo ""
    echo "Smoke suite aborted because the server is not reachable."
    exit 1
fi

test_rpc_check \
    "initialize" \
    "$(jq -nc '{jsonrpc:"2.0",id:1,method:"initialize",params:{protocolVersion:"2025-03-26",clientInfo:{name:"smoke",version:"1.0"},capabilities:{}}}')" \
    '.result.protocolVersion == "2025-03-26" and .result.serverInfo.name == "AOP MCP Server"'

test_rpc_check \
    "initialized" \
    "$(jq -nc '{jsonrpc:"2.0",id:2,method:"initialized",params:{}}')" \
    '.result == {}'

TOOLS_RESPONSE=$(rpc "$(jq -nc '{jsonrpc:"2.0",id:3,method:"tools/list",params:{}}')")
echo -n "Testing tools/list for required workflow tools... "
if json_check \
    "$TOOLS_RESPONSE" \
    '.result.tools | map(.name) as $names | ["search_aops","get_applicability","review_draft_bundle","review_draft_evidence_gaps","review_registry_handoff_bundle","attach_registry_handoff_to_draft","export_draft_review_artifact","save_draft_review_artifact","list_saved_draft_review_artifacts","plan_linear_draft_review_document"] | all(. as $name | $names | index($name))'
then
    record_pass
else
    record_fail "Required tools were not all present: $TOOLS_RESPONSE"
fi

test_rpc_check \
    "prompts/list" \
    "$(jq -nc '{jsonrpc:"2.0",id:4,method:"prompts/list",params:{}}')" \
    '.result.prompts | type == "array"'

test_rpc_check \
    "tools/call (get_applicability)" \
    "$(jq -nc '{jsonrpc:"2.0",id:5,method:"tools/call",params:{name:"get_applicability",arguments:{species:"human",sex:"male",life_stage:"adult"}}}')" \
    '.result.content[0].type == "text" and .result.structuredContent.species == "NCBITaxon:9606" and .result.structuredContent.life_stage == "HsapDv:0000087" and .result.structuredContent.sex == "PATO:0000384"'

echo -n "Testing invalid method handling... "
INVALID_METHOD_RESPONSE=$(rpc "$(jq -nc '{jsonrpc:"2.0",id:6,method:"invalid_method",params:{}}')")
if json_check "$INVALID_METHOD_RESPONSE" '.error.code == -32601'; then
    record_pass
else
    record_fail "Unexpected invalid-method response: $INVALID_METHOD_RESPONSE"
fi

echo -n "Testing invalid tool handling... "
INVALID_TOOL_RESPONSE=$(rpc "$(jq -nc '{jsonrpc:"2.0",id:7,method:"tools/call",params:{name:"nonexistent_tool",arguments:{}}}')")
if json_check "$INVALID_TOOL_RESPONSE" '.error.code == -32601'; then
    record_pass
else
    record_fail "Unexpected invalid-tool response: $INVALID_TOOL_RESPONSE"
fi

if [ "$RUN_LIVE_READS" = "1" ]; then
    test_rpc_check \
        "tools/call (search_aops)" \
        "$(jq -nc '{jsonrpc:"2.0",id:8,method:"tools/call",params:{name:"search_aops",arguments:{text:"liver",limit:1}}}')" \
        '.result.content[0].type == "text"'
else
    record_skip "Live SPARQL-backed read checks are disabled by default. Set AOP_MCP_SMOKE_INCLUDE_LIVE_READS=1 to include search_aops."
fi

CREATE_RESPONSE=$(rpc "$(jq -nc \
    --arg draft_id "$DRAFT_ID" \
    '{jsonrpc:"2.0",id:11,method:"tools/call",params:{name:"create_draft_aop",arguments:{draft_id:$draft_id,title:"Live smoke steatosis draft",description:"Live server smoke test draft.",adverse_outcome:"Liver steatosis",author:"codex",summary:"create live smoke draft"}}}')")
echo -n "Testing create_draft_aop... "
if json_check "$CREATE_RESPONSE" '.result.structuredContent.version_id | type == "string"'; then
    record_pass
else
    record_fail "Unexpected create_draft_aop response: $CREATE_RESPONSE"
fi
VERSION_ID=$(json_get "$CREATE_RESPONSE" '.result.structuredContent.version_id')

ADD_KE_1_RESPONSE=$(rpc "$(jq -nc \
    --arg draft_id "$DRAFT_ID" \
    --arg version_id "$VERSION_ID" \
    '{jsonrpc:"2.0",id:12,method:"tools/call",params:{name:"add_or_update_ke",arguments:{draft_id:$draft_id,version_id:$version_id,author:"codex",summary:"add mie",identifier:"KE:1",title:"Activation, Pregnane-X receptor, NR1I2",event_role:"mie"}}}')")
echo -n "Testing add_or_update_ke (MIE)... "
if json_check "$ADD_KE_1_RESPONSE" '.result.structuredContent.version_id | type == "string"'; then
    record_pass
else
    record_fail "Unexpected add_or_update_ke MIE response: $ADD_KE_1_RESPONSE"
fi
VERSION_ID=$(json_get "$ADD_KE_1_RESPONSE" '.result.structuredContent.version_id')

ADD_KE_2_RESPONSE=$(rpc "$(jq -nc \
    --arg draft_id "$DRAFT_ID" \
    --arg version_id "$VERSION_ID" \
    '{jsonrpc:"2.0",id:13,method:"tools/call",params:{name:"add_or_update_ke",arguments:{draft_id:$draft_id,version_id:$version_id,author:"codex",summary:"add ao",identifier:"KE:2",title:"Liver steatosis",event_role:"ao"}}}')")
echo -n "Testing add_or_update_ke (AO)... "
if json_check "$ADD_KE_2_RESPONSE" '.result.structuredContent.version_id | type == "string"'; then
    record_pass
else
    record_fail "Unexpected add_or_update_ke AO response: $ADD_KE_2_RESPONSE"
fi
VERSION_ID=$(json_get "$ADD_KE_2_RESPONSE" '.result.structuredContent.version_id')

ADD_KER_RESPONSE=$(rpc "$(jq -nc \
    --arg draft_id "$DRAFT_ID" \
    --arg version_id "$VERSION_ID" \
    '{jsonrpc:"2.0",id:14,method:"tools/call",params:{name:"add_or_update_ker",arguments:{draft_id:$draft_id,version_id:$version_id,author:"codex",summary:"add ker",identifier:"KER:1",upstream:"KE:1",downstream:"KE:2",plausibility:"Strong mechanistic rationale."}}}')")
echo -n "Testing add_or_update_ker... "
if json_check "$ADD_KER_RESPONSE" '.result.structuredContent.version_id | type == "string"'; then
    record_pass
else
    record_fail "Unexpected add_or_update_ker response: $ADD_KER_RESPONSE"
fi
VERSION_ID=$(json_get "$ADD_KER_RESPONSE" '.result.structuredContent.version_id')

BUNDLE_RESPONSE=$(rpc "$(jq -nc \
    --arg draft_id "$DRAFT_ID" \
    '{jsonrpc:"2.0",id:15,method:"tools/call",params:{name:"review_draft_bundle",arguments:{draft_id:$draft_id}}}')")
echo -n "Testing review_draft_bundle... "
if json_check "$BUNDLE_RESPONSE" '.result.structuredContent.bundle_summary | has("ready_for_review") and has("validator_warning_count")'; then
    record_pass
else
    record_fail "Unexpected review_draft_bundle response: $BUNDLE_RESPONSE"
fi

EXPORT_RESPONSE=$(rpc "$(jq -nc \
    --arg draft_id "$DRAFT_ID" \
    '{jsonrpc:"2.0",id:16,method:"tools/call",params:{name:"export_draft_review_artifact",arguments:{draft_id:$draft_id,format:"markdown",artifact_profile:"publication"}}}')")
echo -n "Testing export_draft_review_artifact... "
if json_check "$EXPORT_RESPONSE" '.result.structuredContent.artifact_profile == "publication" and .result.structuredContent.format == "markdown"'; then
    record_pass
else
    record_fail "Unexpected export_draft_review_artifact response: $EXPORT_RESPONSE"
fi

SAVE_RESPONSE=$(rpc "$(jq -nc \
    --arg draft_id "$DRAFT_ID" \
    --arg subdirectory "$ARTIFACT_SUBDIR" \
    --arg filename "$ARTIFACT_FILENAME" \
    '{jsonrpc:"2.0",id:17,method:"tools/call",params:{name:"save_draft_review_artifact",arguments:{draft_id:$draft_id,format:"markdown",artifact_profile:"publication",subdirectory:$subdirectory,filename:$filename,overwrite:true}}}')")
echo -n "Testing save_draft_review_artifact... "
if json_check "$SAVE_RESPONSE" '.result.structuredContent.relative_path | type == "string"'; then
    record_pass
else
    record_fail "Unexpected save_draft_review_artifact response: $SAVE_RESPONSE"
fi
RELATIVE_PATH=$(json_get "$SAVE_RESPONSE" '.result.structuredContent.relative_path')

LIST_RESPONSE=$(rpc "$(jq -nc \
    --arg subdirectory "$ARTIFACT_SUBDIR" \
    '{jsonrpc:"2.0",id:18,method:"tools/call",params:{name:"list_saved_draft_review_artifacts",arguments:{subdirectory:$subdirectory,limit:10}}}')")
echo -n "Testing list_saved_draft_review_artifacts... "
FIRST_RELATIVE_PATH=$(json_get "$LIST_RESPONSE" '.result.structuredContent.results[0].relative_path')
if [ "$FIRST_RELATIVE_PATH" = "$RELATIVE_PATH" ]; then
    record_pass
else
    record_fail "Unexpected artifact listing response: $LIST_RESPONSE"
fi

LINEAR_RESPONSE=$(rpc "$(jq -nc \
    --arg artifact_relative_path "$RELATIVE_PATH" \
    '{jsonrpc:"2.0",id:19,method:"tools/call",params:{name:"plan_linear_draft_review_document",arguments:{artifact_relative_path:$artifact_relative_path,project:"Toxicology Reviews"}}}')")
echo -n "Testing plan_linear_draft_review_document... "
if json_check "$LINEAR_RESPONSE" '.result.structuredContent.linear_document.project == "Toxicology Reviews" and .result.structuredContent.source.mode == "saved_artifact"'; then
    record_pass
else
    record_fail "Unexpected plan_linear_draft_review_document response: $LINEAR_RESPONSE"
fi

echo ""
echo "========================================="
echo "Smoke Summary"
echo "========================================="
echo "Saved artifact: $RELATIVE_PATH"
echo "Latest draft version: $VERSION_ID"
echo -e "Passed: ${GREEN}$PASSED${NC}"
echo -e "Failed: ${RED}$FAILED${NC}"
echo "Total: $((PASSED + FAILED))"
echo ""

if [ "$FAILED" -eq 0 ]; then
    echo -e "${GREEN}All smoke checks passed.${NC}"
    exit 0
fi

echo -e "${RED}Some smoke checks failed.${NC}"
exit 1
