# Quickstart: Find an AOP

1. Call `search_aops` first with broad outcome or MIE terms and a higher limit
   when recall matters (for example `steatosis`, `hepatic steatosis`, `MASLD`,
   with `limit=25` or higher).
2. Use `get_aop` only after you already have an AOP identifier (for example
   `AOP:000296`) and want the enriched pathway payload for that single record.
3. Traverse supporting events via `list_key_events` and `list_kers` to inspect
   evidence and applicability metadata.

The FastAPI surface will mirror these tools via HTTP endpoints for direct use
alongside the MCP transport.
