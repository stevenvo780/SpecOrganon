"""Method diagnostics use synthetic ledgers, never live campaign artifacts."""
import json
import subprocess
import sys
from pathlib import Path

import pytest
from specorganon import engine

BASE=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(BASE))
import method_report
import run_pilot


@pytest.fixture(autouse=True)
def isolate_config(monkeypatch):
    for name in ('ORGANON_APPROVERS_FILE','ORGANON_ALLOW_FIXTURES',
                 'ORGANON_LEDGER_ANCHORS_FILE','ORGANON_FIELD_ASSESSORS_FILE'):
        monkeypatch.delenv(name,raising=False)


def run_inspector(case):
    proc=subprocess.run([sys.executable,'-c',method_report.INSPECTOR,str(case)],
                        capture_output=True,text=True,timeout=30)
    return proc,json.loads(proc.stdout)


def frame(case):
    engine.create_case(case,'Synthetic frame','synthetic data','human:test-owner',approval_policy='local')
    engine.put_item(case,'p1','problem','Synthetic problem',[],{},'agent:test-author')
    engine.put_item(case,'a1','actor','Synthetic affected actor',['p1'],{},'agent:test-author')
    engine.put_item(case,'b1','boundary','Synthetic local boundary',['p1'],{},'agent:test-author')
    engine.review_phase(case,'frame','accept','Independent review of synthetic frame','agent:test-reviewer')
    engine.advance(case,'frame','agent:test-author')


def test_post_campaign_guard_does_not_inspect_or_create_output(tmp_path,monkeypatch):
    def forbidden(*args,**kwargs): raise AssertionError('Must not inspect real artifacts before closure')
    monkeypatch.setattr(method_report,'inspect_artifact',forbidden)
    with pytest.raises(RuntimeError,match='incomplete'):
        method_report.report(tmp_path,tmp_path/'output')
    assert not (tmp_path/'output').exists()


def test_current_acceptance_is_distinct_from_historical_review(tmp_path):
    frame(tmp_path/'case')
    proc,accepted=run_inspector(tmp_path/'case')
    assert proc.returncode==0 and accepted['accepted_phases']==['frame']
    assert accepted['phase_review_history'][0]['verdict']=='accept'
    assert accepted['phase_review_history'][0]['independent'] is True
    assert accepted['approval_identity_authenticated'] is False
    assert accepted['phase_review_trust']=='local_declared'
    engine.put_item(tmp_path/'case','p1','problem','Updated synthetic problem',[],{},'agent:test-author')
    proc,stale=run_inspector(tmp_path/'case')
    assert proc.returncode==0 and stale['accepted_phases']==[]
    assert len(stale['phase_review_history'])==1
    assert stale['phases']['frame']['reviewed'] is False
    assert stale['ledger_sha256']!=accepted['ledger_sha256']


def test_invalid_ledger_is_unknown_not_zero_accepted_phases(tmp_path):
    case=tmp_path/'case';case.mkdir()
    (case/'organon.json').write_text('{not JSON}')
    proc,data=run_inspector(case)
    assert proc.returncode!=0 and data['ok'] is False
    assert 'accepted_phases' not in data


def test_container_command_has_no_auth_and_is_read_only(tmp_path):
    argv=method_report.inspection_argv(tmp_path,'sha256:frozen-method','method-test')
    assert argv[argv.index('--network')+1]=='none' and '--read-only' in argv
    assert argv[argv.index('--user')+1]=='1000:1000'
    mounts=[argv[i+1] for i,part in enumerate(argv) if part=='--mount']
    assert mounts==[f'type=bind,src={tmp_path},dst=/trial,readonly']
    assert not any('codex-home' in arg or 'apparmor=unconfined' in arg for arg in argv)


def test_cached_observation_must_agree_with_preserved_raw_output(tmp_path):
    directory=tmp_path/'inspection';directory.mkdir()
    raw=b'{"ok":true,"accepted_phases":[]}\n'
    (directory/'inspection.jsonl').write_bytes(raw)
    (directory/'inspection.stderr').write_bytes(b'')
    artifact=tmp_path/'artifact';image='sha256:method';name='test-observer'
    receipt={'exit_code':0,'timed_out':False,
             'argv':method_report.inspection_argv(artifact,image,name),
             'stdout_sha256':run_pilot.digest(directory/'inspection.jsonl'),
             'stderr_sha256':run_pilot.digest(directory/'inspection.stderr')}
    saved={'result':{'receipt':receipt,'observation':{'ok':True,'accepted_phases':['frame']}}}
    with pytest.raises(RuntimeError,match='Cached observation differs'):
        method_report.validate_cached(saved,directory,artifact,image,name)
    saved['result']['observation']['accepted_phases']=[]
    method_report.validate_cached(saved,directory,artifact,image,name)
    (directory/'inspection.jsonl').write_bytes(b'altered')
    with pytest.raises(RuntimeError,match='Cached observer log changed'):
        method_report.validate_cached(saved,directory,artifact,image,name)
