"""Diagnostic custody/control fixtures; no external provider calls."""
import json
from pathlib import Path

import pytest

from scripts import probe_native_response_schema as probe
from specorganon.role_jobs import canonical,digest


def fixture_plan(tmp_path):
    source=tmp_path/'source';source.mkdir();(source/'bound.py').write_text('original fixture')
    cases=[{'id':name,'role':role,'request':{}} for name,role in [
        ('review-missing-receipt','review'),('approval-outside-mandate','review'),('author-items','author')]]
    p={'classification':'prospective provider syntax diagnostics only','fixture_mode':True,
       'automatic_replacement':False,'max_calls':3,'source_root':str(source),
       'source_sha256':{'bound.py':digest((source/'bound.py').read_bytes())},
       'run_root':str(tmp_path/'runtime'),'native_image':'fixture','test_image':'fixture',
       'public_catalog':'fixture','model':'fixture','original_profile':'fixture',
       'executable':'fixture','seccomp':'fixture','cases':cases}
    raw=canonical(p);path=tmp_path/'registration.json';path.write_bytes(raw)
    return path,digest(raw),p


def test_registration_is_parsed_from_the_single_hashed_read(tmp_path,monkeypatch):
    path,sha,p=fixture_plan(tmp_path);original=probe._read;reads=[]
    def observed(file,*args):
        if file==path:reads.append(file)
        return original(file,*args)
    monkeypatch.setattr(probe,'_read',observed)
    assert probe.load_plan(path,sha)==p and len(reads)==1


def test_source_mutation_closes_remaining_identities_without_native_dispatch(tmp_path,monkeypatch):
    path,sha,p=fixture_plan(tmp_path);calls=[]
    class Synthetic:
        def __init__(self,*args,**kwargs):pass
        def call(self,job,role,request):
            calls.append(job);(Path(p['source_root'])/'bound.py').write_text('changed fixture')
            return {'fixture':True}
    monkeypatch.setattr(probe,'DockerRoles',Synthetic)
    report=probe.run(path,sha)
    assert calls==['review-missing-receipt']
    assert report['closed_cases']==3 and report['dispatch_attempts']==1
    assert report['source_verification_passed'] is False and report['valid_bridge_contracts']==0
    assert [row['status'] for row in report['rows']]==['bridge_contract_valid','not_executed_inconclusive','not_executed_inconclusive']
    assert all((Path(p['run_root'])/(case['id']+'-outcome.json')).exists() for case in p['cases'])


def test_preparation_failure_is_terminal_without_retry_or_missing_rows(tmp_path,monkeypatch):
    path,sha,p=fixture_plan(tmp_path)
    def fail(*args,**kwargs):raise ValueError('synthetic preparation failure')
    monkeypatch.setattr(probe,'DockerRoles',fail)
    report=probe.run(path,sha)
    assert report['closed_cases']==3 and report['dispatch_attempts']==0
    assert report['valid_bridge_contracts']==0 and report['goal_achieved'] is False
    assert all(row['status']=='not_executed_inconclusive' for row in report['rows'])
    with pytest.raises(ValueError,match='already exists'):probe.run(path,sha)


def test_each_original_failed_dispatch_is_counted_once_with_no_replacement(tmp_path,monkeypatch):
    path,sha,p=fixture_plan(tmp_path);calls=[]
    class Synthetic:
        def __init__(self,*args,**kwargs):pass
        def call(self,job,role,request):calls.append(job);raise ValueError('synthetic role failure')
    monkeypatch.setattr(probe,'DockerRoles',Synthetic)
    report=probe.run(path,sha)
    assert calls==[case['id'] for case in p['cases']]
    assert report['closed_cases']==3 and report['dispatch_attempts']==3
    assert report['source_verification_passed'] is True and report['valid_bridge_contracts']==0
    assert all(row['status']=='failed_or_inconclusive' for row in report['rows'])


def test_final_hash_failure_keeps_raw_rows_but_cannot_promote_success(tmp_path,monkeypatch):
    path,sha,p=fixture_plan(tmp_path);calls=[]
    class Synthetic:
        def __init__(self,*args,**kwargs):pass
        def call(self,job,role,request):
            calls.append(job)
            if len(calls)==3:(Path(p['source_root'])/'bound.py').write_text('changed at final fixture')
            return {'fixture':True}
    monkeypatch.setattr(probe,'DockerRoles',Synthetic)
    report=probe.run(path,sha)
    assert report['raw_valid_bridge_contracts']==3 and report['valid_bridge_contracts']==0
    assert report['source_verification_passed'] is False and report['closed_cases']==3
    assert (Path(p['run_root'])/'report.json').exists() and len(calls)==3
