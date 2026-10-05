from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.server.api.server import create_app
from src.server.config.settings import get_settings
from src.server.mcp.sdk2 import CONFIRMATION_META_KEY, POLICY_META_KEY

PROTOCOL = '2026-07-28'
TOKEN = 'aop-sdk2-policy-test-token'


def post(client, method, params=None, **kwargs):
    params = {**(params or {}), '_meta': {
        'io.modelcontextprotocol/protocolVersion': PROTOCOL,
        'io.modelcontextprotocol/clientCapabilities': {},
        **((params or {}).get('_meta', {})),
    }}
    headers = {'Accept': 'application/json, text/event-stream', 'MCP-Protocol-Version': PROTOCOL,
               'Mcp-Method': method, 'Authorization': f'Bearer {TOKEN}'}
    if method == 'tools/call':
        headers['Mcp-Name'] = params['name']
    headers.update(kwargs.pop('headers', {}))
    return client.post('/mcp', headers=headers, json={'jsonrpc': '2.0', 'id': 7, 'method': method, 'params': params}, **kwargs)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('AOP_MCP_ENVIRONMENT', 'test')
    monkeypatch.setenv('AOP_MCP_AUTH_MODE', 'bearer')
    monkeypatch.setenv('AOP_MCP_AUTH_BEARER_TOKEN', TOKEN)
    monkeypatch.setenv('AOP_MCP_AUTH_BEARER_SCOPES', 'toxmcp:read')
    monkeypatch.setenv('AOP_MCP_ALLOWED_ORIGINS', '')
    get_settings.cache_clear()
    try:
        with TestClient(create_app(), base_url='http://localhost:8000') as value:
            yield value
    finally:
        get_settings.cache_clear()


def test_modern_catalog_preserves_schema_and_policy(client):
    result = post(client, 'tools/list').json()['result']
    assert result['ttlMs'] == 60_000
    assert result['cacheScope'] == 'private'
    assert result['resultType'] == 'complete'
    # Modern typed annotations carry core hints; the extension metadata retains AOP policy.
    normalized = []
    for item in result['tools']:
        item = dict(item)
        policy = item.pop('_meta')[POLICY_META_KEY]
        item['annotations'].update(policy)
        if item['name'] != 'compare_aops':
            normalized.append(item)
    baseline = json.loads((Path(__file__).parents[1] / 'compatibility/v0.9.2-catalog-sha256.json').read_text())
    assert len(normalized) == baseline['tools']
    assert hashlib.sha256(json.dumps(normalized, sort_keys=True, separators=(',', ':')).encode()).hexdigest() == baseline['sha256']
    assert PROTOCOL in post(client, 'server/discover').json()['result']['supportedVersions']


def test_modern_auth_and_scopes_remain_enforced(client):
    assert post(client, 'server/discover', headers={'Authorization': ''}).status_code == 401
    denied = post(client, 'tools/call', {'name': 'search_aops', 'arguments': {'text': 'liver', 'limit': 1}})
    error = denied.json()['error']
    assert error['code'] == -32003
    assert error['data']['missingScopes'] == ['toxmcp:live']
    allowed = post(client, 'tools/call', {'name': 'get_applicability', 'arguments': {'species': 'human'}}).json()['result']
    assert allowed['structuredContent']['species'] == 'NCBITaxon:9606'
    assert allowed['_meta']['sources']
    assert 'Sources' in allowed['content'][0]['text']


def test_confirmation_does_not_bypass_scope_denial(client):
    for extra in [{'confirmed': True}, {'_meta': {CONFIRMATION_META_KEY: {'confirmed': True}}}]:
        response = post(client, 'tools/call', {'name': 'create_draft_aop', 'arguments': {'title': 'scope denial'}, **extra})
        assert response.json()['error']['code'] == -32003
        assert response.json()['error']['data']['missingScopes'] == ['toxmcp:execute']


