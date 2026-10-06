"""Adversarial host journal guards; synthetic transports do not qualify T."""
import copy

import pytest

from specorganon import engine
from specorganon.role_jobs import _json
from specorganon.software_controller import ControllerError
from test_t_measurement_custody import ready


def closed_measurement(tmp_path, exit_code=0):
    ctrl = ready(tmp_path, (exit_code,))
    apply = ctrl._apply_test
    ctrl._apply_test = lambda progress, pending: None
    ctrl.step()
    ctrl._apply_test = apply
    progress = _json(ctrl.root / 'progress.json')
    ctrl.fixture_mode = False  # Exercise real guards using explicit synthetic records.
    progress['pending']['packet']['provenance'] = 'actual_isolated_container'
    progress['pending']['packet']['passed'] = exit_code == 0
    return ctrl, progress


@pytest.mark.parametrize('forgery', ['missing_recovery', 'missing_verifier', 'open_job',
                                    'changed_exit', 'changed_job', 'changed_timeout',
                                    'false_verification', 'truthy_verification'])
def test_no_forged_test_can_write_passed_state(tmp_path, forgery):
    ctrl, progress = closed_measurement(tmp_path)
    pending = progress['pending']
    original = copy.deepcopy(pending['packet'])
    ctrl.executor.recover_test = lambda *args: original
    if forgery == 'missing_recovery': ctrl.executor.recover_test = None
    if forgery == 'missing_verifier': ctrl.executor.verify_test = None
    if forgery == 'open_job': ctrl.executor.recover_test = lambda *args: None
    if forgery == 'changed_exit': original['exit_code'] = 1
    if forgery == 'changed_job': original['test_job_ref'] += '-other'
    if forgery == 'changed_timeout': original['timed_out'] = True
    if forgery == 'false_verification': ctrl.executor.verify_test = lambda *args, **kw: False
    if forgery == 'truthy_verification': ctrl.executor.verify_test = lambda *args, **kw: 1
    ledger = (ctrl.case / 'organon.json').read_bytes()
    journal = (ctrl.root / 'progress.json').read_bytes()
    with pytest.raises(ControllerError, match='isolated test journal'):
        ctrl._apply_test(progress, pending)
    assert (ctrl.case / 'organon.json').read_bytes() == ledger
    assert (ctrl.root / 'progress.json').read_bytes() == journal
    assert len(ctrl.executor.calls) == 1


def test_failed_attachment_with_zero_subject_exit_never_becomes_pass(tmp_path):
    ctrl, progress = closed_measurement(tmp_path)
    measurement = progress['pending']['packet']
    measurement['attachment_exit_code'] = 1
    measurement['passed'] = False
    ctrl.executor.recover_test = lambda *args: copy.deepcopy(measurement)
    assert measurement['exit_code'] == 0
    assert ctrl._apply_test(progress, progress['pending'])['passed'] is False
    assert engine.get_state(ctrl.case)['items']['t1']['data']['passed'] is False
    assert len(ctrl.executor.calls) == 1


@pytest.mark.parametrize('result', [None, 1])
def test_original_journal_must_supply_boolean_outcome_before_state_write(tmp_path, result):
    ctrl, progress = closed_measurement(tmp_path)
    progress['pending']['packet']['passed'] = result
    ctrl.executor.recover_test = lambda *args: copy.deepcopy(progress['pending']['packet'])
    ledger = (ctrl.case / 'organon.json').read_bytes()
    with pytest.raises(ControllerError, match='boolean passed result'):
        ctrl._apply_test(progress, progress['pending'])
    assert (ctrl.case / 'organon.json').read_bytes() == ledger


@pytest.mark.parametrize('exit_code', [0, 1])
def test_exact_closed_original_proof_is_checked_before_state_write(tmp_path, exit_code):
    ctrl, progress = closed_measurement(tmp_path, exit_code)
    pending = progress['pending']
    original = copy.deepcopy(pending['packet'])
    ledger = (ctrl.case / 'organon.json').read_bytes()
    calls = []
    def recover(job, argv, files):
        assert job == pending['job_id']
        assert argv == pending['source_state']['items']['t1']['data']['argv']
        assert files == pending['source_files']
        assert (ctrl.case / 'organon.json').read_bytes() == ledger
        calls.append('recover')
        return original
    def verify(data, files, *, require_passed, require_current):
        assert (ctrl.case / 'organon.json').read_bytes() == ledger
        assert data['test_job_ref'] == original['test_job_ref']
        assert files == pending['source_files']
        assert require_passed is False and require_current is True
        calls.append('verify')
        return True
    ctrl.executor.recover_test = recover
    ctrl.executor.verify_test = verify
    result = ctrl._apply_test(progress, pending)
    assert result['passed'] is (exit_code == 0)
    assert engine.get_state(ctrl.case)['items']['t1']['data']['passed'] is (exit_code == 0)
    assert calls == ['recover', 'verify']
    assert len(ctrl.executor.calls) == 1
