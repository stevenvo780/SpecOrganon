"""Synthetic accounting controls; no native delivery or method acceptance."""
import copy
import json

import pytest

from specorganon import engine
from specorganon.role_jobs import _json, canonical
from specorganon.software_controller import Controller, ControllerError
from specorganon.workflow import KIND_TO_PHASE
from test_software_controller import SyntheticTransport, controller, frame_response


def independent_cost(value):
    inner = json.dumps(value, sort_keys=True, ensure_ascii=False,
                       separators=(',', ':'), allow_nan=False)
    return len(json.dumps(inner, sort_keys=True, ensure_ascii=False,
                          separators=(',', ':'), allow_nan=False).encode('utf-8'))


def test_role_sees_exact_stored_costs_with_metadata_unicode_and_escaping(tmp_path):
    packet = frame_response()
    packet['manifest']['steps'][0]['text'] += ' Unicode á 漢字; quote " and slash \\.'
    ctrl = controller(tmp_path, SyntheticTransport(packet))
    ctrl.step()
    state = engine.get_state(ctrl.case)
    before = (ctrl.case / 'organon.json').read_bytes()
    request = ctrl._request(state, 'review', {'history': []})
    costs = json.loads(request['documents']['resource-accounting.json'])
    for phase, row in costs['phases'].items():
        items = {k: v for k, v in state['items'].items() if KIND_TO_PHASE[v['kind']] == phase}
        assert row == [len(items), independent_cost(items)]
    assert costs['phase_columns'] == ['current_item_count', 'current_encoded_bytes']
    assert costs['phases']['frame'][1] > independent_cost(packet)
    assert costs['phases']['critique'] == [0, 4]
    assert costs['delivery'] == {'current_encoded_bytes': 4, 'limit_encoded_bytes': 20000}
    assert costs['phase_limit'] == {'items': 6, 'encoded_bytes': 6000}
    assert 'not future-response admission' in costs['scope']
    assert 'not just the returned manifest' in request['role_instructions']
    assert json.loads(request['documents']['state.json']) == state
    assert (ctrl.case / 'organon.json').read_bytes() == before


def test_raw_response_below_limit_still_rejects_oversized_stored_map_atomically(tmp_path):
    packet = frame_response()
    # Select a response just below the authored-wire cap. Engine fields, not
    # an invented oracle or altered limit, make its stored phase exceed 6000.
    packet['manifest']['steps'][0]['text'] = 'Substantive synthetic accounting control. '
    while independent_cost(packet) < 5900:
        packet['manifest']['steps'][0]['text'] += 'x'
    assert independent_cost(packet) <= 6000
    ctrl = controller(tmp_path, SyntheticTransport(packet))
    before = (ctrl.case / 'organon.json').read_bytes()
    with pytest.raises(ControllerError, match='phase item resource admission exceeded: frame'):
        ctrl.step()
    assert (ctrl.case / 'organon.json').read_bytes() == before
    assert ctrl._files() == {} and len(ctrl.transport.calls) == 1
    assert _json(ctrl.root / 'progress.json')['pending']['status'] == 'closed'
    assert _json(ctrl.root / 'controller.json')['max_phase_encoded_bytes'] == 6000


def test_accounting_changes_with_full_flags_and_delivery_without_mutating_snapshot(tmp_path):
    ctrl = controller(tmp_path, SyntheticTransport(frame_response()))
    ctrl.step()
    state = engine.get_state(ctrl.case)
    before = copy.deepcopy(state)
    base = ctrl._resource_accounting(state, {})
    altered = copy.deepcopy(state)
    altered['items']['p1']['issues'] = ['Synthetic changed validation flag ' * 10]
    files = {'sample.py': 'print("á\\n")\n'}
    changed = ctrl._resource_accounting(altered, files)
    assert changed['phases']['frame'][1] > base['phases']['frame'][1]
    assert changed['delivery']['current_encoded_bytes'] == independent_cost(files)
    assert state == before


def test_new_policy_binds_its_guidance_source_and_preserves_limits(tmp_path):
    from pathlib import Path
    from specorganon import software_controller
    from specorganon.role_jobs import digest
    ctrl = controller(tmp_path, SyntheticTransport(frame_response()))
    policy = _json(ctrl.root / 'controller.json')
    assert policy['schema'] == 9 and policy['resource_hint_schema'] == 1
    assert policy['resource_guidance_source_sha256'] == digest(Path(software_controller.__file__).read_bytes())
    assert policy['max_role_calls'] == 40 and policy['max_phase_items'] == 6
    assert policy['max_phase_encoded_bytes'] == 6000 and policy['max_files_encoded_bytes'] == 20000
    policy['resource_guidance_source_sha256'] = '0' * 64
    from specorganon.role_jobs import _write
    _write(ctrl.root / 'controller.json', policy)
    before = (ctrl.case / 'organon.json').read_bytes()
    with pytest.raises(ControllerError, match='versioned run'):
        Controller(ctrl.case, ctrl.root, ctrl.transport, contract=ctrl.contract,
                   mandate=ctrl.mandate, fixture_mode=True)
    assert (ctrl.case / 'organon.json').read_bytes() == before
