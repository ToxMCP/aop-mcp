# Guided AOP comparison

This additive development tool preserves the 42 released tools and adds `compare_aops`.
It is read-only, uses AOP-Wiki and caller-provided context, and requires both
`toxmcp:read` and `toxmcp:live` when bearer scopes are enforced.

Supply two to four distinct `AOP:<positive integer>` identifiers. `species` and
`life_stage` must be supplied before data is fetched. `sex` is optional. Supported
species aliases are human, Homo sapiens, mouse, rat, and dog; other species use
an `NCBITaxon` CURIE. Life stage is a label or ontology CURIE. Explicit
`unspecified` expresses unknown context without substituting a default.

## Interactive clients

On protocol 2026-07-28, a client advertising form elicitation gets one form for the
missing context fields. The SDK handles the answer and retry. The handler does
not open a server-initiated back-channel. A client callback must display the
question to the user before accepting an answer; this simplified example assumes
the caller has already obtained those values:

```python
from mcp import Client
from mcp.types import ElicitResult

async def answer_context(context, question):
    return ElicitResult(action="accept", content={"species": "human", "life_stage": "adult"})

async with Client("http://127.0.0.1:8000/mcp", elicitation_callback=answer_context) as client:
    result = await client.call_tool("compare_aops", {"aop_ids": ["AOP:345", "AOP:477"]})
```

Decline or cancel returns `status: cancelled` and fetches no scientific records.
Only the fields asked for are accepted. Existing argument values cannot be
overwritten by the form. Malformed answers produce an actionable invalid-input
error rather than a repeated question loop.

## Existing clients and noninteractive scripts

Pass `species` and `life_stage` in tool arguments. A missing context field returns
a normal structured result with `status: input_required` and `missing_inputs`,
which an agent can use to ask the user and make a new call with complete arguments.
There is no requirement for legacy clients to understand the new transport result.

## Scientific interpretation

The completed result contains each AOP's source links, initiating events, outcomes,
KE references, KER identifiers, and missing measurement/applicability or
plausibility/empirical/quantitative fields. Every pair lists shared identifiers
and unique KE identifiers. Matching labels alone never imply shared events.

Context counters measure exact reported identifiers or labels. They do not infer
taxonomic ancestry, development-stage equivalence, or whole-pathway applicability.
Human development terms are not silently assigned to another taxon. An absent
field means it was not returned in the RDF, not that literature evidence does not
exist. This tool does not rank confidence, perform chemical read-across, or predict
toxicity. Missing AOP records and upstream failures return errors without a
partial comparison. External requests are bounded to eight concurrent fetches
per comparison and a 60-second comparison deadline.

## Resume state

The low-level SDK boundary seals each resume token, binding it to its originating
tool and arguments, the exact context-question schema, expiry, and bearer identity.
The default key is process-local: a restart or a different worker rejects an
in-flight token, and the client starts the question again. Stateless HTTP requests
work within a single process.

For multiple workers or restart-surviving retries, configure the same secret
`AOP_MCP_REQUEST_STATE_KEY` (at least 32 bytes) on each worker. Keep it in the
deployment's secret store. Tokens expire after ten minutes per round. Changing
bearer identity, arguments, the question schema, or the key rejects old state.

Client-specific form presentation still requires testing in the intended host.
Automated SDK callback tests validate the protocol flow, not every application's UI.
