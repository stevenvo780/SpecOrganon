"""Synthetic custody and recovery guards, not native acceptance or D/G evidence."""
import json

import pytest

from specorganon import engine, t_measurement_custody as custody
from specorganon.role_jobs import _json, canonical, digest
from specorganon.software_controller import ControllerError
from test_software_controller import controller, frame_response, SyntheticTransport
from test_software_controller_resources import build_fixture, program, stage_tests, repair, Executor


def ready(tmp_path, exits=(0,)):
    ctrl = build_fixture(tmp_path)
    ctrl.executor = Executor(tmp_path, exits)
    program(ctrl); stage_tests(ctrl)
    return ctrl


def test_full_original_capture_exists_before_executor_and_survives_code_repair(tmp_path):
    ctrl = ready(tmp_path, (1, 0))
    original_state = engine.get_state(ctrl.case)
    original_ledger = (ctrl.case / 'organon.json').read_bytes()
    measure = ctrl.executor.measure
    def observe(job, argv, files):
        seal = custody._load(ctrl)
        assert seal['criteria'] == {'crit1': original_state['items']['crit1']}
        assert seal['ancestors']['crit1'] == engine.trace(ctrl.case, 'crit1')['ancestors']
        assert seal['job_id'] == job and seal['files'] == files
        assert (ctrl.root / 'measurement-custody/ledger-before-first-measure.json').read_bytes() == original_ledger
        return measure(job, argv, files)
    ctrl.executor.measure = observe
    assert ctrl.step()['passed'] is False
    first = (ctrl.root / 'measurement-custody/first.json').read_bytes()
    ctrl.executor.measure = measure
    repair(ctrl)
    assert ctrl.step()['passed'] is True
    assert (ctrl.root / 'measurement-custody/first.json').read_bytes() == first
    assert ctrl._files()['test_count.py'] == 'import count\n'
    assert len(ctrl.executor.calls) == 2


@pytest.mark.parametrize('interrupt_at', ['ledger-before-first-measure.json', 'first.sha256', 'first.json'])
def test_interrupted_seal_resumes_same_reserved_measurement_and_clock(tmp_path, monkeypatch, interrupt_at):
    ctrl = ready(tmp_path)
    put = custody._put
    def interrupt(path, raw):
        if path.name == interrupt_at:
            raise OSError('synthetic interrupted seal')
        return put(path, raw)
    monkeypatch.setattr(custody, '_put', interrupt)
    with pytest.raises(ControllerError, match='interrupted seal'):
        ctrl.step()
    pending = _json(ctrl.root / 'progress.json')['pending']
    prepared = (ctrl.root / 'measurement-custody/prepared.json').read_bytes()
    assert ctrl.executor.calls == [] and pending['status'] == 'prepared'
    monkeypatch.setattr(custody, '_put', put)
    assert ctrl.step()['passed'] is True
    assert ctrl.executor.calls == [pending['job_id']]
    assert (ctrl.root / 'measurement-custody/first.json').read_bytes() == prepared
    assert len(ctrl.transport.calls) == 2


@pytest.mark.parametrize('mutation', ['battery', 'argv', 'new_file'])
def test_repair_cannot_ease_battery_change_command_or_add_file(tmp_path, mutation):
    ctrl = ready(tmp_path, (1, 0)); ctrl.step()
    ledger = (ctrl.case / 'organon.json').read_bytes(); files = ctrl._files()
    changes = {'count.py': 'print(11)\n'}
    argv = None
    if mutation == 'battery': changes['test_count.py'] = 'assert True\n'
    if mutation == 'argv': argv = ['/usr/bin/python3', '-c', 'pass']
    if mutation == 'new_file': changes['new.py'] = 'pass\n'
    with pytest.raises(ControllerError, match='sealed'):
        repair(ctrl, changes, argv)
    assert ctrl._files() == files and (ctrl.case / 'organon.json').read_bytes() == ledger
    assert len(ctrl.executor.calls) == 1


@pytest.mark.parametrize('mutation', ['ledger', 'seal', 'policy', 'symlink'])
def test_custody_tampering_refuses_before_second_executor(tmp_path, mutation):
    ctrl = ready(tmp_path, (1, 0)); ctrl.step()
    root = ctrl.root / 'measurement-custody'
    if mutation == 'ledger': (root / 'ledger-before-first-measure.json').write_bytes(b'{}')
    if mutation == 'seal':
        seal = json.loads((root / 'first.json').read_text()); seal['criteria'] = {}
        (root / 'first.json').write_bytes(canonical(seal))
    if mutation == 'policy': (ctrl.root / 'controller.json').write_bytes(b'{}')
    if mutation == 'symlink':
        root.rename(ctrl.root / 'moved-custody'); root.symlink_to(ctrl.root / 'moved-custody')
    ledger = (ctrl.case / 'organon.json').read_bytes(); files = ctrl._files()
    with pytest.raises(ControllerError): repair(ctrl)
    assert ctrl._files() == files and (ctrl.case / 'organon.json').read_bytes() == ledger
    assert len(ctrl.executor.calls) == 1


