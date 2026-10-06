"""Synthetic bridge journals for custody guards, never native provider evidence.

A real Python process produces streams/JobStore closing markers, while Popen's
Docker argv is substituted in this fixture. No Docker/provider is invoked.
"""
import copy
import subprocess
import sys

import pytest

from specorganon.docker_roles import DockerRoles
from specorganon.role_jobs import JobStore, canonical, digest, _json, _write


@pytest.fixture
def closed(tmp_path, monkeypatch):
    from specorganon.native_response_contract import response_contract_from_request,render_prompt,native_command
    t= DockerRoles.__new__(DockerRoles)
    t.root=tmp_path/'transport';t.root.mkdir()
    t.store=JobStore(t.root/'host-journal')
    t.routes={'author':('gemini','fixture-model'),'review':('gemini','fixture-review')}
    t.images={'native':'sha256:'+'a'*64,'test':'sha256:'+'d'*64}
    t.seccomp=None;t.codex_reasoning_effort='low';t.gemini_profile=tmp_path/'synthetic-profile'
    t.gemini_executable=tmp_path/'synthetic-agy';t.gemini_executable.write_bytes(b'Synthetic binary pin; never invoked')
    t.gemini_executable_sha256=digest(t.gemini_executable.read_bytes())
    sources={'scripts/controller_native_role.py':b'# synthetic bridge\n',
             'src/specorganon/__init__.py':b'# synthetic package\n'}
    t.native_sources={n:digest(v) for n,v in sources.items()}
    monkeypatch.setattr(t,'_native_source_bytes',lambda:copy.deepcopy(sources))
    folder=t.root/'jobs/author-01';(folder/'input/library/specorganon').mkdir(parents=True)
    (folder/'output').mkdir()
    request={'schema':1,'role':'author','role_instructions':'Fixture','documents':{
        'author-response-format.json':canonical({'schema':1,'format':'files-v1'}).decode()}}
    (folder/'input/request.json').write_bytes(canonical(request))
    (folder/'input/bridge.py').write_bytes(sources['scripts/controller_native_role.py'])
    (folder/'input/library/specorganon/__init__.py').write_bytes(sources['src/specorganon/__init__.py'])
    label=digest(canonical({'root':str(t.root),'job_id':'author-01'}))[:24]
    plan={'schema':2,'job_id':'author-01','role':'author','provider':'gemini','model':'fixture-model',
          'request_sha256':digest(canonical(request)),'image_id':t.images['native'],
          'container_id':'b'*64,'input_manifest':t._inventory(folder/'input'),'codex_reasoning_effort':None,
          'name':'specorganon-role-'+label,'label':label,'execution_nonce':'c'*32,
          'creation_not_before':'2026-10-06T00:00:00+00:00'}
    plan['create_argv']=t._launch_argv(folder,'author',request,label,plan['execution_nonce'])
    _write(folder/'launch.json',plan);_write(folder/'create-attempt.json',t._creation_attempt(plan))
    metadata={k:plan[k] for k in ('role','provider','model','image_id','container_id','input_manifest')}
    native_meta={'schema':1,'image_id':plan['image_id'],'executable_path':'/usr/local/bin/agy',
        'executable_sha256':t.gemini_executable_sha256,'known_configuration_path':'/home/stev/.gemini/settings.json',
        'known_configuration_sha256':None,'other_effective_configuration':'unknown; trusted launcher/profile boundary',
        'response_schema_sha256':digest(canonical(response_contract_from_request(request))),
        'response_schema_scope':'Prompt guidance and strict local validation only; no provider enforcement claim'}
    _write(folder/'output/role-response-schema.json',response_contract_from_request(request))
    _,prompt=render_prompt(canonical(request))
    payload=canonical({'event':'user','message':{'role':'user','content':[{'type':'text','text':prompt}]}})+b'\n'
    native=JobStore(folder/'output/native',max_jobs=2)
    body={'schema':1,'files':{'probe.py':'print(1)'},'documents':{},'reason':'Synthetic content'}
    text=canonical(body).decode();conversation='synthetic-transcript'
    events=[{'event':'init','conversation_id':conversation,'init':{}},
        {'event':'step_update','step_update':{'conversation_id':conversation,'step_index':0,'state':'DONE','step_type':'user_input'}},
        {'event':'step_update','step_update':{'conversation_id':conversation,'step_index':1,'state':'DONE','step_type':'agent_response','text_delta':text}},
        {'event':'result','result':{'conversation_id':conversation,'status':'SUCCESS','num_turns':1,'response':text,'usage':{'tokens':1}}}]
    transcript='\n'.join(canonical(e).decode() for e in events)+'\n'
    original=subprocess.Popen
    def fake_inner(argv,**kwargs):
        return original([sys.executable,'-c','import sys;sys.stdin.buffer.read();sys.stdout.write(sys.argv[1])',transcript],**kwargs)
    monkeypatch.setattr(subprocess,'Popen',fake_inner)
    native.execute('call',native_command('gemini','fixture-model'),{'provider':'gemini','model':'fixture-model'},
        cwd=t.root,metadata=native_meta,timeout_seconds=180,stdin_bytes=payload)
    # Coherent container-path fixture only: these are deliberately fabricated
    # journals, not attestation of /input or a provider. The trusted-host boundary
    # admits consistency checks; this test never attributes native execution.
    root=native.root;envelope=_json(root/'call/request.json');envelope['cwd']='/input';_write(root/'call/request.json',envelope)
    sha=digest(canonical(envelope));receipt=_json(root/'call/receipt.json');receipt['cwd']='/input';receipt['request_sha256']=sha
    _write(root/'call/receipt.json',receipt)
    started=_json(root/'call/started.json');started['request_sha256']=sha;_write(root/'call/started.json',started)
    close=_json(root/'.complete-call.json');close.update(request_sha256=sha,receipt_sha256=digest(canonical(receipt)),
        started_sha256=digest((root/'call/started.json').read_bytes()));_write(root/'.complete-call.json',close)
    actual={'schema':1,'provider':'gemini','model':'fixture-model',
            'request_sha256':plan['request_sha256'],'native_exit_code':0,
            'invocation_metadata':native_meta,'result':body,'usage_reported':{'tokens':1},'native_reconnections':[]}
    def synthetic_popen(argv,**kwargs):
        assert argv==['/usr/bin/docker','start','--attach',plan['container_id']]
        return original([sys.executable,'-c','import sys;sys.stdout.write(sys.argv[1])',canonical(actual).decode()],**kwargs)
    monkeypatch.setattr(subprocess,'Popen',synthetic_popen)
    result=t.store.execute('author-01',['/usr/bin/docker','start','--attach',plan['container_id']],request,
                           cwd=t.root,metadata=metadata,timeout_seconds=180)
    from specorganon.docker_roles import _terminal_container
    _write(folder/'terminal-container.json', _terminal_container({'Id':plan['container_id'], 'Image':plan['image_id'],
        'State':{'Status':'exited','Running':False,'Dead':False,'Restarting':False,'ExitCode':0,'OOMKilled':False}}, plan))
    packet={**actual,'actor':'agent:gemini-isolated-author',
        'receipt_ref':str(t.store.root/'author-01/receipt.json'),'provenance':'native'}
    def forbidden(*args,**kwargs):raise AssertionError('verification must not execute or reconcile')
    monkeypatch.setattr(subprocess,'Popen',forbidden);monkeypatch.setattr(t,'_cli',forbidden)
    monkeypatch.setattr(t,'call',forbidden);monkeypatch.setattr(t,'reconcile',forbidden)
    return t,folder,request,packet,result


