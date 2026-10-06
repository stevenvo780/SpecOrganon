"""Supplemental observer tests use synthetic deliveries and stub Docker executions."""
import hashlib
import json
import sys
from pathlib import Path

import pytest

BASE=Path(__file__).resolve().parents[2];sys.path.insert(0,str(BASE))
import schedule
import clean_runtime


def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data))


def sha(data): return hashlib.sha256(data).hexdigest()


def fixture(base):
    rows=schedule.make_schedule(17863)
    (base/'evaluator.py').write_bytes(b'frozen evaluator fixture')
    (base/'delivery_entry.py').write_bytes(b'entry fixture')
    save(base/'frozen/manifest.json',{'schedule':rows,'files':{},'images':{'control':'control-id'}})
    save(base/'runs/complete.json',{'runs':18,'stages':36})
    save(base/'development/delivery-build.json',{'exit_code':0,'image_id':'delivery-id','base_image_id':'control-id',
         'entry_sha256':sha(b'entry fixture'),'evaluator_sha256':sha(b'frozen evaluator fixture')})
    save(base/'planning/clean-runtime-addendum.json',{'primary_protocol_changed':False,
         'coverage':{'runs':18,'stages_per_run':[1,2],'expected_observations':36,'arms':['N','S','T'],'selective_winner_only_check':False},
         'runtime':{'image_id':'delivery-id','base_image_id':'control-id','entry_sha256':sha(b'entry fixture'),
                    'evaluator_sha256':sha(b'frozen evaluator fixture'),'flags':['-E','-s','-S','-B'],
                    'candidate_uid':1000,'network':'none','auth_volume':False,'read_only_candidate':True}})
    for row in rows:
        for stage in (1,2):
            root=base/'runs'/row['id']/f'stage{stage}'
            candidate=root/'artifact/solution/backup.py';candidate.parent.mkdir(parents=True)
            candidate.write_bytes(b'candidate fixture')
            save(root/'artifact.receipt.json',{'files':{'solution/backup.py':sha(b'candidate fixture')}})
            save(root/'complete.json',{})
            save(root/'evaluation.receipt.json',{'exit_code':0,'timed_out':False})
    return rows


def grade(number):
    names=clean_runtime.expected_names(number)
    return {'isolation':{'candidate_uid':1000,'development_only':False},'score':1.0,
            'checks_total':len(names),'checks_passed':len(names),'critical_failures':[],
            'inconclusive':False,'details':[{'name':name,'passed':True} for name in names],
            'output_streams':[]}


def observer(counter,infra=False):
    def fake(candidate,row,number,image,directory):
        counter.append((row['id'],number))
        data=grade(number);directory.mkdir(parents=True,exist_ok=True)
        (directory/'evaluation.jsonl').write_text(json.dumps(data))
        (directory/'evaluation.stderr').write_bytes(b'')
        receipt={'argv':clean_runtime.argv(candidate,row,number,image),'exit_code':125 if infra else 0,
                 'timed_out':False,'duration_seconds':1,
                 'stdout_sha256':sha((directory/'evaluation.jsonl').read_bytes()),'stderr_sha256':sha(b'')}
        save(directory/'receipt.json',receipt)
        return receipt
    return fake


def test_incomplete_guard_precedes_inspection_and_output_creation(tmp_path,monkeypatch):
    monkeypatch.setattr(clean_runtime,'observe',lambda *args:pytest.fail('No premature inspection'))
    with pytest.raises(RuntimeError,match='incomplete'):
        clean_runtime.run(tmp_path,tmp_path/'output')
    assert not (tmp_path/'output').exists()


def test_full_balanced_coverage_and_cached_receipts(tmp_path,monkeypatch):
    fixture(tmp_path);calls=[]
    monkeypatch.setattr(clean_runtime,'check_image',lambda value:value)
    monkeypatch.setattr(clean_runtime,'observe',observer(calls))
    result=clean_runtime.run(tmp_path,tmp_path/'output')
    assert len(calls)==36 and result['counts']=={'evaluated':36}
    for arm in 'NST':
        for number in ('1','2'):
            assert result['groups'][arm][number]['expected']==6
            assert result['groups'][arm][number]['observed']==6
    clean_runtime.run(tmp_path,tmp_path/'output');assert len(calls)==36


def test_changed_source_is_unknown_and_never_executed(tmp_path,monkeypatch):
    rows=fixture(tmp_path);calls=[]
    monkeypatch.setattr(clean_runtime,'check_image',lambda value:value)
    monkeypatch.setattr(clean_runtime,'observe',observer(calls))
    (tmp_path/'runs'/rows[0]['id']/'stage1/artifact/solution/backup.py').write_bytes(b'changed')
    result=clean_runtime.run(tmp_path,tmp_path/'output')
    assert len(calls)==35 and result['counts']['input_changed']==1
    assert result['observations'][0]['evaluation'] is None