@pytest.mark.parametrize('verifier_kind', ['missing', 'false', 'truthy'])
def test_native_label_alone_never_authorizes_state(tmp_path, verifier_kind):
    transport = SyntheticTransport(frame_response()); ctrl = controller(tmp_path, transport)
    ctrl.fixture_mode = False  # Exercise guard only, no native provenance claim.
    original = transport.call
    def forged(job, role, request):
        packet = original(job, role, request); packet['provenance'] = 'native'
        return packet
    transport.call = forged
    if verifier_kind != 'missing':
        transport.verify_role = lambda *args: False if verifier_kind == 'false' else 1
    ledger = (ctrl.case / 'organon.json').read_bytes()
    with pytest.raises(ControllerError, match='original native role journal'):
        ctrl.step()
    assert (ctrl.case / 'organon.json').read_bytes() == ledger and ctrl._files() == {}
    assert len(transport.calls) == 1


def test_exact_original_source_is_archived_before_dispatch_and_recovery_keeps_it(tmp_path):
    transport = SyntheticTransport(frame_response()); ctrl = controller(tmp_path, transport)
    original = transport.call
    def observe(job, role, request):
        capture = _json(ctrl.root / ('role-artifacts/' + job + '-source.json'))
        assert capture['request'] == request
        assert capture['state'] == engine.get_state(ctrl.case)
        assert capture['files'] == ctrl._files()
        assert digest(canonical(capture['state'])) == capture['source_fingerprint']
        raise OSError('synthetic interrupted dispatch')
    transport.call = observe
    with pytest.raises(OSError, match='interrupted dispatch'): ctrl.step()
    pending = _json(ctrl.root / 'progress.json')['pending']
    capture_path = ctrl.root / ('role-artifacts/' + pending['job_id'] + '-source.json')
    first = capture_path.read_bytes()
    transport.call = original
    ctrl.step()
    assert capture_path.read_bytes() == first
    assert transport.calls == [(pending['job_id'], 'author')]


def test_large_complete_source_archive_is_recoverable_without_truncating(tmp_path):
    ctrl = controller(tmp_path, SyntheticTransport(frame_response()))
    # Request + authoritative state can exceed one request's 128K boundary.
    value = {'request': {'documents': {'full': 'x' * 100_000}}, 'state': 'y' * 60_000}
    path = ctrl._archive_role_artifact('large-source', 'source', value)
    assert len(canonical(value)) > 128_000
    assert ctrl._archive_role_artifact('large-source', 'source', value) == path


def test_later_criterion_revision_does_not_replace_original_capture(tmp_path):
    ctrl = ready(tmp_path, (1, 0)); ctrl.step()
    first = (ctrl.root / 'measurement-custody/first.json').read_bytes()
    state = engine.get_state(ctrl.case); item = state['items']['crit1']
    engine.put_item(ctrl.case, 'crit1', 'criterion', 'Later synthetic weaker criterion',
                    list(item['deps']), item['data'], 'author:synthetic',
                    expected_version=item['version'], expected_deps=item['deps'])
    seal = custody._load(ctrl)
    assert seal['criteria']['crit1']['text'] == item['text']
    assert seal['criteria']['crit1']['version'] == item['version']
    assert (ctrl.root / 'measurement-custody/first.json').read_bytes() == first
    assert not engine.get_state(ctrl.case)['phases']['specify']['accepted']
    assert len(ctrl.executor.calls) == 1


def test_invalidated_specify_is_refused_before_first_measurement(tmp_path):
    ctrl = ready(tmp_path)
    state = engine.get_state(ctrl.case); item = state['items']['crit1']
    engine.put_item(ctrl.case, 'crit1', 'criterion', item['text'] + ' changed',
                    list(item['deps']), item['data'], 'author:synthetic',
                    expected_version=item['version'], expected_deps=item['deps'])
    current = engine.get_state(ctrl.case)
    pending = {'job_id': 'synthetic-unaccepted-criteria', 'source_state': current,
               'source_files': ctrl._files(), 'source_fingerprint': digest(canonical(current)), 'test_id': 't1'}
    with pytest.raises(ControllerError, match='accepted specify'):
        ctrl._criteria_before_measure(pending)
    assert ctrl.executor.calls == []
    assert not (ctrl.root / 'measurement-custody/first.json').exists()
