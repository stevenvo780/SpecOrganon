"""Synthetic rubric contracts, not native judgments or study scores."""
import copy
import pytest
from scripts.study_assessment import AssessmentError,rubric_ids,validate,summarize,observe


def fixture(method):
    return {dimension:[{'id':id,'verdict':'inconclusive','locator':'absent:synthetic-fixture',
                       'reason':'Synthetic rubric schema control only'} for id in ids]
            for dimension,ids in rubric_ids(method).items()}


@pytest.mark.parametrize('method',['N','S','T','A'])
def test_point_denominators_and_missing_evidence_do_not_become_method_success(method):
    value=fixture(method); summary=summarize(value,method)
    assert summary['combined_score'] is None and summary['functional_score'] is None
    assert summary['dimensions']['documentation']['denominator']==10
    assert summary['dimensions']['common']['denominator']==6
    assert summary['dimensions']['adherence']['denominator']=={'N':0,'S':8,'T':9,'A':9}[method]
    assert all(row['satisfied']==0 for row in summary['dimensions'].values())
    if method=='N': assert summary['dimensions']['adherence']['status']=='not_applicable'


@pytest.mark.parametrize('mutation',['duplicate','missing','boolean','absent-pass','no-locator','extra'])
def test_unusable_rubric_output_is_inconclusive_without_regeneration(mutation):
    value=fixture('T')
    if mutation=='duplicate': value['documentation'][1]['id']='D1'
    elif mutation=='missing': value['common'].pop()
    elif mutation=='boolean': value['documentation'][0]['verdict']=True
    elif mutation=='absent-pass':value['documentation'][0]['verdict']='satisfied'
    elif mutation=='no-locator': value['documentation'][0]['locator']=''
    else:value['adherence'][0]['unrequested']='field'
    with pytest.raises(AssessmentError):validate(value,'T')
    result=observe({'tests_executed':False,'assessment':value},'T')
    assert result['status']=='inconclusive' and result['combined_score'] is None


def test_text_reviewer_execution_claim_or_missing_assessment_is_not_imputed():
    assert observe({'tests_executed':True,'assessment':fixture('N')},'N')['status']=='inconclusive'
    assert observe({'tests_executed':False},'N')['status']=='inconclusive'
