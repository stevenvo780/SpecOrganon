"""Strict grammar guidance and rejection tests; no native success is inferred."""
import copy
import json

import pytest

from specorganon.author_contract import author_manifest_contract, manifest_error_detail
from specorganon import engine
from specorganon.role_jobs import _json, digest, _read
from specorganon.software_controller import Controller, ControllerError
from specorganon.workflow import KIND_TO_PHASE, PHASES
from test_software_controller import SyntheticTransport, controller, frame_response


def test_author_request_declares_put_fields_for_each_phase_without_invented_content(tmp_path):
    ctrl = controller(tmp_path, SyntheticTransport(frame_response()))
    request = ctrl._request(engine.get_state(ctrl.case), 'author', {'history': []})
    declared = json.loads(request['documents']['author-manifest-contract.json'])
    assert declared == author_manifest_contract('frame')
    assert declared['steps_count'] == [1, 32]
    assert set(declared['put_required']) == {'op', 'id', 'kind', 'text', 'refs', 'data'}
    assert 'author-manifest-contract.json' in request['role_instructions']
    for phase in PHASES:
        contract = author_manifest_contract(phase.id)
        expected = {k for k, p in KIND_TO_PHASE.items()
                    if p == phase.id or (phase.id == 'study' and k == 'evidence')}
        assert set(contract['kinds']) == expected
        assert contract['id_pattern'] == engine.ITEM_ID.pattern
    assert 'passed' not in declared['response_fields']
    assert declared['advisory'] is True


@pytest.mark.parametrize('fault,detail', [
    ('missing_op', 'step 0: requires op=put for author work'),
    ('extra_field', 'unknown manifest fields'),
    ('invalid_id', 'step 0: has invalid item id'),
    ('bad_deps', 'step 1: expected_deps must map every ref to a positive version'),
    ('empty_steps', 'author needs bounded substantive puts'),
])
def test_known_native_failure_shapes_still_reject_without_rewriting_packet_or_ledger(tmp_path, fault, detail):
    response = frame_response()
    if fault == 'missing_op': response['manifest']['steps'][0].pop('op')
    elif fault == 'extra_field': response['manifest']['phase'] = 'frame'
    elif fault == 'invalid_id': response['manifest']['steps'][0]['id'] = 'bad.id'
    elif fault == 'bad_deps': response['manifest']['steps'][1]['expected_deps'] = {}
    else: response['manifest']['steps'] = []
    original = copy.deepcopy(response)
    transport = SyntheticTransport(response)
    ctrl = controller(tmp_path, transport)
    before = (ctrl.case / 'organon.json').read_bytes()
    with pytest.raises(ControllerError, match=detail):
        ctrl.step()
    assert response == original
    assert (ctrl.case / 'organon.json').read_bytes() == before
    assert ctrl._files() == {}
    progress = _json(ctrl.root / 'progress.json')
    assert progress['pending']['packet']['result'] == original
    assert transport.calls == [('role-01-frame-author', 'author')]


def test_schema9_cannot_be_resumed_under_new_contract_even_with_no_work(tmp_path):
    ctrl = controller(tmp_path, SyntheticTransport(frame_response()))
    policy = _json(ctrl.root / 'controller.json')
    assert policy['schema'] == 10
    assert policy['author_manifest_contract_source_sha256'] == digest(
        _read(__import__('specorganon.author_contract', fromlist=['x']).__file__, 128000))
    policy['schema'] = 9
    from specorganon.role_jobs import _write
    _write(ctrl.root / 'controller.json', policy)
    before = (ctrl.case / 'organon.json').read_bytes()
    with pytest.raises(ControllerError, match='versioned run'):
        Controller(ctrl.case, ctrl.root, ctrl.transport, contract=ctrl.contract,
                   mandate=ctrl.mandate, fixture_mode=True)
    assert (ctrl.case / 'organon.json').read_bytes() == before
    assert ctrl.transport.calls == []


def test_error_detail_never_echoes_untrusted_operation_or_unknown_errors():
    arbitrary = "secret-like-untrusted-value\n" + "x" * 10000
    assert manifest_error_detail(ValueError('step 0 has unsupported op: ' + arbitrary)) == (
        'step 0: requires op=put for author work')
    assert manifest_error_detail(ValueError(arbitrary)) == 'manifest violates declared grammar'


def test_T_and_A_receive_identical_author_grammar(tmp_path):
    from test_software_comparison_v3_cells import cell
    treatment = controller(tmp_path / 'T', SyntheticTransport(frame_response()))
    request_T = treatment._request(engine.get_state(treatment.case), 'author', {'history': []})
    ablation, _ = cell(tmp_path / 'A', method='A')
    request_A = ablation._request(_json(ablation.root / 'progress.json'), 'frame')
    assert request_T['documents']['author-manifest-contract.json'] == request_A['documents']['author-manifest-contract.json']
    # Reviews do not carry redundant author grammar at the tight input ceiling.
    request_review = treatment._request(engine.get_state(treatment.case), 'review', {'history': []})
    assert 'author-manifest-contract.json' not in request_review['documents']


def test_contract_tracks_parser_field_changes(monkeypatch):
    import specorganon.author_contract as contract
    monkeypatch.setattr(contract, 'PUT_OPTIONAL_FIELDS', contract.PUT_OPTIONAL_FIELDS | {'new_field'})
    assert 'new_field' in contract.author_manifest_contract('frame')['put_optional']
