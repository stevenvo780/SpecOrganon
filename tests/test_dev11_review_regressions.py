"""Adversarial reviewer reproductions; synthetic clocks/journals, no native calls."""
import copy
import json
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

from specorganon import engine
from specorganon.docker_roles import DockerControlDeadlineError, DockerRoles, PendingCleanupError
from specorganon.role_jobs import _json, _write, canonical
from test_closed_native_role import closed
from test_t_common_controller import make


def test_F1_first_T_terminal_never_promotes_changed_audited_state(tmp_path,monkeypatch):
    c,_ = make(tmp_path); terminal = c._terminal; mutated = []
    def change(status,**options):
        if options.get('common_ready') and not mutated:
            engine.put_item(c.controller.case,'external-terminal-item','problem',
                'Synthetic unrelated valid event inserted after audit',[],{},'agent:external-fixture')
            mutated.append(True)
        return terminal(status,**options)
    monkeypatch.setattr(c,'_terminal',change)
    report = c.run()
    assert mutated and report['status'] == 'failed'
    assert not any(report[k] for k in ('common_review_ready','method_review_ready','native_ready'))
    assert 'first terminal readiness' in report['failure']


@pytest.mark.parametrize('change',['expired','boot'])
def test_F2_T_closure_clock_includes_capture_and_verification_work(tmp_path,monkeypatch,change):
    from specorganon import t_common_controller as module
    c,_ = make(tmp_path); original = c._terminal
    def terminal(status,**options):
        if options.get('common_ready'):
            now = copy.deepcopy(c.initial['clock']);now['boottime_ns'] += 5999*10**9
            monkeypatch.setattr(module,'_clock',lambda:copy.deepcopy(now))
            capture = c._capture
            def capture_then_advance(*args,**kwargs):
                value = capture(*args,**kwargs)
                if change == 'expired': now['boottime_ns'] = c.initial['clock']['boottime_ns']+6001*10**9
                else: now['boot_id_sha256'] = 'f'*64
                return value
            monkeypatch.setattr(c,'_capture',capture_then_advance)
        return original(status,**options)
    monkeypatch.setattr(c,'_terminal',terminal)
    report = c.run()
    assert report['status'] == 'failed' and not any(report[k] for k in ('common_review_ready','method_review_ready','native_ready'))
    if change == 'expired': assert report['whole_attempt_seconds'] == 6001
    else: assert report['clock_error'] and report['whole_attempt_seconds'] is None


@pytest.mark.parametrize('status',['missing','restarting','dead','created','exited'])
def test_F3_cleanup_only_confirms_observed_owned_terminal_lifecycle(closed,monkeypatch,status):
    t,folder,request,_,_ = closed
    monkeypatch.setattr(t,'reconcile',DockerRoles.reconcile.__get__(t,DockerRoles))
    plan = _json(folder/'launch.json'); plan['container_id'] = None; _write(folder/'launch.json',plan)
    record = None if status == 'missing' else {'Id':'b'*64,'State':{'Running':False,'Status':status}}
    monkeypatch.setattr(t,'_inspect',lambda ignored:copy.deepcopy(record))
    if status in ('created','exited'):
        assert t.reconcile_pending('author-01','author',request) is True
    else:
        with pytest.raises(PendingCleanupError): t.reconcile_pending('author-01','author',request)
        if status == 'missing': assert _json(folder/'reconciliation.json')['cleanup_confirmed'] is False


def test_F3_disappearance_after_kill_is_not_confirmed_stop(closed,monkeypatch):
    t,_,request,_,_ = closed
    monkeypatch.setattr(t,'reconcile',DockerRoles.reconcile.__get__(t,DockerRoles))
    records = iter([{'Id':'b'*64,'State':{'Running':True,'Status':'running'}},None])
    monkeypatch.setattr(t,'_inspect',lambda ignored:next(records))
    calls=[];monkeypatch.setattr(t,'_cli',lambda argv,**kwargs:calls.append(argv))
    with pytest.raises(PendingCleanupError): t.reconcile_pending('author-01','author',request)
    assert calls == [['kill','b'*64]]


def test_F5_swapped_outer_and_inner_reads_cannot_promote_unverified_packet(closed,monkeypatch):
    import specorganon.docker_roles as dr
    from specorganon.role_jobs import JobStore
    t,folder,request,packet,_ = closed
    altered = copy.deepcopy(packet);altered['result']['reason'] = 'Unverified replacement content'
    outer = t.store.root/'author-01/stdout.bin'
    actual = {k:v for k,v in altered.items() if k not in ('actor','receipt_ref','provenance')}
    original_read = dr._read; outer_reads=[]
    def read(path,*args,**kwargs):
        raw = original_read(path,*args,**kwargs)
        if Path(path) == outer:
            outer_reads.append(True)
            if len(outer_reads)==1: outer.write_bytes(canonical(actual))
        return raw
    monkeypatch.setattr(dr,'_read',read)
    # A packet generated from bytes AFTER the checked cut is always rejected.
    with pytest.raises(ValueError): t.verify_role(altered,'author-01','author',request)
    assert len(outer_reads) == 1


def test_F5_inner_parser_uses_original_checked_buffers_without_second_reads(closed,monkeypatch):
    from specorganon.role_jobs import JobStore
    t,folder,request,packet,_ = closed; original = JobStore._read; counts={}
    def read(store,path,*args,**kwargs):
        raw = original(store,path,*args,**kwargs)
        if store.root == folder/'output/native' and Path(path).name in ('stdout.bin','stderr.bin'):
            counts[str(path)] = counts.get(str(path),0)+1
            Path(path).write_bytes(b'Changed AFTER verified original cut')
        return raw
    monkeypatch.setattr(JobStore,'_read',read)
    assert t.verify_role(packet,'author-01','author',request) is True
    assert set(counts.values()) == {1}
    with pytest.raises(ValueError): t.verify_role(packet,'author-01','author',request)


def test_F6_each_attach_timeout_includes_suspend_even_with_global_time_remaining(tmp_path,monkeypatch):
    from specorganon.role_jobs import JobStore
    calls=[]
    def boottime(clock_id):
        calls.append(True);return (1000 if len(calls)==1 else 1000+181*10**9)
    monkeypatch.setattr(time,'clock_gettime_ns',boottime)
    store=JobStore(tmp_path/'jobs');began=time.monotonic()
    result=store.execute('call',[sys.executable,'-c','import time;time.sleep(30)'],{},cwd=tmp_path,timeout_seconds=180)
    assert result['receipt']['timed_out'] is True and result['receipt']['exit_code'] == -signal.SIGKILL
    assert time.monotonic()-began < 3


def test_F6_each_control_timeout_includes_suspend_even_with_global_time_remaining(monkeypatch):
    calls=[];original=subprocess.Popen;processes=[]
    def boottime(clock_id):
        calls.append(True);return (1000 if len(calls)==1 else 1000+16*10**9)
    def popen(argv,**kwargs):
        p=original([sys.executable,'-c','import time;time.sleep(30)'],**kwargs);processes.append(p);return p
    monkeypatch.setattr(time,'clock_gettime_ns',boottime);monkeypatch.setattr(subprocess,'Popen',popen)
    with pytest.raises(DockerControlDeadlineError): DockerRoles._cli(['synthetic-control'])
    assert processes[0].poll() == -signal.SIGKILL
