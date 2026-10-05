from pathlib import Path
import json,datetime,hashlib
base=Path(__file__).parent;web=base/'web';run=Path('/datos/workspaces/personal/specorganon-validation/autonomous-software-v1/software-comparison-v3');prep=run.with_name('software-comparison-v3-preparation')
registration=prep/'registration-04.json';assert hashlib.sha256(registration.read_bytes()).hexdigest()=='0bc7182ab4713080db3120183e11ca45ad1f6f1ed752c856dc4028b24b728ed5'
r=json.loads(registration.read_text());raw=(run/'budget/progress.json').read_bytes();p=json.loads(raw)
report_path=base/'report-posthoc-v1.json';report=json.loads(report_path.read_text()) if report_path.exists() else None
if report:
 assert report['registration_sha256']==hashlib.sha256(registration.read_bytes()).hexdigest() and len(report['cells'])==42
 by_id={row['id']:row for row in report['cells']}
else:by_id={}
rows=[]
for row in r['cells']:
 v=p['cells'][row['id']];closed=v['terminal'];snapshot=json.loads((run/'cells'/row['id']/'terminal-snapshot.json').read_text()) if closed else None
 proof_path=run/'cells'/row['id']/'milestone-proof.json';proof=json.loads(proof_path.read_text()) if proof_path.exists() else None
 final=by_id.get(row['id']);state=snapshot['process'].get('state') if snapshot else None
 phases=sum(t['accepted'] for t in state['phases'].values()) if state else None
 files=snapshot['files'] if snapshot else {}
 rows.append({'id':row['id'],'task':row['task'],'family':row['family'],'method':row['method'],'rep':row['rep'],'status':closed['status'] if closed else ('open' if v['clock'] else 'not_started'),'native_calls':len(v['roles']),'own_tests':len(v['tests']),'elapsed_seconds':closed['elapsed_seconds'] if closed else None,'programme_present':row['task'].lower()+'.py' in files,'accepted_phases':phases,'native_T9_eligible':proof and proof['status']=='eligible' or False,'scores':{'F':final['functional']['F_total'] if final else None,**{k:final['qualitative']['scores'][k] if final else None for k in ['D','G','H']}},'full_package':final['full_package'] if final else None,'functional_breakdown':final['functional'] if final else None})
assert raw==(run/'budget/progress.json').read_bytes(),'snapshot changed during read; rerun this read-only exporter later'
value={'schema':1,'updated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'final_report_available' if report else 'generation_in_progress','registered_at':r['registered_at'],'registration_sha256':hashlib.sha256(registration.read_bytes()).hexdigest(),'source_report_sha256':hashlib.sha256(report_path.read_bytes()).hexdigest() if report else None,'planned_cells':42,'terminal_cells':sum(v['terminal'] is not None for v in p['cells'].values()),'completed_deliveries':sum(row['status']=='complete' for row in rows),'eligible_T9':sum(row['native_T9_eligible'] for row in rows),'F_evaluated':report['evaluation_complete'] if report else False,'rows':rows,'comparisons':report['comparisons'] if report else {},'strata':report['strata'] if report else {},'monetary_cost':None,'normalized_tokens':None,'field_or_general_thesis_proven':False,'candidate_version':'0.2.0rc2','candidate_controls':69,'candidate_CLI_operations':15,'candidate_MCP_operations':15,'goal_completed':False,'aggregation':report.get('aggregation') if report else None}
(web/'src/software-campaign-v3.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');(web/'public/resultados/software/campana-v3.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:value[k] for k in ['terminal_cells','completed_deliveries','eligible_T9','F_evaluated','updated_at']}))
# Update the combined progress download without rewriting historical results.
path=web/'src/software-results.json';combined=json.loads(path.read_text());combined['updated_at']=value['updated_at'];combined['comparison_v3']={'status':value['status'],'planned_cells':42,'admitted_cells':sum(v['clock'] is not None for v in p['cells'].values()),'terminal_cells':value['terminal_cells'],'completed_deliveries':value['completed_deliveries'],'new_nine_phase_deliveries':value['eligible_T9'],'registration_sha256':value['registration_sha256'],'registered_at':value['registered_at'],'F_evaluated':value['F_evaluated'],'tasks':['FractionMix','PolicyPick','ListPatch'],'task_selection_before_LotLedger_outcome':True}
combined['goal_status']='pending_final_publication' if report else 'evaluation_in_progress'
combined['scope']='Local software milestone: 42 original generations closed and all reserved evaluations recorded; post-campaign aggregation repair after primary report exit1; final publication verification pending; no field or general thesis proof' if report else 'Local software milestone: 42 original generations closed; original reserved evaluation in progress; no field or general thesis proof'
combined['remaining']=(['Comprobar el informe completo, los paquetes públicos y los criterios de cierre','Publicar y verificar la página y todas las descargas; el hito local no demuestra superioridad general ni eficacia de campo'] if report else ['Completar la única evaluación reservada de las 42 entregas originales','Comprobar informe, paquetes y criterios de cierre','Publicar y verificar la página y descargas; no declarar eficacia de campo ni tesis general'])
combined['limits']=[x.replace('La campaña nueva se detuvo tras siete de 28 celdas','La campaña histórica02 se detuvo tras siete de 28 celdas') for x in combined['limits']]
combined['autonomous_rc2']={'version':'0.2.0rc2','installed_controls':69,'CLI_operations':15,'MCP_operations':15,'synthetic_ledger_control_scenarios':3,'scope':'isolated engineering candidate; no broad whole-platform pass or field efficacy'}
path.write_text(json.dumps(combined,ensure_ascii=False,indent=2)+'\n');(web/'public/resultados/software/avance.json').write_text(json.dumps(combined,ensure_ascii=False,indent=2)+'\n')