def test_infrastructure_failure_retains_unknown_quality_and_is_not_retried(tmp_path,monkeypatch):
    fixture(tmp_path);calls=[]
    monkeypatch.setattr(clean_runtime,'check_image',lambda value:value)
    monkeypatch.setattr(clean_runtime,'observe',observer(calls,infra=True))
    result=clean_runtime.run(tmp_path,tmp_path/'output')
    assert result['counts']=={'infrastructure_failure':36}
    assert all(entry['evaluation'] is None for entry in result['observations'])
    clean_runtime.run(tmp_path,tmp_path/'output');assert len(calls)==36


def test_cached_fabricated_success_is_rejected(tmp_path,monkeypatch):
    rows=fixture(tmp_path);calls=[]
    monkeypatch.setattr(clean_runtime,'check_image',lambda value:value)
    monkeypatch.setattr(clean_runtime,'observe',observer(calls))
    clean_runtime.run(tmp_path,tmp_path/'output')
    path=tmp_path/'output'/rows[0]['id']/'stage1/result.json'
    saved=json.loads(path.read_text());saved['entry']['evaluation']['score']=0.1;save(path,saved)
    with pytest.raises(RuntimeError,match='Cached result differs'):
        clean_runtime.run(tmp_path,tmp_path/'output')


def test_runtime_hash_drift_refuses_observation(tmp_path,monkeypatch):
    fixture(tmp_path);monkeypatch.setattr(clean_runtime,'check_image',lambda value:value)
    (tmp_path/'delivery_entry.py').write_bytes(b'changed')
    with pytest.raises(RuntimeError,match='Runtime input changed'):
        clean_runtime.run(tmp_path,tmp_path/'output')
    assert not (tmp_path/'output').exists()


def test_no_auth_and_wrapper_target_in_observer_command(tmp_path):
    row=schedule.make_schedule(17863)[0]
    command=clean_runtime.argv(tmp_path,row,2,'image-id')
    assert command[command.index('--candidate')+1]=='/entry/backup.py'
    assert command[command.index('--network')+1]=='none' and '--read-only' in command
    assert command[command.index('--mount')+1]==f'type=bind,src={tmp_path},dst=/candidate,readonly'
    assert not any('codex-home' in arg or 'apparmor=unconfined' in arg for arg in command)


def test_missing_product_has_no_fabricated_runtime_result(tmp_path,monkeypatch):
    rows=fixture(tmp_path);calls=[]
    monkeypatch.setattr(clean_runtime,'check_image',lambda value:value)
    monkeypatch.setattr(clean_runtime,'observe',observer(calls))
    stage=tmp_path/'runs'/rows[0]['id']/'stage1'
    (stage/'artifact/solution/backup.py').unlink();save(stage/'artifact.receipt.json',{'files':{}})
    result=clean_runtime.run(tmp_path,tmp_path/'output')
    assert len(calls)==35 and result['counts']['missing_product']==1
    assert result['observations'][0]['evaluation'] is None
    path=tmp_path/'output'/rows[0]['id']/'stage1/result.json'
    saved=json.loads(path.read_text());saved['entry'].update(status='evaluated',evaluation=grade(1))
    save(path,saved)
    with pytest.raises(RuntimeError,match='Cached nonexecuted observation'):
        clean_runtime.run(tmp_path,tmp_path/'output')


def test_cached_arm_reassignment_is_rejected(tmp_path,monkeypatch):
    rows=fixture(tmp_path);calls=[]
    monkeypatch.setattr(clean_runtime,'check_image',lambda value:value)
    monkeypatch.setattr(clean_runtime,'observe',observer(calls))
    clean_runtime.run(tmp_path,tmp_path/'output')
    path=tmp_path/'output'/rows[0]['id']/'stage1/result.json'
    saved=json.loads(path.read_text());saved['entry']['arm']='N' if rows[0]['arm']!='N' else 'S'
    save(path,saved)
    with pytest.raises(RuntimeError,match='Cached observation assignment'):
        clean_runtime.run(tmp_path,tmp_path/'output')


def test_nonfinite_grade_is_unknown_not_quality_zero(tmp_path,monkeypatch):
    fixture(tmp_path);calls=[];original=observer(calls)
    monkeypatch.setattr(clean_runtime,'check_image',lambda value:value)
    def bad(candidate,row,number,image,directory):
        receipt=original(candidate,row,number,image,directory)
        data=grade(number);data['score']=float('nan')
        path=directory/'evaluation.jsonl';path.write_text(json.dumps(data))
        receipt['stdout_sha256']=sha(path.read_bytes());save(directory/'receipt.json',receipt)
        return receipt
    monkeypatch.setattr(clean_runtime,'observe',bad)
    result=clean_runtime.run(tmp_path,tmp_path/'output')
    assert result['counts']=={'invalid_evaluation':36}
    assert all(entry['evaluation'] is None for entry in result['observations'])


def test_registered_runtime_cannot_silently_change(tmp_path,monkeypatch):
    fixture(tmp_path);monkeypatch.setattr(clean_runtime,'check_image',lambda value:value)
    path=tmp_path/'planning/clean-runtime-addendum.json'
    plan=json.loads(path.read_text());plan['runtime']['image_id']='another-image';save(path,plan)
    with pytest.raises(RuntimeError,match='Registered runtime differs'):
        clean_runtime.run(tmp_path,tmp_path/'output')
    assert not (tmp_path/'output').exists()
