import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from mcp.client import Client
from mcp.client.stdio import StdioServerParameters
from specorganon import engine
from specorganon.ledger import read_project


root = Path(sys.argv[1]) if len(sys.argv) == 2 else Path('/tmp/specorganon-D103-native-o4sxm73a')
case = root / 'case'
bin_dir = Path(sys.executable).parent
env = {'PATH': os.pathsep.join((str(bin_dir), '/usr/bin', '/bin')),
       'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1',
       'ORGANON_ROOT': str(root)}
if 'HOME' in os.environ:
    env['HOME'] = os.environ['HOME']
for key in tuple(os.environ):
    if key.startswith('ORGANON_'):
        del os.environ[key]
raw = (case / 'organon.json').read_bytes()
project = read_project(case)  # Validates complete hash chain.
assert project['project']['approval_policy'] == 'signed'
events = project['events']
assert len(events) == 5
assert all(e['kind'] == 'item_put' for e in events)
assert {e['payload']['id'] for e in events} == {'p_native','a_A','b_A','a_B','b_B'}
state = engine.get_state(case)
assert state['revision'] == 5 and not any(p['accepted'] for p in state['phases'].values())
receipts = {r: json.loads((root / ('writer-'+r) / 'receipt.json').read_text()) for r in ('A','B')}
release = json.loads((root / 'release.json').read_text())
calls = {r: json.loads((root / ('writer-'+r) / 'calls.json').read_text()) for r in ('A','B')}
for role in ('A','B'):
    assert receipts[role]['installed_verified_before_and_after']
    assert receipts[role]['case_id'] == state['project']['case_id']
    assert receipts[role]['project_sha256'] == state['project_sha256']
    assert receipts[role]['released_monotonic_ns'] >= release['releases'][role]['write_started_monotonic_ns']
    assert len(calls[role]) == 2 and all(c['exit'] == 0 and c['stderr'] == '' for c in calls[role])
    for id, kind in (('a_'+role,'actor'),('b_'+role,'boundary')):
        item = state['items'][id]
        assert item['author'] == 'agent:native-D103-'+role and item['version'] == 1 and item['kind'] == kind
        deps = {'p_native':1} if kind == 'actor' else {'p_native':1,'a_'+role:1}
        assert item['deps'] == deps
        assert sum(e['payload']['id'] == id for e in events) == 1
overlap = max(0, min(receipts[r]['finished_monotonic_ns'] for r in receipts)
              - max(receipts[r]['released_monotonic_ns'] for r in receipts))
call_overlaps = [max(0, min(a['end_monotonic_ns'], b['end_monotonic_ns'])
                    - max(a['start_monotonic_ns'], b['start_monotonic_ns']))
                 for a in calls['A'] for b in calls['B']]
assert overlap > 0 and max(call_overlaps) > 0
records = []


async def check():
    params = StdioServerParameters(command=str(bin_dir / 'organon-mcp'), cwd=str(root), env=env)
    async with Client(params, mode='legacy') as client:
        discovery = await client.list_tools()
        records.append({'transport':'mcp', 'operation':'list_tools',
                        'response':discovery.model_dump(mode='json', by_alias=True)})
        assert len(discovery.tools) == 22
        for op, extra, arguments in (
            ('status', [], {'path':str(case)}),
            ('gate', ['frame'], {'path':str(case),'phase':'frame'}),
            ('trace', ['b_A'], {'path':str(case),'id':'b_A'}),
            ('next_task', [], {'path':str(case)}),
        ):
            argv = [str(bin_dir / 'organon'), op.replace('_','-'), str(case), *extra]
            result = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=30)
            records.append({'transport':'cli','operation':op,'argv':argv,'exit':result.returncode,
                            'stdout':result.stdout,'stderr':result.stderr})
            assert result.returncode == 0
            response = await client.call_tool(op, arguments)
            records.append({'transport':'mcp','operation':op,'arguments':arguments,
                            'response':response.model_dump(mode='json',by_alias=True)})
            assert response.is_error is False
            value = response.structured_content
            if value is None:
                value = json.loads(response.content[0].text)
            assert value == json.loads(result.stdout)
            assert (case / 'organon.json').read_bytes() == raw


try:
    asyncio.run(check())
finally:
    with (root / 'verification-transports.json').open('x') as f:
        json.dump(records,f,indent=2);f.write('\n')
summary = {'schema':1,'verified_at_monotonic_ns':time.monotonic_ns(),'passed':True,
           'case_id':state['project']['case_id'],'project_sha256':state['project_sha256'],
           'events':len(events),'guarded_native_items':4,'ledger_chain_valid':True,
           'ledger_before_and_after_readonly_sha256':hashlib.sha256(raw).hexdigest(),
           'native_activity_overlap_ns':overlap,'max_cli_call_overlap_ns':max(call_overlaps),
           'cli_call_pair_overlaps_ns':call_overlaps,
           'actor_sequence':[e['actor'] for e in events],
           'readonly_cli_mcp_pairs':4,'mcp_discovery_raw_sdk_archived':True,
           'field_impact':False,'human_approvals':0,'accepted_phases':0,
           'barrier_induced_overlap_not_model_advantage':True,
           'model_and_effort_authenticated':False,
           'verifier_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
with (root / 'verification.json').open('x') as f:
    json.dump(summary,f,indent=2);f.write('\n')
print(json.dumps(summary))
