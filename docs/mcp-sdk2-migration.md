# SDK2 migration candidate

0.10.0 adopts stable Python MCP SDK 2.2.0 (protocol 2026-07-28). Python 3.11 remains supported. The last published version is 0.9.2; this branch is for review.

## Existing HTTP clients

Keep the same `/mcp` URL, bearer configuration and requests. The custom legacy dispatcher still answers `initialize` with the released 2025-03-26 revision and retains its `mcp/tool/*` aliases. Unversioned legacy calls are unchanged. SDK2 is selected only when a request claims a modern protocol in its header or namespaced request metadata. Unsupported modern claims are validated by the SDK.

Modern responses use JSON and stateless request isolation. Discovery, private catalog cache hints and the SDK's modern metadata are enabled. The 42 tools retain their names, input/output JSON schemas and core annotations. Domain defaults, scientific interpretation, bundled fixtures and draft versioning remain unchanged.

## Hosting configuration

Existing bearer authentication, scopes, browser Origin checks and production fail-closed settings apply before both dispatchers. Actual streamed and declared request bodies are bounded by `AOP_MCP_MAX_REQUEST_BYTES` before parsing.

For SDK2 clients reaching a public authority, set `AOP_MCP_ALLOWED_HOSTS` (comma separated, for example `aop.example.org`). The default is `localhost:*`, `127.0.0.1:*`, `[::1]:*`. Set `AOP_MCP_ALLOWED_ORIGINS` to exact allowed browser origins as before. These are independent controls. Review gateway forwarding of Host, Origin and Authorization before deployment.

## Tool policy and confirmation

Legacy tools retain their existing extension annotations. Modern SDK annotations carry the four standard hints, while `tool._meta["org.toxmcp/toolPolicy"]` carries `riskClass`, `requiredScopes`, `requiresConfirmation` and `sources` unchanged.

Every call still passes the existing scope/confirmation guards, JSON schema validation and audit boundary. Source labels remain in text and result `_meta.sources`. Confirmation does not grant missing scopes. Existing raw confirmation flags remain accepted; typed modern clients can explicitly provide:

```json
{"_meta":{"org.toxmcp/confirmation":{"confirmed":true}}}
```

Use the client's per-call metadata parameter and obtain the user's confirmation before setting it. The server does not remember client permissions or auto-confirm calls.

## Optional stdio

Run `aop-mcp-stdio` after installation, or `python -m src.server.mcp.sdk2`. Both SDK1 and SDK2 clients can negotiate stdio. This is a new local transport; the released HTTP configuration remains supported. As with the existing development HTTP mode, local stdio is trusted and uses the existing full local scopes without bearer confirmation enforcement. Do not expose it as an authenticated gateway.

## Verification

Live pre-merge testing uncovered an existing slow key-event query, independent of the MCP protocol. KE 177 combines 18 genes, five raw taxon values, two sex values and 43 linked AOPs; the old query repeats its long descriptions across that product. The candidate reads independent annotations in separate query branches, keeping AOP/title and reference/citation fields together for the existing normalizers. No result limit or scientific schema change is used. A sparse-row regression test verifies annotation and reference pairing, and live checks compare normalized records and exercise confidence assessment through both client generations.

The real-client matrix uses isolated MCP 1.30.0 and 2.2.0 clients over HTTP and stdio. It compares all tool schemas and 16 fixture workflows, including confidence assessment, draft creation/edits, OECD validation, source attribution and tool audits. Test-only launchers fix application clocks/identities and force bundled offline fixtures; production entry points never import them. Comparison validates and excludes only additive protocol envelope fields, retaining application values, hashes, timestamps and source labels.

```bash
uv sync --locked --extra dev
uv sync --locked --project tests/compatibility/legacy-client
uv run --no-sync python scripts/verify_protocol_clients.py \
  --legacy-python "$PWD/tests/compatibility/legacy-client/.venv/bin/python" \
  --server-root "$PWD" --output-dir /tmp/aop-client-results
```

Installed-wheel CI runs from outside the checkout. Unit tests exercise bearer scope denial, explicit confirmation, Host/Origin rejection, malformed and oversized bodies, all four legacy revision headers and concurrent modern calls with distinct results and audit IDs.

[Official SDK2 migration guide](https://py.sdk.modelcontextprotocol.io/migration/)
