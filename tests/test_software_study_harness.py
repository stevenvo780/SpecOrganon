"""Synthetic admission/recovery fixtures; never study solutions/native reviews."""
from pathlib import Path
import pytest

from scripts.software_study_harness import BasicCell, StudyHarnessError, registration
from specorganon.role_jobs import canonical, digest, _json, _write


class FixtureTransport:
    def __init__(self, *, fail_first=False):
        self.calls={}; self.tests={}; self.fail_first=fail_first

    def call(self, job_id, role, request):
        if job_id in self.calls:
            packet=self.calls[job_id]
            assert packet['request_sha256']==digest(canonical(request))
            return packet
        stage=request['documents']['stage.txt']
        manifest={'schema':1,'steps':[]}
        if role=='review':
            response={'schema':1,'verdict':'accept','reason':'Synthetic control only',
                      'findings':[],'tests_executed':False}
        else:
            if stage=='spec': files={'SPEC.md':'Synthetic identified fixture requirements.'}
            elif stage=='design-tasks': files={'DESIGN.md':'Synthetic fixture alternatives.','TASKS.md':'Synthetic finite tasks.'}
            elif stage in {'program','repair'}:
                files={'routeplan.py':"print('synthetic fixture '+"+repr(stage)+")\n",'README.md':'Synthetic guard fixture only. '*12}
                if stage=='repair': files['test_fixture.py']='pass\n'
            elif stage=='tests': files={'test_fixture.py':'pass\n'}
            else: files={stage+'.md':'Synthetic unaccepted '+stage+' draft, no actual approval.'}
            if stage in {'tests','repair'}:
                manifest['test_argv']=['/opt/specorganon/venv/bin/python','/input/delivery/test_fixture.py']
            response={'schema':1,'manifest':manifest,'files':files,'reason':'Synthetic control only'}
        packet={'result':response,'request_sha256':digest(canonical(request)),
                'provenance':'synthetic','actor':'agent:synthetic-'+role,'receipt_ref':'synthetic:'+job_id}
        self.calls[job_id]=packet
        return packet

    def measure(self, job_id, argv, files):
        if job_id not in self.tests:
            self.tests[job_id]={'passed':not self.fail_first or bool(self.tests),
                'test_job_ref':'synthetic:'+job_id,'exit_code':1 if self.fail_first and not self.tests else 0,
                'delivery_tree_sha256':digest(canonical(files))}
        return self.tests[job_id]

    def verify_test(self, data, files, **kwargs):
        assert self.tests[data['test_job_ref'].split(':')[1]]['delivery_tree_sha256']==digest(canonical(files))


def cell(tmp_path, method='N', **kwargs):
    transport=FixtureTransport(**kwargs)
    c=BasicCell(tmp_path/'cell',transport,method=method,task='routeplan',
        contract='Synthetic mechanics contract only',sdd_guide='Synthetic SDD guide only',
        protocol_sha256='a'*64,fixture_mode=True)
    return c,transport


@pytest.mark.parametrize('method',['N','S','A'])
def test_routes_keep_process_separate_from_code_and_do_not_invent_engine_acceptance(tmp_path,method):
    c,t=cell(tmp_path,method)
    for _ in range(16):
        if c.step().get('complete'): break
    state=_json(c.root/'progress.json')
    assert state['complete']
    assert len(t.tests)==1
    assert len(t.calls)=={'N':3,'S':5,'A':11}[method]
    assert set(state['files'])=={'routeplan.py','README.md','test_fixture.py'}
    assert not (c.root/'case').exists(), 'ablation must not fabricate engine acceptance'
    assert c.step()['classification']=='synthetic'
    if method=='S':
        assert state['history'][0]['stage']=='spec' and state['history'][1]['stage']=='design-tasks'
        assert set(state['process'])=={'SPEC.md','DESIGN.md','TASKS.md'}
    if method=='A':
        assert len(state['process'])==8  # seven prebuild phase drafts plus validation
        assert all('unaccepted' in v for v in state['process'].values())


def test_actual_failed_measurement_permits_one_repair_without_rewriting_early_process(tmp_path):
    c,t=cell(tmp_path,'S',fail_first=True)
    for _ in range(15):
        if c.step().get('complete'): break
    state=_json(c.root/'progress.json')
    assert [m['passed'] for m in state['measurements']]==[False,True]
    assert len(t.tests)==2 and [h['stage'] for h in state['history']].count('repair')==1
    assert state['process']['SPEC.md']=='Synthetic identified fixture requirements.'


def test_closed_packet_after_checkpoint_failure_replays_same_job(tmp_path,monkeypatch):
    import scripts.software_study_harness as harness
    c,t=cell(tmp_path)
    original=harness._write
    def fail(path,value):
        if path.name=='progress.json': raise OSError('synthetic checkpoint failure')
        return original(path,value)
    monkeypatch.setattr(harness,'_write',fail)
    with pytest.raises(OSError): c.step()
    assert len(t.calls)==1 and _json(c.root/'progress.json')['index']==0
    monkeypatch.setattr(harness,'_write',original)
    assert c.step()['action']=='program'
    assert len(t.calls)==1 and _json(c.root/'progress.json')['index']==1


def test_tests_stage_cannot_replace_sealed_program(tmp_path):
    c,t=cell(tmp_path); c.step()
    original=t.call
    def malicious(job_id,role,request):
        packet=original(job_id,role,request)
        packet['result']['files']['routeplan.py']='changed\n'
        return packet
    t.call=malicious
    before=(c.root/'progress.json').read_bytes()
    result=c.step()
    assert result['action']=='failed' and 'sealed' in result['failure']['reason']
    state=_json(c.root/'progress.json')
    assert state['files']==__import__('json').loads(before)['files']
    jobs=len(t.calls)
    assert c.step()['action']=='failed' and len(t.calls)==jobs


def test_draft_registration_refuses_before_any_transport_or_provider(tmp_path):
    path=tmp_path/'registration.json'
    _write(path,{'schema':1,'status':'draft_not_preregistered'})
    with pytest.raises(StudyHarnessError,match='preregistration'): registration(path,tmp_path)


def test_exhausted_native_budget_is_terminal_without_invented_grade(tmp_path):
    from scripts.study_cell_budget import CellBudget
    c,t=cell(tmp_path)
    c.transport=CellBudget(tmp_path/'budget',transport=t,protocol_sha256='a'*64,
        max_calls=1,max_total_input_bytes=20000,max_elapsed_seconds=6000)
    c.step()
    result=c.step()
    assert result['action']=='failed'
    assert result['failure']['error_type']=='StudyBudgetError'
    assert result['failure']['grade'] is None and not result['failure']['automatic_retry']
    assert c.step()['action']=='failed' and len(t.calls)==1


def test_verbose_public_stream_closes_cell_with_raw_evidence_preserved(tmp_path):
    c,t=cell(tmp_path)
    c.step(); c.step(); c.step()
    state=_json(c.root/'progress.json')
    folder=tmp_path/'raw'; folder.mkdir()
    (folder/'stdout.bin').write_bytes(b'X'*5000); (folder/'stderr.bin').write_bytes(b'')
    item=state['measurements'][0]
    item['test_job_ref']=str(folder/'receipt.json')
    item['stdout_sha256']=digest(b'X'*5000);item['stderr_sha256']=digest(b'')
    _write(c.root/'progress.json',state)
    c.fixture=False
    result=c.step()
    assert result['action']=='failed' and 'stream input ceiling' in result['failure']['reason']
    assert (folder/'stdout.bin').read_bytes()==b'X'*5000
    assert len(t.calls)==2 and c.step()['action']=='failed'
