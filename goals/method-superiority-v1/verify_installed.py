"""Installed CLI/MCP and synthetic author grammar guard, with no model calls."""
import asyncio
import importlib.metadata
import json
from pathlib import Path
import subprocess

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import specorganon
from specorganon import engine
from specorganon.author_contract import author_manifest_contract
from specorganon.role_jobs import canonical, digest
from specorganon.software_controller import Controller, ControllerError


class SyntheticTransport:
    def call(self, job_id, role, request):
        # An invalid synthetic packet must be retained and never applied.
        return {'schema': 1, 'actor': 'agent:synthetic-control',
                'receipt_ref': 'synthetic-control:' + job_id, 'provenance': 'synthetic',
                'request_sha256': digest(canonical(request)),
                'result': {'schema': 1, 'manifest': {'schema': 1, 'steps': []},
                           'files': {}, 'reason': 'Synthetic empty-step rejection only'}}


async def main():
    assert importlib.metadata.version('specorganon') == '0.2.0rc3.dev1'
    assert '/site-packages/' in specorganon.__file__
    root = Path('/runs')
    cli = subprocess.run(['organon', 'init', str(root/'cli-control'),
                          '--title', 'Installed grammar mechanics control',
                          '--domain', 'development', '--approval-policy', 'local',
                          '--actor', 'human:owner'], capture_output=True, text=True, timeout=20)
    assert cli.returncode == 0, cli.stderr
    case = root / 'cli-control'
    controller = Controller(case, root/'controller-control', SyntheticTransport(),
                            contract='Synthetic installed grammar rejection',
                            mandate='Authorized mechanical verification only', fixture_mode=True)
    before = (case/'organon.json').read_bytes()
    try:
        controller.step()
    except ControllerError as error:
        assert 'bounded substantive puts' in str(error)
    else:
        raise AssertionError('empty author steps accepted')
    assert (case/'organon.json').read_bytes() == before
    assert json.loads((controller.root/'controller.json').read_text())['schema'] == 10
    params = StdioServerParameters(command='/opt/specorganon/venv/bin/organon-mcp',
                                   env={'ORGANON_ROOT': str(root), 'ORGANON_ALLOW_FIXTURES': '0'})
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
            assert {'init', 'status', 'report', 'next_task'} <= names
            result = await session.call_tool('init', {'path':'mcp-control',
                'title':'Installed stdio transport control','domain':'development',
                'actor':'human:owner','approval_policy':'local','test_gate_policy':'local_report'})
            assert not result.is_error, str(result)
            for operation in ['status', 'report', 'next_task']:
                result = await session.call_tool(operation, {'path':'mcp-control'})
                assert not result.is_error, str(result)
            count = len(names)
    assert author_manifest_contract('build')['steps_count'] == [1,32]
    print(json.dumps({'version':importlib.metadata.version('specorganon'),
        'installed_module':specorganon.__file__,'CLI_exit_code':cli.returncode,
        'actual_stdio':True,'MCP_tools_discovered':count,
        'MCP_operations':['init','status','report','next_task'],
        'empty_steps_rejected':True,'ledger_unchanged_after_rejection':True,
        'controller_schema':10,'network_enabled':False,'new_model_calls':0,'new_subjects':0,
        'scope':'installed CLI/MCP and synthetic grammar mechanics; not a native nine-phase delivery'}))


asyncio.run(main())
