"""Original partition findings reproduced mechanically, no native generations."""
import json

from specorganon import engine, neutral_pilot as pilot
from test_neutral_pilot import plan
from test_software_controller_resources import build_fixture, program, stage_tests, Executor


def test_CT01_T_role_consumes_original_checked_measurement_buffers(tmp_path, monkeypatch):
    ctrl = build_fixture(tmp_path)
    ctrl.executor = Executor(tmp_path, stdout=b'original complete measured stdout')
    program(ctrl); stage_tests(ctrl); ctrl.step()
    name = 'read_test' if hasattr(ctrl.executor, 'read_test') else 'verify_test'
    original = getattr(ctrl.executor, name)
    def swap_after_check(*args, **kwargs):
        checked = original(*args, **kwargs)
        receipt = next((ctrl.executor.root / 'test-1').glob('receipt.json'))
        receipt.with_name('stdout.bin').write_bytes(b'unverified replacement stdout')
        return checked
    monkeypatch.setattr(ctrl.executor, name, swap_after_check)
    state = engine.get_state(ctrl.case)
    request = ctrl._request(state, 'review', {'history': []})
    measured = json.loads(request['documents']['measured-test-records.json'])
    assert measured['t1']['streams']['stdout']['text'] == 'original complete measured stdout'
    row = measured['t1']; data = json.loads(request['documents']['state.json'])['items']['t1']['data']
    assert row['receipt_shared_source'] == 'state.json/items/t1/data'
    reconstructed = {**row['receipt'], **{key: data[key] for key in row['receipt_shared_keys']}}
    assert reconstructed == json.loads((ctrl.executor.root / 'test-1/receipt.json').read_text())


def test_TEX01_N_context_explicitly_supersedes_only_legacy_procedure(tmp_path, monkeypatch):
    r = plan(tmp_path); captured = {}
    monkeypatch.setattr(pilot, 'AutonomousNeutralController', lambda *args, **kwargs: captured.update(kwargs))
    for a in pilot.ATTEMPTS:
        if a['method'] != 'N': continue
        pilot.controller(r, a, tmp_path)
        contract = captured['contract']
        original = pilot.bound_source(r, r['tasks'][a['task']]['contract']).decode()
        assert original in contract
        assert 'N procedural override v2' in contract
        assert 'code may precede notes' in contract and 'program and battery may be authored together' in contract
        assert 'functional requirements and required delivery documents remain unchanged' in contract
