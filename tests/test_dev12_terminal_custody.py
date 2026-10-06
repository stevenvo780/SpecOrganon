"""Reproduce F9/F10/F11 with explicit synthetic journals, never native evidence."""
import copy

import pytest

from specorganon import neutral_pilot as pilot, t_common_controller as T
from specorganon.role_jobs import UncertainJob, _json, _write, canonical
from test_closed_native_role import closed
from test_neutral_pilot import PublicFixture, plan
from test_t_common_controller import make


def test_F9_first_terminal_reverifies_common_auditor_before_readiness(tmp_path, monkeypatch):
    ctrl, holders = make(tmp_path)
    original = ctrl._terminal
    def mutate_before_closure(status, **kwargs):
        if kwargs.get('common_ready'):
            path = holders[0].jobs / 'T-common-audit-0001/packet.json'
            packet = _json(path)
            packet['result']['reason'] = 'Replacement after the last audit check'
            _write(path, packet)
        return original(status, **kwargs)
    monkeypatch.setattr(ctrl, '_terminal', mutate_before_closure)
    with pytest.raises(T.TCommonError, match='auditor receipt'):
        ctrl.run()
    assert not (ctrl.root / 'terminal-intent.json').exists()
    assert not (ctrl.root / 'terminal.json').exists()


@pytest.mark.parametrize('state', [
    {'Status': 'dead', 'Running': False, 'Dead': True, 'Restarting': False},
    {'Status': 'restarting', 'Running': False, 'Dead': False, 'Restarting': True},
    {'Status': 'created', 'Running': False, 'Dead': False, 'Restarting': False},
    {'Status': 'exited', 'Running': 0, 'Dead': False, 'Restarting': False},
    {'Status': 'exited', 'Running': False, 'Dead': 0, 'Restarting': False},
    {'Status': 'exited', 'Running': False, 'Dead': False, 'Restarting': 0},
])
def test_F10_normal_closure_refuses_uncertain_lifecycle(closed, monkeypatch, state):
    t, folder, request, packet, result = closed
    launch = _json(folder / 'launch.json')
    (folder / 'terminal-container.json').unlink()
    monkeypatch.setattr(t, '_prepare', lambda *args: (folder, copy.deepcopy(launch)))
    monkeypatch.setattr(t.store, 'execute', lambda *args, **kwargs: result)
    observed = {'Id': launch['container_id'], 'Image': launch['image_id'],
                'State': {**state, 'ExitCode': 0, 'OOMKilled': False}}
    monkeypatch.setattr(t, '_inspect', lambda *args: copy.deepcopy(observed))
    with pytest.raises(UncertainJob, match='lifecycle'):
        t._execute('author-01', 'author', request)
    assert not (folder / 'terminal-container.json').exists()


def test_F11_public_score_consumes_exact_verified_buffers(tmp_path, monkeypatch):
    r = plan(tmp_path); a = pilot.ATTEMPTS[0]; count = pilot.CASE_COUNTS[a['task']]
    cases = list(pilot.case_index(r, a['task']).items())[:2]
    failed = [{'name': name, 'passed': False, 'exit_code': 1, 'input_sha256': pin,
               'stdout_sha256': 'a' * 64, 'stderr_sha256': 'b' * 64} for name, pin in cases]
    result = {**pilot.CHECKER_IDENTITY[a['task']], 'cases': count, 'passed': count - 2,
              'failed': failed, 'observations_sha256': 'c' * 64}
    forged = {**result, 'passed': count - 1, 'failed': failed[:1]}
    folder = tmp_path / 'attempt'; folder.mkdir(mode=0o700)
    t = PublicFixture(folder / 'public-check', result, exit_code=1)
    name = 'read_test' if hasattr(t, 'read_test') else 'verify_test'
    original = getattr(t, name)
    def mutate_after_verification(*args, **kwargs):
        checked = original(*args, **kwargs)
        (t.store.root / 'independent-public-check/stdout.bin').write_bytes(canonical(forged))
        return checked
    monkeypatch.setattr(t, name, mutate_after_verification)
    monkeypatch.setattr(pilot, 'transport', lambda *args, **kwargs: t)
    value = pilot._public(r, a, folder, {'program.py': '# Synthetic only'}, True)
    assert value['status'] == 'observed'
    assert value['score'] == (count - 2) / count
    assert value['result'] == result
