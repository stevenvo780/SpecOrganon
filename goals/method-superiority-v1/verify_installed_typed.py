"""Installed dev2 CLI/MCP and synthetic typed custody checks; no model calls."""
import asyncio
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import specorganon
from specorganon import engine
from specorganon.role_jobs import canonical, digest
from specorganon.software_controller import Controller, ControllerError


class SyntheticTransport:
    def __init__(self, empty=False): self.empty = empty
    def call(self, job_id, role, request):
        items = [] if self.empty else [
            {'id':'p1','kind':'problem','text':'Synthetic installed typed control','refs':[],'data':{}},
            {'id':'a1','kind':'actor','text':'Synthetic authorized mechanical actor','refs':['p1'],'data':{}},
            {'id':'b1','kind':'boundary','text':'Synthetic transport mechanics only','refs':['p1'],'data':{}}]
        return {'schema':1,'actor':'agent:synthetic-control','receipt_ref':'synthetic:'+job_id,
                'provenance':'synthetic','request_sha256':digest(canonical(request)),
                'result':{'schema':1,'items':items,'files':{},'reason':'Synthetic typed custody control'}}


async def main():
    assert importlib.metadata.version('specorganon') == '0.2.0rc3.dev2'
    assert '/site-packages/' in specorganon.__file__
    root = Path('/runs')
    cli = subprocess.run(['organon','init',str(root/'cli-control'),'--title','Installed typed control',
        '--domain','development','--approval-policy','local','--actor','human:owner'],
        capture_output=True,text=True,timeout=20)
    assert cli.returncode == 0, cli.stderr
    ctrl = Controller(root/'cli-control',root/'typed-control',SyntheticTransport(),
        contract='Synthetic installed typed transport',mandate='Authorized mechanical verification',
        fixture_mode=True,author_format='items-v1')
    result = ctrl.step()
    assert result['author_format'] == 'items-v1'
    raw = json.loads(Path(result['raw_packet_ref']).read_text())
    derived = json.loads(Path(result['derived_manifest_ref']).read_text())
    assert result['raw_packet_sha256'] == digest(canonical(raw))
    assert result['derived_manifest_sha256'] == digest(canonical(derived['manifest']))
    assert derived['scope'] == 'derived candidate, not acceptance'
    assert all('op' not in item for item in raw['result']['items'])
    assert all(s['op']=='put' and s['expected_version']==0 for s in derived['manifest']['steps'])
    assert derived['manifest']['steps'][1]['expected_deps']=={'p1':1}
    policy=json.loads((ctrl.root/'controller.json').read_text())
    assert policy['schema']==11
    engine.create_case(root/'reject-control','Synthetic empty control','development','human:owner',approval_policy='local')
    bad = Controller(root/'reject-control',root/'empty-control',SyntheticTransport(empty=True),
        contract='Synthetic empty rejection',mandate='Authorized mechanics only',fixture_mode=True,author_format='items-v1')
    before=(bad.case/'organon.json').read_bytes()
    try: bad.step()
    except ControllerError: pass
    else: raise AssertionError('empty typed items accepted')
    assert (bad.case/'organon.json').read_bytes()==before
    params=StdioServerParameters(command='/opt/specorganon/venv/bin/organon-mcp',
        env={'ORGANON_ROOT':str(root),'ORGANON_ALLOW_FIXTURES':'0'})
    async with stdio_client(params) as (read,write):
        async with ClientSession(read,write) as session:
            await session.initialize()
            names={t.name for t in (await session.list_tools()).tools}
            assert {'init','status','report','next_task'}<=names
            r=await session.call_tool('init',{'path':'mcp-control','title':'Installed stdio control',
                'domain':'development','actor':'human:owner','approval_policy':'local','test_gate_policy':'local_report'})
            assert not r.is_error,str(r)
            for operation in ['status','report','next_task']:
                r=await session.call_tool(operation,{'path':'mcp-control'})
                assert not r.is_error,str(r)
    package=Path(specorganon.__file__).parent
    hashes={name:hashlib.sha256((package/name).read_bytes()).hexdigest()
            for name in ['author_contract.py','runner.py','software_controller.py']}
    print(json.dumps({'version':importlib.metadata.version('specorganon'),
        'installed_module':specorganon.__file__,'CLI_exit_code':cli.returncode,
        'actual_stdio':True,'MCP_tools_discovered':len(names),
        'MCP_operations':['init','status','report','next_task'],
        'typed_dual_archive_verified':True,'immutable_source_bound_guards_verified':True,
        'empty_typed_items_rejected':True,'ledger_unchanged_after_rejection':True,
        'installed_core_source_sha256':hashes,'controller_schema':11,
        'network_enabled':False,'new_model_calls':0,'new_subjects':0,
        'scope':'installed CLI/MCP and synthetic typed mechanics; not a native nine-phase delivery'}))


asyncio.run(main())
