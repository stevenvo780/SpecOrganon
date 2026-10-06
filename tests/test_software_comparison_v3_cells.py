"""Synthetic stage/replay guards, not source-correct software or native9phases."""
import copy
import json
from pathlib import Path
import pytest

from experiments.software_comparison_v3.cells import BasicCell,ToolkitCell,StudyHarnessError
from experiments.software_comparison_v3.rubric import rubric
from experiments.software_comparison_v3.reserved import TASK_FILES
from specorganon.role_jobs import canonical,digest,_json
from specorganon.workflow import PHASES


class FixtureTransport:
    def __init__(self,fail=False):self.calls={};self.tests={};self.fail=fail
    def call(self,job_id,role,request):
        if job_id in self.calls:return self.calls[job_id]
        stage=request['documents']['stage.txt'];manifest={'schema':1,'steps':[]};files={}
        if role=='review':
            r=rubric(request['documents']['method.txt'])
            audit={'schema':1,'binding':json.loads(request['documents']['audit-binding.json']),
                   'reason':'Synthetic schema fixture only; no substantive acceptance.','tests_executed':False}
            for group in 'DGH':
                audit[group]={i:{'status':'fail','reason':'Synthetic fixtures do not prove quality.','evidence':[]} for i in r[group]}
            result={'schema':1,'verdict':'reject','reason':'Synthetic fixture only','findings':[], 'tests_executed':False,'audit':audit}
        else:
            if stage in ('spec','design','tasks','verification'):
                files={('VERIFY' if stage=='verification' else stage.upper())+'.md':'Synthetic prerequisites, no substantive proof.'}
            elif stage in ('program','repair'):
                files={'fractionmix.py':"print('synthetic fixture '+"+repr(stage)+")\n",'README.md':'Synthetic guard fixture only. '*12}
                if stage=='repair':files['test_fixture.py']='assert True\n'
            elif stage=='tests':files={'test_fixture.py':'pass\n'}
            if 'artifact-format-guidance.txt' in request['documents']:
                items=json.loads(request['documents']['state.json'])['items'];last=list(items)[-1:] if items else []
                def step(identity,kind,refs,data=None):return {'op':'put','id':identity,'kind':kind,'text':'Synthetic typed guard fixture.','refs':refs,'data':data or {}}
                if stage=='program':manifest['steps']=[step('implementation-fixture','implementation',last)]
                elif stage in ('tests','repair'):
                    argv=['/opt/specorganon/venv/bin/python','/input/delivery/test_fixture.py']
                    manifest['steps']=[step('test-fixture','test',['requirement-fixture'],{'argv':argv}),step('implementation-fixture','implementation',['requirement-fixture','test-fixture'])]
                else:
                    kinds={'frame':'problem','critique':'concept','study':'protocol','observe':'evidence','explain':'synthesis','compare':'option','specify':'requirement','validate':'assessment'}
                    manifest['steps']=[step(kinds[stage]+'-fixture',kinds[stage],last)];files={}
            elif stage in ('tests','repair'):
                manifest['test_argv']=['/opt/specorganon/venv/bin/python','/input/delivery/test_fixture.py']
            result={'schema':1,'manifest':manifest,'files':files,'reason':'Synthetic fixture only'}
        packet={'result':result,'request_sha256':digest(canonical(request)),'provenance':'synthetic','actor':'agent:synthetic-'+role,'receipt_ref':'synthetic:'+job_id}
        self.calls[job_id]=packet;return packet
    def measure(self,job_id,argv,files):
        self.tests.setdefault(job_id,{'passed':not(self.fail and not self.tests),'test_job_ref':'synthetic:'+job_id,'delivery_tree_sha256':digest(canonical(files))})
        return self.tests[job_id]
    def verify_test(self,data,files,**kwargs):
        assert self.tests[data['test_job_ref'].split(':')[1]]['delivery_tree_sha256']==digest(canonical(files))


def cell(root,method='N',fail=False):
    t=FixtureTransport(fail);c=BasicCell(root,t,method=method,task='fractionmix',contract='Synthetic mechanics only',sdd_guide='Synthetic SDD guide',protocol_sha256='a'*64,fixture_mode=True,mandate='Synthetic mandate fixture only',author_format='manifest-v1')
    return c,t


def finish(c):
    for _ in range(20):
        result=c.step()
        assert result['action']!='failed',result
        if result.get('complete'):return _json(c.root/'progress.json')
    pytest.fail('fixture did not terminate')


@pytest.mark.parametrize('method',['N','S','A'])
def test_routes_use_bound_audit_and_A_retains_typed_candidates_never_acceptance(tmp_path,method):
    c,t=cell(tmp_path/'cell',method);state=finish(c)
    assert len(t.tests)==1 and len(t.calls)=={'N':3,'S':7,'A':11}[method]
    assert state['final_review']['verdict']=='reject' and _json(c.root/'assessment.json')['G']['g1']['status']=='fail'
    assert c.step()['classification']=='synthetic' and not (c.root/'case').exists()
    if method=='S':assert list(state['process'])==['DESIGN.md','SPEC.md','TASKS.md','VERIFY.md']
    if method=='A':
        items=state['candidate_items'];assert len(items)==10 and items['implementation-fixture']['version']==2
        assert items['implementation-fixture']['deps']['test-fixture']==1
        assert all(i['status']=='candidate' and 'accepted' not in i for i in items.values())
        assert {i['kind'] for i in items.values()} >= {'problem','concept','protocol','evidence','synthesis','option','requirement','implementation','test','assessment'}
        state['candidate_items']['problem-fixture']['text']='tampered'
        with pytest.raises(StudyHarnessError,match='snapshot'):c.validate_closed(state)


