"""Synthetic role packets exercise production guards; no model approvals here."""
from pathlib import Path

import pytest

from specorganon import engine
from specorganon.role_jobs import canonical, digest, _write
from specorganon.software_controller import Controller, ControllerError


def frame_response():
    return {'schema': 1, 'manifest': {'schema': 1, 'steps': [
        {'op': 'put', 'id': 'p1', 'kind': 'problem', 'text': 'Synthetic bounded controller problem', 'refs': [], 'data': {}},
        {'op': 'put', 'id': 'a1', 'kind': 'actor', 'text': 'Synthetic local actor', 'refs': ['p1'], 'data': {}},
        {'op': 'put', 'id': 'b1', 'kind': 'boundary', 'text': 'Synthetic mechanics only', 'refs': ['p1'], 'data': {}},
    ]}, 'files': {}, 'reason': 'Synthetic mechanics packet only'}


class SyntheticTransport:
    def __init__(self, result): self.result = result; self.calls = []
    def call(self, job_id, role, request):
        self.calls.append((job_id, role))
        return {'schema': 1, 'request_sha256': digest(canonical(request)), 'result': self.result,
                'actor': 'agent:synthetic-' + role, 'receipt_ref': 'synthetic:' + job_id,
                'provenance': 'synthetic', 'usage_reported': None}


def controller(tmp_path, transport):
    case = tmp_path / 'case'; engine.create_case(case, 'Synthetic controller guards', 'development', 'human:owner', approval_policy='local')
    return Controller(case, tmp_path / 'run', transport, contract='Synthetic test contract',
                      mandate='Synthetic local owner mandate for guard tests', fixture_mode=True)


@pytest.mark.parametrize('old_schema', [2, 5])
def test_new_review_contract_does_not_silently_resume_old_run(tmp_path, old_schema):
    transport = SyntheticTransport(frame_response()); ctrl = controller(tmp_path, transport)
    ctrl.step()
    policy_path = ctrl.root / 'controller.json'
    from specorganon.role_jobs import _json
    policy = _json(policy_path); policy['schema'] = old_schema
    if old_schema == 5:
        for key in ('max_build_authors', 'max_phase_items', 'max_phase_encoded_bytes',
                    'max_files_encoded_bytes', 'max_test_stream_encoded_bytes'):
            policy.pop(key)
    _write(policy_path, policy)
    before = (ctrl.case / 'organon.json').read_bytes()
    with pytest.raises(ControllerError, match='versioned run'):
        Controller(ctrl.case, ctrl.root, transport, contract=ctrl.contract,
                   mandate=ctrl.mandate, fixture_mode=True)
    assert (ctrl.case / 'organon.json').read_bytes() == before
    assert transport.calls == [('role-01-frame-author', 'author')]


def test_task_context_deduplicates_contents_but_keeps_complete_authoritative_state(tmp_path):
    import json
    from specorganon.runner import describe_task
    ctrl = controller(tmp_path, SyntheticTransport(frame_response())); ctrl.step()
    state = engine.get_state(ctrl.case); task = describe_task(state)
    request = ctrl._request(state, 'review', {'history': []})
    assert json.loads(request['documents']['state.json']) == state
    view = json.loads(request['documents']['next-task.json'])
    for original, compact in zip(task['artifacts']['items'], view['artifacts']['items']):
        assert compact['id'] == original['id'] and compact['version'] == original['version']
        assert compact['issues'] == original['issues']
        assert 'refs' not in compact and 'omitted_refs' not in compact
        assert compact['refs_locator'] == 'state.json/items/' + original['id'] + '/deps'
        assert all(state['items'][original['id']]['deps'][key] == version
                   for key, version in original['refs'].items())
        assert 'text' not in compact and 'data' not in compact
        assert compact['content_locator'] == 'state.json/items/' + original['id']
        assert state['items'][compact['id']]['text'] == original['text']
    assert describe_task(state) == task, 'public task API must remain unchanged'


@pytest.mark.parametrize('target_shape', ['objects', 'strings'])
def test_mandate_target_shape_never_coerces_an_invalid_native_judgment(tmp_path, target_shape):
    import json
    from specorganon.role_jobs import _json
    from specorganon.runner import run_manifest
    transport = SyntheticTransport({'schema': 1, 'tests_executed': False, 'verdict': 'accept',
                                    'reason': 'Synthetic mechanics only', 'findings': []})
    ctrl = controller(tmp_path, transport)
    steps = json.loads((Path(__file__).parents[1] / 'workflows/synthetic_full.json').read_text())['steps']
    for step in steps:
        if step['op'] == 'advance':
            if step['phase'] == 'critique': break
            ctrl.step()
        else:
            current = engine.get_state(ctrl.case)
            guarded = {**step, 'expected_version': 0,
                       'expected_deps': {ref: current['items'][ref]['version'] for ref in step['refs']}}
            run_manifest(ctrl.case, {'schema': 1, 'steps': [guarded]}, 'author:synthetic-fixture')
    state = engine.get_state(ctrl.case)
    request = ctrl._request(state, 'approval', {'history': []})
    assert json.loads(request['documents']['approval-target-ids.json']) == ['n1']
    transport.result = {'schema': 1, 'tests_executed': False, 'verdict': 'accept', 'reason': 'Synthetic mandate fixture only',
                        'findings': [], 'mandate_conformity': True,
                        'approval_targets': [{'id': 'n1', 'version': 1}] if target_shape == 'objects' else ['n1']}
    before = (ctrl.case / 'organon.json').read_bytes()
    if target_shape == 'objects':
        with pytest.raises(ControllerError, match='mismatched'): ctrl.step()
        assert (ctrl.case / 'organon.json').read_bytes() == before
        assert _json(ctrl.root / 'progress.json')['pending']['status'] == 'closed'
        assert engine.get_state(ctrl.case)['items']['n1']['approved'] is False
    else:
        assert ctrl.step()['action'] == 'approval'
        assert engine.get_state(ctrl.case)['items']['n1']['approved'] is True
        assert engine.get_state(ctrl.case)['phases']['critique']['accepted'] is False


