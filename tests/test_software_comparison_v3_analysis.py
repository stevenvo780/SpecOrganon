"""Synthetic analysis controls: unknowns never become passing measurements."""
import pytest
from experiments.software_comparison_v3.analysis import functional_summary, descriptive_differences, AnalysisError
from experiments.software_comparison_v3.reserved import recipes, TASK_FILES


@pytest.mark.parametrize('task', TASK_FILES)
def test_error_only_reply_cannot_be_mistaken_for_valid_contract_conformance(task):
    matrix = recipes(task)
    # A constant invalid_input response passes many rejection probes but no
    # valid request. Its stratified report must expose that distinction.
    rows = [{'id': r['id'], 'status': 'pass' if r['expected'] is None else 'fail'} for r in matrix]
    result = functional_summary(matrix, rows)
    assert result['F_total']['lower'] > .5
    assert result['F_valid_success']['lower'] == result['F_valid_success']['upper'] == 0
    assert result['F_invalid_rejection']['lower'] == 1
    assert result['F_balanced_valid_invalid_secondary'] == {'lower': .5, 'upper': .5}
    assert result['contract_complete'] is False


@pytest.mark.parametrize('task', TASK_FILES)
def test_unevaluated_prerequisite_preserves_unknown_range_and_design_denominator(task):
    matrix = recipes(task)
    result = functional_summary(matrix, [], evaluated=False)
    assert result['F_total']['denominator'] == len(matrix)
    assert result['F_total']['pass'] == result['F_total']['fail'] == 0
    assert result['F_total']['not_evaluated'] == len(matrix)
    assert result['F_total']['lower'] == 0 and result['F_total']['upper'] == 1
    assert result['contract_complete'] is False


def test_partial_or_duplicate_rows_do_not_silently_change_denominators():
    matrix = recipes('fractionmix')
    with pytest.raises(AnalysisError): functional_summary(matrix, [{'id': matrix[0]['id'], 'status': 'pass'}])
    rows = [{'id': r['id'], 'status': 'inconclusive'} for r in matrix]
    with pytest.raises(AnalysisError): functional_summary(matrix, rows + rows[:1])
    with pytest.raises(AnalysisError): functional_summary(matrix, rows, evaluated=False)


def test_paired_unknowns_stay_in_the_full_block_set_instead_of_selecting_complete_pairs():
    report = descriptive_differences([
        ('block-a', {'lower': .8, 'upper': .8}, {'lower': .3, 'upper': .3}),
        ('block-b', {'lower': 0, 'upper': 1}, {'lower': .5, 'upper': .5}),
    ])
    assert report['n_blocks'] == 2
    assert report['mean']['lower'] == pytest.approx(0)
    assert report['mean']['upper'] == pytest.approx(.5)
    assert report['range'] == {'lower': -.5, 'upper': .5}


@pytest.mark.parametrize('bad', [{'lower': True, 'upper': 1}, {'lower': float('nan'), 'upper': 1}, {'lower': .8, 'upper': .2}])
def test_impossible_numeric_intervals_are_rejected(bad):
    with pytest.raises(AnalysisError): descriptive_differences([('x', bad, {'lower': 0, 'upper': 0})])
