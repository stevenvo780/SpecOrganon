"""Post-campaign report repair. No generation, Subject execution or native review.

Original report() exited 1. This companion does not overwrite its sources or
invent report.json. Missing pass evidence is zero under the registered rule.
Auditor assertions remain separate from universally verified point statuses.
"""
from pathlib import Path
import json,hashlib,copy,datetime
from experiments.software_comparison_v3.registration import Registration
from experiments.software_comparison_v3.campaign import Campaign
from experiments.software_comparison_v3.evaluation import Evaluation,score_points,comparison_groups,require
from experiments.software_comparison_v3.audit_evidence import resolve,validate_response,EvidenceError
from experiments.software_comparison_v3.rubric import rubric
from experiments.software_comparison_v3.analysis import functional_summary
from experiments.software_comparison_v3.reserved import recipes
from specorganon.role_jobs import _json,canonical,digest

base=Path(__file__).resolve().parent;validation=base.parent
source=Path('/home/stev/.codex/worktrees/comparison-v3-budget/SpecOrganon')
run=validation/'software-comparison-v3';prep=validation/'software-comparison-v3-preparation'
target=base/'report-posthoc-v1.json';assert not target.exists() and not (run/'report.json').exists()
registration=Registration(prep/'registration-04.json',source);registration.validate()
assert registration.sha=='0bc7182ab4713080db3120183e11ca45ad1f6f1ed752c856dc4028b24b728ed5'
c=Campaign(registration,prep/'quota-admission-06.json');e=Evaluation(c)
budget=_json(run/'budget/progress.json');progress=_json(run/'evaluation/progress.json')
assert progress['complete'] and all(p['complete'] for p in progress['cells'].values())
assert sum(len(p['rows']) for p in progress['cells'].values())==3500
gate=budget['evaluation'];assert gate['status']=='released_once' and gate['reserved_evaluation_allowed']
original_paths=[prep/'registration-04.json',run/'budget/progress.json',run/'evaluation/progress.json',run/'evaluation/policy.json']
original_paths += [run/'cells'/r['id']/'terminal-snapshot.json' for r in c.value['cells']]
original_paths += [run/'exports'/r['opaque_id']/'delivery.json' for r in c.value['cells']]
before={str(p):digest(p.read_bytes()) for p in original_paths}
_,payloads=e.exports();rows=[];invalid=[]
for row in c.value['cells']:
    snapshot=_json(run/'cells'/row['id']/'terminal-snapshot.json')
    require(snapshot['delivery_sha256']==payloads[row['opaque_id']]['delivery_sha256'],'changed delivery')
    outcomes=list(progress['cells'][row['opaque_id']]['rows'].values())
    assert len(outcomes)==len(recipes(row['task']))
    functional=functional_summary(recipes(row['task']),outcomes,evaluated=True)
    definition=rubric(row['method']);audit=None;native=None;dual={}
    if snapshot['status']=='complete':
        runner,evidence=c.cell(row)
        if row['method']=='T':
            packet=_json(runner.root/'common-final-review.json');request=_json(runner.root/'common-final-request.json');identity='common-final-review'
            runner.controller.package_gate()
        else:
            state=_json(runner.root/'progress.json');runner.validate_closed(state);identity=state['history'][-1]['job_id']
            packet=_json(runner.root/(identity+'-packet.json'));request=_json(runner.root/(identity+'-request.json'))
        native=evidence.role(identity,'review',request=request,packet=packet)
        binding=json.loads(request['documents']['audit-binding.json'])
        audit=validate_response(packet['result']['audit'],row['method'],binding)
        require(binding['delivery_sha256']==snapshot['delivery_sha256'],'audit binding changed')
    status='inconclusive' if snapshot['status']=='infra_inconclusive' else 'fail'
    points={group:copy.deepcopy(audit[group]) if audit else {identity:{'status':status,'reason':'native final audit missing after '+snapshot['status'],'evidence':[]} for identity in definition[group]} for group in ('D','G','H')}
    for group in ('D','G','H'):
        for identity,entry in points[group].items():
            errors=[];asserted=entry['status']
            if asserted=='pass':
                for locator in entry['evidence']:
                    try:resolve(locator,request['documents'])
                    except EvidenceError as exc:errors.append({'locator':locator,'exception_type':type(exc).__name__,'reason':str(exc)})
            if errors:
                entry['status']='fail';entry['reason']='Registered missing-evidence rule: invalid pass locator; original auditor assertion retained separately'
                invalid.append({'id':row['id'],'dimension':group,'point':identity,'auditor_status':asserted,'verified_status':'fail','score':0,'errors':errors})
            dual[group+'/'+identity]={'auditor_status':asserted if audit else None,'verified_status':entry['status'],'errors':errors}
    qualitative={'scores':{group:score_points(p) for group,p in points.items()},'points':points,'native_assertions':audit,'point_verification':dual,'native_final_receipt_sha256':native['native_receipt_sha256'] if native else None,'semantic_scope':'existing separate native judgment; frozen evidence resolver applied to every pass; invalid evidence zero by registered rule'}
    points_ok=all(score['fail']==score['inconclusive']==0 for score in qualitative['scores'].values())
    rows.append({**row,'generation_status':snapshot['status'],'evaluation_status':'complete','functional':functional,'qualitative':qualitative,'full_package':functional['contract_complete'] and points_ok,'resources':e.resources(row)})
    print(json.dumps({'cell':row['id'],'recorded_results':len(outcomes),'models_or_subjects_started':0}),flush=True)
comparisons=comparison_groups(rows,nst_blocks=12,a_blocks=6);strata={}
for dimension,nst_count,a_count in [('task',4,2),('family',6,3)]:
    strata[dimension]={identity:comparison_groups([r for r in rows if r[dimension]==identity],nst_blocks=nst_count,a_blocks=a_count) for identity in sorted({r[dimension] for r in rows})}
registration.validate();assert before=={str(p):digest(p.read_bytes()) for p in original_paths}
result={'schema':1,'registration_sha256':registration.sha,'gate':gate,'cells':rows,'comparisons':comparisons,'strata':strata,'generation_cells':42,'evaluation_complete':True,'design_denominator':42,'field_or_general_thesis_proven':False,'native_replicate_unit':'author/task/family/rep cell, not each recipe','aggregation':{'version':'posthoc-v1','at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'original_report_exit_code':1,'original_report_present':False,'original_exception':'EvidenceError: empty evidence cannot support pass','rule':'missing evidence zero, registered before generation; exhaustive pass-locator verification','invalid_points':invalid,'new_model_calls':0,'new_subject_calls':0,'originals_sha256_unchanged':before,'original_source_modified':False,'scope':'companion closure after native report failure; not a clean primary pipeline completion'}}
target.write_bytes(canonical(result)+b'\n');print(json.dumps({'report':str(target),'sha256':digest(target.read_bytes()),'invalid_points':invalid}),flush=True)
