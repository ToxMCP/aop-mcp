"""SPARQL endpoint connectivity check and sample capture for the AOP MCP."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.adapters import AOPWikiAdapter, SparqlClient  # noqa: E402
from src.adapters.sparql_client import SparqlEndpoint  # noqa: E402
from src.server.config.settings import get_settings  # noqa: E402


ASK_QUERY = "ASK { ?s ?p ?o }"


@dataclass
class EndpointResult:
    name: str
    url: str
    ok: bool
    detail: str | None = None


async def _check_endpoint(name: str, url: str) -> EndpointResult:
    endpoint = SparqlEndpoint(url=url, name=name)
    async with SparqlClient([endpoint], max_retries=1, timeout=10.0) as client:
        try:
            payload = await client.query(ASK_QUERY, use_cache=False)
        except Exception as exc:  # pragma: no cover - network validation
            return EndpointResult(name=name, url=url, ok=False, detail=str(exc))

    boolean = payload.get("boolean")
    ok = bool(boolean)
    detail = None if ok else f"ASK query returned unexpected payload: {payload!r}"
    return EndpointResult(name=name, url=url, ok=ok, detail=detail)


async def check_all(endpoints: Sequence[tuple[str, Iterable[str]]]) -> list[EndpointResult]:
    results: list[EndpointResult] = []
    for group_name, urls in endpoints:
        for url in urls:
            result = await _check_endpoint(group_name, url)
            results.append(result)
    return results


async def capture_samples(search_text: str, limit: int, aop_id: str, output_dir: Path) -> None:
    settings = get_settings()
    output_dir.mkdir(parents=True, exist_ok=True)

    async with SparqlClient(settings.aop_wiki_sparql_endpoints, max_retries=1, timeout=15.0) as client:
        adapter = AOPWikiAdapter(client)
        search_results = await adapter.search_aops(text=search_text, limit=limit)
        aop_record = await adapter.get_aop(aop_id)

    (output_dir / "search_aops.json").write_text(
        json.dumps({"text": search_text, "limit": limit, "results": search_results}, indent=2),
        encoding="utf-8",
    )
    (output_dir / "get_aop.json").write_text(
        json.dumps({"aop_id": aop_id, "record": aop_record}, indent=2),
        encoding="utf-8",
    )


def format_result(result: EndpointResult) -> str:
    status = "OK" if result.ok else "FAIL"
    message = f"[{status}] {result.name} -> {result.url}"
    if result.detail:
        message += f"\n    {result.detail}"
    return message


async def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--search-text",
        default="liver",
        help="Text to use when capturing search_aops sample (default: %(default)s)",
    )
    parser.add_argument(
        "--search-limit",
        default=5,
        type=int,
        help="Result limit for search_aops sample capture (default: %(default)s)",
    )
    parser.add_argument(
        "--aop-id",
        default="AOP:296",
        help="AOP identifier for get_aop sample capture (default: %(default)s)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("tests/golden/live"),
        help="Directory to write sample JSON payloads (default: %(default)s)",
    )
    parser.add_argument(
        "--skip-endpoint-checks",
        action="store_true",
        help="Skip SPARQL endpoint health checks",
    )
    parser.add_argument(
        "--skip-sample-capture",
        action="store_true",
        help="Skip sample response capture",
    )

    args = parser.parse_args(argv)
    settings = get_settings()

    exit_code = 0

    if not args.skip_endpoint_checks:
        endpoint_groups = [
            ("AOP-Wiki", settings.aop_wiki_sparql_endpoints),
            ("AOP-DB", settings.aop_db_sparql_endpoints),
        ]
        results = await check_all(endpoint_groups)
        for result in results:
            print(format_result(result))
            if not result.ok:
                exit_code = 1

    if not args.skip_sample_capture:
        try:
            await capture_samples(
                search_text=args.search_text,
                limit=args.search_limit,
                aop_id=args.aop_id,
                output_dir=args.output_dir,
            )
            print(f"Sample payloads written to {args.output_dir}")
        except Exception as exc:  # pragma: no cover - network validation
            print(f"Failed to capture sample payloads: {exc}")
            exit_code = 1

    return exit_code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
