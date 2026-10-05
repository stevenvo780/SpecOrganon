"""Synthetic budget/gate mechanics; no provider, native delivery or milestone."""
import copy
import pytest

from experiments.software_comparison_v3.budget import RunJournal,RoleBudget,BudgetError,ClockUnknown
from scripts.controller_native_role import render_prompt,NativeRoleError
from specorganon.role_jobs import canonical,digest,_json,_write


def population():
    return [{'id':f'fixture-{i:02d}','method':m} for i,m in enumerate(['T','A','N','S']*6+['T','N','S']*6)]


def setup(root, **kw):
    def validated(): return {'registration_sha256':'a'*64,'scope':'synthetic registration control'}
    return RunJournal(root,registration_sha256='a'*64,cells=population(),
        validate_registration=kw.get('validate',validated),validate_quota=kw.get('quota',lambda:{'scope':'synthetic quota'}))


def request(text='fixture',role='author'):
    return {'schema':1,'role':role,'role_instructions':'Synthetic budget control. No solution.',
            'documents':{'fixture.md':text}}


class Transport:
    def __init__(self): self.calls={};self.tests={};self.passed=False
    def call(self,job_id,role,req):
        self.calls.setdefault(job_id,{'request_sha256':digest(canonical(req)),
            'result':{'verdict':'reject'} if role=='review' else {},'scope':'synthetic control'})
        return self.calls[job_id]
    def measure(self,job_id,argv,files):
        self.tests.setdefault(job_id,{'test_job_ref':'synthetic:'+job_id,'passed':self.passed})
        return self.tests[job_id]
    def verify_test(self,*args,**kwargs): return True


def test_prepared_but_unstarted_resumption_rechecks_quota_without_reallocating(tmp_path):
    observations=[]
    j=setup(tmp_path,quota=lambda:observations.append('read') or {'scope':'synthetic quota'})
    binding={'role':'author','request_sha256':'b'*64,'rendered_input_bytes':100}
    j.admit('fixture-00','first','roles',binding)
    before=_json(j.root/'progress.json')['cells']['fixture-00']['clock']
    j.recheck_prepared_dispatch('fixture-00','first','roles')
    after=_json(j.root/'progress.json')['cells']['fixture-00']
    assert len(observations)==2 and before==after['clock'] and len(after['roles'])==1
    j.quota=lambda:(_ for _ in ()).throw(ValueError('synthetic expired capacity'))
    with pytest.raises(ValueError):j.recheck_prepared_dispatch('fixture-00','first','roles')
    assert j.summary()['admitted_native_jobs']==1


def test_prepared_resumption_cannot_bypass_original_deadline_or_sealed_outcome(tmp_path):
    from experiments.software_comparison_v3 import budget
    j=setup(tmp_path);binding={'role':'author','request_sha256':'b'*64,'rendered_input_bytes':100}
    j.admit('fixture-00','first','roles',binding)
    state=_json(j.root/'progress.json');state['cells']['fixture-00']['clock']['monotonic']-=6000
    _write(j.root/'progress.json',state)
    with pytest.raises(BudgetError,match='deadline'):j.recheck_prepared_dispatch('fixture-00','first','roles')
    j.outcome('fixture-00','first','roles',{'scope':'synthetic stopped witness'})
    with pytest.raises(BudgetError,match='unresolved'):j.recheck_prepared_dispatch('fixture-00','first','roles')


def test_prompt_uses_actual_bytes_API_and_counts_complete_rendered_text(tmp_path):
    j=setup(tmp_path);t=Transport();b=RoleBudget(j,'fixture-00',t);req=request('é'*70)
    parsed,text=render_prompt(canonical(req))
    assert parsed==req and req['role_instructions'] in text and canonical(req).decode() in text
    b.call('first','author',req);b.call('first','author',req)
    assert j.summary()['admitted_native_jobs']==1
    assert j.summary()['rendered_input_bytes']==len(text.encode()) and len(t.calls)==1
    with pytest.raises(BudgetError,match='input changed'):b.call('first','author',request('different'))


def test_fixed_order_and_terminal_seals_cannot_reopen(tmp_path):
    j=setup(tmp_path);t=Transport();b=RoleBudget(j,'fixture-01',t)
    with pytest.raises(BudgetError,match='order'):b.call('outoforder','author',request())
    b=RoleBudget(j,'fixture-00',t);b.call('first','author',request())
    seal=j.close_cell('fixture-00',status='generation_failed',delivery_sha256=digest(canonical({})))
    assert seal==j.close_cell('fixture-00',status='generation_failed',delivery_sha256=digest(canonical({})))
    with pytest.raises(BudgetError,match='sealed'):b.call('extra','author',request())
    with pytest.raises(BudgetError,match='changed'):j.close_cell('fixture-00',status='complete',delivery_sha256='b'*64)
    assert j.summary()['terminal_cells']==1


