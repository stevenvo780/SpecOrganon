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


print(json.dumps(baseline(sys.argv[1])))
