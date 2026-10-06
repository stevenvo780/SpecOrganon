"""Synthetic resource/stage guards; no software delivery or native acceptance."""
import copy
import json
from pathlib import Path
import pytest
from specorganon import engine
from specorganon.role_jobs import _json, _write, canonical, digest
from specorganon.software_controller import ControllerError, encoded_contribution
from specorganon.workflow import KIND_TO_PHASE
from test_software_controller import SyntheticTransport, controller, frame_response

README = ('# Synthetic program\nRun Python on count.py. Input: none. Output: 10. '
          'Errors and scope: synthetic mechanism fixture only. No field evidence, '
          'dependencies, network or native model review. Tests check process output.\n')


def put(id, kind, refs, data=None, text='Synthetic resource guard fixture'):
    return {'op': 'put', 'id': id, 'kind': kind, 'refs': refs, 'data': data or {}, 'text': text}


def response(steps, files):
    return {'schema': 1, 'manifest': {'schema': 1, 'steps': steps}, 'files': files,
            'reason': 'Synthetic mechanics only; not native authorship'}


def build_fixture(tmp_path):
    ctrl = controller(tmp_path, SyntheticTransport(frame_response()))
    steps = json.loads((Path(__file__).parents[1] / 'workflows/synthetic_full.json').read_text())['steps']
    for s in steps:
        if s.get('kind') == 'implementation': break
        if s['op'] == 'put':
            state = engine.get_state(ctrl.case)
            engine.put_item(ctrl.case, s['id'], s['kind'], s['text'], s['refs'], s['data'],
                            'author:synthetic-prerequisite', expected_version=0,
                            expected_deps={r: state['items'][r]['version'] for r in s['refs']})
            if s['kind'] in {'norm', 'decision'}:
                engine.approve(ctrl.case, s['id'], 'Invented fixture mandate', 'human:owner')
        else:
            engine.review_phase(ctrl.case, s['phase'], 'accept', 'Invented prerequisite fixture review', 'reviewer:synthetic-prerequisite')
            engine.advance(ctrl.case, s['phase'], 'agent:synthetic-fixture')
    return ctrl


def program(ctrl):
    ctrl.transport.result = response([put('impl1', 'implementation', ['req1'])],
                                     {'count.py': 'print(10)\n', 'README.md': README})
    return ctrl.step()


def stage_tests(ctrl):
    ctrl.transport.result = response([put('impl1', 'implementation', ['req1']),
        put('t1', 'test', ['impl1', 'crit1'], {'argv': ['/usr/bin/python3', '-B', '/input/delivery/test_count.py']})],
        {'test_count.py': 'import count\n'})
    return ctrl.step()


class Executor:
    def __init__(self, root, exits=(0,), stdout=b'', stderr=b''):
        self.root = root; self.exits = exits; self.calls = []; self.stdout = stdout; self.stderr = stderr
    def measure(self, job_id, argv, files):
        self.calls.append(job_id); folder = self.root / ('test-' + str(len(self.calls))); folder.mkdir()
        raw = {'stdout': self.stdout, 'stderr': self.stderr}
        for name, data in raw.items(): (folder / (name + '.bin')).write_bytes(data)
        _write(folder / 'receipt.json', {'synthetic': True, 'job_id': job_id})
        return {'subject_argv': argv, 'delivery_tree_sha256': digest(canonical(files)),
                'exit_code': self.exits[min(len(self.calls)-1, len(self.exits)-1)], 'timed_out': False,
                'truncated_streams': [], 'test_job_ref': str(folder / 'receipt.json'),
                'stdout_sha256': digest(raw['stdout']), 'stderr_sha256': digest(raw['stderr']), 'provenance': 'synthetic'}
    def verify_test(self, *args, **kwargs): return True


def test_program_then_tests_preserves_seal_and_defers_measurement(tmp_path):
    ctrl = build_fixture(tmp_path); ctrl.executor = Executor(tmp_path)
    assert program(ctrl)['build_stage'] == 'program'
    assert len(ctrl.transport.calls) == 1 and ctrl.executor.calls == []
    seal = (ctrl.root / 'build-program.json').read_bytes()
    assert stage_tests(ctrl)['build_stage'] == 'tests'
    assert (ctrl.root / 'build-program.json').read_bytes() == seal
    assert ctrl._files()['count.py'] == 'print(10)\n'
    assert ctrl.step()['passed'] is True
    assert len(ctrl.executor.calls) == 1
    assert not engine.get_state(ctrl.case)['phases']['build']['accepted']


