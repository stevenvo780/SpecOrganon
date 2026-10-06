"""Typed content assembly controls are synthetic, never native method scores."""
import copy
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import pytest

from specorganon import engine
from specorganon.author_contract import typed_author_manifest, author_manifest_contract
from specorganon.role_jobs import _json, _write, canonical, digest
from specorganon.software_controller import Controller, ControllerError
from scripts.controller_native_role import validate_result, author_format_from_request, NativeRoleError
from test_software_controller import SyntheticTransport, frame_response


def typed_response():
    response = frame_response()
    return {'schema': 1, 'items': [{k: copy.deepcopy(v) for k, v in s.items() if k != 'op'}
                                 for s in response['manifest']['steps']],
            'files': response['files'], 'reason': response['reason']}


def typed_controller(root, response=None):
    case = root / 'case'
    engine.create_case(case, 'Synthetic typed mechanics', 'development', 'human:owner', approval_policy='local')
    transport = SyntheticTransport(response or typed_response())
    return Controller(case, root / 'run', transport, contract='Synthetic typed control',
                      mandate='Synthetic mechanics only', fixture_mode=True, author_format='items-v1')


def test_typed_assembly_changes_only_mechanics_and_archives_both_forms(tmp_path):
    response = typed_response(); response['items'][0]['data'] = {'label': ['synthetic']}
    original = copy.deepcopy(response)
    manifest = typed_author_manifest(response)
    manifest['steps'][0]['data']['label'].append('changed clone')
    assert response == original
    ctrl = typed_controller(tmp_path, response)
    result = ctrl.step()
    assert result['author_format'] == 'items-v1'
    raw = _json(result['raw_packet_ref'])
    derived = _json(result['derived_manifest_ref'])
    assert raw['result'] == original and response == original
    assert digest(canonical(raw)) == result['raw_packet_sha256']
    assert digest(canonical(derived['manifest'])) == result['derived_manifest_sha256']
    assert derived['scope'] == 'derived candidate, not acceptance'
    assert derived['author_generated_fields'] == ['items', 'files', 'reason']
    assert 'op' in derived['controller_assembled_fields']
    assert all(s['op'] == 'put' and s['expected_version'] == 0 for s in derived['manifest']['steps'])
    assert derived['manifest']['steps'][1]['expected_deps'] == {'p1': 1}
    assert len(ctrl.transport.calls) == 1


@pytest.mark.parametrize('fault', ['op', 'expected_version', 'expected_deps', 'extra', 'empty', 'root_extra'])
def test_typed_fields_never_filtered_or_filled(tmp_path, fault):
    response = typed_response()
    if fault == 'empty': response['items'] = []
    elif fault == 'root_extra': response['manifest'] = {'schema': 1, 'steps': []}
    else: response['items'][0][fault] = 'not allowed'
    original = copy.deepcopy(response)
    with pytest.raises(ValueError, match='typed author'):
        typed_author_manifest(response)
    with pytest.raises(NativeRoleError, match='typed author'):
        validate_result(response, 'author', author_format='items-v1')
    ctrl = typed_controller(tmp_path, response)
    before = (ctrl.case/'organon.json').read_bytes()
    with pytest.raises(ControllerError):
        ctrl.step()
    assert (ctrl.case/'organon.json').read_bytes() == before
    assert response == original
    assert _json(ctrl.root/'progress.json')['pending']['packet']['result'] == original
    assert len(ctrl.transport.calls) == 1


@pytest.mark.parametrize('fault', ['unknown_ref', 'future_phase', 'fabricated_pass', 'duplicate_id'])
def test_typed_assembly_preserves_semantic_guards(tmp_path, fault):
    response = typed_response()
    if fault == 'unknown_ref': response['items'][0]['refs'] = ['unknown-item']
    elif fault == 'future_phase': response['items'][0]['kind'] = 'assessment'
    elif fault == 'fabricated_pass': response['items'][0]['data'] = {'passed': True}
    else: response['items'].append(copy.deepcopy(response['items'][0]))
    ctrl = typed_controller(tmp_path, response)
    before = (ctrl.case/'organon.json').read_bytes()
    with pytest.raises(ControllerError):
        ctrl.step()
    assert (ctrl.case/'organon.json').read_bytes() == before
    assert ctrl._files() == {}


