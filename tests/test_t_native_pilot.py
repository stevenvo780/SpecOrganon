"""Synthetic registration/sealed-reader guards; zero native generations."""
import copy
import importlib.util
from pathlib import Path

import pytest

from specorganon import t_native_pilot as T
from specorganon.neutral_pilot import PilotError, inventory
from specorganon.role_jobs import _write, canonical, digest
from test_neutral_pilot import plan as neutral_plan


SOURCE = Path(__file__).resolve().parents[1]


def registration(tmp_path):
    neutral = neutral_plan(tmp_path)
    spec = importlib.util.spec_from_file_location('register_t_fixture', SOURCE / 'scripts/register_t_native_pilot.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    capacity = {'observed_at': '2026-10-06T00:00:00Z',
                'scope': 'Observation only; no availability or admission inferred',
                'catalog': {'status': 'unknown', 'source': 'Explicit fixture', 'sha256': None},
                'quota': {'status': 'unknown', 'source': 'Explicit fixture', 'sha256': None}}
    return module.prepare(SOURCE, tmp_path / 'T-runtime', 'fixture-T-registration', neutral['transport'], capacity)


def test_registration_ten_original_positions_three_types_preserves_unknown(tmp_path):
    r = registration(tmp_path)
    assert r['attempts'] == T.ATTEMPTS and len(r['attempts']) == 10
    assert {t: sum(a['task'] == t for a in r['attempts']) for t in T.TASKS} == {
        'rangeaudit': 4, 'ledgerfold': 3, 'topoplan': 3}
    assert r['capacity_evidence']['quota']['status'] == 'unknown'
    assert not r['automatic_replacement'] and not Path(r['run_root']).exists()
    assert not r['scope']['goal_achieved'] and r['scope']['external_F'] is None
    assert 'GOAL.md' in r['source_sha256'] and T.MANDATE in r['source_sha256']


@pytest.mark.parametrize('change', ['fixture', 'replace', 'version', 'order', 'missing_source',
    'nine_positions', 'N_mandate', 'H_missing', 'deadline', 'unknown_as_known', 'mutable_image', 'source_runtime'])
def test_registration_refuses_weakened_policy_or_source(tmp_path, change):
    r = copy.deepcopy(registration(tmp_path))
    if change == 'fixture': r['fixture_mode'] = True
    elif change == 'replace': r['automatic_replacement'] = True
    elif change == 'version': r['candidate_version'] = '0.2.0rc3.dev11'
    elif change == 'order': r['attempts'].reverse()
    elif change == 'missing_source': r['source_sha256'].pop('src/specorganon/docker_roles.py')
    elif change == 'nine_positions': r['attempts'].pop()
    elif change == 'N_mandate': r['mandate'] = 'goals/method-superiority-v1/development/neutral-autonomy-v2/mandate.md'
    elif change == 'H_missing': r['H_checklist'].pop(next(iter(r['H_checklist'])))
    elif change == 'deadline': r['controller_limits']['elapsed_admission_seconds'] = 6001
    elif change == 'unknown_as_known': r['capacity_evidence']['quota']['status'] = 'known'
    elif change == 'mutable_image': r['transport']['test_image'] = 'latest'
    elif change == 'source_runtime': r['run_root'] = r['source_root']
    with pytest.raises(PilotError): T.validate_registration(r)


def test_report_not_started_is_pure_and_keeps_ten_positions(tmp_path, monkeypatch):
    r = registration(tmp_path)
    monkeypatch.setattr(T, 'load_plan', lambda *args, **kwargs: r)  # Explicit bootstrap fixture.
    def forbidden(*args, **kwargs): pytest.fail('report must not dispatch, construct or lock')
    for name in ('controller', '_lock', 'run_attempt', 'transport'):
        monkeypatch.setattr(T, name, forbidden)
    result = T.execute(tmp_path / 'not-needed.json', 'a' * 64, 'report', installed_root=tmp_path)
    assert result['status'] == 'incomplete' and result['planned_denominator'] == 10
    assert result['closed_attempts'] == result['original_native_ready_count'] == 0
    assert [p['attempt'] for p in result['positions']] == T.ATTEMPTS
    assert all(p['status'] == 'not_started' for p in result['positions'])
    assert not result['development_qualification'] and not result['goal_achieved']
    assert not Path(r['run_root']).exists()


def sealed_fixture(tmp_path):
    # These deliberately fabricated records test sealed consistency only.
    a = T.ATTEMPTS[0]; expected = 'a' * 64; folder = tmp_path / a['id']
    (folder / 'controller').mkdir(parents=True)
    start = T._clock(); end = T._clock()
    _write(folder / 'started.json', {'schema': 1, 'attempt': a, 'plan_sha256': expected, 'clock': start})
    _write(folder / 'terminal-clock.json', {'schema': 1, 'clock': end})
    terminal = {'schema': 1, 'method': 'T', 'attempt_id': a['id'], 'fixture_mode': False, 'native_ready': False,
                'status': 'failed', 'failure': 'Explicit fabricated reader control'}
    for name in ('terminal.json', 'terminal-intent.json'): _write(folder / 'controller' / name, terminal)
    row = {'schema': 1, 'plan_sha256': expected, 'attempt': a, 'controller_report': terminal,
           'whole_driver_seconds': T._elapsed(start, end), 'clock_error': None,
           'public_development_functionality': {'status': 'unavailable', 'score': None},
           'shared_preparation_seconds': None, 'monetary_cost': None,
           'external_F': None, 'common_complete': None, 'goal_achieved': False,
           'evidence_sha256': inventory(folder)}
    _write(folder / 'outcome.json', row)
    _write(folder / 'closure.json', {'schema': 1, 'outcome_sha256': digest(canonical(row)),
                                   'evidence_sha256': inventory(folder)})
    return folder, expected, a, row


def test_sealed_reader_never_rewrites_or_requalifies(tmp_path):
    folder, expected, a, row = sealed_fixture(tmp_path)
    before = {str(p): (p.stat().st_mtime_ns, p.read_bytes()) for p in folder.rglob('*') if p.is_file()}
    assert T.read_closed(folder, expected, a) == row
    after = {str(p): (p.stat().st_mtime_ns, p.read_bytes()) for p in folder.rglob('*') if p.is_file()}
    assert before == after


@pytest.mark.parametrize('target', ['started.json', 'terminal-clock.json', 'controller/terminal.json',
                                  'controller/terminal-intent.json', 'outcome.json', 'closure.json', 'extra.txt'])
def test_sealed_reader_refuses_original_custody_changes(tmp_path, target):
    folder, expected, a, row = sealed_fixture(tmp_path)
    _write(folder / target, {'changed': 'Explicit fixture tamper'})
    with pytest.raises((ValueError, KeyError)): T.read_closed(folder, expected, a)


def test_controller_factory_receives_same_original_budget(tmp_path, monkeypatch):
    r = registration(tmp_path); a = T.ATTEMPTS[0]; captured = {}
    def fake_controller(root, **kwargs):
        captured.update(kwargs); return object()
    monkeypatch.setattr(T, 'TCommonController', fake_controller)
    monkeypatch.setattr(T, 'transport', lambda r, root, **kwargs: kwargs)
    T.controller(r, a, tmp_path)
    binding = {'attempt_clock': T._clock(), 'attempt_initial_sha256': 'b' * 64}
    assert captured['fixture_mode'] is False
    assert captured['transport_factory'](tmp_path, **binding) == binding
    assert captured['transport_policy']['terminal_container_policy'] == 'strict-exited-lifecycle-v1'
