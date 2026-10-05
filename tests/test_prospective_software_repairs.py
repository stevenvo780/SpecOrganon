"""New mechanical controls only; no study solution or native acceptance."""
import re
from pathlib import Path

import pytest

from specorganon import engine
from specorganon.role_jobs import _json, _write
from specorganon.software_controller import Controller, ControllerError
from experiments.software_comparison_v1.reserved import docker_evaluator as D
from test_software_controller import SyntheticTransport, controller, frame_response


def critique_controller(tmp_path):
    transport = SyntheticTransport(frame_response())
    ctrl = controller(tmp_path, transport)
    ctrl.step()
    transport.result = judgment('accept')
    ctrl.step()
    steps = _json(Path(__file__).parents[1] / 'workflows/synthetic_full.json')['steps']
    transport.result = {'schema': 1, 'manifest': {'schema': 1, 'steps': steps[4:9]},
                        'files': {}, 'reason': 'Synthetic critique mechanism only'}
    ctrl.step()
    return ctrl


def judgment(verdict, approval=False):
    result = {'schema': 1, 'verdict': verdict, 'reason': 'Synthetic control judgment', 'findings': []}
    if approval:
        result.update(mandate_conformity=True, approval_targets=['n1'])
    return result


def approve_and_reject(ctrl):
    ctrl.transport.result = judgment('accept', approval=True)
    assert ctrl.step()['action'] == 'approval'
    ctrl.transport.result = judgment('reject')
    assert ctrl.step()['verdict'] == 'reject'


def correct_concept(ctrl):
    state = engine.get_state(ctrl.case)
    c = state['items']['c1']
    ctrl.transport.result = {'schema': 1, 'manifest': {'schema': 1, 'steps': [
        {'op': 'put', 'id': 'c1', 'kind': 'concept', 'text': c['text'] + ' corrected',
         'refs': list(c['deps']), 'data': c['data']}]}, 'files': {},
        'reason': 'Synthetic substantive correction'}
    assert ctrl.step()['action'] == 'author'


def test_approval_rejection_correction_can_receive_second_phase_review(tmp_path):
    ctrl = critique_controller(tmp_path)
    approve_and_reject(ctrl)
    correct_concept(ctrl)
    # A fresh controller resumes the same counters, not a replacement case.
    ctrl = Controller(ctrl.case, ctrl.root, ctrl.transport, contract=ctrl.contract,
                      mandate=ctrl.mandate, fixture_mode=True)
    ctrl.transport.result = judgment('accept')
    assert ctrl.step()['verdict'] == 'accept'
    state = engine.get_state(ctrl.case)
    assert state['phases']['critique']['accepted']
    history = _json(ctrl.root / 'progress.json')['history']
    assert [h['action'] for h in history if h['phase'] == 'critique'] == [
        'author', 'approval', 'review', 'author', 'review']


def test_persistent_rejection_terminates_without_third_author_or_acceptance(tmp_path):
    ctrl = critique_controller(tmp_path)
    approve_and_reject(ctrl)
    correct_concept(ctrl)
    ctrl.transport.result = judgment('reject')
    assert ctrl.step()['verdict'] == 'reject'
    before = (ctrl.case / 'organon.json').read_bytes()
    calls = len(ctrl.transport.calls)
    with pytest.raises(ControllerError, match='budget'):
        ctrl.step()
    assert len(ctrl.transport.calls) == calls
    assert (ctrl.case / 'organon.json').read_bytes() == before
    assert not engine.get_state(ctrl.case)['phases']['critique']['accepted']


