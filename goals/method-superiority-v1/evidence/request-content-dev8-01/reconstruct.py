"""Offline regression of archived refused requests. Never dispatches a model."""
import sys, pathlib, json, copy, os, subprocess, hashlib
import specorganon.neutral_controller as base
import specorganon.neutral_autonomy as autonomy
from specorganon.role_jobs import canonical, digest
from specorganon.native_response_contract import render_prompt

ARCHIVE=pathlib.Path('/home/stev/.codex/worktrees/strong-controls-v1/SpecOrganon/goals/method-superiority-v1/evidence')
B=pathlib.Path(__file__).resolve().parent


def read_history(a):
    folder=ARCHIVE/('neutral-native-pilot-dev7-01' if a in ('attempt-01','attempt-02') else 'neutral-native-pilot-dev7-final-01')/'closed-raw'/a
    controller=folder/'controller';closed=json.loads((folder/'closure.json').read_bytes());row=json.loads((folder/'outcome.json').read_bytes())
    assert closed['outcome_sha256']==digest((folder/'outcome.json').read_bytes())
    past=[];pins={}
    paths=sorted((controller/'generations').glob('*.json'))
    def read(p):
        raw=p.read_bytes();key=str(p.relative_to(folder));assert closed['evidence_sha256'][key]==digest(raw);pins[key]=digest(raw);return json.loads(raw)
    for g in paths[:-1]:
        past.append({'reservation':read(controller/'reservations'/g.name),
                     'result':read(controller/'results'/g.name),'state':read(g)['state']})
    state=copy.deepcopy(past[-1]['state']);policy=read(controller/'initial.json')['policy']
    return state,past,policy,pins,folder


def baseline(a):
    # Separate diagnostic process only; frozen historical source imported.
    state,past,policy,pins,folder=read_history(a)
    cls=autonomy.AutonomousNeutralController if policy['method']=='N' else base.NeutralController
    obj=object.__new__(cls);obj.policy=policy
    original=base.LIMITS['request_bytes'];base.LIMITS['request_bytes']=10_000_000
    base.render_prompt=lambda raw:None;autonomy.render_prompt=lambda raw:None
    req,ref=obj._request(state,past,len(past)+1);assert ref is None
    return {'bytes':len(canonical(req)),'original_limit':original,
            'context':{'files':json.loads(req['documents']['current-files.json']),
                       'documents':json.loads(req['documents']['current-documents.json']),
                       'history':json.loads(req['documents']['history.json'])}}

if len(sys.argv)>1 and sys.argv[1]=='baseline':
    print(json.dumps(baseline(sys.argv[2])));raise SystemExit(0)

from specorganon.request_content import decode_content

rows=[]
for n in range(1,7):
    a=f'attempt-{n:02d}';state,past,policy,pins,folder=read_history(a)
    env=os.environ.copy();env['PYTHONPATH']='/home/stev/.codex/worktrees/strong-controls-v1/SpecOrganon/src'
    # This script imports only its old baseline branch dependencies there;
    # request_content import is intentionally deferred below in future only.
    response=subprocess.check_output([sys.executable,str(B/'baseline.py'),a],env=env)
    old=json.loads(response)
    cls=autonomy.AutonomousNeutralController if policy['method']=='N' else base.NeutralController
    obj=object.__new__(cls);obj.policy=policy
    request,snapshot=obj._request(state,past,len(past)+1);assert snapshot is None
    document=json.loads(request['documents']['package-context.json'])
    context=decode_content(document['context']) if document['encoding']=='content-refs-v1' else document['context']
    assert canonical({k:context[k] for k in ('files','documents','history')})==canonical(old['context']),a
    if policy['method']=='N':
        assert context['controller_context']['control_history']==state['control_history']
    else:
        assert 'controller_context' not in context
    raw=canonical(request);_,prompt=render_prompt(raw)
    assert old['bytes']>110000 and len(raw)<=110000 and len(prompt.encode())<=128000
    assert base.LIMITS['request_bytes']==110000
    (B/(a+'-new-request.json')).write_bytes(raw)
    rows.append({'attempt':a,'method':policy['method'],'stage':state['stage'],'old_full_request_canonical_bytes':old['bytes'],
                 'new_request_canonical_bytes':len(raw),'new_rendered_prompt_bytes':len(prompt.encode()),
                 'context_canonical_sha256':digest(canonical(context)),'all_context_exact':True,
                 'current_files_exact':context['files']==state['files'],'current_documents_exact':context['documents']==state['documents'],
                 'historical_packets_captures_metadata_exact':True,'history_length':len(past),'input_sha256':pins,
                 'new_request_sha256':digest(raw),'source_archive':str(folder)})
report={'schema':1,'scope':'Offline reconstruction using exact archived original context, no native rerun or qualification',
        'version':'0.2.0rc3.dev8','request_limit_unchanged':110000,'prompt_limit_unchanged':128000,
        'new_model_calls':0,'rows':rows,'complete_native_packages':None,'competence_established':False,'goal_achieved':False}
(B/'request-regression.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps([{k:r[k] for k in ('attempt','old_full_request_canonical_bytes','new_request_canonical_bytes','new_rendered_prompt_bytes','all_context_exact')} for r in rows],indent=2))