def test_call_cumulative_and_rendered_caps_refuse_before_dispatch(tmp_path):
    j=setup(tmp_path);t=Transport();b=RoleBudget(j,'fixture-00',t)
    for i in range(40): b.call(f'job{i}','author',request())
    with pytest.raises(BudgetError,match='call ceiling'):b.call('extra','author',request())
    assert len(t.calls)==40
    j=setup(tmp_path/'bytes');t=Transport();b=RoleBudget(j,'fixture-00',t)
    for i in range(31):b.call(f'job{i}','author',request('x'*100000))
    with pytest.raises(BudgetError,match='cumulative'):b.call('overflow','author',request('x'*127000))
    assert len(t.calls)==31
    with pytest.raises(NativeRoleError):b.call('oversize','author',request('x'*128000))
    assert len(t.calls)==31


def test_current_quota_only_for_fresh_admissions_sources_always_checked(tmp_path):
    checks=[];fresh=[]
    def validated():checks.append('sources');return {'registration_sha256':'a'*64}
    def quota():fresh.append('quota');return {'scope':'synthetic'}
    j=setup(tmp_path,validate=validated,quota=quota);b=RoleBudget(j,'fixture-00',Transport())
    b.call('one','author',request());b.call('one','author',request())
    assert len(checks)==2 and len(fresh)==1
    j.registration=lambda:{'registration_sha256':'b'*64}
    with pytest.raises(BudgetError,match='validation'):b.call('two','author',request())
    assert j.summary()['admitted_native_jobs']==1


def test_quota_failure_does_not_allocate_and_clock_is_rechecked_after_wait(tmp_path,monkeypatch):
    def expired():raise ValueError('synthetic stale quota')
    j=setup(tmp_path,quota=expired);b=RoleBudget(j,'fixture-00',Transport())
    with pytest.raises(ValueError):b.call('one','author',request())
    assert _json(j.root/'progress.json')['global_clock'] is None
    j.quota=lambda:{'scope':'synthetic'};b.call('one','author',request())
    from experiments.software_comparison_v3 import budget
    base=budget.time.monotonic()
    state=_json(j.root/'progress.json');state['cells']['fixture-00']['clock']['monotonic']=base-5810
    _write(j.root/'progress.json',state)
    def slow_quota():monkeypatch.setattr(budget.time,'monotonic',lambda:base+20);return {}
    j.quota=slow_quota
    with pytest.raises(BudgetError,match='during quota'):b.call('two','author',request())
    assert j.summary()['admitted_native_jobs']==1


def test_deadline_boot_unknown_and_budget_policy_change_never_reset(tmp_path):
    j=setup(tmp_path);b=RoleBudget(j,'fixture-00',Transport());b.call('one','author',request())
    state=_json(j.root/'progress.json');state['global_clock']['boot_id_sha256']='other-boot';_write(j.root/'progress.json',state)
    old=(j.root/'progress.json').read_bytes()
    with pytest.raises(ClockUnknown):b.call('two','author',request())
    assert (j.root/'progress.json').read_bytes()==old
    policy=_json(j.root/'policy.json');policy['cell_limits']['calls']=41;_write(j.root/'policy.json',policy)
    with pytest.raises(BudgetError,match='policy'):b.call('one','author',request())


def test_tests_need_actual_failure_and_executable_change_not_readme(tmp_path):
    j=setup(tmp_path);t=Transport();b=RoleBudget(j,'fixture-00',t)
    files={'test_fixture.py':'pass\n','README.md':'synthetic'};argv=['/opt/specorganon/venv/bin/python','test_fixture.py']
    b.measure('first',argv,files);b.measure('first',argv,files)
    with pytest.raises(BudgetError,match='executable'):b.measure('second',argv,{**files,'README.md':'changed'})
    b.measure('second',argv,{**files,'test_fixture.py':'assert True\n'})
    with pytest.raises(BudgetError,match='two-test'):b.measure('third',argv,{**files,'test_fixture.py':'assert 1\n'})
    assert len(t.tests)==2 and j.summary()['admitted_native_jobs']==0


