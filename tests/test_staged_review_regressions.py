"""Negative reproductions for static R1/R2/R4/R5/R6/R7; no provider calls."""
import copy

import pytest

import specorganon.neutral_controller as module
from specorganon.docker_roles import DockerRoleError
from specorganon.neutral_controller import NeutralController,NeutralControllerError
from specorganon.role_jobs import canonical,digest,_json,_write
from test_closed_native_role import closed
from test_native_source_custody import transport
from test_neutral_controller import controller,ARGV,POLICY


def test_R1_mounted_Gemini_executable_replacement_refused_before_preparation(tmp_path,monkeypatch):
    t,_,options=transport(tmp_path,monkeypatch)
    options['gemini_executable'].write_text('replacement binary fixture')
    with pytest.raises(DockerRoleError,match='Gemini executable changed'):t._prepare('new','review',{'fixture':True})
    assert not (t.root/'jobs/new').exists()


@pytest.mark.parametrize('field',['create_argv','codex_reasoning_effort','image_id','name','label','provider','model'])
def test_R2_launch_pin_drift_rejected_even_with_rebound_creation_intent(closed,field):
    t,folder,request,packet,_=closed;plan=_json(folder/'launch.json')
    if field=='create_argv':plan[field]=['create','--privileged']
    else:plan[field]='changed'
    _write(folder/'launch.json',plan);_write(folder/'create-attempt.json',t._creation_attempt(plan))
    with pytest.raises(DockerRoleError):t.verify_role(packet,'author-01','author',request)


def rebind(root,job,envelope=None,receipt=None):
    path=root/job;envelope=envelope or _json(path/'request.json');receipt=receipt or _json(path/'receipt.json')
    _write(path/'request.json',envelope);sha=digest(canonical(envelope));receipt['request_sha256']=sha;receipt['cwd']=envelope['cwd']
    _write(path/'receipt.json',receipt)
    started=_json(path/'started.json');started['request_sha256']=sha;_write(path/'started.json',started)
    close=_json(root/('.complete-'+job+'.json'));close.update(request_sha256=sha,
        receipt_sha256=digest(canonical(receipt)),started_sha256=digest((path/'started.json').read_bytes()))
    _write(root/('.complete-'+job+'.json'),close)


@pytest.mark.parametrize('field',['schema','image_id','executable_sha256','executable_path','response_schema_sha256','known_configuration_path'])
def test_R2_native_metadata_pin_drift_rejected_even_with_rebound_outer_receipt(closed,field):
    t,folder,request,packet,_=closed
    packet['invocation_metadata'][field]='changed'
    actual={k:v for k,v in packet.items() if k not in ('actor','receipt_ref','provenance')}
    raw=canonical(actual);path=t.store.root/'author-01';(path/'stdout.bin').write_bytes(raw)
    receipt=_json(path/'receipt.json');receipt['stdout_sha256']=digest(raw);receipt['stdout_bytes']=len(raw)
    rebind(t.store.root,'author-01',receipt=receipt)
    with pytest.raises(DockerRoleError):t.verify_role(packet,'author-01','author',request)


@pytest.mark.parametrize('field',['argv','stdin_sha256','metadata','request'])
def test_R2_actual_inner_command_input_and_metadata_are_bound_not_just_declared(closed,field):
    t,folder,request,packet,_=closed;root=folder/'output/native';envelope=_json(root/'call/request.json')
    envelope[field]=[] if field=='argv' else 'changed'
    rebind(root,'call',envelope=envelope)
    with pytest.raises((DockerRoleError,ValueError)):t.verify_role(packet,'author-01','author',request)


@pytest.mark.parametrize('argv',[
    ['/opt/specorganon/venv/bin/python','-c','pass','/input/delivery/test_program.py'],
    ['/bin/true','/input/delivery/test_program.py'],
    ['/opt/specorganon/venv/bin/python','-m','unittest','/input/delivery/test_program.py'],
    ['/opt/specorganon/venv/bin/python','-E','-s','-B','/input/delivery/test_program.py']])
def test_R4_test_argument_presence_never_substitutes_for_execution(tmp_path,argv):
    with pytest.raises(NeutralControllerError,match='isolated Python'):
        NeutralController(tmp_path/'run',attempt_id='fixture',method='N',contract='Public',mandate='Local',argv=argv,
            test_file='test_program.py',transport_policy=POLICY,transport_factory=lambda p:None,fixture_mode=True)
    assert not (tmp_path/'run').exists()


