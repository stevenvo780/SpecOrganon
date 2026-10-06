"""Mechanical guard tests, not a generated CSVShape implementation or acceptance."""
import json

import pytest

from experiments.csvshape_delivery_v1.reserved import judge, recipes, summary
from scripts import csvshape_delivery as driver
from specorganon import engine
from specorganon.role_jobs import _write, _json


def test_prospective_matrix_unique_boundaries_and_public_examples():
    matrix = recipes()
    assert len(matrix) == 48 and len({r['id'] for r in matrix}) == 48
    assert [r['id'] for r in matrix if r['public']] == ['public-1', 'public-2']
    selected = {r['id']: r for r in matrix}
    for size in (65536, 65537):
        assert len(bytes.fromhex(selected['input-bytes-' + str(size)]['stdin_hex'])) == size
    assert selected['input-bytes-65536']['expected']['rows'] == 16
    assert selected['input-bytes-65537']['expected'] is None
    assert selected['rows-1000']['expected']['rows'] == 1000
    assert selected['rows-1001']['expected'] is None


def test_typed_judge_rejects_booleans_extra_keys_and_uncertain_results():
    recipe = recipes()[0]
    value = recipe['expected'].copy()
    def result(output): return {'exit_code': 0, 'stdout': json.dumps(output).encode() + b'\n', 'stderr': b'',
                                'timed_out': False, 'truncated_streams': False}
    assert judge(recipe, result(value))['status'] == 'pass'
    value['rows'] = True
    assert judge(recipe, result(value))['status'] == 'fail'
    value = dict(recipe['expected'], extra=0)
    assert judge(recipe, result(value))['status'] == 'fail'
    value = result(recipe['expected']); value['infrastructure_error'] = 'unknown receipt'
    assert judge(recipe, value)['status'] == 'inconclusive'


def test_error_judge_exact_atomic_framing():
    recipe = next(r for r in recipes() if r['id'] == 'empty')
    value = {'exit_code': 2, 'stdout': b'', 'stderr': b'{"error":"invalid_input"}\n',
             'timed_out': False, 'truncated_streams': False}
    assert judge(recipe, value)['status'] == 'pass'
    for key, changed in [('stdout', b'{}\n'), ('stderr', b'bad input\n'), ('exit_code', 0)]:
        assert judge(recipe, {**value, key: changed})['status'] == 'fail'


def configured(tmp_path, monkeypatch):
    case = tmp_path / 'case'; root = tmp_path / 'run'; source = tmp_path / 'source'; source.mkdir()
    value = {'run_root': str(root), 'case': str(case), 'source_root': str(source),
             'images': {'native': 'synthetic', 'test': 'synthetic'}, 'public_catalog': 'catalog.json',
             'routes': {'author': {'model': 'synthetic'}, 'review': {'model': 'synthetic'}}, 'profiles': {}}
    calls = []
    def verify(path, **kwargs):
        calls.append(kwargs.get('check_sources', True)); return value, 'a' * 64
    value['identity'] = 'synthetic-guard'
    monkeypatch.setattr(driver, 'verify_registration', verify)
    monkeypatch.setattr(driver, 'current_quota', lambda p: {'synthetic': True})
    return value, calls


def test_single_initialization_does_not_generate_artifacts(tmp_path, monkeypatch):
    value, calls = configured(tmp_path, monkeypatch)
    result = driver.run('synthetic', 'synthetic', initialize=True)
    assert result == {'status': 'initialized', 'artifact_generation_calls': 0}
    state = engine.get_state(value['case']); assert not state['items']
    assert calls == [False, True]
    before = (tmp_path / 'case/organon.json').read_bytes()
    assert driver.run('synthetic', 'synthetic', initialize=True)['status'] == 'delivery_stopped'
    assert (tmp_path / 'case/organon.json').read_bytes() == before


def test_native_failure_closes_identity_and_retry_dispatches_nothing(tmp_path, monkeypatch):
    value, _ = configured(tmp_path, monkeypatch)
    driver.run('synthetic', 'synthetic', initialize=True)
    dispatch = []
    def failed_transport(*args, **kwargs):
        dispatch.append(1); raise driver.DockerRoleError('synthetic native startup failure')
    monkeypatch.setattr(driver, 'DockerRoles', failed_transport)
    first = driver.run('synthetic', 'synthetic')
    assert first['status'] == 'delivery_stopped' and first['replacement'] is False
    assert driver.run('synthetic', 'synthetic', steps=80) == first
    assert dispatch == [1]


def test_quota_pause_never_initializes_or_creates_terminal(tmp_path, monkeypatch):
    value, _ = configured(tmp_path, monkeypatch)
    def stale(p): raise driver.CampaignPause('stale synthetic quota')
    monkeypatch.setattr(driver, 'current_quota', stale)
    result = driver.run('synthetic', 'synthetic', initialize=True)
    assert result['status'] == 'paused' and not result['budget_renewed']
    assert not (tmp_path / 'case').exists() and not (tmp_path / 'run/terminal.json').exists()


def test_observed_source_change_closes_existing_identity(tmp_path, monkeypatch):
    value, _ = configured(tmp_path, monkeypatch)
    driver.run('synthetic', 'synthetic', initialize=True)
    def changed(path, **kwargs):
        if kwargs.get('check_sources', True): raise driver.RegistrationError('registered source changed')
        return value, 'a' * 64
    monkeypatch.setattr(driver, 'verify_registration', changed)
    result = driver.run('synthetic', 'synthetic')
    assert result['status'] == 'delivery_stopped'
    assert _json(tmp_path / 'run/terminal.json') == result


@pytest.mark.parametrize('mode', ['complete', 'failed_point', 'missing_point', 'boolean_as_number'])
def test_final_native_rubric_requires_every_typed_point_and_retains_rejection(tmp_path, monkeypatch, mode):
    case = tmp_path / 'case'; root = tmp_path / 'run'; root.mkdir()
    engine.create_case(case, 'Synthetic audit guard', 'development', 'human:owner', approval_policy='local')
    _write(root / 'progress.json', {'history': []})
    class Controller:
        contract = 'synthetic audit guard'
        def _files(self): return {'README.md': 'synthetic audit mechanics only'}
    controller = Controller(); controller.case = case; controller.root = root
    class Budget:
        def call(self, job_id, role, request):
            assert job_id == 'final-doc-method-audit' and role == 'review'
            assert 'reserved' not in request['documents']
            result = {'schema': 1, 'tests_executed': False, 'reason': 'Synthetic guard judgment only',
                      'verdict': 'reject' if mode == 'failed_point' else 'accept', 'findings': [],
                      'doc_checks': [{'id': i, 'passed': True, 'reason': 'synthetic'} for i in driver.DOC_IDS],
                      'method_checks': [{'id': i, 'passed': True, 'reason': 'synthetic'} for i in driver.METHOD_IDS]}
            if mode == 'failed_point': result['doc_checks'][0]['passed'] = False
            if mode == 'missing_point': result['doc_checks'].pop()
            if mode == 'boolean_as_number': result['doc_checks'][0]['passed'] = 1
            from scripts.controller_native_role import validate_result
            validate_result(result, 'review')
            return {'result': result, 'provenance': 'synthetic'}
    if mode in {'missing_point', 'boolean_as_number'}:
        with pytest.raises(driver.ControllerError): driver.final_audit(controller, Budget(), root)
    else:
        audit = driver.final_audit(controller, Budget(), root)
        assert audit['documentation_passed'] == (mode == 'complete')
        assert audit['documentation_score'] == (8 if mode == 'complete' else 7)
        assert _json(root / 'final-doc-method-audit.json') == audit
