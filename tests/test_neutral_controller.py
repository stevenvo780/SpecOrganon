"""Staged controller guard fixtures; no provider generations or efficacy proof."""
import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

import specorganon.neutral_controller as module
from specorganon.common_review import checklist
from specorganon.neutral_controller import NeutralController, NeutralControllerError
from specorganon.role_jobs import UncertainJob, _json, _write, canonical, digest


PROGRAM='def result(): return 7\nif __name__ == "__main__": print(result())\n'
TEST='from pathlib import Path\nimport runpy\nassert runpy.run_path(str(Path(__file__).with_name("program.py")))["result"]()==7\nprint("guard control passed")\n'
ARGV=['/opt/specorganon/venv/bin/python','-I','-B','/input/delivery/test_program.py']
POLICY={'fixture':'synthetic neutral transport only'}


class FixtureTransport:
    def __init__(self,root,*,responses=None,measurements=None,H='pass',verdict='accept'):
        self.root=root;self.root.mkdir(exist_ok=True,mode=0o700)
        self.store=SimpleNamespace(root=root/'host-journal');self.store.root.mkdir(exist_ok=True,mode=0o700)
        _write(root/'transport-policy.json',POLICY)
        self.responses=responses or {};self.measurements=list(measurements or [True])
        self.H=H;self.verdict=verdict;self.dispatched=[]

    def call(self,job,role,request):
        folder=self.store.root/job;folder.mkdir(exist_ok=True,mode=0o700)
        resultpath=folder/'fixture-packet.json'
        if resultpath.exists():return _json(resultpath)
        if (folder/'started.json').exists():raise UncertainJob('fixture started without closed result; never replay')
        _write(folder/'started.json',{'fixture':True});self.dispatched.append(job)
        stage=request['documents']['stage.txt']
        if stage in self.responses:
            values=self.responses[stage]
            value=copy.deepcopy(values.pop(0) if isinstance(values,list) else values)
        elif stage=='plan':
            names=('SPEC.md','DESIGN.md','TASKS.md') if _json(self.root.parent/'initial.json')['policy']['method']=='S' else ('own-notes.txt',)
            value={'schema':1,'files':{},'documents':{n:'Original criterion: result() returns seven; alternatives and task links are fixture prose.' for n in names},'reason':'Fixture plan'}
        elif stage=='plan-review':value={'schema':1,'verdict':'accept','reason':'Synthetic design judgment','findings':[],'tests_executed':False}
        elif stage in ('program','repair'):value={'schema':1,'files':{'program.py':PROGRAM,'README.md':'Fixture documentation only'},'documents':{},'reason':'Synthetic code'}
        elif stage=='tests':value={'schema':1,'files':{'test_program.py':TEST,'fixture.json':'{ "value": 7 }\n'},'documents':{},'reason':'Synthetic original battery'}
        elif stage=='audit':
            from specorganon.ledger import strict_json_loads
            d=strict_json_loads(request['documents']['review-response-format.json'])
            value={'schema':1,'verdict':self.verdict,'reason':'Synthetic bound assertions; not a semantic review',
                'findings':[],'tests_executed':False,'audit':{'binding':d['binding'],**{
                group:{name:{'status':self.H if group=='H' else 'pass','reason':'Synthetic assertion',
                    'evidence':['contract:public']} for name in points} for group,points in checklist(d['method']).items()}}}
        else:raise AssertionError(stage)
        packet={'schema':1,'result':value,'provenance':'fixture','actor':role+':fixture',
            'request_sha256':digest(canonical(request))}
        _write(resultpath,packet);return packet

    def measure(self,job,argv,files):
        folder=self.store.root/job;folder.mkdir(exist_ok=True,mode=0o700);path=folder/'fixture-measured.json'
        if path.exists():return _json(path)
        if (folder/'started.json').exists():raise UncertainJob('fixture measured once; no closed result')
        _write(folder/'started.json',{'fixture':True});self.dispatched.append(job)
        stdout=b'Fixture only; no subject executed\n';stderr=b''
        for name,raw in [('stdout',stdout),('stderr',stderr)]:(folder/(name+'.bin')).write_bytes(raw)
        value={'passed':self.measurements.pop(0) if self.measurements else True,
            'provenance':'fixture','subject_argv':argv,'delivery_tree_sha256':digest(canonical(files)),
            'test_job_ref':str(path),'stdout_sha256':digest(stdout),'stderr_sha256':digest(stderr),
            'stdout_bytes':len(stdout),'stderr_bytes':len(stderr)}
        _write(path,value);return value

    def reconcile_pending(self,job,role,request):
        return False # Explicit fixture: there is no physical container to reconcile

    def recover_role(self,job,role,request):
        path=self.store.root/job/'fixture-packet.json'
        return _json(path) if path.exists() else None

    def recover_test(self,job,argv,files):
        path=self.store.root/job/'fixture-measured.json'
        return _json(path) if path.exists() else None

    def verify_test(self,data,files,**options):
        measured=_json(data['test_job_ref'])
        if measured['subject_argv']!=data['argv'] or measured['delivery_tree_sha256']!=digest(canonical(files)):
            raise ValueError('fixture measurement binding diverged')
        return True


