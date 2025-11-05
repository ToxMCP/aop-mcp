# Quickstart: Find an AOP

1. Call the forthcoming `search_aops` tool with query terms for the molecular
   initiating event or adverse outcome of interest.
2. Use `get_aop` with an AOP identifier (e.g. `AOP:000296`) to retrieve the
   enriched pathway payload.
3. Traverse supporting events via `list_key_events` and `list_kers` to inspect
   evidence and applicability metadata.

The FastAPI surface will mirror these tools via HTTP endpoints for direct use
alongside the MCP transport.
