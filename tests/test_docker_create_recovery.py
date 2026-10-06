"""Control response loss fixtures; no provider generation or acceptance."""
import json
import subprocess
from types import SimpleNamespace

import pytest

from specorganon.docker_roles import DockerRoles, DockerRoleError, DockerControlDeadlineError
from specorganon.role_jobs import UncertainJob, _json, _write


@pytest.fixture
def recovery(tmp_path, monkeypatch):
    t = DockerRoles.__new__(DockerRoles)
    t.store = SimpleNamespace(root=tmp_path / 'journal')
    t.store.root.mkdir()
    folder = tmp_path / 'job'; folder.mkdir()
    plan = {'schema': 2, 'execution_nonce': 'd'*32, 'creation_not_before': '2026-10-06T00:00:00+00:00', 'create_argv': ['create'], 'name': 'owned-job', 'label': 'owner-label', 'image_id': 'sha256:' + 'a'*64}
    value = {'Name': '/owned-job', 'Created': '2026-10-06T01:00:00Z', 'Id': 'b'*64, 'Image': plan['image_id'],
             'Config': {'Labels': {'specorganon.run': plan['label'], 'specorganon.execution_nonce': plan['execution_nonce']}},
             'State': {'Status': 'created', 'Running': False, 'Restarting': False, 'Dead': False,
                       'StartedAt': '0001-01-01T00:00:00Z'}}
    monkeypatch.setattr(t, '_cli', lambda *a, **k: subprocess.CompletedProcess([], 0, json.dumps([value]).encode(), b''))
    _write(folder / 'create-attempt.json', t._creation_attempt(plan))
    return t, folder, plan, value


def test_create_deadline_requires_owned_never_started_proof(recovery):
    t, folder, plan, value = recovery
    assert t._recover_created('job', folder, plan, DockerControlDeadlineError('create')) == value['Id']
    receipt = _json(folder / 'control-recovery.json')
    assert receipt['create_repeated'] is False and receipt['execution_started_at_observation'] is False
    assert receipt['scope'] == 'control response recovery only; no role outcome or acceptance'
    assert not (t.store.root / 'job/started.json').exists()


@pytest.mark.parametrize('key,changed', [('Status','exited'), ('Status','running'),
    ('Running',True), ('Restarting',True), ('Dead',True),
    ('StartedAt','2026-10-06T03:00:00Z'), ('Running',0), ('Dead',None)])
def test_started_or_ambiguous_container_cannot_recover(recovery, key, changed):
    t, folder, plan, value = recovery
    value['State'][key] = changed
    with pytest.raises(UncertainJob):
        t._recover_created('job', folder, plan, DockerControlDeadlineError('create'))
    assert not (folder / 'control-recovery.json').exists()


@pytest.mark.parametrize('field', ['label','image','id'])
def test_wrong_ownership_or_handle_cannot_recover(recovery, field):
    t, folder, plan, value = recovery
    if field == 'label': value['Config']['Labels']['specorganon.run'] = 'other'
    if field == 'image': value['Image'] = 'sha256:'+'c'*64
    if field == 'id': value['Id'] = 'invalid'
    with pytest.raises((DockerRoleError, UncertainJob)):
        t._recover_created('job', folder, plan, DockerControlDeadlineError('create'))
    assert not (folder / 'control-recovery.json').exists()


@pytest.mark.parametrize('name', ['started.json','receipt.json'])
def test_journal_execution_proof_prevents_create_recovery(recovery, name):
    t, folder, plan, value = recovery
    (t.store.root / 'job').mkdir(); _write(t.store.root / 'job' / name, {'fixture': True})
    with pytest.raises(UncertainJob):
        t._recover_created('job', folder, plan, DockerControlDeadlineError('create'))


def test_missing_container_or_inspection_deadline_stays_uncertain(recovery, monkeypatch):
    t, folder, plan, value = recovery
    monkeypatch.setattr(t, '_inspect', lambda plan: None)
    with pytest.raises(UncertainJob):
        t._recover_created('job', folder, plan, DockerControlDeadlineError('create'))
    def timeout(plan): raise DockerControlDeadlineError('inspect')
    monkeypatch.setattr(t, '_inspect', timeout)
    with pytest.raises(DockerControlDeadlineError, match='inspect'):
        t._recover_created('job', folder, plan, DockerControlDeadlineError('create'))
    assert not (folder / 'control-recovery.json').exists()


def test_other_control_deadlines_are_not_recoverable(recovery):
    t, folder, plan, value = recovery
    with pytest.raises(DockerControlDeadlineError, match='inspect'):
        t._recover_created('job', folder, plan, DockerControlDeadlineError('inspect'))
    assert not (folder / 'control-recovery.json').exists()


