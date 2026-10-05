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


def test_author_puts_are_guarded_and_phase_requires_another_real_role(tmp_path):
    transport = SyntheticTransport(frame_response()); ctrl = controller(tmp_path, transport)
    result = ctrl.step()
    state = engine.get_state(ctrl.case)
    assert result['action'] == 'author' and state['revision'] == 3
    assert not state['phases']['frame']['accepted']
    transport.result = {'schema': 1, 'verdict': 'reject', 'reason': 'Synthetic insufficient evidence', 'findings': []}
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
    transport.result = {'schema': 1, 'verdict': 'reject', 'reason': 'Synthetic missing actor detail', 'findings': []}; ctrl.step()
    transport.result = frame_response(); transport.result['manifest']['steps'][1]['text'] = 'Repaired synthetic actor detail'
    result = ctrl.step()
    assert result['action'] == 'author' and transport.calls[-1][1] == 'author'
    assert not engine.get_state(ctrl.case)['phases']['frame']['accepted']


def test_no_replacement_review_when_author_changes_nothing_after_rejection(tmp_path):
    transport = SyntheticTransport(frame_response()); ctrl = controller(tmp_path, transport); ctrl.step()
    transport.result = {'schema': 1, 'verdict': 'reject', 'reason': 'Synthetic failure retained', 'findings': []}; ctrl.step()
    transport.result = frame_response()
    with pytest.raises(ControllerError, match='material'): ctrl.step()
    assert [role for _, role in transport.calls] == ['author', 'review', 'author']
    assert not engine.get_state(ctrl.case)['phases']['frame']['accepted']


def test_failed_test_needs_changed_author_work_before_bounded_second_measurement(tmp_path, monkeypatch):
    transport = SyntheticTransport(frame_response()); ctrl = controller(tmp_path, transport)
    engine.put_item(ctrl.case, 't1', 'test', 'Synthetic process exit criterion', [],
                    {'argv': ['/usr/bin/python3', '-c', 'raise SystemExit(1)']}, 'agent:synthetic',
                    expected_version=0, expected_deps={})
    def task(state):
        return {'action': 'execute_test', 'phase': 'build', 'test_execution_targets': [{'id': 't1'}]}
    monkeypatch.setattr('specorganon.software_controller.describe_task', task)
    class Executor:
        def __init__(self): self.calls = []
        def measure(self, job_id, argv, files):
            self.calls.append(job_id)
            folder = tmp_path / ('measurement-' + str(len(self.calls))); folder.mkdir()
            for name in ('stdout', 'stderr'): (folder / (name + '.bin')).write_bytes(b'')
            _write(folder / 'receipt.json', {'synthetic': True})
            return {'subject_argv': argv, 'delivery_tree_sha256': digest(canonical(files)),
                    'exit_code': 1 if len(self.calls) == 1 else 0, 'timed_out': False,
                    'truncated_streams': [], 'test_job_ref': str(folder / 'receipt.json'),
                    'stdout_sha256': digest(b''), 'stderr_sha256': digest(b''), 'provenance': 'synthetic'}
        def verify_test(self, *args, **kwargs): return True
    ctrl.executor = Executor()
    assert ctrl.step()['passed'] is False
    transport.result = {'schema': 1, 'manifest': {'schema': 1, 'steps': [
        {'op': 'put', 'id': 't1', 'kind': 'test', 'text': 'Repaired synthetic exit criterion', 'refs': [],
         'data': {'argv': ['/usr/bin/python3', '-c', 'raise SystemExit(0)']}}]},
        'files': {'probe.py': 'raise SystemExit(0)\n'}, 'reason': 'Synthetic engineering repair after measured exit1'}
    assert ctrl.step()['action'] == 'author'
    assert len(ctrl.executor.calls) == 1
    assert ctrl.step()['passed'] is True
    assert len(ctrl.executor.calls) == 2
    with pytest.raises(ControllerError, match='budget'): ctrl.step()


def test_measured_test_rejects_invalid_stream_binding_before_ledger_write(tmp_path, monkeypatch):
    ctrl = controller(tmp_path, SyntheticTransport(frame_response()))
    engine.put_item(ctrl.case, 't1', 'test', 'Synthetic exit criterion', [],
                    {'argv': ['/usr/bin/python3', '-c', 'pass']}, 'agent:synthetic',
                    expected_version=0, expected_deps={})
    monkeypatch.setattr('specorganon.software_controller.describe_task', lambda state: {
        'action': 'execute_test', 'phase': 'build', 'test_execution_targets': [{'id': 't1'}]})
    class Executor:
        def measure(self, job_id, argv, files):
            return {'subject_argv': argv, 'delivery_tree_sha256': digest(canonical(files)),
                    'exit_code': 0, 'timed_out': False, 'truncated_streams': [],
                    'test_job_ref': 'synthetic:bad-stream-hash', 'stdout_sha256': [],
                    'stderr_sha256': digest(b''), 'provenance': 'synthetic'}
    ctrl.executor = Executor(); before = engine.get_state(ctrl.case)['revision']
    with pytest.raises(ControllerError, match='binding'): ctrl.step()
    assert engine.get_state(ctrl.case)['revision'] == before
