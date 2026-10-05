"""Common budget admission controls; no native models or study solutions."""
import pytest

from scripts.study_cell_budget import CellBudget, StudyBudgetError
from scripts.controller_native_role import render_prompt
from specorganon.role_jobs import canonical


class RecordedTransport:
    def __init__(self): self.started = set()
    def call(self, job_id, role, request):
        reused = job_id in self.started
        self.started.add(job_id)
        return {'classification':'synthetic transport control','reused':reused}


def request(text='test'):
    return {'schema':1,'role':'author','role_instructions':'Return exact JSON, do not use tools.',
            'documents':{'contract.txt':text}}


def budget(root, transport, **overrides):
    return CellBudget(root, transport=transport, protocol_sha256='a'*64, max_calls=2,
                      max_total_input_bytes=overrides.get('bytes',20000),max_elapsed_seconds=6000)


def test_rendered_input_is_measured_and_closed_reuse_not_double_counted(tmp_path):
    t=RecordedTransport(); b=budget(tmp_path/'budget',t); req=request('é'*30)
    assert not b.call('job1','author',req)['reused']
    assert b.call('job1','author',req)['reused']
    expected=len(render_prompt(canonical(req))[1].encode('utf-8'))
    assert b.summary()['rendered_input_bytes']==expected
    assert b.summary()['admitted_native_jobs']==1 and len(t.started)==1
    with pytest.raises(StudyBudgetError): b.call('job1','author',request('changed'))


def test_budget_cannot_grow_and_rejects_before_native_dispatch(tmp_path):
    t=RecordedTransport(); root=tmp_path/'budget'; b=budget(root,t)
    b.call('job1','author',request()); b.call('job2','author',request())
    with pytest.raises(StudyBudgetError,match='call ceiling'): b.call('job3','author',request())
    assert len(t.started)==2
    with pytest.raises(StudyBudgetError,match='changed'): budget(root,t,bytes=30000)
    tiny=budget(tmp_path/'tiny',t,bytes=1)
    with pytest.raises(StudyBudgetError,match='input ceiling'): tiny.call('not-started','author',request())
    assert len(t.started)==2 and tiny.summary()['admitted_native_jobs']==0


def test_actual_provider_failure_does_not_refund_admission(tmp_path):
    class Failure:
        def call(self,*args): raise RuntimeError('synthetic provider failure')
    b=budget(tmp_path/'budget',Failure())
    with pytest.raises(RuntimeError): b.call('bad','author',request())
    assert b.summary()['admitted_native_jobs']==1
    assert b.summary()['token_usage'] is None and b.summary()['monetary_cost'] is None


def test_public_measurements_share_deadline_and_require_executable_change(tmp_path):
    class Tests(RecordedTransport):
        def measure(self,job_id,argv,files): return {'job_id':job_id}
        def verify_test(self,*args,**kwargs): return True
    b=budget(tmp_path/'budget',Tests())
    argv=['/opt/specorganon/venv/bin/python','test_fixture.py']
    files={'test_fixture.py':'pass\n','README.md':'Synthetic fixture'}
    assert b.measure('test1',argv,files)==b.measure('test1',argv,files)
    with pytest.raises(StudyBudgetError,match='changed executable'):
        b.measure('test2',argv,{**files,'README.md':'changed docs only'})
    b.measure('test2',argv,{**files,'test_fixture.py':'assert True\n'})
    with pytest.raises(StudyBudgetError,match='two-test ceiling'):
        b.measure('test3',argv,{**files,'test_fixture.py':'assert 1\n'})
    assert b.summary()['admitted_public_tests']==2
    from specorganon.role_jobs import _json,_write
    anchor=_json(b.root/'clock.json'); anchor['monotonic']-=6001
    _write(b.root/'clock.json',anchor)
    with pytest.raises(StudyBudgetError,match='deadline'):
        b.call('late','author',request())


def test_registration_rechecked_before_each_call_or_closed_reuse(tmp_path):
    events=[]
    def changed():
        events.append('checked')
        if len(events)>1: raise StudyBudgetError('registered source changed')
    t=RecordedTransport()
    b=CellBudget(tmp_path/'budget',transport=t,validate=changed,protocol_sha256='a'*64,
                 max_calls=2,max_total_input_bytes=20000,max_elapsed_seconds=6000)
    b.call('first','author',request())
    with pytest.raises(StudyBudgetError,match='source changed'): b.call('first','author',request())
    assert len(t.started)==1


def test_oversized_rendered_prompt_is_refused_before_admission(tmp_path):
    from scripts.controller_native_role import NativeRoleError
    t=RecordedTransport();b=budget(tmp_path/'budget',t)
    with pytest.raises(NativeRoleError):b.call('oversized','author',request('X'*128000))
    assert not t.started and b.summary()['admitted_native_jobs']==0


def test_boot_discontinuity_pauses_without_new_admission_or_clock_renewal(tmp_path):
    from scripts.study_cell_budget import StudyClockPause
    from specorganon.role_jobs import _json,_write
    t=RecordedTransport();b=budget(tmp_path/'budget',t);b.call('first','author',request())
    anchor=_json(b.root/'clock.json');anchor['boot_id_sha256']='synthetic-other-boot'
    _write(b.root/'clock.json',anchor);before=(b.root/'clock.json').read_bytes()
    with pytest.raises(StudyClockPause):b.call('second','author',request())
    assert t.started=={'first'} and (b.root/'clock.json').read_bytes()==before
