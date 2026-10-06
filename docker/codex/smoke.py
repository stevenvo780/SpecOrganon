"""Integration test against the installed MCP process, with Landlock enabled."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

ROOT = Path('/workspace')
BIN = Path('/opt/specorganon/venv/bin')
TOOLS = set('init put status report review retire_indicator approval_challenge approve '
            'test_execution_challenge record_test_execution test_observation_challenge '
            'record_test_observation field_attestation_challenge attest_field challenge '
            'resolve_challenge gate phase_review_challenge review_phase advance trace '
            'next_task run audit_lot_journal'.split())


def payload(result):
    assert not result.is_error, result.content
    return result.structured_content or json.loads(result.content[0].text)


async def exercise():
    case = ROOT / 'cases' / f'mcp-smoke-{uuid4().hex}'
    env = {k: v for k, v in os.environ.items() if not k.startswith('ORGANON_')}
    env['ORGANON_ROOT'] = str(ROOT)
    params = StdioServerParameters(command=str(BIN / 'organon-mcp'), cwd=str(ROOT), env=env)
    async with Client(params, mode='legacy') as client:
        discovered = {tool.name for tool in (await client.list_tools()).tools}
        assert discovered == TOOLS, discovered ^ TOOLS
        payload(await client.call_tool('init', {
            'path': str(case), 'title': 'Real Docker MCP transport test',
            'domain': 'software integration', 'actor': 'human:owner', 'approval_policy': 'local',
        }))
        for id, kind, refs in [('p1', 'problem', []), ('a1', 'actor', ['p1']),
                               ('b1', 'boundary', ['p1'])]:
            payload(await client.call_tool('put', {
                'path': str(case), 'id': id, 'kind': kind,
                'text': f'Docker integration test: {kind}', 'actor': 'agent:smoke', 'refs': refs,
            }))
        state = payload(await client.call_tool('status', {'path': str(case)}))
        assert state['project']['approval_policy'] == 'local'
        assert set(state['items']) == {'p1', 'a1', 'b1'}
        gate = payload(await client.call_tool('gate', {'path': str(case), 'phase': 'frame'}))
        assert gate['ready'] and not gate['accepted'], gate
        payload(await client.call_tool('report', {'path': str(case)}))
        task = payload(await client.call_tool('next_task', {'path': str(case)}))
        before = (case / 'organon.json').read_bytes()
        rejected = await client.call_tool('put', {
            'path': str(case), 'id': 'p1', 'kind': 'problem', 'text': 'stale write',
            'actor': 'agent:smoke', 'expected_version': 0,
        })
        assert rejected.is_error
        assert (case / 'organon.json').read_bytes() == before
        escape_path = Path('/tmp') / f'organon-escape-{uuid4().hex}'
        rejected = await client.call_tool('init', {
            'path': str(escape_path), 'title': 'Rejected escape', 'domain': 'test',
            'actor': 'human:owner', 'approval_policy': 'local',
        })
        assert rejected.is_error and not escape_path.exists()
    # A new process must recover the persisted state without replaying writes.
    async with Client(params, mode='legacy') as client:
        recovered = payload(await client.call_tool('status', {'path': str(case)}))
        assert recovered == state
    cli = subprocess.run([str(BIN / 'organon'), 'status', str(case)],
                         capture_output=True, text=True, check=True, timeout=30)
    assert json.loads(cli.stdout) == state
    return {'passed': True, 'case': str(case), 'tools_discovered': sorted(discovered),
            'checks': ['MCP stdio initialization', '24 tools', 'local case', 'linked writes',
                       'frame gate', 'report', 'next_task', 'stale write rejected',
                       'outside root rejected', 'restart persistence', 'CLI/MCP parity'],
            'next_task': task, 'ledger_sha256': hashlib.sha256(before).hexdigest()}


def main():
    started = time.monotonic()
    result = asyncio.run(asyncio.wait_for(exercise(), timeout=90))
    result.update(timestamp=datetime.now(timezone.utc).isoformat(),
                  duration_seconds=round(time.monotonic() - started, 3))
    output = ROOT / 'results' / f'mcp-smoke-{uuid4().hex}.json'
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'passed': True, 'report': str(output), 'case': result['case'],
                      'tools_discovered': len(result['tools_discovered'])}, indent=2))


if __name__ == '__main__':
    main()
