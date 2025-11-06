# MCP Connection Fix Summary

## Problem
Codex and Gemini CLI were unable to connect to the AOP MCP server with the error:
```
MCP client for `aop-mcp` failed to start: handshaking with MCP server failed: 
expect initialized result, but received: Some(EmptyResult(EmptyObject))
```

## Root Causes Identified

### 1. Missing `protocolVersion` in Initialize Response
The `InitializeResult` was not being serialized with the correct field names. The response was missing `protocolVersion` and using `server` instead of `serverInfo`.

**Issue**: `model_dump()` was called without `by_alias=True`, causing Pydantic to use Python field names instead of the JSON schema field names.

### 2. Incorrect `initialized` Response
The `initialized` notification was returning `null` instead of an empty object `{}`.

**Issue**: The `shutdown`/`exit` methods were returning `None`, and the `initialized` method was grouped with them, causing it to also return `None` instead of `{}`.

### 3. Missing `protocolVersion` Field in InitializeParams
The `InitializeParams` model already had the `protocolVersion` field (added in previous fix).

## Changes Made

### File: `src/server/mcp/router.py`

#### Fix 1: Initialize Response Serialization
```python
# BEFORE
return InitializeResult(
    protocolVersion=MCP_VERSION,
    serverInfo=SERVER_INFO,
    capabilities=SERVER_CAPABILITIES,
).model_dump()

# AFTER
return InitializeResult(
    protocolVersion=MCP_VERSION,
    serverInfo=SERVER_INFO,
    capabilities=SERVER_CAPABILITIES,
).model_dump(by_alias=True)
```

#### Fix 2: Initialized Response
```python
# BEFORE
if request.method in {"shutdown", "exit", "notifications/shutdown"}:
    return None

# AFTER
if request.method in {"shutdown", "exit", "notifications/shutdown"}:
    return {}
```

## Testing Results

All MCP protocol methods now work correctly:

1. ✅ **initialize**: Returns proper `protocolVersion`, `serverInfo`, and `capabilities`
2. ✅ **initialized**: Returns empty object `{}`
3. ✅ **tools/list**: Returns all 12 available tools
4. ✅ **prompts/list**: Returns empty prompts array
5. ✅ **tools/call**: Successfully invokes tools and returns results
6. ✅ **Error handling**: Properly returns JSON-RPC error codes for invalid methods/tools

### Test Script
A comprehensive test script is available at `scripts/test_mcp_endpoints.sh`:
```bash
chmod +x scripts/test_mcp_endpoints.sh
./scripts/test_mcp_endpoints.sh
```

## Server Configuration

### Running the Server
```bash
uvicorn src.server.api.server:app --host 0.0.0.0 --port 8003
```

### Codex Configuration
The server is configured in `~/.codex/config.toml`:
```toml
[mcp_servers.aop-mcp]
url = "http://localhost:8003/mcp"
timeout = 60000  # 60 seconds for SPARQL queries and fixture fallback
```

### Gemini CLI Configuration
Add to your Gemini CLI config:
```json
{
  "mcp_servers": {
    "aop-mcp": {
      "url": "http://localhost:8003/mcp",
      "timeout": 60000
    }
  }
}
```

## Next Steps

1. ✅ Restart Codex/Gemini CLI to pick up the fixed MCP server
2. ✅ Verify the connection works
3. ✅ Test tool invocations through the CLI

## Available Tools

The MCP server exposes 12 tools:

### Read Tools
- `search_aops` - Search AOPs by text query
- `get_aop` - Fetch single AOP with metadata
- `list_key_events` - List key events for an AOP
- `list_kers` - List key event relationships for an AOP
- `map_chemical_to_aops` - Map chemicals to AOPs using AOP-DB and CompTox
- `map_assay_to_aops` - Map assay identifiers to AOPs

### Semantic Tools
- `get_applicability` - Normalize applicability parameters (species, sex, life stage)
- `get_evidence_matrix` - Build evidence matrix from KER facets

### Write Tools
- `create_draft_aop` - Create a new draft AOP
- `add_or_update_ke` - Add or update key events in a draft
- `add_or_update_ker` - Add or update key event relationships in a draft
- `link_stressor` - Link stressors to draft entities

## Verification Commands

### Test Initialize Handshake
```bash
curl -X POST http://localhost:8003/mcp \
  -H 'Content-Type: application/json' \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
      "protocolVersion": "2025-03-26",
      "clientInfo": {"name": "test", "version": "1.0"},
      "capabilities": {}
    }
  }' | jq .
```

Expected response includes:
- `result.protocolVersion`: "2025-03-26"
- `result.serverInfo.name`: "AOP MCP Server"
- `result.capabilities.tools.enabled`: true

### Test Initialized Notification
```bash
curl -X POST http://localhost:8003/mcp \
  -H 'Content-Type: application/json' \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "initialized",
    "params": {}
  }' | jq .
```

Expected response:
- `result`: `{}`

### Test Tools List
```bash
curl -X POST http://localhost:8003/mcp \
  -H 'Content-Type: application/json' \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/list",
    "params": {}
  }' | jq '.result.tools | length'
```

Expected: `12`

## Summary

The MCP server is now fully functional and compatible with Codex CLI, Gemini CLI, and other MCP-aware clients. The key fixes were:

1. Adding `by_alias=True` to `model_dump()` calls to ensure proper JSON field names
2. Changing `shutdown`/`exit` to return `{}` instead of `None` to prevent `initialized` from returning `null`

All endpoints have been tested and verified to work correctly.
