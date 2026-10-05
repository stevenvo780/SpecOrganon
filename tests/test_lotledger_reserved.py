"""Evaluator controls, not generated LotLedger deliveries or nine-phase cases."""
import copy
import json

import pytest

from experiments.lotledger_delivery_v1.reserved import GROUPS, judge, recipes


def execution(stdout=b'', stderr=b'', exit_code=0, **extra):
    return {'stdout': stdout, 'stderr': stderr, 'exit_code': exit_code,
            'timed_out': False, 'truncated_streams': False, **extra}


def ideal(recipe):
    if recipe['expected'] is None:
        return execution(stderr=b'{"error":"invalid_input"}\n', exit_code=2)
    return execution(json.dumps(recipe['expected'], ensure_ascii=False).encode() + b'\n')


@pytest.mark.parametrize('recipe', recipes(), ids=lambda r: r['id'])
def test_declared_oracle_and_opposite_result(recipe):
    # Each declared expected result passes framing; each opposite outcome fails.
    # This checks the judge, not correctness of the 63 domain oracles.
    good = ideal(recipe)
    assert judge(recipe, good)['status'] == 'pass'
    bad = execution(b'{}\n') if recipe['expected'] is None else execution(
        stderr=b'{"error":"invalid_input"}\n', exit_code=2)
    assert judge(recipe, bad)['status'] == 'fail'


@pytest.mark.parametrize('raw', [
    b'{"unique_events":false,"duplicate_events":0,"stocks":[]}\n',
    b'{"unique_events":0.0,"duplicate_events":0,"stocks":[]}\n',
    b'{"unique_events":0,"unique_events":0,"duplicate_events":0,"stocks":[]}\n',
    b'{"unique_events":0,"duplicate_events":0,"stocks":[],"extra":0}\n',
    b'{"unique_events":0,"duplicate_events":0,"stocks":[]}\n\n',
    b' {"unique_events":0,"duplicate_events":0,"stocks":[]}\n',
    b'{"unique_events":0,"duplicate_events":0,"stocks":[]} \n',
    b'{"unique_events":0,"duplicate_events":0,"stocks":[]}',
    b'{"unique_events":NaN,"duplicate_events":0,"stocks":[]}\n',
    b'{"unique_events":0,"duplicate_events":0,"stocks":[]}\n{}\n',
    b'\xef\xbb\xbf{"unique_events":0,"duplicate_events":0,"stocks":[]}\n',
    b'\xff\n',
])
def test_output_can_never_hide_types_duplicate_keys_or_framing(raw):
    assert judge(recipes()[0], execution(raw))['status'] == 'fail'


def test_pretty_json_and_arbitrary_key_order_are_permitted_inside_object():
    r = recipes()[1]
    value = dict(reversed(list(r['expected'].items())))
    raw = json.dumps(value, indent=2).encode() + b'\n'
    assert judge(r, execution(raw))['status'] == 'pass'


@pytest.mark.parametrize('change', [
    {'timed_out': True}, {'truncated_streams': True}, {'exit_code': 2},
    {'stderr': b'noise'},
])
def test_even_correct_value_does_not_override_runtime_or_stream_failure(change):
    good = ideal(recipes()[0]); good.update(change)
    assert judge(recipes()[0], good)['status'] == 'fail'


def test_infrastructure_uncertainty_is_not_imputed_pass_or_contract_error():
    good = ideal(recipes()[0]); good['infrastructure_error'] = 'handle uncertain'
    assert judge(recipes()[0], good)['status'] == 'inconclusive'


def test_wrong_stock_order_duplicates_and_quantity_types_are_rejected():
    r = recipes()[1]
    mutations = []
    wrong = copy.deepcopy(r['expected']); wrong['stocks'].reverse(); mutations.append(wrong)
    wrong = copy.deepcopy(r['expected']); wrong['stocks'].append(wrong['stocks'][0]); mutations.append(wrong)
    wrong = copy.deepcopy(r['expected']); wrong['stocks'][0]['quantity'] = 2.0; mutations.append(wrong)
    wrong = copy.deepcopy(r['expected']); wrong['stocks'][0]['quantity'] = True; mutations.append(wrong)
    for wrong in mutations:
        assert judge(r, execution(json.dumps(wrong).encode() + b'\n'))['status'] == 'fail'


def test_matrix_allocation_boundaries_and_named_metamorphic_relations():
    matrix = recipes(); indexed = {r['id']: r for r in matrix}
    assert len(indexed) == 63
    assert sum(r['public'] for r in matrix) == 2
    assert [sum(r['group'] == g for r in matrix) for g in GROUPS] == [11, 10, 10, 12, 10, 10]
    for n in (65536, 65537):
        assert len(bytes.fromhex(indexed['boundaries-bytes-' + str(n)]['stdin_hex'])) == n
    for n in (1000, 1001):
        raw = bytes.fromhex(indexed['boundaries-events-' + str(n)]['stdin_hex'])
        assert raw.count(b'\n') == n and len(raw) <= 65536
    base = indexed['boundaries-metamorphic-base']['expected']
    dupe = indexed['boundaries-metamorphic-duplicates']['expected']
    renamed = indexed['boundaries-metamorphic-bijection']['expected']
    assert base['stocks'] == dupe['stocks'] and base['unique_events'] == dupe['unique_events']
    assert dupe['duplicate_events'] == 2
    assert sorted(x['quantity'] for x in base['stocks']) == sorted(x['quantity'] for x in renamed['stocks'])
    assert indexed['identity-consume-after-depletion']['expected']['stocks'] == []
    assert indexed['identity-move-after-depletion']['expected']['stocks'] == [{'lot':'L','site':'B','quantity':1}]
