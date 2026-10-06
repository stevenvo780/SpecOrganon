"""Offline hypothetical audit packet from real archived N measure states.

No model, no attempt reopen, no actual audit acceptance. Writes only new scratch
snapshots under this evidence folder. Original source/runtime/archives readonly.
"""
from pathlib import Path
from types import SimpleNamespace
import copy,json,hashlib
from specorganon.neutral_autonomy import AutonomousNeutralController
from specorganon.neutral_controller import NeutralControllerError
from specorganon.common_evidence import read_snapshot
from specorganon.request_content import decode_content
from specorganon.native_response_contract import render_prompt
from specorganon.role_jobs import canonical,digest

B=Path(__file__).resolve().parent
OLD=Path('/home/stev/.codex/worktrees/strong-controls-v1/SpecOrganon/goals/method-superiority-v1/evidence')
rows=[]
for a in ('attempt-01','attempt-03','attempt-05'):
    source=OLD/('neutral-native-pilot-dev7-01' if a=='attempt-01' else 'neutral-native-pilot-dev7-final-01')/'closed-raw'/a
    root=source/'controller';seal=json.loads((source/'closure.json').read_bytes());past=[]
    def read(p):
        raw=p.read_bytes();assert seal['evidence_sha256'][str(p.relative_to(source))]==digest(raw);return json.loads(raw)
    for g in sorted((root/'generations').glob('*.json'))[:-1]:
        past.append({'reservation':read(root/'reservations'/g.name),'result':read(root/'results'/g.name),'state':read(g)['state']})
    state=copy.deepcopy(past[-1]['state']);state['stage']='audit';assert state['measurement_passed']
    obj=object.__new__(AutonomousNeutralController);obj.root=B/'local-install'/('hypothetical-audit-'+a);obj.root.mkdir(parents=True,exist_ok=True,mode=0o700);obj.policy=read(root/'initial.json')['policy']
    (obj.root/'snapshots').mkdir(exist_ok=True,mode=0o700)
    obj._get_transport=lambda:SimpleNamespace(store=SimpleNamespace(root=root/'transport/host-journal'))
    try:req,snapshot=obj._request(state,past,len(past)+1)
    except (ValueError,NeutralControllerError) as e:
        rows.append({'attempt':a,'status':'failed','reason':str(e),'hypothetical_not_dispatched':True});continue
    original=read_snapshot(snapshot['path'],snapshot['manifest_sha256'])['locators'];document=json.loads(req['documents']['evidence-context.json']);v=decode_content(document['context']) if document['encoding']=='content-refs-v1' else document['context'];assert set(v['locator_index'])==set(original)
    assert v['controller_context'] == {'control_history':state['control_history'],
        'battery_partition':state['battery_partition'],
        'prior_measurement_binding':{'binding':state['measurement_binding'],
            'passed':state['measurement_passed'],'job_id':state['measure_job'],
            'criteria_capture':state['original_criteria']}}
    for name,raw in original.items():
        sha=v['locator_index'][name];item=v['content_by_sha256'][sha];restored=canonical(item['value']) if item['encoding']=='canonical-json' else item['value'].encode();assert restored==raw and digest(restored)==sha
    raw=canonical(req);_,prompt=render_prompt(raw);(B/(a+'-hypothetical-audit-request.json')).write_bytes(raw)
    rows.append({'attempt':a,'status':'within_budget','request_bytes':len(raw),'prompt_bytes':len(prompt.encode()),'physical_locators_count':len(original),'all_physical_locators_exact':True,'all_controller_metadata_and_original_criteria_exact':True,'hypothetical_not_dispatched':True,'auditor_acceptance':None,'native_ready':False})
(B/'audit-context-regression.json').write_text(json.dumps({'schema':1,'scope':'Hypothetical audit context from actual archived passed N measures; no role or semantic assertion/qualification','request_limit':110000,'prompt_limit':128000,'rows':rows,'provider_calls':0,'goal_achieved':False},indent=2)+'\n');print(json.dumps(rows,indent=2))