@pytest.mark.parametrize('mutation', ['program', 'readme', 'new_impl', 'new_other_file'])
def test_stage_two_admission_rejects_changed_program_or_identity_before_any_write(tmp_path, mutation):
    ctrl = build_fixture(tmp_path); program(ctrl)
    original = ctrl.step
    # Prepare a real stage-two response without dispatching it first.
    ctrl.transport.result = response([put('impl1', 'implementation', ['req1']),
        put('t1', 'test', ['impl1', 'crit1'], {'argv': ['/usr/bin/python3', '/input/delivery/test_count.py']})],
        {'test_count.py': 'import count\n'})
    if mutation == 'program': ctrl.transport.result['files']['count.py'] = 'print(11)\n'
    if mutation == 'readme': ctrl.transport.result['files']['README.md'] = README + 'changed'
    if mutation == 'new_impl': ctrl.transport.result['manifest']['steps'][0]['id'] = 'impl2'
    if mutation == 'new_other_file': ctrl.transport.result['files']['extra.py'] = 'pass\n'
    before = (ctrl.case / 'organon.json').read_bytes(); files = ctrl._files()
    with pytest.raises(ControllerError): original()
    assert (ctrl.case / 'organon.json').read_bytes() == before and ctrl._files() == files
    assert _json(ctrl.root / 'progress.json')['pending']['status'] == 'closed'


@pytest.mark.parametrize('oversize', ['count', 'phase', 'files', 'late_conflict'])
def test_whole_author_packet_is_admitted_before_first_real_file_or_put(tmp_path, oversize):
    ctrl = controller(tmp_path, SyntheticTransport(frame_response()))
    if oversize == 'count':
        ctrl.transport.result['manifest']['steps'] += [put('p'+str(i), 'problem', []) for i in range(2,6)]
    if oversize == 'phase': ctrl.transport.result['manifest']['steps'][-1]['text'] = '\\"' * 4000
    if oversize == 'files':
        ctrl = build_fixture(tmp_path / 'build'); ctrl.transport.result = response([put('impl1','implementation',['req1'])],
            {'count.py': 'print(10)\n' + '#' * 21000, 'README.md': README})
    if oversize == 'late_conflict':
        ctrl.transport.result['manifest']['steps'][-1]['refs'] = ['b1']
    before = (ctrl.case / 'organon.json').read_bytes()
    with pytest.raises(ValueError): ctrl.step()
    assert (ctrl.case / 'organon.json').read_bytes() == before and ctrl._files() == {}


def test_cannot_measure_unsealed_injected_test(tmp_path):
    ctrl = build_fixture(tmp_path); program(ctrl); ctrl.executor = Executor(tmp_path)
    state = engine.get_state(ctrl.case)
    engine.put_item(ctrl.case, 't1', 'test', 'Injected draft must not execute', ['impl1','crit1'],
                    {'argv':['/usr/bin/python3','-c','pass'], 'command':'/usr/bin/python3 -c pass'}, 'agent:synthetic-injection',
                    expected_version=0, expected_deps={r:state['items'][r]['version'] for r in ['impl1','crit1']})
    with pytest.raises(ControllerError, match='both sealed'): ctrl.step()
    assert ctrl.executor.calls == []


def repair(ctrl, files=None, argv=None, test_id='t1'):
    ctrl.transport.result = response([put('impl1','implementation',['req1']),
        put(test_id,'test',['impl1','crit1'], {'argv': argv or ['/usr/bin/python3','-B','/input/delivery/test_count.py']})],
        files or {'test_count.py':'import count\nassert True\n'})
    return ctrl.step()


