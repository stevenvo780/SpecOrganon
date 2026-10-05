"""Synthetic strict audit-format controls, no actual audited delivery."""
import copy
import pytest
from experiments.software_comparison_v3.rubric import rubric, validate_response, summarize_assertions, RubricError

BINDING = {'contract_sha256': 'a' * 64, 'delivery_sha256': 'b' * 64, 'history_sha256': 'c' * 64}


def fixture(method):
    r = rubric(method)
    return {'schema': 1, 'binding': copy.deepcopy(BINDING), 'tests_executed': False,
            'reason': 'Synthetic format assertion, no native audit or delivery',
            **{group: {key: {'status': 'pass', 'reason': 'Synthetic evidence shape', 'evidence': ['fixture:synthetic']}
                       for key in r[group]} for group in ('D', 'G', 'H')}}


@pytest.mark.parametrize('method,points', [('N', 0), ('S', 5), ('T', 9), ('A', 9)])
def test_method_specific_checklists_do_not_penalize_free_work_for_missing_nine_phases(method, points):
    r = rubric(method)
    assert len(r['D']) == 8 and len(r['G']) == 6 and len(r['H']) == points
    parsed = validate_response(fixture(method), method, BINDING)
    summary = summarize_assertions(parsed, method, BINDING)
    assert summary['H_applicable'] == (method != 'N')
    assert 'full_package' not in summary


@pytest.mark.parametrize('change', ['binding', 'IDs', 'reason', 'no-evidence', 'invented-execution', 'bool-schema', 'extra'])
def test_structural_or_snapshot_mismatches_cannot_be_turned_into_success(change):
    value = fixture('T')
    if change == 'binding': value['binding']['delivery_sha256'] = 'd' * 64
    elif change == 'IDs': value['H'].pop('h9')
    elif change == 'reason': value['D']['d1']['reason'] = ''
    elif change == 'no-evidence': value['G']['g4']['evidence'] = []
    elif change == 'invented-execution': value['tests_executed'] = True
    elif change == 'bool-schema': value['schema'] = True
    else: value['score'] = 100
    with pytest.raises(RubricError): validate_response(value, 'T', BINDING)


def test_inconclusive_stays_a_range_and_zero_denominator_is_not_a_fake_perfect_score():
    value = fixture('N')
    value['G']['g4'] = {'status': 'inconclusive', 'reason': 'Synthetic receipt availability unknown', 'evidence': []}
    value['D']['d8'] = {'status': 'fail', 'reason': 'Synthetic missing content', 'evidence': []}
    summary = summarize_assertions(value, 'N', BINDING)
    assert summary['G']['lower'] == 5 and summary['G']['upper'] == 6
    assert summary['D']['lower'] == summary['D']['upper'] == 7
    assert summary['H']['denominator'] == 0 and summary['H']['lower'] == summary['H']['upper'] == 0
