"""Run real legacy/modern clients against both transports, including installed wheels."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
POLICY_META_KEY = 'org.toxmcp/toolPolicy'


def catalog_fingerprint(items):
    normalized = []
    for tool in items:
        tool = dict(tool)
        metadata = tool.pop('_meta', {})
        if metadata:
            assert set(metadata) == {POLICY_META_KEY}, metadata
            tool['annotations'].update(metadata[POLICY_META_KEY])
        normalized.append(tool)
    return hashlib.sha256(json.dumps(normalized, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def application_results(report):
    results = {}
    for label, result in report['results'].items():
        result = dict(result)
        metadata = dict(result['_meta'])
        server_info = metadata.pop('io.modelcontextprotocol/serverInfo', None)
        if server_info is not None:
            assert server_info == {'name': 'AOP MCP Server', 'version': report.get('serverVersion', '0.9.2')}
        result['_meta'] = metadata
        if 'resultType' in result:
            assert result.pop('resultType') == 'complete'
        # SDK2 serializes the optional error flag explicitly; SDK1 leaves it unset.
        if 'isError' in result:
            assert result.pop('isError') is False
        results[label] = result
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--legacy-python', required=True)
    parser.add_argument('--server-python', default=sys.executable)
    parser.add_argument('--server-root')
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args()
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    expected = json.loads((ROOT / 'tests/compatibility/v0.9.2-catalog-sha256.json').read_text())
    env = os.environ.copy()
    env.pop('VIRTUAL_ENV', None)
    env.pop('PYTHONPATH', None)
    if args.server_root:
        env['PYTHONPATH'] = str(Path(args.server_root).resolve())
    common = ['--server-python', args.server_python, '--launcher', str(ROOT / 'scripts/compatibility_server.py'),
              '--fixtures', str(ROOT / 'tests/compatibility/requests.json')]
    if args.server_root:
        common += ['--server-root', str(Path(args.server_root).resolve())]
    reports = []
    with tempfile.TemporaryDirectory(prefix='aop-clients-') as workspace:
        for modern in [False, True]:
            python = args.server_python if modern else args.legacy_python
            for transport in ['stdio', 'http']:
                label = ('modern' if modern else 'legacy') + '-' + transport
                command = [python, str(ROOT / 'scripts/protocol_probe.py'), *common,
                           '--output', str(output / (label + '.json'))]
                if modern:
                    command.append('--modern')
                server = None
                with (output / (label + '.log')).open('w') as log:
                    try:
                        if transport == 'http':
                            with socket.socket() as listener:
                                listener.bind(('127.0.0.1', 0))
                                port = listener.getsockname()[1]
                            server = subprocess.Popen([args.server_python, str(ROOT / 'scripts/compatibility_server.py'),
                                '--transport', 'http', '--port', str(port)], cwd=workspace, env=env, stdout=log, stderr=log)
                            for _ in range(100):
                                if server.poll() is not None:
                                    raise RuntimeError(f'{label}: server exited')
                                try:
                                    with urlopen(f'http://127.0.0.1:{port}/health', timeout=0.2) as response:
                                        if response.status == 200:
                                            break
                                except OSError:
                                    time.sleep(0.05)
                            else:
                                raise RuntimeError(f'{label}: server did not start')
                            command += ['--url', f'http://127.0.0.1:{port}/mcp']
                        subprocess.run(command, cwd=workspace, env=env, stdout=log, stderr=log, check=True, timeout=60)
                    finally:
                        if server:
                            server.terminate()
                            server.wait(timeout=10)
                report = json.loads((output / (label + '.json')).read_text())
                # Preserve the complete released catalog while allowing this additive tool.
                original = [item for item in report['catalog'] if item['name'] != 'compare_aops']
                assert len(report['catalog']) == expected['tools'] + 1
                assert len(original) == expected['tools']
                assert catalog_fingerprint(original) == expected['sha256'], label
                reports.append(report)
                print(label, report['protocol'], len(report['results']), 'workflows passed', flush=True)
    results = application_results(reports[0])
    for report in reports[1:]:
        assert application_results(report) == results, report['protocol']
    (output / 'summary.json').write_text(json.dumps({'tools': expected['tools'],
        'catalogSHA256': expected['sha256'], 'workflows': len(results), 'combinations': 4,
        'applicationResultsIdentical': True}, indent=2) + '\n')


if __name__ == '__main__':
    main()