def test_native_adapter_cannot_choose_a_format_from_the_response(tmp_path):
    ctrl = typed_controller(tmp_path)
    request = ctrl._request(engine.get_state(ctrl.case), 'author', {'history': []})
    assert author_format_from_request(request) == 'items-v1'
    assert author_manifest_contract('frame', 'items-v1')['items_count'] == [1, 32]
    assert validate_result(typed_response(), 'author', author_format='items-v1') == typed_response()
    with pytest.raises(NativeRoleError): validate_result(typed_response(), 'author')
    with pytest.raises(NativeRoleError): validate_result(frame_response(), 'author', author_format='items-v1')
    request['documents']['author-response-format.json'] = '{"schema":true,"format":"items-v1"}'
    with pytest.raises(NativeRoleError): author_format_from_request(request)


def test_author_format_change_rejects_existing_run(tmp_path):
    ctrl = typed_controller(tmp_path)
    before = (ctrl.case/'organon.json').read_bytes()
    with pytest.raises(ControllerError, match='versioned run'):
        Controller(ctrl.case, ctrl.root, ctrl.transport, contract=ctrl.contract,
                   mandate=ctrl.mandate, fixture_mode=True, author_format='manifest-v1')
    assert (ctrl.case/'organon.json').read_bytes() == before


def test_real_sigkill_replays_typed_closed_packet_without_another_author(tmp_path):
    ctrl = typed_controller(tmp_path)
    counter = tmp_path / 'calls'
    script = f"""
import os,signal
from pathlib import Path
from specorganon import engine
from specorganon.software_controller import Controller
from test_software_controller import SyntheticTransport
transport=SyntheticTransport({typed_response()!r})
original_call=transport.call
def call(*args):
 Path({str(counter)!r}).write_text('1')
 return original_call(*args)
transport.call=call
controller=Controller(Path({str(ctrl.case)!r}),Path({str(ctrl.root)!r}),transport,
 contract={ctrl.contract!r},mandate={ctrl.mandate!r},fixture_mode=True,author_format='items-v1')
original_put=engine.put_item
def interrupted(*args,**kwargs):
 result=original_put(*args,**kwargs)
 if Path(args[0])==controller.case: os.kill(os.getpid(),signal.SIGKILL)
 return result
engine.put_item=interrupted
controller.step()
"""
    env = dict(os.environ)
    env['PYTHONPATH'] = str(Path(__file__).parent) + os.pathsep + env.get('PYTHONPATH', '')
    child = subprocess.run([sys.executable, '-c', script], env=env, capture_output=True, timeout=20)
    assert child.returncode == -signal.SIGKILL, child.stderr.decode()
    pending = _json(ctrl.root/'progress.json')['pending']
    assert pending['status'] == 'applying' and pending['author_format'] == 'items-v1'
    assert pending['raw_packet_sha256'] and pending['derived_manifest_sha256']
    result = ctrl.step()
    assert result['action'] == 'author' and ctrl.transport.calls == []
    assert counter.read_text() == '1'
    assert all(item['version'] == 1 for item in engine.get_state(ctrl.case)['items'].values())


