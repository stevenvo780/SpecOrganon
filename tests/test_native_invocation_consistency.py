"""Coherent fabricated Codex journals for consistency guards; zero native calls.

These controlled records are explicitly fixtures, not provider/daemon attestation.
"""
import copy

import pytest

from specorganon.docker_roles import DockerRoleError
from specorganon.native_response_contract import (CODEX_TEXT_ONLY_DISABLED,native_command,
    role_model_catalog,render_prompt)
from specorganon.native_transcript import validate_codex_features
from specorganon.role_jobs import canonical,digest,_json,_write
from test_closed_native_role import closed
from test_staged_review_regressions import rebind


def fabricated(root,job,template,*,argv,request,meta,stdout,stdin,timeout):
    folder=root/job;folder.mkdir(exist_ok=True)
    env=copy.deepcopy(template['env']);env.update(argv=argv,request=request,metadata=meta,cwd='/input',
        stdin_sha256=digest(stdin) if stdin else None,timeout_seconds=timeout)
    sha=digest(canonical(env));_write(folder/'request.json',env)
    receipt=copy.deepcopy(template['receipt']);receipt.update(job_id=job,request_sha256=sha,argv=argv,cwd='/input',
        metadata=meta,stdin_bytes_sent=len(stdin),stdin_bytes_expected=len(stdin),stdin_complete=True,
        stdout_bytes=len(stdout),stdout_sha256=digest(stdout),stderr_bytes=0,stderr_sha256=digest(b''))
    (folder/'stdout.bin').write_bytes(stdout);(folder/'stderr.bin').write_bytes(b'');_write(folder/'receipt.json',receipt)
    started=copy.deepcopy(template['started']);started.update(metadata=meta,request_sha256=sha);_write(folder/'started.json',started)
    _write(root/('.complete-'+job+'.json'),{'schema':1,'request_sha256':sha,
        'receipt_sha256':digest(canonical(receipt)),'started_sha256':digest((folder/'started.json').read_bytes())})


@pytest.fixture
def codex_closed(closed):
    t,folder,request,packet,_=closed;root=folder/'output/native'
    template={'env':_json(root/'call/request.json'),'receipt':_json(root/'call/receipt.json'),'started':_json(root/'call/started.json')}
    t.routes['author']=('codex','fixture-model');t.volume='synthetic-original-volume'
    public=canonical({'models':[{'slug':'fixture-model','supported_reasoning_levels':[{'effort':'low'}]}]})
    (folder/'input/public-models.json').write_bytes(public);t.launch_input_sha256={'public-models.json':digest(public)}
    projected=canonical(role_model_catalog(_json(folder/'input/public-models.json'),'fixture-model'))
    (folder/'output/runtime-model-catalog.json').write_bytes(projected)
    plan=_json(folder/'launch.json');plan.update(provider='codex',codex_reasoning_effort='low',input_manifest=t._inventory(folder/'input'))
    plan['create_argv']=t._launch_argv(folder,'author',request,plan['label'],plan['execution_nonce'])
    _write(folder/'launch.json',plan);_write(folder/'create-attempt.json',t._creation_attempt(plan))
    raw_features=('\n'.join(name+' stable false' for name in CODEX_TEXT_ONLY_DISABLED)+'\nunified_exec stable true\n').encode()
    base=copy.deepcopy(packet['invocation_metadata']);base.update(
        executable_path='/usr/local/lib/node_modules/@openai/codex/bin/codex.js',executable_sha256='e'*64,
        known_configuration_path='/home/codex/.codex/config.toml',public_model_catalog_sha256=digest(public),
        runtime_model_catalog_sha256=digest(projected),requested_reasoning_effort='low',
        effective_remote_reasoning_effort='not observed',tool_surface_override='direct; no shell, patch, search or experimental tools')
    meta={**base,'effective_features':validate_codex_features(raw_features.decode())}
    argv=native_command('codex','fixture-model',model_catalog='/output/runtime-model-catalog.json',reasoning_effort='low')
    check=[argv[0]]
    for i,arg in enumerate(argv[:-1]):
        if arg in ('-c','--disable'):check.extend([arg,argv[i+1]])
    fabricated(root,'configuration-check',template,argv=check+['features','list'],
        request={'purpose':'native feature restriction check, no model call'},meta=base,stdout=raw_features,stdin=b'',timeout=10)
    usage={'input_tokens':1,'output_tokens':1};text=canonical(packet['result']).decode()
    events=[{'type':'thread.started','thread_id':'synthetic-thread'},{'type':'turn.started'},
        {'type':'item.completed','item':{'id':'synthetic-response','type':'agent_message','text':text}},
        {'type':'turn.completed','usage':usage}]
    transcript=('\n'.join(canonical(e).decode() for e in events)+'\n').encode()
    _,prompt=render_prompt(canonical(request))
    fabricated(root,'call',template,argv=argv,request={'provider':'codex','model':'fixture-model'},
        meta=meta,stdout=transcript,stdin=prompt.encode(),timeout=180)
    packet.update(provider='codex',actor='agent:codex-isolated-author',invocation_metadata=meta,usage_reported=usage)
    actual={k:v for k,v in packet.items() if k not in ('actor','receipt_ref','provenance')}
    outer=t.store.root/'author-01';raw=canonical(actual);(outer/'stdout.bin').write_bytes(raw)
    env=_json(outer/'request.json');env['metadata'].update(provider='codex',input_manifest=plan['input_manifest'])
    receipt=_json(outer/'receipt.json');receipt.update(metadata=env['metadata'],stdout_bytes=len(raw),stdout_sha256=digest(raw))
    started=_json(outer/'started.json');started['metadata']=env['metadata'];_write(outer/'started.json',started)
    rebind(t.store.root,'author-01',envelope=env,receipt=receipt)
    return t,folder,request,packet


def test_measured_Codex_features_command_body_and_environment_consistent(codex_closed):
    t,_,request,packet=codex_closed
    assert t.verify_role(packet,'author-01','author',request) is True


@pytest.mark.parametrize('fault',['shell_true','environment','timeout','stdin','metadata'])
def test_R9_preflight_contradiction_cannot_be_hidden_by_call_metadata(codex_closed,fault):
    t,folder,request,packet=codex_closed;root=folder/'output/native';path=root/'configuration-check'
    env=_json(path/'request.json');receipt=_json(path/'receipt.json')
    if fault=='shell_true':
        raw=(path/'stdout.bin').read_bytes().replace(b'shell_tool stable false',b'shell_tool stable true')
        (path/'stdout.bin').write_bytes(raw);receipt.update(stdout_sha256=digest(raw),stdout_bytes=len(raw))
    elif fault=='environment':env['environment_sha256']='f'*64
    elif fault=='timeout':env['timeout_seconds']=180
    elif fault=='stdin':env['stdin_sha256']=digest(b'injected');receipt.update(stdin_bytes_sent=8,stdin_bytes_expected=8)
    elif fault=='metadata':env['metadata']={'scope':'false preflight identity'};receipt['metadata']=env['metadata']
    rebind(root,'configuration-check',envelope=env,receipt=receipt)
    with pytest.raises(ValueError):t.verify_role(packet,'author-01','author',request)