def test_R5_repair_cannot_add_framework_shadow_module(tmp_path):
    repair={'schema':1,'files':{'unittest.py':'class TestCase: pass\ndef main(): pass\n'},'documents':{},'reason':'Indirect battery weakening'}
    c=controller(tmp_path/'run',measurements=[False],responses={'repair':repair});report=c.run()
    assert report['status']=='failed' and report['counts']['build_authors']==3
    assert report['counts']['test_runs']==1
    assert 'unittest.py' not in _json(c.root/'generations/0005.json')['state']['files']


def test_R6_transport_closed_before_results_crash_recovers_after_admission_cutoff(tmp_path,monkeypatch):
    c=controller(tmp_path/'run');original=module._write
    def crash(path,value,**kwargs):
        if path==c.root/'results/0001.json':raise KeyboardInterrupt('crash after transport closes before results persistence')
        return original(path,value,**kwargs)
    monkeypatch.setattr(module,'_write',crash)
    with pytest.raises(KeyboardInterrupt):c.step()
    assert len(c.transport.dispatched)==1
    monkeypatch.setattr(module,'_write',original)
    now=copy.deepcopy(c.initial['clock']);now['boottime_ns']+=6001*10**9
    monkeypatch.setattr(module,'_clock',lambda:now)
    monkeypatch.setattr(c.transport,'call',lambda *a:(_ for _ in ()).throw(AssertionError('must read closed job, no dispatch')))
    report=c.step();assert report['stage']=='program' and report['counts']['roles']==1
    assert report['whole_attempt_seconds']==6001
    report=c.step();assert report['status']=='failed' and report['counts']['roles']==1
    assert len(c.transport.dispatched)==1


def test_R7_failed_H_plan_repair_preserves_original_criteria_and_DG_route(tmp_path):
    refusal={'schema':1,'verdict':'reject','reason':'H design defect','findings':[{'problem':'Missing alternatives'}],'tests_executed':False}
    invalid={'schema':1,'files':{},'documents':{},'reason':'Invalid second plan'}
    c=controller(tmp_path/'run','S');c.step();t=c.transport
    t.responses['plan-review']=refusal;t.responses['plan']=invalid
    report=c.run();assert report['status']=='review_ready',report
    assert report['common_review_ready'] and not report['method_review_ready']
    assert report['counts']['stages']['plan']==2 and report['counts']['stages']['plan-review']==1
    state=_json(c.root/'generations/0007.json')['state']
    assert state['original_criteria'] and state['documents']==state['original_criteria']


@pytest.mark.parametrize('field',['result','usage_reported','native_reconnections'])
def test_R8_valid_inner_transcript_must_match_packet_not_just_stream_hash(closed,field):
    t,folder,request,packet,_=closed
    if field=='result':packet['result']['files']['probe.py']='print(2)'
    elif field=='usage_reported':packet[field]={'tokens':99}
    else:packet[field]=[{'attempt':1,'limit':5,'message_sha256':'a'*64}]
    actual={k:v for k,v in packet.items() if k not in ('actor','receipt_ref','provenance')}
    raw=canonical(actual);path=t.store.root/'author-01';(path/'stdout.bin').write_bytes(raw)
    receipt=_json(path/'receipt.json');receipt.update(stdout_sha256=digest(raw),stdout_bytes=len(raw))
    rebind(t.store.root,'author-01',receipt=receipt)
    with pytest.raises(DockerRoleError,match='body/usage/reconnections'):t.verify_role(packet,'author-01','author',request)


def test_R10_closed_native_contract_error_in_H_branch_preserves_DG_and_consumption(tmp_path):
    from specorganon.docker_roles import ClosedResponseContractError
    refusal={'schema':1,'verdict':'reject','reason':'H defect','findings':[{'problem':'alternatives'}],'tests_executed':False}
    c=controller(tmp_path/'run','S');c.step();t=c.transport;t.responses['plan-review']=refusal;c.step()
    original=t.call
    def closed_invalid(job,role,request):
        if request['documents']['stage.txt']=='plan':
            proof={'schema':1,'provenance':'fixture_closed_invalid_response','request_sha256':digest(canonical(request)),
                'result':{'schema':1,'files':{},'documents':{},'reason':'Inadmissible but closed native turn'},
                'scope':'Fixture only; real bridge classification tested separately'}
            raise ClosedResponseContractError(proof)
        return original(job,role,request)
    t.call=closed_invalid
    report=c.run();assert report['status']=='review_ready',report
    assert report['common_review_ready'] and not report['method_review_ready'] and not report['native_ready']
    assert report['counts']['stages']['plan']==2
    r=_json(c.root/'results/0003.json');assert r['kind']=='response_error'