def test_recovery_observation_cannot_be_replaced(recovery):
    t, folder, plan, value = recovery
    t._recover_created('job', folder, plan, DockerControlDeadlineError('create'))
    before = (folder / 'control-recovery.json').read_bytes()
    value['Id'] = 'c'*64
    with pytest.raises(UncertainJob, match='observation changed'):
        t._recover_created('job', folder, plan, DockerControlDeadlineError('create'))
    assert (folder / 'control-recovery.json').read_bytes() == before


@pytest.mark.parametrize('change', ['nonce', 'missing_nonce', 'predates_intent', 'invalid_time', 'wrong_name'])
def test_nonce_and_creation_time_bind_exact_persisted_intent(recovery, change):
    t, folder, plan, value = recovery
    if change == 'nonce': value['Config']['Labels']['specorganon.execution_nonce'] = 'e'*32
    if change == 'missing_nonce': del value['Config']['Labels']['specorganon.execution_nonce']
    if change == 'predates_intent': value['Created'] = '2026-10-05T23:00:00Z'
    if change == 'wrong_name': value['Name'] = '/other-job'
    if change == 'invalid_time': value['Created'] = 'unknown'
    with pytest.raises(DockerRoleError):
        t._recover_created('job', folder, plan, DockerControlDeadlineError('create'))
    assert not (folder / 'control-recovery.json').exists()


def test_crash_before_handle_then_missing_container_does_not_recreate(recovery, monkeypatch):
    t, folder, plan, value = recovery
    t._recover_created('job', folder, plan, DockerControlDeadlineError('create'))
    plan['container_id'] = None
    monkeypatch.setattr(t, '_prepare', lambda *a: (folder, plan))
    monkeypatch.setattr(t, '_inspect', lambda plan: None)
    def forbidden_create(*a, **k): raise AssertionError('must not recreate missing recovered container')
    monkeypatch.setattr(t, '_cli', forbidden_create)
    with pytest.raises(UncertainJob): t._execute('job', 'author', {'fixture': True})


def test_attempt_without_recovery_record_and_missing_container_never_recreates(recovery, monkeypatch):
    t, folder, plan, value = recovery
    plan['container_id'] = None
    monkeypatch.setattr(t, '_prepare', lambda *a: (folder, plan))
    monkeypatch.setattr(t, '_inspect', lambda plan: None)
    def forbidden(*a, **k): raise AssertionError('missing uncertain create must not be retried')
    monkeypatch.setattr(t, '_cli', forbidden)
    with pytest.raises(UncertainJob, match='previously attempted'):
        t._execute('job', 'author', {'fixture': True})


@pytest.mark.parametrize('change', ['already_started', 'running_flag', 'missing_attempt', 'changed_attempt'])
def test_resume_adoption_uses_same_never_started_and_attempt_guards(recovery, monkeypatch, change):
    t, folder, plan, value = recovery
    plan['container_id'] = None
    if change == 'already_started': value['State']['StartedAt'] = '2026-10-06T02:00:00Z'
    if change == 'running_flag': value['State']['Running'] = True
    if change == 'missing_attempt': (folder/'create-attempt.json').unlink()
    if change == 'changed_attempt': _write(folder/'create-attempt.json', {'changed': True})
    monkeypatch.setattr(t, '_prepare', lambda *a: (folder, plan))
    with pytest.raises(UncertainJob): t._execute('job', 'author', {'fixture': True})
    assert not (folder/'launch.json').exists()


@pytest.mark.parametrize('change', ['marker_changed', 'marker_deleted', 'recovery_changed', 'recovery_deleted'])
def test_closed_handle_validates_historical_creation_records_before_reuse(recovery, monkeypatch, change):
    from specorganon.role_jobs import digest, _read
    t, folder, plan, value = recovery
    plan['container_id'] = t._recover_created('job', folder, plan, DockerControlDeadlineError('create'))
    plan['control_recovery_sha256'] = digest(_read(folder/'control-recovery.json'))
    # A finished container's current state must not be used as the historical observation.
    value['State']['Status'] = 'exited'
    value['State']['StartedAt'] = '2026-10-06T02:00:00Z'
    monkeypatch.setattr(t, '_prepare', lambda *a: (folder, plan))
    record = folder/('create-attempt.json' if change.startswith('marker') else 'control-recovery.json')
    if change.endswith('deleted'): record.unlink()
    else: _write(record, {'changed': True})
    def forbidden(*a, **k): raise AssertionError('divergence must be rejected before any Docker control/reuse')
    monkeypatch.setattr(t, '_cli', forbidden)
    with pytest.raises(UncertainJob): t._execute('job', 'author', {'fixture': True})