@pytest.mark.parametrize('method',['N','S','A'])
def test_failed_first_measurement_keeps_history_and_only_one_repair(tmp_path,method):
    c,t=cell(tmp_path/'cell',method,fail=True);state=finish(c)
    assert [m['passed'] for m in state['measurements']]==[False,True]
    assert sum(h['stage']=='repair' for h in state['history'])==1 and len(t.tests)==2
    if method=='A':assert state['candidate_items']['implementation-fixture']['version']==3 and state['candidate_items']['test-fixture']['version']==2


def test_crash_after_closed_packet_recovers_same_job(tmp_path,monkeypatch):
    from experiments.software_comparison_v3 import cells
    c,t=cell(tmp_path/'cell');original=cells._write
    def crash(path,value):
        if path.name=='progress.json':raise OSError('synthetic checkpoint crash')
        return original(path,value)
    monkeypatch.setattr(cells,'_write',crash)
    with pytest.raises(OSError):c.step()
    assert len(t.calls)==1 and _json(c.root/'progress.json')['index']==0
    monkeypatch.setattr(cells,'_write',original);assert c.step()['action']=='program' and len(t.calls)==1


def test_native_route_rejects_synthetic_packet_before_commit(tmp_path):
    t=FixtureTransport();c=BasicCell(tmp_path/'cell',t,method='N',task='fractionmix',contract='Fixture',sdd_guide='',protocol_sha256='a'*64)
    assert c.step()['action']=='failed' and _json(c.root/'progress.json')['files']=={}


def test_A_cannot_forge_measurement_or_approval_steps(tmp_path):
    c,t=cell(tmp_path/'cell','A');original=t.call
    def forged(job_id,role,request):
        packet=original(job_id,role,request);packet['result']['manifest']['steps'][0]['data']['passed']=True;return packet
    t.call=forged
    assert c.step()['action']=='failed' and _json(c.root/'progress.json')['candidate_items']=={}
    c,t=cell(tmp_path/'other','A');original=t.call
    def approval(job_id,role,request):
        packet=original(job_id,role,request);packet['result']['manifest']['steps']=[{'op':'advance','phase':'frame'}];return packet
    t.call=approval;assert c.step()['action']=='failed' and _json(c.root/'progress.json')['candidate_items']=={}


@pytest.mark.parametrize('method',['N','S'])
def test_repair_cannot_discard_test_files(tmp_path,method):
    c,t=cell(tmp_path/'cell',method,fail=True);original=t.call
    def omitted(job_id,role,request):
        packet=original(job_id,role,request)
        if request['documents']['stage.txt']=='repair':packet['result']['files'].pop('test_fixture.py')
        return packet
    t.call=omitted
    for _ in range(10):
        result=c.step()
        if result['action']=='failed':break
    assert result['action']=='failed' and len(t.tests)==1
    assert 'test_fixture.py' in _json(c.root/'progress.json')['files']


def test_uncertain_native_handle_propagates_without_terminal_or_new_job(tmp_path):
    from specorganon.role_jobs import UncertainJob
    c,t=cell(tmp_path/'cell');original=t.call
    def uncertain(job_id,role,request):
        original(job_id,role,request);raise UncertainJob('synthetic unresolved same handle')
    t.call=uncertain
    for _ in range(2):
        with pytest.raises(UncertainJob):c.step()
    assert len(t.calls)==1 and _json(c.root/'progress.json')['index']==0
    assert not (c.root/'terminal-failure.json').exists()


def test_final_context_keeps_process_measurements_once(tmp_path):
    c,t=cell(tmp_path/'cell','S');state=finish(c)
    last=state['history'][-1];req=_json(c.root/(last['job_id']+'-request.json'));docs=req['documents']
    assert 'process-documents.json' not in docs and 'public-measurements.json' not in docs
    history=json.loads(docs['audit-history.json'])
    assert history['process']==state['process'] and history['measurements']==state['measurements']


@pytest.mark.parametrize('mutation',[{'schema':True},{'passed':True},{'receipt':{'exit_code':0}}])
def test_basic_route_cannot_accept_boolean_schema_or_fabricated_test_results(tmp_path,mutation):
    c,t=cell(tmp_path/'cell');original=t.call
    def forged(job_id,role,request):
        packet=original(job_id,role,request);packet['result']['manifest'].update(mutation);return packet
    t.call=forged;assert c.step()['action']=='failed'
    assert _json(c.root/'progress.json')['files']=={} and len(t.tests)==0
