"""Synthetic preregistration/quota/manifest guards, never real acceptance."""
import copy
import datetime as dt
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
