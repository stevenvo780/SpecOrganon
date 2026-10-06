"""Actual offline measures with synthetic autonomous roles; no provider calls."""
import os
from pathlib import Path

import pytest

from specorganon.docker_roles import DockerRoles
from specorganon.neutral_autonomy import AutonomousNeutralController
from specorganon.role_jobs import _json, digest
from test_neutral_autonomy import FreeFixture, PACKAGE, PARTITION, choice
from test_neutral_controller import ARGV, POLICY, PROGRAM, TEST
from test_neutral_docker_controls import OPTIONS, COUNTER


pytestmark = pytest.mark.skipif(os.environ.get('SPECORGANON_AUTONOMY_DOCKER') != '1',
                               reason='explicit autonomous offline mechanical controls')
SOURCE = Path(__file__).resolve().parents[1]


def actual(root, *, repair=False):
    t = None
    # Count actual starts before the deliberately failing assertion, including
    # failed measures. The same original battery is used after program repair.
    package = {**PACKAGE, 'test_program.py': 'from pathlib import Path\n' + COUNTER + TEST}
    if repair: package['program.py'] = PROGRAM.replace('return 7', 'return 0')
    responses = [choice('measure', files=package, battery=PARTITION)]
    if repair: responses.append(choice('measure', files={'program.py': PROGRAM}))
    responses.append(choice('audit'))
    def factory(path):
        nonlocal t
        if t is None:
            names = [SOURCE / 'scripts/controller_native_role.py', *sorted((SOURCE / 'src/specorganon').glob('*.py')),
                     SOURCE / 'experiments/software_comparison_v3/public-models.json']
            pins = {str(p.relative_to(SOURCE)): digest(p.read_bytes()) for p in names}
            real = DockerRoles(path / 'actual-tests', **OPTIONS, source_bindings=pins)
            t = FreeFixture(path, responses=responses)
            t.store = real.store; t.actual = real
            t.measure = real.measure; t.verify_test = real.verify_test; t.recover_test = real.recover_test
            t.reconcile_pending = lambda job, role, request: real.reconcile_pending(job, role, request) if role == 'test' else False
        return t
    return AutonomousNeutralController(root, attempt_id='autonomy-docker-fixture', method='N',
        contract='Synthetic offline fixture only: result seven.', mandate='No model account calls.',
        argv=ARGV, test_file='test_program.py', transport_policy=POLICY,
        transport_factory=factory, fixture_mode=True)


def cleanup(c):
    if c.transport:
        t = c.transport.actual
        for file in (t.root / 'jobs').glob('*/launch.json'):
            p = _json(file)
            if p['container_id']: t._cli(['rm', '--force', p['container_id']], allow_failure=True)


def test_actual_autonomous_measure_offline_no_credentials_and_replay_no_second_run(tmp_path, monkeypatch):
    c = actual(tmp_path / 'run')
    try:
        r = c.run(); assert r['status'] == 'review_ready' and not r['native_ready'] and r['fixture_mode']
        t = c.transport.actual; folders = list((t.root / 'jobs').iterdir()); assert len(folders) == 1
        folder = folders[0]; measured = _json(folder / 'measured-test.json')
        assert measured['provenance'] == 'actual_isolated_container' and measured['passed']
        plan = _json(folder / 'launch.json'); inspected = t._inspect(plan)
        assert inspected['HostConfig']['NetworkMode'] == 'none' and inspected['HostConfig']['ReadonlyRootfs']
        assert all(m['Destination'] not in {'/home/codex/.codex', '/home/stev/.gemini', '/var/run/docker.sock'}
                   for m in inspected['Mounts'])
        assert (folder / 'output/own-runs.txt').read_text() == '1'
        monkeypatch.setattr(t, 'measure', lambda *a: pytest.fail('closed attempt must not reexecute'))
        assert c.step() == r and (folder / 'output/own-runs.txt').read_text() == '1'
    finally: cleanup(c)


def test_actual_failed_autonomous_measure_repair_keeps_original_battery_bytes(tmp_path):
    c = actual(tmp_path / 'run', repair=True)
    try:
        r = c.run(); assert r['status'] == 'review_ready' and r['counts']['test_runs'] == 2
        folders = sorted((c.transport.actual.root / 'jobs').iterdir()); assert len(folders) == 2
        values = [_json(folder / 'measured-test.json') for folder in folders]
        assert [v['passed'] for v in values] == [False, True]
        reservations = [_json(p) for p in sorted((c.root / 'reservations').iterdir()) if _json(p)['stage'] == 'measure']
        for n in PARTITION['test_files']:
            assert reservations[0]['request']['files'][n] == reservations[1]['request']['files'][n]
        assert all((folder / 'output/own-runs.txt').read_text() == '1' for folder in folders)
        assert all(v['provenance'] == 'actual_isolated_container' for v in values)
    finally: cleanup(c)


def test_actual_autonomous_closed_measure_crash_recovers_same_receipt_without_dispatch(tmp_path, monkeypatch):
    c = actual(tmp_path / 'run')
    try:
        c.step(); original = c._apply
        def crash(state, r, result, past):
            if r['stage'] == 'measure': raise KeyboardInterrupt('after real closed measurement')
            return original(state, r, result, past)
        monkeypatch.setattr(c, '_apply', crash)
        with pytest.raises(KeyboardInterrupt): c.step()
        assert (c.root / 'results/0002.json').exists()
        t = c.transport.actual; folder = next((t.root / 'jobs').iterdir())
        raw = (folder / 'measured-test.json').read_bytes()
        monkeypatch.setattr(c, '_apply', original)
        monkeypatch.setattr(c.transport, 'measure', lambda *a: pytest.fail('recover exact closed receipt'))
        r = c.run()
        assert r['status'] == 'review_ready' and r['counts']['test_runs'] == 1
        assert (folder / 'measured-test.json').read_bytes() == raw
        assert (folder / 'output/own-runs.txt').read_text() == '1'
    finally: cleanup(c)
