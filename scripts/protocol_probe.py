"""Record actual SDK1/SDK2 client catalogs and unmodified application results."""
from __future__ import annotations

import argparse
import json
from contextlib import asynccontextmanager
from importlib.metadata import version
from pathlib import Path

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@asynccontextmanager
async def connection(args):
    target = args.url or StdioServerParameters(
        command=args.server_python,
        args=[args.launcher, '--transport', 'stdio'],
        env={'PYTHONPATH': args.server_root} if args.server_root else {},
    )
    if args.modern:
        from mcp import Client
        async with Client(target) as client:
            assert client.protocol_version == '2026-07-28'
            yield client, client.protocol_version, None
    else:
        if args.url:
            from mcp.client.streamable_http import streamablehttp_client
            transport = streamablehttp_client(args.url)
        else:
            transport = stdio_client(target)
        async with transport as streams, ClientSession(streams[0], streams[1]) as client:
            initialized = await client.initialize()
            yield client, initialized.model_dump(mode='json', by_alias=True)['protocolVersion'], initialized.serverInfo.version


async def collect(args):
    fixture = json.loads(Path(args.fixtures).read_text())
    async with connection(args) as (client, protocol, server_version):
        tools = (await client.list_tools()).model_dump(mode='json', by_alias=True, exclude_none=True)['tools']
        # Core SDK1 annotation parsing can add default hints; retain the complete wire result.
        results = {}
        for call in fixture['calls']:
            response = await client.call_tool(call['name'], call['arguments'])
            wire = response.model_dump(mode='json', by_alias=True, exclude_none=True)
            assert not wire.get('isError', False), (call['label'], wire)
            assert wire['structuredContent'] is not None
            assert wire['_meta']['sources']
            assert 'Sources:' in wire['content'][0]['text']
            results[call['label']] = wire
        return {'clientSDK': version('mcp'), 'protocol': protocol, 'serverVersion': client.server_info.version if args.modern else server_version, 'catalog': tools, 'results': results}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--server-python', required=True)
    parser.add_argument('--server-root')
    parser.add_argument('--launcher', required=True)
    parser.add_argument('--url')
    parser.add_argument('--modern', action='store_true')
    parser.add_argument('--fixtures', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    report = anyio.run(collect, args)
    Path(args.output).write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')
    print(json.dumps({'clientSDK': report['clientSDK'], 'protocol': report['protocol'],
                      'tools': len(report['catalog']), 'workflows': len(report['results'])}))


if __name__ == '__main__':
    main()
