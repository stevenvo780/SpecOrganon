"""Synthetic global gate/opaque export/once-only controls; no real T9 assertion."""
from contextlib import nullcontext
from types import SimpleNamespace
import copy
import pytest

from experiments.software_comparison_v3.evaluation import Evaluation,EvaluationError,score_points
from specorganon.role_jobs import _write,_json,canonical,digest


def coordinator(root,status='released_once'):
    cells=[{'id':f'fixture-{i:02d}','opaque_id':f'opaque-{i:02d}','task':'fractionmix'} for i in range(42)]
    files={'fractionmix.py':'# synthetic absent functional implementation fixture\n'}
    seals={r['id']:{'terminal':{'delivery_sha256':digest(canonical(files))}} for r in cells}
    budget=root/'budget';budget.mkdir(parents=True)
    _write(budget/'progress.json',{'cells':seals})
    for r in cells:
        folder=root/'exports'/r['opaque_id'];folder.mkdir(parents=True)
        _write(folder/'delivery.json',{'schema':1,'opaque_id':r['opaque_id'],'task':'fractionmix','files':files,'delivery_sha256':digest(canonical(files))})
    gate={'status':status,'reserved_evaluation_allowed':status=='released_once','scope':'synthetic callback only; no actual milestone proof'}
    c=SimpleNamespace(root=root,value={'cells':cells,'images':{'test':'synthetic-image'}},
        journal=SimpleNamespace(root=budget,evaluation_gate=lambda callback:gate),
        registration=SimpleNamespace(sha='a'*64,validate=lambda:None),verify_milestone=lambda *a:None,lock=nullcontext)
    return c,Evaluation(c)


@pytest.mark.parametrize('status',['prerequisite_inconclusive','not_evaluated_by_prerequisite'])
def test_reserved_global_hold_invokes_no_subject_and_keeps_evaluation_uncreated(tmp_path,monkeypatch,status):
    from experiments.software_comparison_v3 import evaluation
    c,e=coordinator(tmp_path,status)
    monkeypatch.setattr(evaluation,'Subjects',lambda *a:pytest.fail('held gate invoked subject'))
    with pytest.raises(EvaluationError,match='prerequisite'):e.step()
    assert not e.root.exists()


def test_export_never_contains_method_model_or_history_and_mutation_rejected(tmp_path):
    c,e=coordinator(tmp_path);manifest,payloads=e.exports()
    assert len(payloads)==42 and all(set(p)=={'schema','opaque_id','task','files','delivery_sha256'} for p in payloads.values())
    path=c.root/'exports/opaque-00/delivery.json';v=_json(path);v['method']='T';_write(path,v)
    with pytest.raises(EvaluationError,match='opaque export'):e.exports()


def test_released_population_is_immutable_and_closed_row_not_executed_twice(tmp_path,monkeypatch):
    from experiments.software_comparison_v3 import evaluation
    c,e=coordinator(tmp_path);calls=[]
    class SyntheticSubject:
        def __init__(self,root,image,task):assert 'opaque-' in str(root)
        def run(self,identity,recipe,files):
            calls.append(identity);return {'id':identity,'public':recipe['public'],'status':'fail','scope':'synthetic result only'}
    monkeypatch.setattr(evaluation,'Subjects',SyntheticSubject)
    first=e.step();second=e.step();assert first['recipe_id']!=second['recipe_id'] and len(calls)==2
    path=c.root/'exports/opaque-00/delivery.json';v=_json(path);v['files']['fractionmix.py']='changed'
    _write(path,v)
    with pytest.raises(EvaluationError):e.step()
    assert len(calls)==2


def test_uncertain_subject_keeps_same_identity_ungraded_for_read_recovery(tmp_path,monkeypatch):
    from experiments.software_comparison_v3 import evaluation
    from specorganon.role_jobs import UncertainJob
    c,e=coordinator(tmp_path);calls=[]
    class UncertainSubject:
        def __init__(self,*a):pass
        def run(self,identity,*a):calls.append(identity);raise UncertainJob('synthetic same owned handle not terminal')
    monkeypatch.setattr(evaluation,'Subjects',UncertainSubject)
    for _ in range(2):
        with pytest.raises(UncertainJob):e.step()
    assert calls[0]==calls[1] and _json(e.root/'progress.json')['cells']['opaque-00']['rows']=={}


def test_prerequisite_unknown_cannot_seal_final_report(tmp_path):
    c,e=coordinator(tmp_path,'prerequisite_inconclusive')
    with pytest.raises(EvaluationError,match='pending report'):e.report()
    assert not (c.root/'report.json').exists()


def test_unknown_rubric_points_keep_interval_and_N_has_no_H_penalty():
    result=score_points({'one':{'status':'pass'},'two':{'status':'fail'},'three':{'status':'inconclusive'}})
    assert result['lower']==pytest.approx(1/3) and result['upper']==pytest.approx(2/3)
    assert score_points({})=={'applicable':False,'pass':0,'fail':0,'inconclusive':0,'denominator':0,'lower':None,'upper':None}


def test_paired_strata_keep_every_unknown_block_and_reject_dropped_or_duplicate_cells():
    from experiments.software_comparison_v3.evaluation import comparison_groups
    rows=[]
    for block in range(4):
        for method in ('N','S','T','A') if block%2==0 else ('N','S','T'):
            interval={'lower':0,'upper':1} if block==3 else {'lower':1,'upper':1}
            rows.append({'block_id':f'b{block}','method':method,'functional':{'F_total':interval},
                'qualitative':{'scores':{k:interval for k in ('D','G','H')}}})
    result=comparison_groups(rows,nst_blocks=4,a_blocks=2)
    assert result['F_T-N']['n_blocks']==4 and result['F_T-A']['n_blocks']==2
    assert result['F_T-N']['mean']=={'lower':-.25,'upper':.25}
    assert 'H_T-N' not in result
    with pytest.raises(EvaluationError,match='all fixed paired blocks'):
        comparison_groups([r for r in rows if r['block_id']!='b3'],nst_blocks=4,a_blocks=2)
    with pytest.raises(EvaluationError,match='distinct methods'):
        comparison_groups(rows+[copy.deepcopy(rows[0])],nst_blocks=4,a_blocks=2)
