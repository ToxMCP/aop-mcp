"""Read-only live probe with actual SDK clients; no fixture fallback.

Run once per client/transport against an installed candidate, outside its checkout.
HTTP bearer credentials, if needed, come only from AOP_GUIDED_TEST_BEARER.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from contextlib import asynccontextmanager
from importlib.metadata import version
from pathlib import Path

import anyio
from jsonschema import validate
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@asynccontextmanager
async def connect(args, callback):
    with tempfile.TemporaryDirectory(prefix="aop-guided-client-") as workspace, open(os.devnull, "w") as quiet:
        if args.url:
            headers = {"Authorization": "Bearer " + os.environ["AOP_GUIDED_TEST_BEARER"]}
            if args.mode == "modern":
                from mcp.client.streamable_http import streamable_http_client
                from mcp.shared._httpx_utils import create_mcp_http_client
                from mcp import Client
                async with create_mcp_http_client(headers=headers) as http_client:
                    async with Client(streamable_http_client(args.url, http_client=http_client), elicitation_callback=callback) as client:
                        yield client, client.protocol_version, client.server_info.version
                return
            from mcp.client.streamable_http import streamablehttp_client
            transport = streamablehttp_client(args.url, headers=headers)
        else:
            transport = stdio_client(StdioServerParameters(command=args.server_python,
                args=["-I", "-m", "src.server.mcp.sdk2"], cwd=workspace,
                env={"PYTHONDONTWRITEBYTECODE": "1", "AOP_MCP_ENABLE_FIXTURE_FALLBACK": "false",
                     "AOP_MCP_ENVIRONMENT": "test", "AOP_MCP_AUTH_MODE": "disabled", "AOP_MCP_LOG_LEVEL": "ERROR"}), errlog=quiet)
            if args.mode == "modern":
                from mcp import Client
                async with Client(transport, elicitation_callback=callback) as client:
                    yield client, client.protocol_version, client.server_info.version
                return
        async with transport as streams:
            async with ClientSession(streams[0], streams[1]) as client:
                initialized = await client.initialize()
                yield client, initialized.protocolVersion, initialized.serverInfo.version


async def run(args):
    report = {"clientSDK": version("mcp"), "mode": args.mode, "transport": "http" if args.url else "stdio",
              "fixtureFallback": False, "calls": [], "questions": [], "applicationResults": {}}
    action = "accept"
    async def answer(ctx, question):
        from mcp.types import ElicitResult
        report["questions"].append({"message": question.message, "fields": sorted(question.requested_schema["properties"]), "action": action})
        values = {"species": "human", "life_stage": "adult"}
        return ElicitResult(action=action, content={key: values[key] for key in question.requested_schema["properties"]} if action == "accept" else None)

    with anyio.fail_after(180):
        async with connect(args, answer) as (client, protocol, server_version):
            report.update(protocol=protocol, serverVersion=server_version)
            tools = (await client.list_tools()).model_dump(mode="json", by_alias=True)["tools"]
            assert len(tools) == 43
            schema = next(item["outputSchema"] for item in tools if item["name"] == "compare_aops")
            async def call(label, arguments, expected="completed"):
                start = time.monotonic()
                result = await client.call_tool("compare_aops", arguments)
                wire = result.model_dump(mode="json", by_alias=True, exclude_none=True)
                assert not wire.get("isError"), wire
                payload = wire["structuredContent"]
                validate(payload, schema)
                assert payload["status"] == expected
                assert wire["_meta"]["sources"] and "Sources:" in wire["content"][0]["text"]
                report["applicationResults"][label] = payload
                report["calls"].append({"label": label, "passed": True, "elapsedSeconds": round(time.monotonic() - start, 3)})
                return payload

            direct = await call("androgen_pair", {"aop_ids": ["AOP:345", "AOP:477"], "species": "human", "life_stage": "adult"})
            assert "KE:26" in [item["id"] for item in direct["pairs"][0]["shared_molecular_initiating_events"]]
            if args.mode == "modern":
                guided = await call("guided_androgen_pair", {"aop_ids": ["AOP:345", "AOP:477"]})
                assert guided == direct
                assert report["questions"][-1]["fields"] == ["life_stage", "species"]
                action = "cancel"
                await call("cancelled_comparison", {"aop_ids": ["AOP:345", "AOP:477"]}, "cancelled")
                action = "accept"
                partial = await call("mouse_context", {"aop_ids": ["AOP:345", "AOP:477"], "species": "mouse"})
                assert partial["requested_context"]["species"] == "NCBITaxon:10090"
                assert report["questions"][-1]["fields"] == ["life_stage"]
            else:
                pending = await call("legacy_missing_context", {"aop_ids": ["AOP:345", "AOP:477"]}, "input_required")
                assert pending["missing_inputs"] == ["species", "life_stage"]
            triple = await call("androgen_triple", {"aop_ids": ["AOP:344", "AOP:345", "AOP:477"], "species": "human", "life_stage": "unspecified"})
            assert len(triple["pairs"]) == 3
            unrelated = await call("different_outcomes", {"aop_ids": ["AOP:40", "AOP:477"], "species": "unspecified", "life_stage": "unspecified"})
            assert unrelated["pairs"][0]["shared_adverse_outcomes"] == []
            assert all(item["context_evidence"]["assessment"] == "requires_expert_review" for item in unrelated["aops"])
            four = await call("four_aops", {"aop_ids": ["AOP:40", "AOP:344", "AOP:345", "AOP:477"], "species": "human", "life_stage": "unspecified"})
            assert len(four["aops"]) == 4 and len(four["pairs"]) == 6
            original = await client.call_tool("get_applicability", {"species": "human"})
            assert original.model_dump(mode="json", by_alias=True)["structuredContent"]["species"] == "NCBITaxon:9606"
    report["passed"] = True
    Path(args.output).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key != "applicationResults"}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["legacy", "modern"], required=True)
    parser.add_argument("--server-python", required=True)
    parser.add_argument("--url")
    parser.add_argument("--output", required=True)
    anyio.run(run, parser.parse_args())