def test_semantic_rejection_must_bind_previous_test_source(tmp_path):
    j=setup(tmp_path);t=Transport();t.passed=True;b=RoleBudget(j,'fixture-00',t)
    files={'test_fixture.py':'pass\n'};argv=['/opt/specorganon/venv/bin/python','test_fixture.py'];new={'test_fixture.py':'assert True\n'}
    b.measure('first',argv,files)
    with pytest.raises(BudgetError,match='actual first'):b.measure('second',argv,new)
    req=request(role='review');req['documents']['delivery-files.json']=canonical(new).decode();b.call('wrong-source-review','review',req)
    with pytest.raises(BudgetError,match='actual first'):b.measure('second',argv,new)
    req['documents']['delivery-files.json']=canonical(files).decode();b.call('bound-review','review',req)
    b.measure('second',argv,new)
    assert j.summary()['admitted_tests']==2


def test_transport_failure_keeps_consumed_pending_job_not_fake_terminal(tmp_path):
    class Fail(Transport):
        def call(self,*args):raise RuntimeError('synthetic uncertain transport')
    j=setup(tmp_path);b=RoleBudget(j,'fixture-00',Fail())
    with pytest.raises(RuntimeError):b.call('uncertain','author',request())
    assert j.summary()['admitted_native_jobs']==1
    with pytest.raises(BudgetError,match='reconciled'):j.close_cell('fixture-00',status='infra_inconclusive',delivery_sha256=digest(canonical({})))
    assert j.summary()['terminal_cells']==0


def close_all(j):
    for cell in population():
        b=RoleBudget(j,cell['id'],Transport());b.call('fixture','author',request())
        j.close_cell(cell['id'],status='generation_failed',delivery_sha256=digest(canonical({})))


def test_prerequisite_requires_all42_generations_and_registered_verifier(tmp_path):
    j=setup(tmp_path)
    with pytest.raises(BudgetError,match='all42'):j.evaluation_gate(lambda *_:None)
    with pytest.raises(BudgetError,match='verifier'):j.evaluation_gate(None)
    with pytest.raises(BudgetError,match='unadmitted'):j.close_cell('fixture-00',status='generation_failed',delivery_sha256=digest(canonical({})))
    close_all(j)
    count=[]
    def failed(identity,seal):count.append(identity);return {'status':'failed','evidence_sha256':'b'*64}
    value=j.evaluation_gate(failed)
    assert value['status']=='not_evaluated_by_prerequisite' and len(count)==12
    assert j.evaluation_gate(lambda *_:pytest.fail('do not regenerate proof'))==value
    assert j.summary()['native_tokens'] is None and j.summary()['monetary_cost'] is None


def test_inconclusive_milestone_waits_without_sealing_or_synthetic_success(tmp_path):
    j=setup(tmp_path);close_all(j)
    result=j.evaluation_gate(lambda *_:{'status':'inconclusive','evidence_sha256':'b'*64})
    assert result['status']=='prerequisite_inconclusive' and not result['reserved_evaluation_allowed']
    assert j.summary()['evaluation'] is None
    # Synthetic callback is a mechanics fixture, never actual9phase evidence.
    value=j.evaluation_gate(lambda identity,_:{'status':'eligible' if identity=='fixture-00' else 'failed','evidence_sha256':'c'*64})
    assert value['status']=='released_once' and value['primary_T']=='fixture-00' and value['eligible_T']==['fixture-00']
    assert value['new_cohort_authorized'] is False and value['reserved_evaluation_allowed'] is True


def test_null_malformed_request_fails_bridge_validation_before_admission(tmp_path):
    j=setup(tmp_path);b=RoleBudget(j,'fixture-00',Transport());req=request();req['documents']=None
    with pytest.raises(NativeRoleError):b.call('null','author',req)
    assert j.summary()['admitted_native_jobs']==0


def test_closed_handles_cannot_dispatch_and_campaign_deadline_also_blocks_complete(tmp_path):
    j=setup(tmp_path);t=Transport();b=RoleBudget(j,'fixture-00',t);b.call('one','author',request())
    state=_json(j.root/'progress.json');state['global_clock']['monotonic']-=252001;_write(j.root/'progress.json',state)
    with pytest.raises(BudgetError,match='campaign deadline'):j.close_cell('fixture-00',status='complete',delivery_sha256=digest(canonical({})))
    j.close_cell('fixture-00',status='infra_inconclusive',delivery_sha256=digest(canonical({})))
    with pytest.raises(BudgetError,match='sealed'):b.call('one','author',request())
    assert len(t.calls)==1