@pytest.mark.parametrize('mutation', ['code', 'docs_only', 'test_id'])
def test_one_conditional_repair_and_no_test_identity_quota_reset(tmp_path, mutation):
    ctrl = build_fixture(tmp_path); ctrl.executor = Executor(tmp_path, (1,0)); program(ctrl); stage_tests(ctrl)
    assert ctrl.step()['passed'] is False
    before = (ctrl.case / 'organon.json').read_bytes()
    if mutation == 'docs_only':
        with pytest.raises(ControllerError, match='executable'): repair(ctrl, {'README.md':README+'cosmetic'})
    elif mutation == 'test_id':
        with pytest.raises(ControllerError, match='same test ID'): repair(ctrl, test_id='t2')
    else:
        assert repair(ctrl)['build_stage'] == 'repair'
        assert ctrl.step()['passed'] is True
        current=engine.get_state(ctrl.case)
        current_tests=[item for item in current['items'].values() if item['kind']=='test']
        assert len(current_tests)==1 and current_tests[0]['id']=='t1'
        assert current_tests[0]['data']['delivery_tree_sha256']==digest(canonical(ctrl._files()))
        measured=[entry for entry in _json(ctrl.root/'progress.json')['history'] if entry['action']=='test']
        assert [entry['passed'] for entry in measured]==[False,True]
        assert current_tests[0]['data']['test_job_ref'].endswith('test-2/receipt.json')
        ctrl.transport.result = {'schema':1, 'verdict':'reject', 'reason':'Synthetic semantic rejection', 'findings':[]}
        assert ctrl.step()['verdict'] == 'reject'
        with pytest.raises(ControllerError, match='budget'): ctrl.step()
        assert len(ctrl.executor.calls) == 2
        return
    assert len(ctrl.executor.calls) == 1 and (ctrl.case / 'organon.json').read_bytes() == before


def test_passed_first_measurement_cannot_repeat_after_documentation_change(tmp_path):
    ctrl = build_fixture(tmp_path); ctrl.executor = Executor(tmp_path); program(ctrl); stage_tests(ctrl); ctrl.step()
    # A guarded docs-only implementation update plus refreshed test references
    # must still fail before the executor, even though the prior test passed.
    state = engine.get_state(ctrl.case); item = state['items']['impl1']; files = ctrl._files(); files['README.md'] += 'cosmetic'
    ctrl._write_files({'source_files':ctrl._files()}, {'README.md':files['README.md']})
    engine.put_item(ctrl.case,'impl1','implementation',item['text'],list(item['deps']),
        {**item['data'],'delivery_tree_sha256':digest(canonical(files))}, 'agent:synthetic',
        expected_version=item['version'],expected_deps=item['deps'])
    state=engine.get_state(ctrl.case); item=state['items']['t1']; data={'argv':item['data']['argv'], 'command':item['data']['command']}
    engine.put_item(ctrl.case,'t1','test',item['text'],list(item['deps']), data,'agent:synthetic',
        expected_version=item['version'],expected_deps={r:state['items'][r]['version'] for r in item['deps']})
    with pytest.raises(ControllerError,match='changed executable'):ctrl.step()
    assert len(ctrl.executor.calls)==1


def test_oversized_test_logs_retained_without_passed_or_partial_ledger_write(tmp_path):
    ctrl=build_fixture(tmp_path);ctrl.executor=Executor(tmp_path,stdout=b'\\'*2100);program(ctrl);stage_tests(ctrl)
    before=(ctrl.case/'organon.json').read_bytes()
    with pytest.raises(ControllerError,match='stream resource'):ctrl.step()
    assert (ctrl.case/'organon.json').read_bytes()==before
    pending=_json(ctrl.root/'progress.json')['pending']; assert pending['status']=='closed'
    assert Path(pending['packet']['test_job_ref']).with_name('stdout.bin').read_bytes()==b'\\'*2100
    with pytest.raises(ControllerError,match='stream resource'):ctrl.step()
    assert len(ctrl.executor.calls)==1