def test_author_puts_are_guarded_and_phase_requires_another_real_role(tmp_path):
    transport = SyntheticTransport(frame_response()); ctrl = controller(tmp_path, transport)
    result = ctrl.step()
    state = engine.get_state(ctrl.case)
    assert result['action'] == 'author' and state['revision'] == 3
    assert not state['phases']['frame']['accepted']
    transport.result = {'schema': 1, 'tests_executed': False, 'verdict': 'reject', 'reason': 'Synthetic insufficient evidence', 'findings': []}
    result = ctrl.step()
    assert result['action'] == 'review' and result['verdict'] == 'reject'
    assert not engine.get_state(ctrl.case)['phases']['frame']['accepted']
    assert engine.get_state(ctrl.case)['phase_review_history'][-1]['verdict'] == 'reject'


@pytest.mark.parametrize('change', ['advance', 'spoofed_receipt', 'future_phase', 'unsafe_file'])
def test_author_cannot_advance_fabricate_receipts_or_write_config(tmp_path, change):
    response = frame_response()
    if change == 'advance': response['manifest']['steps'].append({'op': 'advance', 'phase': 'frame'})
    elif change == 'spoofed_receipt': response['manifest']['steps'][0]['data'] = {'receipt': {'exit_code': 0}, 'passed': True}
    elif change == 'future_phase': response['manifest']['steps'][0]['kind'] = 'assessment'
    else: response['files'] = {'../outside.py': 'forbidden'}
    ctrl = controller(tmp_path, SyntheticTransport(response))
    before = (ctrl.case / 'organon.json').read_bytes()
    with pytest.raises(ControllerError): ctrl.step()
    assert (ctrl.case / 'organon.json').read_bytes() == before
    assert not (tmp_path / 'outside.py').exists()


def test_changed_case_during_role_call_refuses_result_before_write(tmp_path):
    transport = SyntheticTransport(frame_response()); ctrl = controller(tmp_path, transport)
    original = transport.call
    def changed(job_id, role, request):
        result = original(job_id, role, request)
        engine.put_item(ctrl.case, 'external1', 'problem', 'External concurrent edit', [], {}, 'agent:external', expected_version=0, expected_deps={})
        return result
    transport.call = changed
    with pytest.raises(ControllerError, match='snapshot'): ctrl.step()
    assert set(engine.get_state(ctrl.case)['items']) == {'external1'}


def test_wrong_role_packet_binding_is_rejected_before_write(tmp_path):
    transport = SyntheticTransport(frame_response()); ctrl = controller(tmp_path, transport)
    original = transport.call
    def wrong(job_id, role, request):
        response = original(job_id, role, request); response['request_sha256'] = 'wrong'; return response
    transport.call = wrong
    with pytest.raises(ControllerError, match='request'): ctrl.step()
    assert engine.get_state(ctrl.case)['revision'] == 0


def test_synthetic_transport_cannot_be_used_as_production_review(tmp_path):
    ctrl = controller(tmp_path, SyntheticTransport(frame_response())); ctrl.fixture_mode = False
    with pytest.raises(ControllerError, match='synthetic'): ctrl.step()
    assert engine.get_state(ctrl.case)['revision'] == 0


def test_rejected_snapshot_is_repaired_before_another_reviewer_call(tmp_path):
    transport = SyntheticTransport(frame_response()); ctrl = controller(tmp_path, transport); ctrl.step()
    transport.result = {'schema': 1, 'tests_executed': False, 'verdict': 'reject', 'reason': 'Synthetic missing actor detail', 'findings': []}; ctrl.step()
    transport.result = frame_response(); transport.result['manifest']['steps'][1]['text'] = 'Repaired synthetic actor detail'
    result = ctrl.step()
    assert result['action'] == 'author' and transport.calls[-1][1] == 'author'
    assert not engine.get_state(ctrl.case)['phases']['frame']['accepted']


def test_no_replacement_review_when_author_changes_nothing_after_rejection(tmp_path):
    transport = SyntheticTransport(frame_response()); ctrl = controller(tmp_path, transport); ctrl.step()
    transport.result = {'schema': 1, 'tests_executed': False, 'verdict': 'reject', 'reason': 'Synthetic failure retained', 'findings': []}; ctrl.step()
    transport.result = frame_response()
    with pytest.raises(ControllerError, match='material'): ctrl.step()
    assert [role for _, role in transport.calls] == ['author', 'review', 'author']
    assert not engine.get_state(ctrl.case)['phases']['frame']['accepted']


def test_measurement_rejects_invalid_stream_binding_after_valid_stages(tmp_path):
    from test_software_controller_resources import build_fixture, program, stage_tests, Executor
    ctrl = build_fixture(tmp_path); program(ctrl); stage_tests(ctrl)
    class InvalidExecutor(Executor):
        def measure(self, *args):
            result = super().measure(*args); result['stdout_sha256'] = []
            return result
    ctrl.executor = InvalidExecutor(tmp_path)
    before = (ctrl.case / 'organon.json').read_bytes()
    with pytest.raises(ControllerError, match='binding'): ctrl.step()
    assert (ctrl.case / 'organon.json').read_bytes() == before
