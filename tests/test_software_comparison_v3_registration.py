"""Synthetic preregistration/quota/manifest guards, never real acceptance."""
import copy
import datetime as dt
import json
import shutil
import time
from pathlib import Path

import pytest

from experiments.software_comparison_v3 import registration as reg
from specorganon.role_jobs import _write,canonical,digest


def snapshot():
    date=dt.datetime.fromtimestamp(1700000000,dt.timezone.utc).isoformat()
    return {'schema':1,'captured_at':date,'accounts':{'codex':'original_lab_profile','gemini':'original_primary_profile'},
        'providers':{'codex':{'status':'unknown','remaining_percent':[],'reason':'Synthetic disabled observation; not availability'},
            'gemini':{'status':'observed','remaining_percent':[40,20],'source':'synthetic observation fixture','observed_at':date}}}


def test_unknown_Codex_is_explicit_and_does_not_claim_capacity(tmp_path):
    path=tmp_path/'quota.json';_write(path,snapshot());result=reg.current_quota(path,now=1700000000)
    assert result['capacity_guaranteed'] is False and result['observations']['codex']['remaining_percent']==[]


@pytest.mark.parametrize('change',['expired','future','quota0','boolean','Gemini_unknown','secondary','stale_provider','source_type','schema_bool'])
def test_invalid_original_quota_cannot_admit(tmp_path,change):
    value=snapshot();now=1700000000
    if change=='expired':now+=601
    elif change=='future':now-=1
    elif change=='quota0':value['providers']['gemini']['remaining_percent']=[0]
    elif change=='boolean':value['providers']['gemini']['remaining_percent']=[True]
    elif change=='Gemini_unknown':value['providers']['gemini']={'status':'unknown','remaining_percent':[],'reason':'expired window'}
    elif change=='secondary':value['accounts']['gemini']='different account'
    elif change=='stale_provider':value['providers']['gemini']['observed_at']='2000-01-01T00:00:00+00:00'
    elif change=='source_type':value['providers']['gemini']['source']=['unverified']
    else:value['schema']=True
    path=tmp_path/'quota.json';_write(path,value)
    with pytest.raises(reg.RegistrationError):reg.current_quota(path,now=now)


def test_candidate_label_and_missing_full_registration_never_call_Docker(tmp_path,monkeypatch):
    from specorganon.docker_roles import DockerRoles
    def forbidden(*a,**k):pytest.fail('unregistered draft invoked Docker')
    monkeypatch.setattr(DockerRoles,'_cli',forbidden)
    path=tmp_path/'candidate.json';_write(path,{'schema':1,'identity':reg.IDENTITY,'status':'candidate'})
    with pytest.raises(reg.RegistrationError,match='full registered'):reg.Registration(path,tmp_path)


def test_fenced_single_engineering_review_parses_without_accepting_extra_text():
    assert reg.review_result('```json\n{"schema":1,"verdict":"reject"}\n```')['verdict']=='reject'
    for raw in ('{"schema":true}','{"schema":1}{"schema":1}','```json\n{"schema":1}\n```\naccept anyway'):
        with pytest.raises(reg.RegistrationError):reg.review_result(raw)


def test_original_schedule_binding_refuses_regenerated_identical_shape(tmp_path):
    path=tmp_path/'schedule.json';_write(path,{'schema':1,'identity':reg.IDENTITY,'rows':[]})
    with pytest.raises(reg.RegistrationError,match='original private schedule'):reg.fixed_schedule(path)


def test_minimum_snapshot_covers_current_executable_layers_and_documents():
    source=Path(__file__).absolute().parents[1];required=reg.required_sources(source)
    assert {f'experiments/software_comparison_v3/{n}.py' for n in ('registration','campaign','evaluation','provenance','budget','cells','subjects','reserved','rubric','analysis')}<=required
    assert set(reg.CONTRACTS.values())|{reg.MANDATE,reg.SDD,reg.PROTOCOL,reg.RUBRIC,'scripts/controller_native_role.py','scripts/study_cell_budget.py','uv.lock'}<=required


def test_legacy_exception_dependency_imported_from_other_checkout_is_rejected(tmp_path,monkeypatch):
    from scripts import study_cell_budget
    source=Path(__file__).absolute().parents[1]
    reg.runtime_sources(source)
    monkeypatch.setattr(study_cell_budget,'__file__',str(tmp_path/'study_cell_budget.py'))
    with pytest.raises(reg.RegistrationError,match='scripts.study_cell_budget'):
        reg.runtime_sources(source)