@pytest.mark.parametrize('public_contract',[None,'routeplan','treemap'])
def test_maximum_full_validate_context_keeps_all_items_files_and_test_streams(tmp_path,public_contract):
    ctrl=build_fixture(tmp_path);ctrl.executor=Executor(tmp_path,stdout=b'X'*3994,stderr=b'Y'*3994);program(ctrl);stage_tests(ctrl);ctrl.step()
    if public_contract:
        repository=Path(__file__).parents[1]
        ctrl.contract=(repository/'experiments/software_comparison_v1/public'/ (public_contract+'.md')).read_text()
        ctrl.mandate=(repository/'experiments/software_comparison_v1/public/existing-mandate.md').read_text()
    state=engine.get_state(ctrl.case)
    state['phases']['build']['accepted']=True
    # Model a final current snapshot at each declared phase cap. All complete
    # item maps remain in the request, including issues/deps and test receipt.
    for phase in state['phases']:
        group={k:v for k,v in state['items'].items() if KIND_TO_PHASE[v['kind']]==phase}
        if not group:
            item=copy.deepcopy(state['items']['p1']);item.update(id='res1',kind='result')
            state['items']['res1']=item;group={'res1':item}
        template=next(iter(group.values()))
        for index in range(len(group),6):
            item=copy.deepcopy(template);item['id']=phase+str(index);item['data']={};item['text']='Synthetic cap'
            # No cloned measured job refs: a receipt is kept once, in t1.
            item['test_execution_provenance']=None
            group[item['id']]=item;state['items'][item['id']]=item
        target=next(iter(group.values()))
        while encoded_contribution(group)>6000: target['text']=target['text'][:-1]
        while encoded_contribution(group)<6000:
            target['text']+='x'
        target['text']=target['text'][:-1]
        assert 5990<=encoded_contribution(group)<=6000
    files=ctrl._files();files['README.md']+='x'*17000
    while encoded_contribution(files)<20000:files['README.md']+='x'
    files['README.md']=files['README.md'][:-1]
    ctrl._write_files({'source_files':ctrl._files()},{'README.md':files['README.md']})
    progress=_json(ctrl.root/'progress.json')
    # History is complete for this fixture. Arbitrarily large native reasons
    # remain subject to the independent final 110000-byte admission guard.
    request=ctrl._request(state,'review',progress)
    assert len(canonical(request))<=110000
    author_request=ctrl._request(state,'author',progress)
    assert len(canonical(author_request))<=110000
    assert author_request['documents']['state.json']==canonical(state).decode()
    assert request['documents']['state.json']==canonical(state).decode()
    assert json.loads(request['documents']['delivery-files.json'])==files
    streams=json.loads(request['documents']['measured-test-records.json'])['t1']['streams']
    assert streams['stdout']=={'text':'X'*3994,'complete':True}
    assert streams['stderr']=={'text':'Y'*3994,'complete':True}
    from scripts.controller_native_role import render_prompt
    rendered_bytes=len(render_prompt(canonical(request))[1].encode('utf-8'))
    print(json.dumps({'classification':'synthetic maximum item/files/log contribution fixture', 'public_contract':public_contract,'request_bytes':len(canonical(request)), 'rendered_bytes':rendered_bytes,'request_limit':110000,'phase_count':9,'phase_item_limit':6,'phase_encoded_limit':6000,'files_encoded_bytes':encoded_contribution(files),'stream_encoded_bytes':encoded_contribution('X'*3994),'state_preserved':True,'C1_satisfied':False}))
    if public_contract:
        from scripts.software_study_harness import ToolkitCell
        final=object.__new__(ToolkitCell);final.contract=ctrl.contract
        final.rubric=(Path(__file__).parents[1]/'experiments/software_comparison_v1/public/assessment-rubric.md').read_text()
        records=json.loads(request['documents']['measured-test-records.json'])
        current=records['t1']
        # Final review receives both attempts exactly once. Historical streams
        # remain complete but are not claimed as tests of the current code.
        records={'t1':{'current_test_job_ref':state['items']['t1']['data']['test_job_ref'],
                       'delivery_tree_sha256':digest(canonical(files))},
                 'all_public_attempts':{str(i):{'measurement':{'passed':bool(i),
                     'delivery_tree_sha256':digest(canonical(files)) if i else 'a'*64},
                     'applies_to_current_delivery':bool(i), **current} for i in (0,1)}}
        final_bytes=len(render_prompt(canonical(final.final_request(state,files,records)))[1].encode())
        assert final_bytes<=128000
        snapshots=[];phases=list(state['phases']);original_files=ctrl._files
        try:
            for index,phase in enumerate(phases):
                prefix=copy.deepcopy(state)
                available=set(phases[:index+1])
                if index>=phases.index('study'): available.add('observe') # early documentary evidence
                prefix['items']={k:v for k,v in prefix['items'].items() if KIND_TO_PHASE[v['kind']] in available}
                for n,p in enumerate(phases): prefix['phases'][p]['accepted']=n<index
                ctrl._files=lambda:files if phase in {'build','validate'} else {}
                role_request=ctrl._request(prefix,'review',progress)
                size=len(render_prompt(canonical(role_request))[1].encode())
                snapshots.append({'phase':phase,'rendered_bytes':size,
                                  'nominal_calls':3 if phase in {'critique','specify','build'} else 2,
                                  'maximum_stage_calls':5 if phase=='build' else 4})
        finally: ctrl._files=original_files
        nominal=sum(row['rendered_bytes']*row['nominal_calls'] for row in snapshots)+final_bytes
        maximum=sum(row['rendered_bytes']*row['maximum_stage_calls'] for row in snapshots)+final_bytes
        print(json.dumps({'classification':'synthetic phase-prefix cumulative load, not bound on arbitrary native reasons/metadata',
                          'public_contract':public_contract,'phase_snapshots':snapshots,'common_final_rendered_bytes':final_bytes,
                          'nominal_22_role_inputs_bytes':nominal,'maximum_stage_38_role_inputs_bytes':maximum,
                          'prior_1MiB_fits_this_fixture':maximum<=1_048_576,'proposed_2MiB_fits_this_fixture':maximum<=2_097_152,
                          'proposed_3MiB_fits_this_fixture':maximum<=3_145_728,
                          'native_model_calls':0,'study_cells_generated':0,'C1_satisfied':False}))
        assert maximum<=3_145_728


