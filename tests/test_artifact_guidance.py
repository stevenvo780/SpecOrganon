"""Synthetic field/reference controls; never a new delivery or native acceptance."""
import copy
import json
from pathlib import Path

import pytest

from specorganon import engine
from specorganon.artifact_guidance import data_contract, reference_maintenance
from specorganon.role_jobs import _json, _write, canonical
from specorganon.software_controller import Controller, ControllerError


def state_fixture():
    return {'items': {
        'protocol': {'version': 2, 'deps': {}, 'stale': False, 'issues': []},
        'evidence': {'version': 1, 'deps': {'protocol': 1}, 'stale': True, 'issues': []},
        'indicator': {'version': 2, 'deps': {'evidence': 1}, 'stale': True, 'issues': []},
        'observed': {'version': 1, 'deps': {'protocol': 2}, 'stale': False,
                     'issues': ['observed evidence lacks collection method']},
    }}


def test_exact_observed_method_key_is_checked_by_actual_engine_validator():
    data = {'origin': 'observed', 'source': 'Synthetic source', 'date': '2026-10-05',
            'locator': 'Synthetic fixture', 'collection_method': 'Synthetic collection'}
    item = {'kind': 'evidence', 'id': 'e1', 'data': data}
    assert engine._item_issues(item) == ['observed evidence lacks collection method']
    item['data'] = {**data, 'method': 'Synthetic collection'}
    assert engine._item_issues(item) == []
    assert set(data_contract()['evidence']['observed_requires']) == {'method'}


def test_field_contract_returns_owned_copy_not_mutable_global():
    value = data_contract(); value['evidence']['required'].clear()
    assert data_contract()['evidence']['required'] == ['origin', 'source', 'date', 'locator']


def test_transitive_stale_hint_points_to_root_edge_without_mutating_state():
    state = state_fixture(); before = copy.deepcopy(state)
    hint = reference_maintenance(state)
    assert hint['direct_version_mismatches'] == [['evidence', 'protocol', 1, 2]]
    assert hint['stale_item_ids'] == ['evidence', 'indicator']
    assert hint['invalid_item_ids'] == ['observed']
    order = hint['dependency_order']
    assert order.index('protocol') < order.index('evidence') < order.index('indicator')
    assert state == before


def test_cycle_and_missing_dependency_never_claim_repair_or_valid_total_order():
    state = {'items': {'a': {'version': 1, 'deps': {'b': 1}, 'stale': True, 'issues': []},
                       'b': {'version': 1, 'deps': {'a': 1, 'missing': 1}, 'stale': True, 'issues': []}}}
    hint = reference_maintenance(state)
    assert hint['dependency_order'] is None
    assert hint['unresolved_dependency_node_ids'] == ['a', 'b']
    assert hint['direct_version_mismatches'] == [['b', 'missing', 1, None]]
    assert 'not a repair' in hint['scope']


def test_dense_graph_hint_explicitly_summarizes_without_shortening_authoritative_state():
    state = {'items': {}}
    for n in range(54):
        identity = 'item-' + str(n).zfill(2) + '-long-identifier'
        state['items'][identity] = {'version': 2, 'deps': {k: 1 for k in state['items']},
                                   'stale': n > 0, 'issues': []}
    before = copy.deepcopy(state)
    hint = reference_maintenance(state)
    assert hint['mode'] == 'summary_only' and hint['details_omitted']
    assert hint['counts']['direct_version_mismatches'] == 54 * 53 // 2
    assert len(canonical(hint)) <= 4096 and state == before
    assert 'state.json/items' in hint['details_locator']
    tiny = reference_maintenance(state, max_bytes=512)
    assert tiny['mode'] == 'summary_only' and len(canonical(tiny)) <= 512


def create_controller(tmp_path):
    case = tmp_path / 'case'; engine.create_case(case, 'Synthetic guidance controls', 'development',
                                               'human:owner', approval_policy='local')
    return Controller(case, tmp_path / 'run', object(), contract='Synthetic guard scope',
                      mandate='Synthetic guard mandate', fixture_mode=True)