def test_explicit_modern_confirmation_reaches_existing_write_guard(client, monkeypatch):
    monkeypatch.setenv('AOP_MCP_AUTH_BEARER_SCOPES', 'toxmcp:read,toxmcp:execute')
    get_settings.cache_clear()
    try:
        with TestClient(create_app(), base_url='http://localhost:8000') as allowed:
            params = {'name': 'create_draft_aop', 'arguments': {'draft_id': 'sdk2-confirmed-draft', 'title': 'Modern confirmation', 'description': 'SDK2 confirmation contract test', 'adverse_outcome': 'Liver steatosis', 'author': 'protocol test', 'summary': 'Create test draft'}}
            assert post(allowed, 'tools/call', params).json()['error']['code'] == -32003
            params['_meta'] = {CONFIRMATION_META_KEY: {'confirmed': True}}
            result = post(allowed, 'tools/call', params).json()['result']['structuredContent']
            assert result == {'draft_id': 'sdk2-confirmed-draft', 'version_id': 'v1'}
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize('revision', ['2024-11-05', '2025-03-26', '2025-06-18', '2025-11-25'])
def test_released_legacy_handshake_and_aliases_remain(client, revision):
    headers = {'Authorization': f'Bearer {TOKEN}', 'MCP-Protocol-Version': revision}
    init = client.post('/mcp', headers=headers, json={'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': revision}})
    assert init.status_code == 200
    assert init.json()['result']['protocolVersion'] == '2025-03-26'
    alias = client.post('/mcp', headers=headers, json={'jsonrpc': '2.0', 'id': 2, 'method': 'mcp/tool/list', 'params': {}})
    assert alias.status_code == 200
    assert len(alias.json()['result']['tools']) == 43


def test_modern_header_and_authority_rejections(client):
    for headers in [{'Mcp-Method': 'tools/call'}, {'Host': 'attacker.example'}, {'Origin': 'https://attacker.example'}]:
        response = post(client, 'tools/list', headers=headers)
        assert response.status_code in {400, 403, 421}
    assert post(client, 'server/discover').status_code == 200


def test_streamed_and_declared_body_limit_before_dispatch(client, monkeypatch):
    monkeypatch.setenv('AOP_MCP_MAX_REQUEST_BYTES', '256')
    get_settings.cache_clear()
    try:
        with TestClient(create_app(), base_url='http://localhost:8000') as bounded:
            for content in [b' ' * 257, iter([b' ' * 150, b' ' * 150])]:
                response = bounded.post('/mcp', headers={'Authorization': f'Bearer {TOKEN}', 'Content-Type': 'application/json'}, content=content)
                assert response.status_code == 413
            malformed = bounded.post('/mcp', headers={'Authorization': f'Bearer {TOKEN}', 'Content-Length': 'invalid'}, content=b'{}')
            assert malformed.status_code == 400
    finally:
        get_settings.cache_clear()


def test_parallel_modern_calls_preserve_request_results_and_audit(client):
    from concurrent.futures import ThreadPoolExecutor
    from src.instrumentation.audit import tool_call_audit_log
    before = len(tool_call_audit_log.list_records())
    inputs = [('human', 'NCBITaxon:9606'), ('NCBITaxon:10090', 'NCBITaxon:10090'), ('NCBITaxon:10116', 'NCBITaxon:10116')] * 4

    def call(item):
        species, expected = item
        response = post(client, 'tools/call', {'name': 'get_applicability', 'arguments': {'species': species}})
        assert response.status_code == 200
        assert response.json()['id'] == 7
        assert response.json()['result']['structuredContent']['species'] == expected

    with ThreadPoolExecutor(max_workers=12) as pool:
        list(pool.map(call, inputs))
    records = tool_call_audit_log.list_records()[before:]
    assert len(records) == 12
    assert len({record.call_id for record in records}) == 12
    assert all(record.tool_name == 'get_applicability' and record.status == 'success' and record.policy_status == 'passed' and record.output_validation_status == 'passed' for record in records)
    assert len({record.request_hash for record in records}) == 3
