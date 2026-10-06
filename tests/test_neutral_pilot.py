"""Driver fixtures: admission/custody only, no native generations or competence."""
import copy
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from specorganon import neutral_pilot as pilot
from specorganon.docker_roles import PendingCleanupError
from specorganon.role_jobs import _read, _write, canonical, digest


SOURCE = Path(__file__).resolve().parents[1]


def plan(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location('register_fixture', SOURCE / 'scripts/register_neutral_pilot.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    r = module.prepare(SOURCE, tmp_path / 'runtime', 'fixture-driver-01',
                       'sha256:' + 'a' * 64, 'sha256:' + 'b' * 64)
    return r


def snapshot(r, root):
    root.mkdir()
    for name in r['source_sha256']:
        path = root / name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((Path(r['source_root']) / name).read_bytes())
    r['source_root'] = str(root)
    return r


def fresh_report(r, path, *, expected=None, before=''):
    path.write_bytes(canonical(r))
    pin = expected or digest(path.read_bytes())
    source = ('import sys\n' + f'sys.path.insert(0,{str(SOURCE / "src")!r})\n' + before +
              'from specorganon.neutral_native_entry import main\n' +
              f'sys.argv=["organon-controls","report",{str(path)!r},"--plan-sha256",{pin!r}]\n'
              'sys.exit(main())\n')
    return subprocess.run([sys.executable, '-I', '-B', '-c', source], capture_output=True, timeout=20)


def test_fresh_registered_report_keeps_all_six_positions_and_creates_nothing(tmp_path):
    r = plan(tmp_path); result = fresh_report(r, tmp_path / 'plan.json')
    assert result.returncode == 2, result.stderr
    report = json.loads(result.stdout)
    assert report['closed_attempts'] == 0 and report['planned_denominator'] == 6
    assert [p['attempt'] for p in report['positions']] == pilot.ATTEMPTS
    assert all(p['status'] == 'not_started' and p['outcome'] is None for p in report['positions'])
    assert report['external_F'] is None and report['common_complete'] is None and not report['competence_established']
    assert not Path(r['run_root']).exists()


@pytest.mark.parametrize('change', ['wrong_digest', 'wrong_version', 'missing_source', 'source_changed',
                                   'extra_module', 'swapped_attempt', 'foreign_import', 'symlink', 'hardlink',
                                   'wrong_checker_args', 'wrong_case_count'])
def test_bootstrap_rejects_changed_inventory_sources_policy_and_already_imported_package(tmp_path, change):
    r = snapshot(plan(tmp_path), tmp_path / 'snapshot'); path = tmp_path / 'plan.json'; before = ''; expected = None
    if change == 'wrong_digest': expected = 'f' * 64
    elif change == 'wrong_version': r['candidate_version'] = '0.2.0rc3.dev4'
    elif change == 'missing_source': r['source_sha256'].pop('src/specorganon/docker_roles.py')
    elif change == 'source_changed': (Path(r['source_root']) / 'src/specorganon/docker_roles.py').write_text('raise RuntimeError("must never run")\n')
    elif change == 'extra_module': (Path(r['source_root']) / 'src/specorganon/evil.py').write_text('raise RuntimeError("must never run")\n')
    elif change == 'swapped_attempt': r['attempts'] = list(reversed(r['attempts']))
    elif change == 'wrong_checker_args': r['tasks']['ledgerfold']['checker_args'] = ['topoplan']
    elif change == 'wrong_case_count': r['tasks']['ledgerfold']['public_cases'] = 105
    elif change == 'foreign_import': before = 'import specorganon.neutral_controller\n'
    elif change in ('symlink', 'hardlink'):
        p = Path(r['source_root']) / 'src/specorganon/docker_roles.py'
        raw = p.read_bytes(); p.unlink(); target = tmp_path / 'foreign.py'; target.write_bytes(raw)
        if change == 'symlink': p.symlink_to(target)
        else: p.hardlink_to(target)
    result = fresh_report(r, path, expected=expected, before=before)
    assert result.returncode == 2
    rejection = json.loads(result.stderr)
    assert rejection['status'] == 'rejected', result
    assert not Path(r['run_root']).exists()


def test_expected_transport_policy_is_derived_without_Docker_or_clock(tmp_path, monkeypatch):
    r = plan(tmp_path)
    monkeypatch.setattr(pilot, 'transport', lambda *a: pytest.fail('must not inspect Docker'))
    p = pilot.transport_policy(r)
    assert p['schema'] == 5 and p['registered_source_bindings_sha256'] == digest(canonical(r['source_sha256']))
    assert p['routes'] == {'author': ['codex', 'gpt-6.1-sol'], 'review': ['gemini', 'Gemini 3.8 Flash (Medium)']}
    assert set(p['native_source_sha256']) == {n for n in r['source_sha256']
        if n == 'scripts/controller_native_role.py' or n.startswith('src/specorganon/')}


class PublicFixture:
    """Synthetic checker receipts for parser/control tests; no Docker execution."""
    def __init__(self, root, result, *, exit_code=0, pending=False):
        self.root = root; self.root.mkdir(parents=True, exist_ok=True)
        self.store = SimpleNamespace(root=root / 'host-journal'); self.store.root.mkdir()
        self.result = result; self.exit_code = exit_code; self.pending = pending; self.calls = 0
        self.measured = None

    def recover_test(self, *a): return self.measured

    def measure(self, job, argv, files):
        self.calls += 1
        assert (self.root.parent / 'public-check-intent.json').exists()
        if self.pending: raise PendingCleanupError('fixture pending cleanup')
        folder = self.store.root / job; folder.mkdir()
        (folder / 'stdout.bin').write_bytes(self.result if isinstance(self.result, bytes) else canonical(self.result))
        (folder / 'stderr.bin').write_bytes(b'')
        self.measured = {'fixture': True, 'test_job_ref': str(folder / 'receipt.json'),
                         'exit_code': self.exit_code, 'timed_out': False, 'truncated_streams': []}
        return self.measured

    def verify_test(self, *a, **kw): return True


@pytest.mark.parametrize('mode', ['valid', 'failed', 'wrong_denominator', 'bool_count', 'duplicate',
                                 'nonfinite', 'wrong_exit', 'pending'])
def test_public_checker_requires_strict_closed_result_and_keeps_failure_or_unknown(tmp_path, monkeypatch, mode):
    r = plan(tmp_path); a = pilot.ATTEMPTS[0]; folder = tmp_path / 'attempt'; folder.mkdir(mode=0o700)
    result = {**pilot.CHECKER_IDENTITY['rangeaudit'], 'cases': 115, 'passed': 115, 'failed': [],
              'observations_sha256': 'a' * 64}
    code = 0
    if mode == 'failed':
        name, pin = next(iter(pilot.case_index(r, 'rangeaudit').items()))
        result['passed'] = 114; result['failed'] = [{'name': name, 'passed': False, 'exit_code': 1,
            'input_sha256': pin, 'stdout_sha256': 'a' * 64, 'stderr_sha256': 'b' * 64}]; code = 1
    elif mode == 'wrong_denominator': result['cases'] = 116
    elif mode == 'bool_count': result['passed'] = True
    elif mode == 'duplicate': result = b'{"cases":115,"cases":115}'
    elif mode == 'nonfinite': result = b'{"passed":NaN}'
    elif mode == 'wrong_exit': code = 1
    t = PublicFixture(folder / 'public-check', result, exit_code=code, pending=mode == 'pending')
    monkeypatch.setattr(pilot, 'transport', lambda *a: t)
    files = {'range_audit.py': '# fixture only\n'}
    if mode == 'pending':
        with pytest.raises(PendingCleanupError): pilot._public(r, a, folder, files, True)
        assert not (folder / 'public-check-outcome.json').exists()
    else:
        value = pilot._public(r, a, folder, files, True)
        assert value['status'] == ('observed' if mode in ('valid', 'failed') else 'failed')
        assert value['score'] == (1 if mode == 'valid' else 114 / 115 if mode == 'failed' else None)
        assert pilot._public(r, a, folder, files, False) == value and t.calls == 1
        changed = {**files, 'README.md': 'Changed delivery'}
        with pytest.raises(pilot.PilotError): pilot._public(r, a, folder, changed, False)


def test_public_absent_or_collision_never_dispatches(tmp_path, monkeypatch):
    r = plan(tmp_path); monkeypatch.setattr(pilot, 'transport', lambda *a: pytest.fail('cannot dispatch'))
    for files in ({}, {'check_public.py': 'raise RuntimeError()'}):
        v = pilot._public(r, pilot.ATTEMPTS[0], tmp_path, files, True)
        assert v['status'] == 'unavailable' and v['score'] is None


def test_closed_inventory_detects_receipt_and_outcome_mutation_and_symlink(tmp_path):
    folder = tmp_path / 'attempt'; folder.mkdir()
    receipt = folder / 'receipt.json'; _write(receipt, {'fixture': True})
    row = {'plan_sha256': 'a' * 64, 'attempt': pilot.ATTEMPTS[0], 'fixture': True,
           'evidence_sha256': pilot.inventory(folder)}
    _write(folder / 'outcome.json', row)
    seal = {'schema': 1, 'outcome_sha256': digest(_read(folder / 'outcome.json')),
            'evidence_sha256': pilot.inventory(folder)}
    _write(folder / 'closure.json', seal)
    assert pilot._closed(folder, 'a' * 64, pilot.ATTEMPTS[0]) == row
    _write(receipt, {'fixture': False})
    with pytest.raises(pilot.PilotError): pilot._closed(folder, 'a' * 64, pilot.ATTEMPTS[0])
    receipt.unlink(); receipt.symlink_to(folder / 'outcome.json')
    with pytest.raises(ValueError): pilot.inventory(folder)


def test_bound_contract_is_read_and_checked_in_one_operation(tmp_path):
    r = snapshot(plan(tmp_path), tmp_path / 'snapshot')
    name = r['tasks']['rangeaudit']['contract']; raw = pilot.bound_source(r, name)
    assert b'N/S' in raw and b'Ninguna fase del engine T' in raw
    (Path(r['source_root']) / name).write_bytes(raw + b'changed')
    with pytest.raises(pilot.PilotError): pilot.bound_source(r, name)


class ControllerFixture:
    """Outer journal/cost fixture only; not actual accepted native roles."""
    def __init__(self, folder):
        self.folder = folder; self.calls = 0
        self.state = {'status': 'failed', 'files': {}}
    def step(self):
        self.calls += 1
        return self._report(self.state)
    def _load(self): return self.state, [], None, None
    def _report(self, state):
        return {'status': 'failed', 'fixture_mode': True, 'native_ready': False,
                'scope': 'Synthetic outer-driver journal fixture; no provider result'}


def test_crash_after_outcome_seals_same_terminal_result_without_new_step_or_clock(tmp_path, monkeypatch):
    r = plan(tmp_path); root = tmp_path / 'runtime'; root.mkdir(mode=0o700)
    c = ControllerFixture(root)
    monkeypatch.setattr(pilot, 'controller', lambda *a: c)
    original = pilot.immutable
    def interrupt(path, value):
        if path.name == 'closure.json': raise KeyboardInterrupt('fixture interrupted after outcome')
        return original(path, value)
    monkeypatch.setattr(pilot, 'immutable', interrupt)
    with pytest.raises(KeyboardInterrupt): pilot.run_attempt(r, pilot.ATTEMPTS[0], root, 'a' * 64, lambda: r)
    folder = root / pilot.ATTEMPTS[0]['id']
    raw = (folder / 'outcome.json').read_bytes(); clock = (folder / 'terminal-clock.json').read_bytes()
    assert c.calls == 1
    monkeypatch.setattr(pilot, 'immutable', original)
    row = pilot.run_attempt(r, pilot.ATTEMPTS[0], root, 'a' * 64, lambda: r)
    assert c.calls == 1 and row['controller_report']['fixture_mode']
    assert (folder / 'outcome.json').read_bytes() == raw and (folder / 'terminal-clock.json').read_bytes() == clock
    monkeypatch.setattr(pilot, 'controller', lambda *a: pytest.fail('closed attempt cannot construct controller'))
    assert pilot.run_attempt(r, pilot.ATTEMPTS[0], root, 'a' * 64, lambda: r) == row


def test_pending_outer_attempt_never_gets_outcome_terminal_clock_or_new_start(tmp_path, monkeypatch):
    r = plan(tmp_path); root = tmp_path / 'runtime'; root.mkdir(mode=0o700)
    c = ControllerFixture(root)
    def pending(): raise PendingCleanupError('fixture exact handle is pending')
    c.step = pending
    monkeypatch.setattr(pilot, 'controller', lambda *a: c)
    for _ in range(2):
        with pytest.raises(PendingCleanupError): pilot.run_attempt(r, pilot.ATTEMPTS[0], root, 'a' * 64, lambda: r)
        folder = root / pilot.ATTEMPTS[0]['id']
        assert not (folder / 'outcome.json').exists() and not (folder / 'terminal-clock.json').exists()
        raw = (folder / 'started.json').read_bytes()
        if _ == 0: first = raw
        else: assert raw == first


def test_changed_boot_keeps_whole_attempt_duration_unknown(tmp_path, monkeypatch):
    r = plan(tmp_path); root = tmp_path / 'runtime'; root.mkdir(mode=0o700)
    c = ControllerFixture(root); monkeypatch.setattr(pilot, 'controller', lambda *a: c)
    original = pilot._clock; clock = original(); other = {**clock, 'boot_id_sha256': 'f' * 64}
    ticks = iter([clock, other]); monkeypatch.setattr(pilot, '_clock', lambda: next(ticks))
    row = pilot.run_attempt(r, pilot.ATTEMPTS[0], root, 'a' * 64, lambda: r)
    assert row['whole_attempt_seconds'] is None and row['clock_error']
    assert row['external_F'] is None and row['common_complete'] is None


@pytest.mark.parametrize('change', ['add', 'modify'])
def test_R01_mutation_between_outcome_and_closure_refuses_seal(tmp_path, monkeypatch, change):
    r = plan(tmp_path); root = tmp_path / 'runtime'; root.mkdir(mode=0o700)
    c = ControllerFixture(root); monkeypatch.setattr(pilot, 'controller', lambda *a: c)
    original = pilot.immutable
    def interrupt(path, value):
        if path.name == 'closure.json': raise KeyboardInterrupt('fixture crash after bound outcome')
        return original(path, value)
    monkeypatch.setattr(pilot, 'immutable', interrupt)
    with pytest.raises(KeyboardInterrupt): pilot.run_attempt(r, pilot.ATTEMPTS[0], root, 'a' * 64, lambda: r)
    folder = root / pilot.ATTEMPTS[0]['id']; outcome = (folder / 'outcome.json').read_bytes()
    clock = (folder / 'terminal-clock.json').read_bytes()
    if change == 'add': (folder / 'unconsumed-evidence.txt').write_text('must not join the prior outcome')
    else:
        p = folder / 'terminal-clock.json'; value = json.loads(p.read_text()); value['additional'] = 'changed'
        _write(p, value)
    monkeypatch.setattr(pilot, 'immutable', original)
    with pytest.raises(pilot.PilotError): pilot.run_attempt(r, pilot.ATTEMPTS[0], root, 'a' * 64, lambda: r)
    assert (folder / 'outcome.json').read_bytes() == outcome and not (folder / 'closure.json').exists()
    if change == 'add': assert (folder / 'terminal-clock.json').read_bytes() == clock
    assert c.calls == 1


@pytest.mark.parametrize('change', ['wrong_task', 'wrong_classification', 'wrong_oracle', 'null_failures',
                                  'duplicate_failures', 'passed_true', 'foreign_case', 'foreign_input'])
def test_R02_R03_public_result_identity_and_failed_case_schema_reject_without_score(tmp_path, monkeypatch, change):
    r = plan(tmp_path); a = pilot.ATTEMPTS[2] if change == 'wrong_task' else pilot.ATTEMPTS[0]
    task = a['task']; count = pilot.CASE_COUNTS[task]
    result = {**pilot.CHECKER_IDENTITY[task], 'cases': count, 'passed': count, 'failed': [],
              'observations_sha256': 'a' * 64}
    code = 0
    if change == 'wrong_task': result['task'] = 'topoplan'
    elif change == 'wrong_classification': result['classification'] = 'reserved superiority'
    elif change == 'wrong_oracle': result['oracle'] = None
    else:
        name, pin = next(iter(pilot.case_index(r, task).items()))
        failure = {'name': name, 'passed': False, 'exit_code': 1, 'input_sha256': pin,
                   'stdout_sha256': 'a' * 64, 'stderr_sha256': 'b' * 64}
        if change == 'null_failures': result.update(passed=count - 2, failed=[None, None])
        elif change == 'duplicate_failures': result.update(passed=count - 2, failed=[failure, copy.deepcopy(failure)])
        else:
            if change == 'passed_true': failure['passed'] = True
            elif change == 'foreign_case': failure['name'] = 'foreign-case'
            elif change == 'foreign_input': failure['input_sha256'] = 'c' * 64
            result.update(passed=count - 1, failed=[failure])
        code = 1
    folder = tmp_path / 'attempt'; folder.mkdir(mode=0o700)
    t = PublicFixture(folder / 'public-check', result, exit_code=code)
    monkeypatch.setattr(pilot, 'transport', lambda *args: t)
    value = pilot._public(r, a, folder, {'program.py': '# synthetic fixture only'}, True)
    assert value['status'] == 'failed' and value['score'] is None and value['failure']
    assert pilot._public(r, a, folder, {'program.py': '# synthetic fixture only'}, False) == value and t.calls == 1


def test_real_checker_JSONDecodeError_shape_remains_an_observed_functional_failure(tmp_path, monkeypatch):
    r = plan(tmp_path); a = pilot.ATTEMPTS[2]
    name, pin = next(iter(pilot.case_index(r, 'ledgerfold').items()))
    result = {**pilot.CHECKER_IDENTITY['ledgerfold'], 'cases': 104, 'passed': 103,
              'failed': [{'name': name, 'input_sha256': pin, 'passed': False, 'error': 'JSONDecodeError'}],
              'observations_sha256': 'a' * 64}
    folder = tmp_path / 'attempt'; folder.mkdir(mode=0o700)
    t = PublicFixture(folder / 'public-check', result, exit_code=1)
    monkeypatch.setattr(pilot, 'transport', lambda *args: t)
    value = pilot._public(r, a, folder, {'ledger_fold.py': '# parser fixture only'}, True)
    assert value['status'] == 'observed' and value['score'] == 103 / 104
    assert value['result']['failed'][0]['error'] == 'JSONDecodeError'