def test_new_request_adds_guidance_and_preserves_complete_authoritative_state(tmp_path):
    ctrl = create_controller(tmp_path); state = engine.get_state(ctrl.case)
    before = (ctrl.case / 'organon.json').read_bytes()
    request = ctrl._request(state, 'author', {'history': []})
    assert json.loads(request['documents']['state.json']) == state
    assert json.loads(request['documents']['artifact-data-contract.json']) == data_contract()
    assert json.loads(request['documents']['reference-maintenance.json'])['scope'].startswith('Read-only advisory')
    assert (ctrl.case / 'organon.json').read_bytes() == before
    policy = _json(ctrl.root / 'controller.json')
    assert policy['schema'] == 8 and policy['max_author_per_phase'] == 2
    assert policy['max_role_calls'] == 40 and policy['max_phase_encoded_bytes'] == 6000


def test_schema7_rejected_before_recreating_delivery_tree_or_touching_case(tmp_path):
    ctrl = create_controller(tmp_path)
    policy = _json(ctrl.root / 'controller.json'); policy['schema'] = 7
    for key in ('artifact_data_contract_sha256', 'artifact_guidance_source_sha256', 'reference_hint_schema', 'max_reference_hint_bytes'): policy.pop(key)
    _write(ctrl.root / 'controller.json', policy); ctrl.delivery.rmdir()
    before = (ctrl.case / 'organon.json').read_bytes()
    with pytest.raises(ControllerError, match='versioned run'):
        Controller(ctrl.case, ctrl.root, object(), contract=ctrl.contract, mandate=ctrl.mandate, fixture_mode=True)
    assert not ctrl.delivery.exists() and (ctrl.case / 'organon.json').read_bytes() == before


def test_registered_runner_cannot_claim_a_different_source_checkout(tmp_path):
    from scripts.csvshape_delivery import verify_runtime_sources, RegistrationError
    with pytest.raises(RegistrationError, match='executing source checkout'):
        verify_runtime_sources(tmp_path, {})


def test_registered_runner_rejects_imports_without_actual_module_bindings():
    from scripts.csvshape_delivery import verify_runtime_sources, RegistrationError
    source = Path(__file__).absolute().parents[1]
    with pytest.raises(RegistrationError, match='runtime module (is not source-bound|lacks registered source file)'):
        verify_runtime_sources(source, {})


def test_explicit_upstream_then_descendant_puts_clear_real_engine_stale_flags(tmp_path):
    case = tmp_path / 'case'
    engine.create_case(case, 'Synthetic version propagation control', 'development', 'human:owner', approval_policy='local')
    def put(identity, kind, refs, data, text='Synthetic diagnostic artifact, no native acceptance'):
        state = engine.get_state(case)
        engine.put_item(case, identity, kind, text, refs, data, 'agent:synthetic-control',
                        expected_version=state['items'].get(identity, {}).get('version', 0),
                        expected_deps={r: state['items'][r]['version'] for r in refs})
    put('p1', 'problem', [], {})
    put('q1', 'question', ['p1'], {})
    put('h1', 'hypothesis', ['q1'], {})
    protocol = {'population': 'Synthetic populationA', 'method': 'Synthetic enumeration',
                'comparison': 'Synthetic comparison', 'uncertainty': 'Synthetic context, no field result'}
    put('pr', 'protocol', ['q1', 'h1'], protocol)
    evidence = {'origin': 'observed', 'source': 'Synthetic source', 'date': '2026-10-05',
                'locator': 'Synthetic location', 'method': 'Synthetic collection'}
    put('e1', 'evidence', ['pr'], evidence)
    put('i1', 'indicator', ['e1'], {'metric': 'synthetic_metric', 'unit': 'count'})
    put('pr', 'protocol', ['q1', 'h1'], {**protocol, 'population': 'Synthetic populationB'})
    state = engine.get_state(case); hint = reference_maintenance(state)
    assert hint['direct_version_mismatches'] == [['e1', 'pr', 1, 2]]
    assert state['items']['e1']['stale'] and state['items']['i1']['stale']
    put('e1', 'evidence', ['pr'], evidence, 'Synthetic reconsidered evidence after population change; no measured benefit')
    assert engine.get_state(case)['items']['i1']['stale']
    put('i1', 'indicator', ['e1'], {'metric': 'synthetic_metric', 'unit': 'count'},
        'Synthetic reconsidered indicator after explicit evidence revision')
    state = engine.get_state(case)
    assert not state['items']['e1']['stale'] and not state['items']['i1']['stale']
    assert not any(phase['accepted'] for phase in state['phases'].values())


