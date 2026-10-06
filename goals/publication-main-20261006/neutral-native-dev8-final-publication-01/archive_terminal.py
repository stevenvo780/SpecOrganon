"""Read closed originals and archive only sealed bytes; no controller imports/runs."""
from pathlib import Path,PurePosixPath
import json,hashlib,datetime,shutil,re
r=Path(__file__).resolve().parents[3]; pub=Path(__file__).parent
runtime=Path('/datos/workspaces/personal/specorganon-validation/method-superiority-v1/neutral-public-native-dev8-01')
candidate=Path('/home/stev/.codex/worktrees/request-content-v1/SpecOrganon')
out=r/'goals/method-superiority-v1/evidence/neutral-native-dev8-final-01';out.mkdir(exist_ok=True)
h=lambda raw:hashlib.sha256(raw).hexdigest()
planraw=(runtime/'plan.json').read_bytes();plan=json.loads(planraw);assert h(planraw)=='30dd4cf8a4050198f2604057099c3c6f9715b197d474527cc3d75801f49c4215'
assert all(h((candidate/p).read_bytes())==sha for p,sha in plan['source_sha256'].items());assert len(plan['source_sha256'])==56
admission=candidate/'goals/method-superiority-v1/evidence/neutral-native-dev8-admission-01'
terminal=json.loads((admission/'pilot-run-terminal.json').read_text());assert terminal['exit_code']==0 and not Path('/proc/2457956').exists() and not Path('/proc/2457954').exists()
report_raw=(admission/'pilot-run.stdout').read_bytes();report=json.loads(report_raw);assert report['status']=='closed' and report['closed_attempts']==6 and report['planned_denominator']==6 and report['plan_sha256']==h(planraw)
rows=[];verified=0;archive_files=0;archive_bytes=0;oldverified=0;excluded=[]
for pos in range(1,7):
 name=f'attempt-{pos:02d}';a=runtime/name;o_raw=(a/'outcome.json').read_bytes();o=json.loads(o_raw);closure_raw=(a/'closure.json').read_bytes();closure=json.loads(closure_raw)
 assert h(o_raw)==closure['outcome_sha256'];assert o in report['rows'];assert o['plan_sha256']==h(planraw)
 for path,sha in closure['evidence_sha256'].items():
  p=PurePosixPath(path);assert not p.is_absolute() and '..' not in p.parts
  target=a/path;assert not target.is_symlink() and target.is_file();raw=target.read_bytes();assert h(raw)==sha;verified+=1
 for path,sha in o['evidence_sha256'].items():assert closure['evidence_sha256'][path]==sha
 c=o['controller_report'];function=o['public_development_functionality'];assert o['common_complete'] is None and o['external_F'] is None
 assert function['status']=='observed' and function['result']['passed']==function['result']['cases']
 state=json.loads(sorted((a/'controller/generations').glob('*.json'))[-1].read_text())['state']
 row={'position':pos,'attempt':o['attempt'],'status':c['status'],'stage':c['stage'],'failure':c['failure'],'last_admission_failure':state.get('last_admission_failure'),'native_ready':c['native_ready'],'method_review_ready':c['method_review_ready'],'common_review_ready':c['common_review_ready'],'common_complete':None,'external_F':None,'counts':c['counts'],'public_cases':function['result']['cases'],'public_passed':function['result']['passed'],'whole_attempt_seconds':o['whole_attempt_seconds'],'shared_preparation_seconds':o['shared_preparation_seconds'],'monetary_cost':o['monetary_cost'],'token_cost_comparability':c['token_cost_comparability'],'outcome_sha256':h(o_raw),'closure_sha256':h(closure_raw)}
 if pos<=3:
  folder='neutral-native-dev8-progress-01' if pos<=2 else 'neutral-native-dev8-progress-02';old=r/'goals/method-superiority-v1/evidence'/folder/'raw'/name
  for f in old.rglob('*'):
   if f.is_file():assert f.read_bytes()==(a/f.relative_to(old)).read_bytes();oldverified+=1
  row['raw_archive']=folder+'/raw/'+name
 else:
  row['raw_archive']='neutral-native-dev8-final-01/raw/'+name
  selected=set(closure['evidence_sha256'])|{'outcome.json','closure.json'}
  for path in sorted(selected):
   source=a/path;raw=source.read_bytes()
   if source.name.endswith('.lock'):
    assert raw==b'';excluded.append({'path':name+'/'+path,'sha256':h(raw),'reason':'Empty runtime lock; sealed hash preserved, not a transferable execution lock'});continue
   assert source.name not in {'auth.json','id_rsa','id_ed25519'} and not any(x in PurePosixPath(path).parts for x in ['.codex','.gemini','sessions','node_modules','__pycache__'])
   assert not re.search(rb'\bsk-[A-Za-z0-9_-]{20,}\b|\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\b',raw),path
   dest=out/'raw'/name/path;dest.parent.mkdir(parents=True,exist_ok=True)
   if dest.exists():assert dest.read_bytes()==raw
   else:dest.write_bytes(raw)
   archive_files+=1;archive_bytes+=len(raw)
 rows.append(row)