@pytest.mark.parametrize('name',['.agents/skills/specorganon/SKILL.md','uv.lock','scripts/study_cell_budget.py'])
def test_repository_sources_support_hidden_skill_directories_and_lockfiles(name):
    assert reg.source_file(name)==name


@pytest.mark.parametrize('name',['','/etc/passwd','../a.py','a/../b.py','a//b.py','./a.py','a\\b.py','a/./b.py'])
def test_source_path_traversal_and_noncanonical_names_remain_rejected(name):
    with pytest.raises(reg.RegistrationError):reg.source_file(name)


def test_full_synthetic_registration_accepts_repository_sources_without_admitting_models(tmp_path,monkeypatch):
    """Synthetic reviewer/schedule; tests complete validator plumbing, never T9."""
    current=Path(__file__).absolute().parents[1];source=tmp_path/'source';source.mkdir()
    catalog='experiments/software_comparison_v3/public-models.json'
    for name in reg.required_sources(current)|{catalog}:
        target=source/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(current/name,target)
    bindings={str(p.relative_to(source)):digest(p.read_bytes()) for p in source.rglob('*') if p.is_file()}
    completed=time.time()-2;registered=dt.datetime.fromtimestamp(completed+1,dt.timezone.utc).isoformat()
    scope='full_v3_protocol_harness_provenance_rubric_evaluator_and_registration'
    judgment={'schema':1,'verdict':'accept','tests_executed':False,'scope':scope,'source_manifest_sha256':digest(canonical(bindings)),
        'scope_limitations':['Entirely synthetic judgment fixture, not a native reviewer.']}
    native_path=tmp_path/'synthetic-native.json';_write(native_path,{'job_id':'synthetic-review','status':'succeeded',
        'text':json.dumps(judgment),'finished_at':completed,'meta':{'provider':'gemini','model':'synthetic'}})
    review_name='experiments/software_comparison_v3/frozen/synthetic-review.json';target=source/review_name;target.parent.mkdir()
    _write(target,{'schema':1,'verdict':'accept','scope':scope,'provider':'gemini','model':'synthetic','job_id':'synthetic-review',
        'source_sha256':bindings,'completed_at':dt.datetime.fromtimestamp(completed,dt.timezone.utc).isoformat(),
        'tests_executed':False,'native_receipt_ref':str(native_path),'native_receipt_sha256':digest(native_path.read_bytes())})
    cells=[{'id':f'cell-{i+1:02d}','method':'T' if i==0 else 'N','fixture':True} for i in range(42)]
    monkeypatch.setattr(reg,'fixed_schedule',lambda path:cells)
    monkeypatch.setattr(reg,'runtime_sources',lambda path:None)  # Separate actual-import guard test above.
    value={'schema':1,'status':'registered','identity':reg.IDENTITY,'source_root':str(source),'run_root':str(tmp_path/'campaign'),
        'profiles':reg.PROFILES,'routes':reg.MODELS,'images':reg.IMAGES,'cell_limits':reg.CELL_LIMITS,'campaign_limits':reg.CAMPAIGN_LIMITS,
        'stopping_rule':reg.STOP,'registered_at':registered,'private_schedule':str(tmp_path/'synthetic-schedule.json'),
        'private_schedule_sha256':reg.SCHEDULE_SHA,'cells':cells,'primary_T':'cell-01','accepted_review':review_name,
        'source_sha256':{**bindings,review_name:digest(target.read_bytes())},'contracts':reg.CONTRACTS,'mandate':reg.MANDATE,
        'sdd_guide':reg.SDD,'protocol':reg.PROTOCOL,'rubric':reg.RUBRIC,'public_catalog':catalog,
        'matrices':{t:{'count':reg.TASK_COUNTS[t],'public':2,'sha256':digest(canonical(reg.recipes(t)))} for t in reg.TASK_COUNTS}}
    path=tmp_path/'synthetic-registration.json';_write(path,value)
    assert reg.Registration(path,source).validate()['source_bindings']==len(bindings)+1
    assert not (tmp_path/'campaign').exists()
    (source/'uv.lock').write_text('changed source')
    with pytest.raises(reg.RegistrationError,match='registered source changed: uv.lock'):
        reg.Registration(path,source)