def test_missing_dependency_without_cycle_does_not_claim_complete_order():
    state = {'items': {'dependent': {'version': 1, 'deps': {'missing': 1}, 'stale': True, 'issues': []}}}
    hint = reference_maintenance(state)
    assert hint['dependency_order'] is None
    assert hint['unresolved_dependency_node_ids'] == ['dependent']


def test_registered_runtime_accepts_current_bound_modules_and_rejects_outside_import(tmp_path, monkeypatch):
    import sys
    import types
    from scripts.csvshape_delivery import verify_runtime_sources, RegistrationError
    from specorganon.role_jobs import digest
    source = Path(__file__).absolute().parents[1]
    bindings = {}
    for name, module in list(sys.modules.items()):
        if name in ('specorganon', 'scripts', 'experiments') or name.startswith(('specorganon.', 'scripts.', 'experiments.')):
            filename = getattr(module, '__file__', None)
            if filename is not None:
                path = Path(filename).absolute()
                bindings[str(path.relative_to(source))] = digest(path.read_bytes())
    verify_runtime_sources(source, bindings)
    injected = types.ModuleType('experiments.synthetic_outside')
    injected.__file__ = str(tmp_path / 'outside.py')
    monkeypatch.setitem(sys.modules, injected.__name__, injected)
    with pytest.raises(RegistrationError, match='outside registered source'):
        verify_runtime_sources(source, bindings)


@pytest.mark.parametrize('state', [{}, {'items': []}, {'items': {'bad': {}}},
    {'items': {'bad': {'version': True, 'deps': {}, 'stale': False, 'issues': []}}},
    {'items': {'bad': {'version': 1, 'deps': {'parent': '1'}, 'stale': False, 'issues': []}}}])
def test_malformed_reference_state_raises_controlled_value_error(state):
    with pytest.raises(ValueError, match='guidance requires'):
        reference_maintenance(state)


@pytest.mark.parametrize('phase', ['unknown', None, []])
def test_unknown_phase_guidance_raises_controlled_value_error(phase):
    from specorganon.artifact_guidance import phase_guidance
    with pytest.raises(ValueError, match='unknown phase'):
        phase_guidance(phase)


def test_guidance_source_digest_is_bound_and_cannot_resume_different_policy(tmp_path):
    from specorganon.role_jobs import digest
    ctrl = create_controller(tmp_path)
    policy = _json(ctrl.root / 'controller.json')
    guidance = Path(__file__).absolute().parents[1] / 'src/specorganon/artifact_guidance.py'
    assert policy['artifact_guidance_source_sha256'] == digest(guidance.read_bytes())
    policy['artifact_guidance_source_sha256'] = '0' * 64
    _write(ctrl.root / 'controller.json', policy)
    with pytest.raises(ControllerError, match='versioned run'):
        Controller(ctrl.case, ctrl.root, object(), contract=ctrl.contract, mandate=ctrl.mandate, fixture_mode=True)


def test_registered_runtime_rejects_fileless_nonnamespace_module(monkeypatch):
    import sys
    import types
    from scripts.csvshape_delivery import verify_runtime_sources, RegistrationError
    from specorganon.role_jobs import digest
    source = Path(__file__).absolute().parents[1]
    bindings = {}
    for name, module in list(sys.modules.items()):
        if name in ('specorganon', 'scripts', 'experiments') or name.startswith(('specorganon.', 'scripts.', 'experiments.')):
            filename = getattr(module, '__file__', None)
            if filename is not None:
                path = Path(filename).absolute(); bindings[str(path.relative_to(source))] = digest(path.read_bytes())
    injected = types.ModuleType('specorganon.synthetic_fileless')
    monkeypatch.setitem(sys.modules, injected.__name__, injected)
    with pytest.raises(RegistrationError, match='lacks registered source file'):
        verify_runtime_sources(source, bindings)