assert [x['status'] for x in rows]==['failed','failed','review_ready','failed','review_ready','failed']
for dest,source in [('pilot-plan.json',runtime/'plan.json'),('pilot-run-terminal.json',admission/'pilot-run-terminal.json'),('pilot-run.stdout',admission/'pilot-run.stdout'),('pilot-run.stderr',admission/'pilot-run.stderr'),('report.json',admission/'pilot-run.stdout')]:
 raw=source.read_bytes();assert not re.search(rb'\bsk-[A-Za-z0-9_-]{20,}\b|\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\b',raw);(out/dest).write_bytes(raw)
summary={'schema':1,'observed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'classification':'Terminal original six-position public dev8 pilot; not reserved method comparison','plan_sha256':h(planraw),'source_bindings_verified':56,'status':'closed','closed_in_this_cut':6,'registered_original_generations':6,'failed':4,'review_ready':2,'not_evaluated_in_this_cut':0,'original_replacements':0,'driver_session':14349,'driver_pid':2457956,'parent_pid':2457954,'driver_exit_code':0,'driver_exit_interpretation':terminal['driver_exit_interpretation'],'driver_terminal_at':terminal['at'],'driver_alive_at_cut':False,'observations':rows,'public_cases':sum(x['public_cases'] for x in rows),'public_passed':sum(x['public_passed'] for x in rows),'whole_attempt_seconds_sum':sum(x['whole_attempt_seconds'] for x in rows),'common_complete':None,'external_F':None,'shared_preparation_seconds':None,'monetary_cost':None,'comparative_time_ratio':None,'token_cost_comparability':None,'competence_established':False,'T_participation':False,'method_qualification':False,'goal_achieved':False,'previous_raw_files_exact':oldverified,'new_raw_files':archive_files,'new_raw_bytes':archive_bytes,'sealed_runtime_entries_verified':verified,'source_release_scope':'Original dev8 only; dev9partial and prospective prototype do not rewrite outcomes'}
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
(out/'archive-verification.json').write_text(json.dumps({'at':summary['observed_utc'],'sealed_runtime_entries_verified':verified,'six_outcome_sha_verified':True,'six_outcomes_equal_terminal_report':True,'previous_raw_files_exact':oldverified,'new_raw_files':archive_files,'new_raw_bytes':archive_bytes,'source_bindings_verified':56,'empty_runtime_locks_excluded':excluded,'bounded_sk_JWT_hits':0,'no_new_models_docker_tests':True},indent=2)+'\n')
(out/'README.md').write_text('# Piloto original dev8 cerrado, seis posiciones\n\nCuatro failed y dos review_ready; common_complete y F externo null en todos.648/648 comprobaciones públicas descriptivas de seis generaciones, no648 sujetos. El driver14349/PID2457956 y su padre terminaron:exit0 significa informe producido, no gate completo. Sin reemplazos, nuevos modelos, Docker ni pruebas para este archivo.\n\nRAW01/02 se conservan exactamente en ../neutral-native-dev8-progress-01/raw/;03 en ../neutral-native-dev8-progress-02/raw/. Esta carpeta añade04/05/06 y enlaces acumulativos en summary.json. Archive-verification comprueba todos los hashes sellados del runtime, los seis outcomes y su correspondencia con el informe terminal,56fuentes y plan original. Omite sólo locks vacíos del nuevo RAW; sus hashes figuran en cierres y en el recibo. No transfiere perfiles,auth,caches ni sesiones. El clon no puede reanudar ni relocalizar este run.\n\n01 falló transporte de auditoría, envoltorioGemini131246>128000;02 agotó admisión de autor de pruebas;04 añadió documentos prohibidos en esa etapa;06 agotó admisión de pruebas.03N/LedgerFold y05N/TopoPlan quedaron review_ready, no completos. RAW conserva todos los fallos y propuestas. T no participó. Preparación compartida/coste monetario/tokens comparables y ratio de tiempo desconocidos; las duraciones originales se informan sin inferencia comparativa. No demuestra competencia,calificación ni superioridad. Dev9 es ingeniería parcial distinta y el diagnóstico de factorización es una propuesta offline no implementada.\n')
(out/'SHA256SUMS').write_text(''.join(h(x.read_bytes())+'  '+str(x.relative_to(out))+'\n' for x in sorted(out.rglob('*')) if x.is_file() and x.name!='SHA256SUMS'))
print(json.dumps({k:summary[k] for k in ['closed_in_this_cut','failed','review_ready','public_passed','whole_attempt_seconds_sum','new_raw_files','new_raw_bytes','previous_raw_files_exact','sealed_runtime_entries_verified']}))