def test_cleanup_not_confirmed_keeps_reservation_without_terminal_cost_or_redispatch(tmp_path,monkeypatch):
    from specorganon.docker_roles import PendingCleanupError
    c=controller(tmp_path/'run');t=c._get_transport();original=t.call
    def interrupted(job,role,request):raise KeyboardInterrupt('fixture interruption at reserved dispatch boundary')
    t.call=interrupted
    with pytest.raises(KeyboardInterrupt):c.step()
    now=copy.deepcopy(c.initial['clock']);now['boottime_ns']+=6001*10**9
    monkeypatch.setattr(module,'_clock',lambda:now)
    def cleanup(job,role,request):raise PendingCleanupError('fixture cleanup unknown')
    t.reconcile_pending=cleanup
    with pytest.raises(PendingCleanupError):c.step()
    assert not list((c.root/'results').iterdir()) and not list((c.root/'generations').iterdir())
    assert not (c.root/'terminal-clock.json').exists()
    assert len(list((c.root/'reservations').iterdir()))==1
    assert _json(c.root/'reservations/0001.json')['counts']['roles']==1
    t.reconcile_pending=lambda *a:False
    report=c.step();assert report['status']=='failed' and report['counts']['roles']==1


@pytest.mark.parametrize('message,missing',[
 ('error: no such object: recorded-id',True),
 ('Error: No such object: recorded-id',True),
 ('Error response from daemon: No such container: recorded-id',True),
 ('error: no such object: other-id',False),
 ('Cannot connect to the Docker daemon',False),
 ('error: no such object: recorded-id\nCannot connect to the Docker daemon',False),
])
def test_inspect_recognizes_exact_missing_target_only(message,missing):
    import subprocess
    from specorganon.docker_roles import DockerRoles, PendingCleanupError
    t=object.__new__(DockerRoles);calls=[]
    def cli(argv,**kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv,1,stdout=b'[]\n',stderr=message.encode())
    t._cli=cli
    plan={'container_id':'recorded-id','name':'original-name'}
    if missing:assert t._inspect(plan) is None
    else:
        with pytest.raises(PendingCleanupError):t._inspect(plan)
    assert calls==[['inspect','recorded-id']]


def test_R14_inspection_timeout_preserves_pending_result_and_clock(tmp_path):
    from specorganon.docker_roles import DockerRoles,DockerControlDeadlineError,PendingCleanupError
    t=object.__new__(DockerRoles)
    def expired(*args,**kwargs):raise DockerControlDeadlineError('inspect')
    t._cli=expired
    with pytest.raises(PendingCleanupError,match='inspection deadline'):
        t._inspect({'container_id':'recorded-id','name':'owned-name'})
    c=controller(tmp_path/'run');transport=c._get_transport()
    transport.call=lambda *a,**k:t._inspect({'container_id':'recorded-id','name':'owned-name'})
    with pytest.raises(PendingCleanupError):c.step()
    assert not list((c.root/'results').iterdir()) and not list((c.root/'generations').iterdir())
    assert not (c.root/'terminal-clock.json').exists()
    assert _json(c.root/'reservations/0001.json')['counts']['roles']==1


@pytest.mark.parametrize('journal',['reservations','results','generations'])
def test_R15_unpublished_atomic_writer_debris_never_promoted_or_redispatched(tmp_path,monkeypatch,journal):
    import uuid
    c=controller(tmp_path/'run');original=module._write;target=c.root/journal/'0001.json'
    def interrupted(path,value,**kwargs):
        if path==target:
            (path.parent/('.'+path.name+'.'+uuid.uuid4().hex)).write_bytes(b'incomplete JSON not evidence')
            raise KeyboardInterrupt('atomic writer interrupted before replace')
        return original(path,value,**kwargs)
    monkeypatch.setattr(module,'_write',interrupted)
    with pytest.raises(KeyboardInterrupt):c.step()
    monkeypatch.setattr(module,'_write',original)
    report=c.step();assert report['stage']=='program' and report['counts']['roles']==1
    assert c.transport.dispatched==['neutral-0001-plan']
    assert _json(target)['schema']==1