def test_norm_version_changes_do_not_reset_approval_count(tmp_path):
    ctrl = critique_controller(tmp_path)
    for version in range(1, 4):
        if version > 1:
            state = engine.get_state(ctrl.case)
            norm = state['items']['n1']
            engine.put_item(ctrl.case, 'n1', 'norm', norm['text'] + ' revised',
                            list(norm['deps']), norm['data'], 'author:synthetic-fixture',
                            expected_version=norm['version'], expected_deps=norm['deps'])
        ctrl.transport.result = judgment('accept', approval=True)
        if version < 3:
            assert ctrl.step()['action'] == 'approval'
        else:
            before = (ctrl.case / 'organon.json').read_bytes()
            calls = len(ctrl.transport.calls)
            with pytest.raises(ControllerError, match='budget'):
                ctrl.step()
            assert len(ctrl.transport.calls) == calls
            assert (ctrl.case / 'organon.json').read_bytes() == before


def test_global_role_budget_not_renewed_by_new_function_or_phase(tmp_path):
    ctrl = critique_controller(tmp_path)
    path = ctrl.root / 'progress.json'
    p = _json(path)
    p['history'] = [{'action': 'author', 'phase': 'frame'} for _ in range(40)]
    _write(path, p)
    before = (ctrl.case / 'organon.json').read_bytes()
    calls = len(ctrl.transport.calls)
    with pytest.raises(ControllerError, match='budget'):
        ctrl.step()
    assert len(ctrl.transport.calls) == calls
    assert (ctrl.case / 'organon.json').read_bytes() == before


def test_schema6_policy_rejected_before_recreating_delivery(tmp_path):
    ctrl = controller(tmp_path, SyntheticTransport(frame_response()))
    path = ctrl.root / 'controller.json'
    policy = _json(path)
    policy['schema'] = 6
    policy.pop('max_approval_per_phase', None)
    _write(path, policy)
    ctrl.delivery.rmdir()
    before = (ctrl.case / 'organon.json').read_bytes()
    with pytest.raises(ControllerError, match='versioned'):
        Controller(ctrl.case, ctrl.root, ctrl.transport, contract=ctrl.contract,
                   mandate=ctrl.mandate, fixture_mode=True)
    assert not ctrl.delivery.exists()
    assert (ctrl.case / 'organon.json').read_bytes() == before
    assert ctrl.transport.calls == []


def test_logical_identity_is_safe_distinct_and_not_unicode_normalized():
    ids = ['new-control.float', 'nuevo-١', 'suffix-..', '../outside', '/absolute',
           'é', 'e\u0301', 'normal']
    mapped = [D.invocation_identity(x, {'id': x}) for x in ids]
    assert len(set(mapped)) == len(ids)
    assert all(re.fullmatch('[0-9a-f]{64}', x) for x in mapped)
    assert mapped == [D.invocation_identity(x, {'id': x, 'changed': True}) for x in ids]


@pytest.mark.parametrize('id,case', [('', {'id': ''}), (True, {'id': True}),
    ('x', {'id': 'y'}), ('x', {}), ('\udcff', {'id': '\udcff'})])
def test_invalid_or_unbound_identity_rejected_before_invocation(id, case):
    with pytest.raises(D.EvaluationError):
        D.invocation_identity(id, case)


def test_legacy_evaluator_policy_rejected_before_journal_creation(tmp_path, monkeypatch):
    monkeypatch.setattr(D.DockerRoles, '_image', staticmethod(lambda image: image))
    root = tmp_path / 'old'
    root.mkdir(mode=0o700)
    _write(root / 'policy.json', {'schema': 2})
    with pytest.raises(D.EvaluationError, match='policy'):
        D.ReservedDocker(root, 'sha256:' + 'a' * 64)
    assert not (root / 'journal').exists()


def test_bound_identity_failure_does_not_create_even_a_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(D.DockerRoles, '_image', staticmethod(lambda image: image))
    r = D.ReservedDocker(tmp_path / 'new', 'sha256:' + 'a' * 64)
    with pytest.raises(D.EvaluationError, match='identity'):
        r.run('../not-bound', {'id': 'other'}, {})
    assert not (r.root / '.lock').exists()
    assert not (r.root / 'invocations').exists()