def controller(root,method='N',**options):
    transport=None
    def factory(path):
        nonlocal transport
        if transport is None:transport=FixtureTransport(path,**options)
        return transport
    c=NeutralController(root,attempt_id='fixture-01',method=method,contract='Public fixture: result seven.',
        mandate='Local only; no external effects.',argv=ARGV,test_file='test_program.py',
        transport_policy=POLICY,transport_factory=factory,fixture_mode=True)
    return c


def test_free_notes_and_SDD_have_real_stages_but_fixture_never_native_ready(tmp_path):
    for method in ('N','S'):
        c=controller(tmp_path/method,method);report=c.run()
        assert report['status']=='review_ready',report
        assert report['common_review_ready'] and report['native_ready'] is False
        assert report['common_complete'] is None and report['external_F'] is None
        assert report['counts']['roles']==(4 if method=='N' else 5)
        assert report['counts']['build_authors']==2 and report['counts']['test_runs']==1
        state=_json(c.root/'generations'/f"{len(list((c.root/'generations').iterdir())):04d}.json")['state']
        assert state['original_tests']['fixture.json']=='{ "value": 7 }\n'
        if method=='N':assert set(state['original_criteria'])=={'own-notes.txt'}
        assert report['whole_attempt_seconds']>=0


@pytest.mark.parametrize('method',['N','S'])
def test_H_and_root_verdict_do_not_change_DG_readiness_or_trigger_repair(tmp_path,method):
    a=controller(tmp_path/'a',method,H='pass',verdict='accept').run()
    b=controller(tmp_path/'b',method,H='fail',verdict='reject').run()
    assert a['common_review_ready']==b['common_review_ready']==True
    assert a['counts']==b['counts'] and b['counts']['stages'].get('repair',0)==0
    if method=='S':assert a['method_review_ready'] is True and b['method_review_ready'] is False


def test_SDD_plan_repair_uses_same_stage_limits_and_keeps_original_criteria(tmp_path):
    refusal={'schema':1,'verdict':'reject','reason':'Fixture refusal','findings':[{'problem':'Design lacks alternatives'}],'tests_executed':False}
    c=controller(tmp_path/'run','S',responses={'plan-review':[refusal,refusal]});report=c.run()
    assert report['status']=='review_ready' and report['common_review_ready'] and not report['method_review_ready']
    assert report['counts']['stages']['plan']==report['counts']['stages']['plan-review']==2
    assert report['counts']['roles']==7


def test_failed_measure_repairs_program_once_reexecutes_same_original_battery(tmp_path):
    broken={'schema':1,'files':{'program.py':PROGRAM.replace('return 7','return 0'),'README.md':'Fixture initial program'},'documents':{},'reason':'Synthetic defect'}
    c=controller(tmp_path/'run',measurements=[False,True],responses={'program':broken});report=c.run()
    assert report['status']=='review_ready',report
    assert report['counts']['build_authors']==3 and report['counts']['test_runs']==2
    measures=[_json(p) for p in (c.root/'reservations').iterdir() if _json(p)['stage']=='measure']
    assert len(measures)==2
    assert measures[0]['request']['files']['test_program.py']==measures[1]['request']['files']['test_program.py']==TEST
    assert measures[0]['request']['argv']==measures[1]['request']['argv']==ARGV
    assert report['counts']['stages']['repair']==1


def test_original_test_replacement_consumes_last_build_slot_and_fails(tmp_path):
    replacement={'schema':1,'files':{'test_program.py':'print("PASS")'},'documents':{},'reason':'Invalid attempt to weaken tests'}
    c=controller(tmp_path/'run',measurements=[False],responses={'repair':replacement});report=c.run()
    assert report['status']=='failed' and not report['common_review_ready']
    assert report['counts']['build_authors']==3 and report['counts']['test_runs']==1
    assert 'admission' in report['failure']