def test_closed_packet_links_actual_stream_and_all_private_records_without_execution(closed):
    t,_,request,packet,_=closed
    assert t.verify_role(packet,'author-01','author',request) is True
    assert t.verify_role(packet,'author-01','author',request) is True


@pytest.mark.parametrize('fault',['request','role','packet_result','packet_schema','provenance','receipt_path',
    'stdout','stderr','request_record','receipt','closing_marker','started_marker','input','source_copy',
    'current_source','intent','terminal_exit','terminal_oom','terminal_bool_exit','new_recovery','missing_launch'])
def test_divergence_or_fabrication_rejected_without_dispatch(closed,fault,monkeypatch):
    t,folder,request,packet,_=closed;journal=t.store.root/'author-01';role='author'
    if fault=='request':request['role_instructions']='Replacement'
    elif fault=='role':role='review'
    elif fault=='packet_result':packet['result']['reason']='replacement'
    elif fault=='packet_schema':packet['schema']=1.0
    elif fault=='provenance':packet['provenance']='fixture'
    elif fault=='receipt_path':packet['receipt_ref']=str(t.root/'other.json')
    elif fault in ('stdout','stderr'):(journal/(fault+'.bin')).write_bytes(b'Changed stream')
    elif fault in ('request_record','receipt','closing_marker','started_marker'):
        filename={'request_record':'request.json','receipt':'receipt.json','closing_marker':'.complete-job.json','started_marker':'started.json'}[fault]
        target=t.store.root/'.complete-author-01.json' if fault=='closing_marker' else journal/filename
        _write(target,{'synthetic_changed':True})
    elif fault=='input':(folder/'input/request.json').write_bytes(b'{}')
    elif fault=='source_copy':(folder/'input/bridge.py').write_bytes(b'changed')
    elif fault=='current_source':monkeypatch.setattr(t,'_native_source_bytes',lambda:{'scripts/controller_native_role.py':b'changed'})
    elif fault=='intent':_write(folder/'create-attempt.json',{'synthetic_changed':True})
    elif fault.startswith('terminal_'):
        value=_json(folder/'terminal-container.json')
        if fault=='terminal_exit':value['exit_code']=1
        if fault=='terminal_bool_exit':value['exit_code']=False
        if fault=='terminal_oom':value['oom_killed']=True
        _write(folder/'terminal-container.json',value)
    elif fault=='new_recovery':_write(folder/'control-recovery.json',{'synthetic_changed':True})
    elif fault=='missing_launch':(folder/'launch.json').unlink()
    with pytest.raises((ValueError,KeyError)):t.verify_role(packet,'author-01',role,request)
