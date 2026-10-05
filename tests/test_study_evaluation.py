"""Synthetic scoring/closure controls; zero study solutions or native calls."""
import copy
from pathlib import Path
import pytest

from experiments.software_comparison_v1.reserved.campaign_evaluation import (
    functional_delivery,generation_closed,counts,corroborate_documentation,public_examples)
from experiments.software_comparison_v1.reserved.docker_evaluator import EvaluationError
from specorganon.role_jobs import canonical,digest,_json
from scripts.study_assessment import rubric_ids,observe


CASES=_json(Path(__file__).parents[1]/'experiments/software_comparison_v1/reserved/suite-draft.json')['cases']


def packet(task,files):
    return {'schema':1,'opaque_id':'delivery-synthetic','task':task,'files':files,
            'files_sha256':digest(canonical(files))}


def test_no_reserved_feedback_until_all_fixed_generation_closed_or_native_stop():
    cells=[{'id':'a'},{'id':'b'}]
    for p in [{'cells':{},'next_index':0,'paused':None},
              {'cells':{'a':{'status':'running'}},'next_index':0,'paused':{'actual_native_failure':True}}]:
        with pytest.raises(EvaluationError):generation_closed(p,cells)
    generation_closed({'cells':{'a':{'status':'failed'},'b':{'status':'complete'}},'next_index':2,'paused':None},cells)
    generation_closed({'cells':{'a':{'status':'infra_inconclusive'}},'next_index':0,
                       'paused':{'actual_native_failure':True}},cells)


@pytest.mark.parametrize('task,n',[('routeplan',61),('treemap',52)])
def test_missing_model_program_is_zero_but_infrastructure_absence_is_unknown(tmp_path,task,n):
    p=packet(task,{})
    def forbidden(*args):raise AssertionError('absence must not launch substitute programme')
    result=functional_delivery(p,tmp_path/'generation-failure','sha256:'+'a'*64,CASES,runner_factory=forbidden)
    assert result['reserved']['summary']['fail']==n and not result['behavior_satisfied']
    infra=functional_delivery(p,tmp_path/'infra','sha256:'+'a'*64,CASES,runner_factory=forbidden,absence_status='inconclusive')
    assert infra['reserved']['summary']['inconclusive']==n
    assert infra['reserved']['summary']['descriptive_bounds']==[0,1]


def test_uncertain_execution_retained_without_new_subject_on_resume(tmp_path):
    calls=[]
    class SyntheticRunner:
        def __init__(self,*args):pass
        def run(self,id,case,files):
            calls.append(id)
            if id=='self':raise EvaluationError('synthetic uncertain owned handle')
            return {'verdict':{'status':'pass','reason':'synthetic fixture only'}}
    p=packet('routeplan',{'routeplan.py':'# synthetic non-solution fixture'})
    first=functional_delivery(p,tmp_path,'sha256:'+'a'*64,CASES,runner_factory=SyntheticRunner)
    assert len(calls)==63 and first['reserved']['summary']['inconclusive']==1
    second=functional_delivery(p,tmp_path,'sha256:'+'a'*64,CASES,runner_factory=SyntheticRunner)
    assert second==first and len(calls)==63


def test_public_examples_are_fixed_contractual_recipes_not_readme_shell():
    route=public_examples('routeplan');tree=public_examples('treemap')
    assert route[0]['expected']['path']==['A','B','D']
    assert [c['expected']['total_bytes'] for c in tree]==[5,2]
    assert all('/fixture/root' in c['argv'] for c in tree)


def test_documentation_requires_independent_judgment_and_executed_example():
    rows={k:[{'id':id,'verdict':'satisfied','locator':'README.md:3','reason':'synthetic judgment'} for id in ids]
          for k,ids in rubric_ids('N').items()}
    observation=observe({'tests_executed':False,'assessment':rows},'N');original=copy.deepcopy(observation)
    result=corroborate_documentation(observation,[{'verdict':{'status':'fail','reason':'synthetic defect'}},
        {'verdict':{'status':'inconclusive','reason':'synthetic infrastructure'}}])
    assert observation==original
    points={p['id']:p for p in result['dimensions']['documentation']['points']}
    assert points['D3']['verdict']=='unsatisfied' and points['D4']['verdict']=='inconclusive'
    assert result['dimensions']['documentation']['satisfied']==8
    assert result['dimensions']['adherence']['status']=='not_applicable'