def test_interruption_after_closed_packet_recovers_without_call_or_new_slot(tmp_path,monkeypatch):
    c=controller(tmp_path/'run');original=c._apply
    def crash(*args):raise KeyboardInterrupt('fixture crash after closed result before generation')
    monkeypatch.setattr(c,'_apply',crash)
    with pytest.raises(KeyboardInterrupt):c.step()
    assert len(c.transport.dispatched)==1
    monkeypatch.setattr(c,'_apply',original)
    # Deliberately make any dispatch forbidden: recovery must use the closed packet.
    monkeypatch.setattr(c.transport,'call',lambda *a:(_ for _ in ()).throw(AssertionError('must not dispatch again')))
    report=c.step()
    assert report['stage']=='program' and report['counts']['roles']==1
    assert len(c.transport.dispatched)==1


def test_interruption_without_closed_transport_result_closes_uncertain_no_new_job(tmp_path,monkeypatch):
    c=controller(tmp_path/'run');t=c._get_transport();original=t.call
    def crash(job,role,request):
        folder=t.store.root/job;folder.mkdir();_write(folder/'started.json',{'fixture':True})
        raise KeyboardInterrupt('fixture interruption before transport closure')
    monkeypatch.setattr(t,'call',crash)
    with pytest.raises(KeyboardInterrupt):c.step()
    monkeypatch.setattr(t,'call',original)
    report=c.step();assert report['status']=='failed' and report['counts']['roles']==1
    assert 'UncertainJob' in report['failure']
    assert c.step()==report
    assert len(list((c.root/'reservations').iterdir()))==1


def test_atomic_generation_and_persistent_counters_reject_tampering(tmp_path):
    c=controller(tmp_path/'run');c.step();p=c.root/'generations/0001.json';g=_json(p)
    g['state']['counts']['roles']=0;_write(p,g)
    with pytest.raises(NeutralControllerError,match='generation diverged'):c.step()


def test_policy_change_and_fixture_downgrade_cannot_resume(tmp_path):
    c=controller(tmp_path/'run');c.step()
    with pytest.raises(NeutralControllerError,match='policy changed'):
        NeutralController(c.root,attempt_id='fixture-01',method='N',contract='Changed',mandate='Local only; no external effects.',
            argv=ARGV,test_file='test_program.py',transport_policy=POLICY,transport_factory=c.factory,fixture_mode=True)
    with pytest.raises(NeutralControllerError,match='registered sources'):
        NeutralController(tmp_path/'native',attempt_id='x',method='N',contract='Public',mandate='Local',
            argv=ARGV,test_file='test_program.py',transport_policy=POLICY,transport_factory=c.factory)


def test_attempt_clock_starts_before_factory_and_includes_preparation(tmp_path,monkeypatch):
    now={'boot_id_sha256':'a'*64,'host_id_sha256':'b'*64,'boottime_ns':100,'epoch_ns':100}
    monkeypatch.setattr(module,'_clock',lambda:copy.deepcopy(now))
    c=controller(tmp_path/'run');original=c.factory
    def factory(path):
        assert _json(c.root/'initial.json')['clock']['boottime_ns']==100
        now['boottime_ns']+=5_000_000_000
        return original(path)
    c.factory=factory
    assert c.step()['whole_attempt_seconds']==5


def test_boot_change_closes_without_dispatch_unknown_cost_and_no_reset(tmp_path,monkeypatch):
    c=controller(tmp_path/'run');old=copy.deepcopy(c.initial['clock']);old['boot_id_sha256']='c'*64
    monkeypatch.setattr(module,'_clock',lambda:old)
    report=c.step()
    assert report['status']=='failed' and report['whole_attempt_seconds'] is None
    assert report['counts']['roles']==0 and c.transport is None
    assert c.step()==report


def test_whole_attempt_elapsed_admission_failure_cannot_reset_clock(tmp_path,monkeypatch):
    c=controller(tmp_path/'run');now=copy.deepcopy(c.initial['clock']);now['boottime_ns']+=6001*10**9
    monkeypatch.setattr(module,'_clock',lambda:now)
    report=c.step();assert report['status']=='failed' and report['whole_attempt_seconds']==6001
    assert report['counts']['roles']==0 and c.transport is None


def test_complete_candidate_budget_rejections_consume_roles_without_applying_files(tmp_path):
    too_large={'schema':1,'files':{'program.py':PROGRAM,'README.md':'a'*21000},'documents':{},'reason':'Too large'}
    c=controller(tmp_path/'run',responses={'program':too_large});report=c.run()
    assert report['status']=='failed' and report['counts']['build_authors']==2
    assert report['counts']['stages']['program']==2 and report['counts']['test_runs']==0
    state=_json(c.root/'generations/0003.json')['state'];assert not state['files']
