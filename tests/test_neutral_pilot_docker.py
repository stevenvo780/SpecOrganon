"""Opt-in offline Docker measurements; no native roles or account calls."""
import importlib.util
import os
from pathlib import Path

import pytest

from specorganon import neutral_pilot as pilot
from specorganon.docker_roles import DockerRoles
from specorganon.role_jobs import _json, canonical


pytestmark = pytest.mark.skipif(os.environ.get('SPECORGANON_NEUTRAL_PILOT_DOCKER') != '1',
                               reason='explicit offline public-pilot Docker controls only')
SOURCE = Path(__file__).resolve().parents[1]
NATIVE = 'sha256:aa4eae810628bd2b78bd48ed3059c284a497bdc7c92d81daacdfe906a3bae3ae'
TEST = 'sha256:6d196a4a021b872e2ea7d799e1797834e23b570e635bd640095f4521cca04ce2'


def registration(tmp_path):
    spec = importlib.util.spec_from_file_location('register_fixture', SOURCE / 'scripts/register_neutral_pilot.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module.prepare(SOURCE, tmp_path / 'runtime', 'docker-driver-control-01', NATIVE, TEST)


def cleanup(t):
    for path in (t.root / 'jobs').glob('*/launch.json'):
        plan = _json(path)
        if plan['container_id']:
            t._cli(['rm', '--force', plan['container_id']], allow_failure=True)


def test_actual_transport_matches_derived_policy_without_any_native_call(tmp_path):
    r = registration(tmp_path); t = pilot.transport(r, tmp_path / 'transport')
    assert canonical(_json(t.root / 'transport-policy.json')) == canonical(pilot.transport_policy(r))
    assert not (t.root / 'jobs').exists()


def test_actual_offline_public_checker_binds_failed_program_and_recovers_without_reexecution(tmp_path, monkeypatch):
    r = registration(tmp_path); folder = tmp_path / 'attempt'; folder.mkdir(mode=0o700)
    built = []; original = pilot.transport
    def capture(r, root):
        t = original(r, root); built.append(t); return t
    monkeypatch.setattr(pilot, 'transport', capture)
    files = {'range_audit.py': 'print("synthetic invalid output")\n',
             'README.md': 'Intentionally broken offline mechanical fixture; no native generation.'}
    try:
        value = pilot._public(r, pilot.ATTEMPTS[0], folder, files, True)
        assert value['status'] == 'observed' and value['score'] == 0
        assert value['result']['cases'] == 115 and value['measurement']['exit_code'] == 1
        assert value['measurement']['provenance'] == 'actual_isolated_container'
        plan = _json(built[0].root / 'jobs/independent-public-check/launch.json')
        inspected = built[0]._inspect(plan)
        assert inspected['HostConfig']['NetworkMode'] == 'none'
        assert inspected['HostConfig']['ReadonlyRootfs']
        assert all(m['Destination'] not in {'/home/codex/.codex', '/home/stev/.gemini', '/var/run/docker.sock'}
                   for m in inspected['Mounts'])
        monkeypatch.setattr(DockerRoles, 'measure', lambda *a: pytest.fail('closed checker cannot reexecute'))
        assert pilot._public(r, pilot.ATTEMPTS[0], folder, files, False) == value
        assert len(list((built[0].root / 'jobs').iterdir())) == 1
    finally:
        for t in built: cleanup(t)


def test_R01_actual_closed_checker_cannot_seal_evidence_added_after_outcome(tmp_path, monkeypatch):
    """Synthetic terminal author state plus real checker; no native author calls."""
    r = registration(tmp_path); root = tmp_path / 'runtime'; root.mkdir(mode=0o700)
    from test_neutral_pilot import ControllerFixture
    c = ControllerFixture(root)
    c.state['files'] = {'range_audit.py': 'print("synthetic invalid output")\n'}
    monkeypatch.setattr(pilot, 'controller', lambda *a: c)
    built = []; original_transport = pilot.transport; original_immutable = pilot.immutable
    def capture(r, path):
        t = original_transport(r, path); built.append(t); return t
    def interrupt(path, value):
        if path.name == 'closure.json': raise KeyboardInterrupt('fixture crash before closure')
        return original_immutable(path, value)
    monkeypatch.setattr(pilot, 'transport', capture); monkeypatch.setattr(pilot, 'immutable', interrupt)
    try:
        with pytest.raises(KeyboardInterrupt): pilot.run_attempt(r, pilot.ATTEMPTS[0], root, 'a' * 64, lambda: r)
        folder = root / pilot.ATTEMPTS[0]['id']; outcome = (folder / 'outcome.json').read_bytes()
        assert _json(folder / 'outcome.json')['public_development_functionality']['score'] == 0
        assert c.calls == 1
        (folder / 'new-unconsumed-proof.txt').write_text('must not join the earlier outcome')
        monkeypatch.setattr(pilot, 'immutable', original_immutable)
        monkeypatch.setattr(DockerRoles, 'measure', lambda *a: pytest.fail('cannot repeat closed public measurement'))
        with pytest.raises(pilot.PilotError): pilot.run_attempt(r, pilot.ATTEMPTS[0], root, 'a' * 64, lambda: r)
        assert not (folder / 'closure.json').exists() and (folder / 'outcome.json').read_bytes() == outcome
        assert c.calls == 1 and len(list((built[0].root / 'jobs').iterdir())) == 1
    finally:
        for t in built: cleanup(t)


def test_R04_authored_subprocess_shadow_cannot_fake_checker_success(tmp_path, monkeypatch):
    r = registration(tmp_path); folder = tmp_path / 'attempt'; folder.mkdir(mode=0o700)
    result = {'classification': 'independent public development checks; not reserved or blinded',
              'task': 'ledgerfold', 'cases': 104, 'passed': 104, 'failed': [], 'observations_sha256': 'a' * 64}
    # This module would print a forged valid summary during the checker's import.
    shadow = 'print(' + repr(__import__('json').dumps(result)) + ')\nraise SystemExit(0)\n'
    files = {'ledger_fold.py': 'print("synthetic invalid output")\n', 'subprocess.py': shadow}
    built = []; original = pilot.transport
    def capture(r, path):
        t = original(r, path); built.append(t); return t
    monkeypatch.setattr(pilot, 'transport', capture)
    try:
        value = pilot._public(r, pilot.ATTEMPTS[2], folder, files, True)
        assert value['status'] == 'observed' and value['score'] == 0
        assert value['result']['passed'] == 0 and value['result']['cases'] == 104
        assert value['measurement']['exit_code'] == 1
        assert value['measurement']['subject_argv'][:4] == ['/opt/specorganon/venv/bin/python', '-I', '-S', '-B']
        monkeypatch.setattr(DockerRoles, 'measure', lambda *a: pytest.fail('closed checker cannot execute again'))
        assert pilot._public(r, pilot.ATTEMPTS[2], folder, files, False) == value
        assert len(list((built[0].root / 'jobs').iterdir())) == 1
    finally:
        for t in built: cleanup(t)