@pytest.mark.parametrize('bad',['.0001.json.bad','.0000.json.'+'a'*32,'.0081.json.'+'a'*32,
 '0001Xjson','.0001.json.'+'a'*32+'/directory','.0001.json.'+'a'*32+'/symlink','.0001.json.'+'a'*32+'/hardlink'])
def test_R15_unknown_or_unsafe_debris_rejected(tmp_path,bad):
    c=controller(tmp_path/'run');parts=bad.split('/');p=c.root/'results'/parts[0]
    if len(parts)==1:p.write_bytes(b'not an admitted record')
    elif parts[1]=='directory':p.mkdir()
    elif parts[1]=='symlink':p.symlink_to(c.root/'initial.json')
    else:
        import os
        target=tmp_path/'linked-temp-source';target.write_bytes(b'unsafe multiply linked temporary');os.link(target,p)
    with pytest.raises(NeutralControllerError,match='unexpected controller journal entry'):c.step()
    assert not (c.root/'terminal-clock.json').exists()


def test_R16_repair_cannot_add_new_document_preserves_prior_maps_and_budget(tmp_path):
    repair={'schema':1,'files':{},'documents':{'new.md':'Added beyond existing-document repair scope'},'reason':'Synthetic inadmissible repair'}
    c=controller(tmp_path/'run',measurements=[False],responses={'repair':repair});report=c.run()
    assert report['status']=='failed' and report['counts']['build_authors']==3
    assert report['counts']['test_runs']==1
    state=_json(c.root/'generations/0005.json')['state']
    assert 'new.md' not in state['documents'] and state['documents']==state['original_criteria']


def test_R14_transport_unavailable_with_existing_creation_intent_never_seals_terminal(tmp_path):
    from specorganon.docker_roles import PendingCleanupError
    c=controller(tmp_path/'run');t=c._get_transport()
    t.call=lambda *a,**k:(_ for _ in ()).throw(KeyboardInterrupt('existing pending dispatch'))
    with pytest.raises(KeyboardInterrupt):c.step()
    folder=c.root/'transport/jobs/neutral-0001-plan';folder.mkdir(parents=True)
    _write(folder/'create-attempt.json',{'fixture':'Conservative existence guard, not native execution proof'})
    c.transport=None
    c.factory=lambda path:(_ for _ in ()).throw(OSError('transport constructor unavailable'))
    with pytest.raises(PendingCleanupError):c.step()
    assert not list((c.root/'results').iterdir()) and not (c.root/'terminal-clock.json').exists()
    assert len(list((c.root/'reservations').iterdir()))==1


@pytest.mark.parametrize('missing',['launch','intent'])
def test_R17_missing_cleanup_binding_never_means_absence(closed,missing):
    from specorganon.docker_roles import PendingCleanupError
    t,folder,request,packet,_=closed
    (folder/('launch.json' if missing=='launch' else 'create-attempt.json')).unlink()
    with pytest.raises(PendingCleanupError):t.reconcile_pending('author-01','author',request)


@pytest.mark.parametrize('late',[False,True])
def test_R17_existing_creation_intent_requires_true_cleanup_before_any_terminal(tmp_path,monkeypatch,late):
    from specorganon.docker_roles import PendingCleanupError
    c=controller(tmp_path/'run');t=c._get_transport()
    t.call=lambda *a,**k:(_ for _ in ()).throw(KeyboardInterrupt('pending dispatch fixture'))
    with pytest.raises(KeyboardInterrupt):c.step()
    folder=c.root/'transport/jobs/neutral-0001-plan';folder.mkdir(parents=True)
    _write(folder/'create-attempt.json',{'fixture':'Intent existence guard only; launch deliberately absent'})
    if late:
        now=copy.deepcopy(c.initial['clock']);now['boottime_ns']+=6001*10**9
        monkeypatch.setattr(module,'_clock',lambda:now)
    else:t.call=lambda *a,**k:(_ for _ in ()).throw(ValueError('missing launch'))
    t.reconcile_pending=lambda *a:False
    with pytest.raises(PendingCleanupError):c.step()
    assert not list((c.root/'results').iterdir()) and not list((c.root/'generations').iterdir())
    assert not (c.root/'terminal-clock.json').exists()
    assert len(list((c.root/'reservations').iterdir()))==1
    assert _json(c.root/'reservations/0001.json')['counts']['roles']==1