def test_immutable_raw_packet_cannot_be_changed_before_resume(tmp_path, monkeypatch):
    ctrl = typed_controller(tmp_path)
    original = ctrl._write_files
    def interrupted(*args): raise RuntimeError('Synthetic interruption')
    monkeypatch.setattr(ctrl, '_write_files', interrupted)
    with pytest.raises(RuntimeError): ctrl.step()
    pending = _json(ctrl.root/'progress.json')['pending']
    archive = ctrl.root/'role-artifacts'/(pending['job_id']+'-packet.json')
    changed = _json(archive); changed['result']['reason'] = 'Altered fixture'
    _write(archive, changed)
    monkeypatch.setattr(ctrl, '_write_files', original)
    before = (ctrl.case/'organon.json').read_bytes()
    with pytest.raises(ControllerError, match='immutable role artifact'):
        ctrl.step()
    assert (ctrl.case/'organon.json').read_bytes() == before
    assert len(ctrl.transport.calls) == 1


def test_T_A_typed_requests_have_same_content_contract(tmp_path):
    from experiments.software_comparison_v3.cells import BasicCell
    t = typed_controller(tmp_path/'T')
    request_T = t._request(engine.get_state(t.case), 'author', {'history': []})
    a = BasicCell(tmp_path/'A', object(), method='A', task='fractionmix', contract='Synthetic',
                  sdd_guide='', protocol_sha256='a'*64, fixture_mode=True)
    request_A = a._request(_json(a.root/'progress.json'), 'frame')
    for name in ['author-response-format.json', 'author-manifest-contract.json']:
        assert request_T['documents'][name] == request_A['documents'][name]


@pytest.mark.parametrize('corruption', ['source_snapshot', 'missing_raw_digest'])
def test_resuming_cannot_change_snapshot_or_omit_derivation_binding(tmp_path, monkeypatch, corruption):
    ctrl = typed_controller(tmp_path)
    original = ctrl._write_files
    def interrupted(*args): raise RuntimeError('Synthetic interruption')
    monkeypatch.setattr(ctrl, '_write_files', interrupted)
    with pytest.raises(RuntimeError): ctrl.step()
    path = ctrl.root/'progress.json'; progress = _json(path)
    if corruption == 'source_snapshot': progress['pending']['source_state']['revision'] += 1
    else: progress['pending'].pop('raw_packet_sha256')
    _write(path, progress)
    monkeypatch.setattr(ctrl, '_write_files', original)
    before = (ctrl.case/'organon.json').read_bytes()
    with pytest.raises(ControllerError, match='binding invalid'): ctrl.step()
    assert (ctrl.case/'organon.json').read_bytes() == before
    assert len(ctrl.transport.calls) == 1


def test_typed_A_executes_all_draft_stages_and_preserves_derivations(tmp_path):
    from test_software_comparison_v3_cells import FixtureTransport, finish
    from experiments.software_comparison_v3.cells import BasicCell
    class TypedFixtureTransport(FixtureTransport):
        def call(self, job_id, role, request):
            packet = super().call(job_id, role, request)
            if role == 'author' and 'manifest' in packet['result']:
                response = packet['result']
                packet['result'] = {'schema':1, 'items':[
                    {k:v for k,v in step.items() if k not in {'op','expected_version','expected_deps'}}
                    for step in response['manifest']['steps']],
                    'files':response['files'], 'reason':response['reason']}
            return packet
    c = BasicCell(tmp_path, TypedFixtureTransport(), method='A', task='fractionmix',
                  contract='Synthetic typed A mechanics', sdd_guide='', protocol_sha256='a'*64,
                  fixture_mode=True, mandate='Synthetic mechanics only')
    finish(c)
    state = _json(c.root/'progress.json')
    assert state['complete'] is True and len(state['derivations']) == 10
    for identity, record in state['derivations'].items():
        raw = _json(c.root/(identity+'-packet.json'))
        derived = _json(c.root/(identity+'-manifest.json'))
        assert record['format'] == 'items-v1'
        assert record['raw_packet_sha256'] == digest(canonical(raw))
        assert record['derived_manifest_sha256'] == digest(canonical(derived['manifest']))
    assert all(item['status']=='candidate' for item in state['candidate_items'].values())
