"""Test-only offline launcher with deterministic application identities and clocks."""
from __future__ import annotations

import argparse
import itertools
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID


def configure() -> None:
    os.environ['AOP_MCP_ENABLE_FIXTURE_FALLBACK'] = '1'
    os.environ['AOP_MCP_ENVIRONMENT'] = 'test'
    os.environ['AOP_MCP_AUTH_MODE'] = 'disabled'
    from src.adapters.sparql_client import SparqlClient, SparqlUpstreamError
    from src.instrumentation import audit, cache
    from src.server.mcp import router
    from src.server.tools import aop
    from src.services.draft_store import model
    from src.services.jobs import model as jobs
    from src.semantic import curie_service

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 1, 12, tzinfo=timezone.utc).astimezone(tz) if tz else cls(2026, 10, 1, 12)

        @classmethod
        def utcnow(cls):
            return cls(2026, 10, 1, 12)

    for module in [audit, cache, aop, model, jobs]:
        module.datetime = FixedDatetime
    audit_ids = itertools.count(1)
    curie_ids = itertools.count(1_000)
    timer = itertools.count(0)
    router.uuid4 = lambda: UUID(int=next(audit_ids), version=4)
    router.perf_counter = lambda: next(timer) / 1000
    curie_service.uuid = SimpleNamespace(uuid4=lambda: UUID(int=next(curie_ids), version=4))

    async def unavailable(*args, **kwargs):
        raise SparqlUpstreamError('Deterministic client compatibility fixture')

    SparqlClient.query = unavailable


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--transport', choices=['http', 'stdio'], required=True)
    parser.add_argument('--port', type=int)
    args = parser.parse_args()
    configure()
    if args.transport == 'http':
        import uvicorn
        from src.server.api.server import create_app
        uvicorn.run(create_app(), host='127.0.0.1', port=args.port, log_level='warning')
    else:
        from src.server.mcp.sdk2 import main as serve
        serve()


if __name__ == '__main__':
    main()
