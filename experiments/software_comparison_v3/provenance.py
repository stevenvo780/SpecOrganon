"""Read-only native/test evidence validation under the trusted Docker boundary.

No credentials are read or copied, no models invoked, no journal constructed or
changed. Historical receipts can validate mechanics, never a new9phase delivery.
Hash bindings attest consistency, not cryptographic identity or model weights.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from specorganon import engine
from specorganon.docker_roles import DockerRoles
from specorganon.role_jobs import JobStore, canonical, digest, _json, _read, _safe
from specorganon.ledger import strict_json_loads
from specorganon.software_controller import fingerprint
from specorganon.runner import describe_task
from specorganon.workflow import PHASES
from scripts.controller_native_role import (render_prompt, parse_native, parse_gemini_stream,
    validate_result, native_argv, CODEX_TEXT_ONLY_DISABLED, validate_codex_features,
    role_model_catalog, codex_feature_argv)
from experiments.software_comparison_v3.budget import identifier
from experiments.software_comparison_v3.audit_evidence import verify_locators


class ProvenanceError(ValueError):
    pass


def require(condition,message):
    if not condition: raise ProvenanceError(message)


def journal_receipt(root, job_id):
    """Use existing strict JobStore validation through a read-only descriptor."""
    root=_safe(root);identifier(job_id)
    require(root.is_dir() and (root/'policy.json').is_file(),'existing journal required')
    reader=JobStore.__new__(JobStore);reader.root=root
    reader._root_fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        info=os.fstat(reader._root_fd)
        require(info.st_uid==os.geteuid() and info.st_mode & 0o022==0,'private owned journal required')
        reader.policy=reader._json(root/'policy.json')['policy']
        require(reader.policy.get('schema')==3,'existing journal schema3 required')
        path=root/job_id;receipt=reader._json(path/'receipt.json')
        reader._validate_receipt(path,job_id,receipt)
        request=reader._read(path/'request.json');envelope=strict_json_loads(request.decode())
        require(digest(request)==receipt['request_sha256'],'receipt request envelope hash differs')
        require(all(envelope[k]==receipt[k] for k in ('argv','cwd','metadata')),'receipt/envelope execution differs')
        streams={n:reader._read(path/(n+'.bin'),2097152) for n in ('stdout','stderr')}
        require(all(digest(raw)==receipt[n+'_sha256'] and len(raw)==receipt[n+'_bytes'] for n,raw in streams.items()),'captured stream differs')
        return receipt,envelope,streams
    finally:
        os.close(reader._root_fd);reader._root_fd=None


class NativeEvidence:
    def __init__(self, transport):
        self.transport=transport;self.root=_safe(transport.root)
        self.policy=_json(self.root/'transport-policy.json')
        p=self.policy
        require(p.get('schema')==3 and p['source_root']==str(transport.source)
                and p['images']==transport.images and p['routes']=={k:list(v) for k,v in transport.routes.items()},'registered transport policy differs')
        require(p['codex_original_volume']=='specorganon-lab_codex-home'
                and p['gemini_original_profile']=='/home/stev/.gemini','original authorized profiles required')
        require(set(p['routes'])=={'author','review'} and {v[0] for v in p['routes'].values()}=={'codex','gemini'},'distinct registered author/reviewer families required')

    def _execution(self, job_id, role, *, allow_failed_test=False):
        identifier(job_id);folder=self.root/'jobs'/job_id;plan=_json(folder/'launch.json')
        require(plan['job_id']==job_id and plan['role']==role,'role/launch identity differs')
        require(plan['image_id']==self.policy['images']['test' if role=='test' else 'native'],'launch image differs')
        raw=_read(folder/'input/request.json',128000);request=strict_json_loads(raw.decode())
        require(digest(raw)==plan['request_sha256'],'prepared role request differs')
        label=digest(canonical({'root':str(self.root),'job_id':job_id}))[:24]
        require(plan['label']==label and plan['name']=='specorganon-role-'+label,'owned container label/name differs')
        require(self.transport._inventory(folder/'input')==plan['input_manifest'],'prepared input snapshot differs')
        outer,envelope,streams=journal_receipt(self.root/'host-journal',job_id)
        expected={'role':role,'provider':plan['provider'],'model':plan['model'],'image_id':plan['image_id'],
                  'container_id':plan['container_id'],'input_manifest':plan['input_manifest']}
        require(envelope['request']==request and outer['metadata']==expected and outer['cwd']==str(self.root)
                and outer['argv']==['/usr/bin/docker','start','--attach',plan['container_id']]
                and envelope['cancel_argv']==['/usr/bin/docker','kill',plan['container_id']],'host receipt differs from prepared container dispatch')
        require(allow_failed_test or not outer['timed_out'] and not outer['truncated_streams'],'bounded execution failed/inconclusive')
        terminal=_json(folder/'terminal-container.json');observed=self.transport._inspect(plan)
        require(observed is not None and observed['Id']==plan['container_id'] and observed['Image']==plan['image_id'],'recorded terminal container missing or changed')
        require(not observed['State']['Running'] and not observed['State']['OOMKilled']
                and (observed['State']['ExitCode']==outer['exit_code'] or allow_failed_test and (outer['timed_out'] or outer['truncated_streams'])),'container and captured exit differ')
        require(terminal=={'id':plan['container_id'],'exit_code':observed['State']['ExitCode'],'image_id':plan['image_id'],'oom_killed':False},'saved terminal container differs')
        host=observed['HostConfig']
        require(host['ReadonlyRootfs'] is True and host['Privileged'] is False and 'ALL' in host['CapDrop']
                and any(x.startswith('no-new-privileges') for x in host['SecurityOpt']),'container isolation differs')
        require(host['Memory']==1073741824 and host['NanoCpus']==2000000000 and host['PidsLimit']==128,
                'container resource limits differ')
        require(observed['Config']['User']==('ubuntu' if role=='test' else 'codex'),'registered image user differs')
        mounts=observed['Mounts']
        require(any(m['Destination']=='/input' and m['Source']==str(folder/'input') and m['RW'] is False for m in mounts),'read-only input mount differs')
        require(any(m['Destination']=='/output' and m['Source']==str(folder/'output') and m['RW'] is True for m in mounts),'captured output mount differs')
        if role=='test':
            require(host['NetworkMode']=='none' and {m['Destination'] for m in mounts}=={'/input','/output'},'test network/credential isolation differs')
            require(observed['Config']['Cmd']==request['argv'] and observed['Config']['Entrypoint'] in (None,[])
                    and observed['Config']['WorkingDir']=='/input/delivery','physical test command/working directory differs')
        else:
            provider,model=self.policy['routes'][role]
            require((plan['provider'],plan['model'])==(provider,model),'registered native route differs')
            auth='/home/codex/.codex' if provider=='codex' else '/home/stev/.gemini'
            require({m['Destination'] for m in mounts}==({'/input','/output',auth} if provider=='codex' else {'/input','/output',auth,'/usr/local/bin/agy'}),'unexpected native mount surface')
            profile=next(m for m in mounts if m['Destination']==auth)
            require(profile.get('Name')==self.policy['codex_original_volume'] if provider=='codex' else profile['Source']==self.policy['gemini_original_profile'],'native original profile mount differs')
            command=['/input/bridge.py','--provider',provider,'--model',model,'--request','/input/request.json','--output-dir','/output']
            if provider=='codex':command+=['--model-catalog','/input/public-models.json','--codex-reasoning-effort',self.policy['codex_reasoning_effort']]
            require(observed['Config']['Cmd']==command and observed['Config']['Entrypoint']==['/opt/specorganon/.venv/bin/python']
                    and observed['Config']['WorkingDir']=='/input','physical native bridge/working directory differs')
        return folder,plan,request,outer,streams

    def role(self, job_id, role, *, request=None, packet=None):
        require(role in ('author','review'),'native role required')
        folder,plan,actual,outer,streams=self._execution(job_id,role)
        require(outer['exit_code']==0,'native bridge did not succeed')
        if request is not None:require(request==actual,'supplied native request differs')
        manifest=plan['input_manifest'];source=self.transport.source
        require(manifest['bridge.py']==digest(_read(source/'scripts/controller_native_role.py')),'copied bridge differs from source registration')
        expected={str(p.relative_to(source/'src')):digest(_read(p)) for p in (source/'src/specorganon').rglob('*.py')}
        copied={k.removeprefix('library/'):v for k,v in manifest.items() if k.startswith('library/') and k.endswith('.py')}
        require(copied==expected,'copied library differs from registered source')
        inner,env,native=journal_receipt(folder/'output/native','call')
        require(inner['exit_code']==0 and not inner['timed_out'] and not inner['truncated_streams'] and inner['stdin_complete'],'actual native process failed/inconclusive')
        provider,model=plan['provider'],plan['model'];parsed,prompt=render_prompt(canonical(actual))
        require(inner['cwd']=='/input' and inner['metadata']['image_id']==plan['image_id'],'native working directory/image differs')
        payload=canonical({'event':'user','message':{'role':'user','content':[{'type':'text','text':prompt}]}})+b'\n' if provider=='gemini' else prompt.encode()
        require(env['request']=={'provider':provider,'model':model} and env['stdin_sha256']==digest(payload)
                and inner['stdin_bytes_expected']==len(payload) and inner['stdin_bytes_sent']==len(payload),'actual native prompt/route differs')
        argv=inner['argv']
        if provider=='gemini':
            require(argv==native_argv(provider,model,prompt),'Gemini native argv differs')
            require(inner['metadata']['executable_sha256']==self.policy['gemini_executable_sha256'],
                    'Gemini executable differs from registered original CLI')
            result,usage=parse_gemini_stream(native['stdout'].decode())
        else:
            require(manifest['public-models.json']==self.policy['public_catalog_sha256']
                    and inner['metadata']['public_model_catalog_sha256']==self.policy['public_catalog_sha256']
                    and inner['metadata']['requested_reasoning_effort']==self.policy['codex_reasoning_effort'],'Codex model catalog/effort metadata differs')
            require(argv[:2]==['/usr/local/bin/codex','exec'] and argv[argv.index('-m')+1]==model
                    and argv[argv.index('-s')+1]=='read-only' and argv[argv.index('-C')+1]=='/input','Codex native argv route/sandbox differs')
            require(all(any(argv[i:i+2]==['--disable',feature] for i in range(len(argv)-1)) for feature in CODEX_TEXT_ONLY_DISABLED),'Codex requested tool restriction differs')
            effort='model_reasoning_effort='+json.dumps(self.policy['codex_reasoning_effort'])
            require(effort in argv and 'approval_policy="never"' in argv and 'web_search="disabled"' in argv,'Codex native effort/approval/search differs')
            public=strict_json_loads(_read(folder/'input/public-models.json').decode())
            projected=role_model_catalog(public,model)
            require(_read(folder/'output/runtime-model-catalog.json')==canonical(projected)
                    and inner['metadata']['runtime_model_catalog_sha256']==digest(canonical(projected))
                    and 'model_catalog_json="/output/runtime-model-catalog.json"' in argv,'Codex runtime model catalog differs')
            pre,pre_env,features=journal_receipt(folder/'output/native','configuration-check')
            require(pre['exit_code']==0 and not pre['timed_out'] and not pre['truncated_streams'],'Codex configuration preflight failed')
            require(pre['argv']==codex_feature_argv(argv) and pre['cwd']=='/input'
                    and pre_env['request']=={'purpose':'native feature restriction check, no model call'}
                    and pre['metadata']=={k:v for k,v in inner['metadata'].items() if k!='effective_features'},
                    'Codex configuration receipt differs from actual native options')
            require(validate_codex_features(features['stdout'].decode())==inner['metadata']['effective_features'],'Codex observed features differ')
            result,usage=parse_native(provider,native['stdout'].decode())
        validate_result(result,role)
        if role=='review':require(result.get('tests_executed') is False,'native reviewer execution claim unsupported')
        raw_packet=strict_json_loads(streams['stdout'].decode())
        require(raw_packet=={'schema':1,'provider':provider,'model':model,'request_sha256':plan['request_sha256'],
                'invocation_metadata':inner['metadata'],'native_exit_code':0,'usage_reported':usage,'result':result},'bridge packet differs from captured native response')
        wrapped={**raw_packet,'actor':('agent:' if role=='author' else 'reviewer:')+provider+'-isolated-'+role,
                 'receipt_ref':str(self.root/'host-journal'/job_id/'receipt.json'),'provenance':'native'}
        if packet is not None:require(packet==wrapped,'stored role packet differs from actual native streams')
        return {'schema':1,'job_id':job_id,'role':role,'provider':provider,'model':model,'container_id':plan['container_id'],
                'request':actual,'packet':wrapped,'outer_receipt_sha256':digest(canonical(outer)),
                'native_receipt_sha256':digest(canonical(inner)),'rendered_input_bytes':len(prompt.encode()),
                'usage_reported':usage,'money':None,'identity_scope':'trusted original profiles/argv/streams, not remote weights or cryptographic identity',
                'Gemini_internal_tools_absolute_off_proven':False}

    def test(self, job_id, files, *, require_passed=True):
        folder,plan,request,receipt,streams=self._execution(job_id,'test',allow_failed_test=not require_passed)
        measured=_json(folder/'measured-test.json')
        terminal=_json(folder/'terminal-container.json')
        passed=receipt['exit_code']==0 and not receipt['timed_out'] and not receipt['truncated_streams']
        expected={**receipt,'subject_argv':request['argv'],'attachment_exit_code':receipt['exit_code'],
                  'exit_code':terminal['exit_code'],'test_job_ref':str(self.root/'host-journal'/job_id/'receipt.json'),
                  'delivery_tree_sha256':digest(canonical(files)),'image_id':plan['image_id'],
                  'container_id':plan['container_id'],'provenance':'actual_isolated_container','passed':passed}
        require(measured==expected and (not require_passed or passed),'measured test/physical receipt differs or test failed')
        require(request=={'schema':1,'argv':measured['subject_argv'],'delivery_tree_sha256':digest(canonical(files))},'test command/input differs')
        actual={k.removeprefix('delivery/'):v for k,v in plan['input_manifest'].items() if k.startswith('delivery/')}
        require(actual=={k:digest(v.encode()) for k,v in files.items()},'physical test input files differ')
        return {'schema':1,'job_id':job_id,'container_id':plan['container_id'],'passed':measured['passed'],
                'delivery_sha256':digest(canonical(files)),'receipt_sha256':digest(canonical(receipt))}


def toolkit_milestone(runner,evidence):
    """Qualify only current native T package, final D/G/H and physical receipts.

    Reserved functional results are deliberately absent; this milestone precedes
    that evaluation. Semantic judgments come from actual distinct native peers,
    not a checklist parser claiming truth.
    """
    runner.controller.package_gate();state=engine.get_state(runner.case);files=runner.controller._files()
    history=_json(runner.controller.root/'progress.json')['history'];proofs={};authors={p.id:[] for p in PHASES}
    for entry in history:
        if entry['action']=='test':
            stored=evidence.root/'jobs'/entry['job_id']/'input/delivery'
            previous={str(p.relative_to(stored)):_read(p).decode() for p in stored.rglob('*') if p.is_file()}
            proofs[entry['job_id']]=evidence.test(entry['job_id'],previous,require_passed=False)
            require(proofs[entry['job_id']]['delivery_sha256']==entry['source_files_sha256'],'historical test input/history differs')
            continue
        role='author' if entry['action']=='author' else 'review';proof=evidence.role(entry['job_id'],role)
        request=proof['request'];source_state=strict_json_loads(request['documents']['state.json']);source_files=strict_json_loads(request['documents']['delivery-files.json'])
        require(fingerprint(source_state)==entry['source_fingerprint'] and source_state['phases'][entry['phase']]['snapshot']==entry['source_phase_snapshot']
                and digest(canonical(source_files))==entry['source_files_sha256'],'native controller history/source snapshot differs')
        require(proof['packet']['actor']==entry['actor'] and proof['packet']['receipt_ref']==entry['receipt_ref']
                and proof['packet']['result']['reason']==entry['reason'],'native history actor/judgment differs')
        require(request['documents']['action.txt']==entry['action']
                and strict_json_loads(request['documents']['phase-contract.json'])['id']==entry['phase'],'native action/phase differs from history')
        if role=='review':
            require(proof['packet']['result']['verdict']==entry['verdict']
                    and proof['packet']['result']['findings']==entry['findings'],'native review verdict/findings differ from history')
            if entry['action']=='approval':
                response=proof['packet']['result'];targets=describe_task(source_state)['approval_targets']
                require(response['verdict']=='accept' and response.get('mandate_conformity') is True
                        and response.get('approval_targets')==[item['id'] for item in targets],
                        'native mandate approval target/judgment differs')
        proofs[entry['job_id']]={k:v for k,v in proof.items() if k not in ('request','packet')}
        if role=='author':authors[entry['phase']].append(proof['container_id'])
    for phase in (p.id for p in PHASES):
        latest=next((h for h in reversed(history) if h['phase']==phase and h['action']=='review'),None)
        require(latest and latest['verdict']=='accept' and latest['source_phase_snapshot']==state['phases'][phase]['snapshot'],'phase lacks current accepted actual native review')
        proof=proofs[latest['job_id']]
        require(authors[phase] and proof['container_id'] not in authors[phase],'author and phase reviewer must be physically distinct')
    final_request=_json(runner.root/'common-final-request.json');final_packet=_json(runner.root/'common-final-review.json')
    final=evidence.role('common-final-review','review',request=final_request,packet=final_packet)
    actual=runner.final_request(state,files,{**{item['id']:{'current_test_job_ref':item['data']['test_job_ref'],'delivery_tree_sha256':digest(canonical(files))} for item in state['items'].values() if item['kind']=='test'},'all_public_attempts':runner.public_attempts(files)})
    require(final_request==actual,'final native snapshot differs from current package')
    audit=final_packet['result']['audit'];binding=strict_json_loads(final_request['documents']['audit-binding.json'])
    verify_locators(audit,'T',binding,final_request['documents'])
    require(final_packet['result']['verdict']=='accept' and all(point['status']=='pass' for group in ('D','G','H') for point in audit[group].values()),'final native substantive/documentation/grounding audit incomplete')
    require(final['container_id'] not in {cid for group in authors.values() for cid in group},'final reviewer must be physically separate from authors')
    result={'schema':1,'status':'eligible','delivery_sha256':digest(canonical(files)),'state_sha256':digest(canonical(state)),
            'native_role_and_test_proofs':proofs,'final_native_receipt_sha256':final['native_receipt_sha256'],
            'final_audit_sha256':digest(canonical(audit)),'scope':'actual local native9phase/software evidence, not reserved F or field/thesis efficacy'}
    return result