@pytest.mark.parametrize('stage,operation',[('program','rename'),('program','put'),('tests','put'),('tests','seal')])
def test_sigkill_with_sealed_stage_replays_same_closed_packet_without_new_author(tmp_path,stage,operation):
    import os,signal,subprocess,sys
    ctrl=build_fixture(tmp_path)
    if stage=='tests':program(ctrl)
    if stage=='program':
        packet=response([put('impl1','implementation',['req1'])], {'count.py':'print(10)\n','README.md':README})
    else:
        packet=response([put('impl1','implementation',['req1']),put('t1','test',['impl1','crit1'],
            {'argv':['/usr/bin/python3','-B','/input/delivery/test_count.py']})],{'test_count.py':'import count\n'})
    counter=tmp_path/'calls.txt'
    code=f'''import os,signal,sys
from pathlib import Path
sys.path.insert(0,{str(Path(__file__).parent)!r})
from test_software_controller import SyntheticTransport
from specorganon.software_controller import Controller
from specorganon import engine
transport=SyntheticTransport({packet!r})
original_call=transport.call
def call(*args):
 Path({str(counter)!r}).write_text('1')
 return original_call(*args)
transport.call=call
c=Controller(Path({str(ctrl.case)!r}),Path({str(ctrl.root)!r}),transport,contract={ctrl.contract!r},mandate={ctrl.mandate!r},fixture_mode=True)
'''
    if operation=='rename':
        code+='''original=os.replace
def interrupted(source,target,*args,**kwargs):
 if Path(target).name=='count.py':os.kill(os.getpid(),signal.SIGKILL)
 return original(source,target,*args,**kwargs)
os.replace=interrupted
'''
    elif operation=='put':
        code+=f'''original=engine.put_item
def interrupted(*args,**kwargs):
 result=original(*args,**kwargs)
 if Path(args[0])==Path({str(ctrl.case)!r}):os.kill(os.getpid(),signal.SIGKILL)
 return result
engine.put_item=interrupted
'''
    else:
        code+='''original=c._seal
def interrupted(*args):
 original(*args)
 os.kill(os.getpid(),signal.SIGKILL)
c._seal=interrupted
'''
    code+='c.step()\n'
    child=subprocess.Popen([sys.executable,'-c',code],stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    try:
        _,stderr=child.communicate(timeout=20);assert child.returncode==-signal.SIGKILL,stderr.decode()
        assert _json(ctrl.root/'progress.json')['pending']['status']=='applying'
        calls=len(ctrl.transport.calls)
        assert ctrl.step()['build_stage']==stage
        assert len(ctrl.transport.calls)==calls and counter.read_text()=='1'
        assert ctrl._checkpoint(stage if stage=='tests' else 'program')
        state=engine.get_state(ctrl.case)
        assert state['items']['impl1']['version']==(1 if stage=='program' else 2)
        assert ctrl._files()['count.py']=='print(10)\n'
    finally:
        if child.poll() is None:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=5)
