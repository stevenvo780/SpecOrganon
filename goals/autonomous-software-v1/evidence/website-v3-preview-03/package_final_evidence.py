"""Curate a sealed full campaign only. Never evaluate, repair, dispatch or publish.
Run only after the original immutable report exists; output remains private.
"""
from pathlib import Path
import json,hashlib,zipfile,datetime,statistics,shutil
base=Path(__file__).parent;validation=base.parent;run=validation/'software-comparison-v3';prep=validation/'software-comparison-v3-preparation';source=Path('/home/stev/.codex/worktrees/comparison-v3-budget/SpecOrganon');website=base/'web/public/resultados/software'
sha=lambda raw:hashlib.sha256(raw).hexdigest()
canonical=lambda value:json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
registration_raw=(prep/'registration-04.json').read_bytes();registration=json.loads(registration_raw);assert sha(registration_raw)=='0bc7182ab4713080db3120183e11ca45ad1f6f1ed752c856dc4028b24b728ed5'
report_path=run/'report.json'
if not report_path.exists():raise SystemExit('No immutable original report: no package is written.')
report_raw=report_path.read_bytes();report=json.loads(report_raw);p=json.loads((run/'budget/progress.json').read_text());ev=json.loads((run/'evaluation/progress.json').read_text())
assert report['registration_sha256']==sha(registration_raw) and report['evaluation_complete'] is True and report['design_denominator']==42 and ev['complete'] is True
assert report['gate']['status']=='released_once' and report['gate']['reserved_evaluation_allowed'] is True
assert [r['id'] for r in report['cells']]==[r['id'] for r in registration['cells']] and all(c['terminal'] is not None for c in p['cells'].values())
assert sum(len(c['rows']) for c in ev['cells'].values())==3500 and all(c['complete'] for c in ev['cells'].values())
files={'original/registration-04.json':registration_raw,'original/report.json':report_raw,'original/evaluation-progress.json':(run/'evaluation/progress.json').read_bytes()};subjects=0;observer_count=0;physical={}
for name,expected in registration['source_sha256'].items():
 path=source/name;raw=path.read_bytes();assert sha(raw)==expected,'frozen source changed: '+name;files['frozen-source/'+name]=raw
for row in registration['cells']:
 cell=run/'cells'/row['id'];snap_raw=(cell/'terminal-snapshot.json').read_bytes();snapshot=json.loads(snap_raw);delivery=(run/'exports'/row['opaque_id']/'delivery.json').read_bytes();dv=json.loads(delivery)
 assert sha(canonical(dv['files']))==p['cells'][row['id']]['terminal']['delivery_sha256']==snapshot['delivery_sha256']
 files['original/cells/'+row['id']+'/terminal-snapshot.json']=snap_raw;files['original/deliveries/'+row['opaque_id']+'.json']=delivery
 ledger=cell/'generation/case/organon.json'
 if ledger.exists():files['original/cells/'+row['id']+'/organon.json']=ledger.read_bytes()
 proof=cell/'milestone-proof.json'
 if proof.exists():physical[row['id']]=json.loads(proof.read_text())['status'];files['original/cells/'+row['id']+'/milestone-proof.json']=proof.read_bytes()
 for recipe_id,result in ev['cells'][row['opaque_id']]['rows'].items():
  ref=result.get('receipt_ref')
  if not ref:continue
  subjects+=1;receipt=Path(ref).resolve();assert receipt.is_relative_to((run/'evaluation/subjects').resolve()),'unexpected receipt path'
  files['original/execution-receipts/'+row['opaque_id']+'/'+recipe_id+'/receipt.json']=receipt.read_bytes()
  observer=result.get('observer_ref')
  if observer:
   path=Path(observer).resolve();assert path.is_relative_to((run/'evaluation/subjects').resolve());files['original/execution-receipts/'+row['opaque_id']+'/'+recipe_id+'/observer.json']=path.read_bytes();observer_count+=1
assert len(physical)==12 and all(v in ('eligible','failed') for v in physical.values()) and 'eligible' in physical.values()
notes='''# Evidencia de la campaña v3 original

42 celdas originales, tres tareas, dos familias, dos repeticiones, N/S/T/A.
El informe conserva 3500 resultados contractuales; los programas ausentes
fallan sin ejecutar sujetos. Las invocaciones físicas tienen recibos separados.
No son 3500 replicaciones de autor ni una prueba de superioridad causal general.

Los registros, entregas y fuentes congeladas se copian con sus bytes originales.
Los archivos bajo original conservan sus nombres y sus referencias históricas.
Los recibos y observadores son un extracto público; los perfiles, credenciales,
cuotas privadas y journals nativos completos permanecen fuera de este paquete.
La custodia depende del operador y del sistema de archivos. Los hashes no
prueban por sí solos la verdad de un juicio semántico ni una identidad externa.

El ZIP del toolkit rc2 separado incluye construcción Docker e instrucciones
CLI/MCP verificadas. Estas fuentes congeladas corresponden a la campaña anterior
al empaquetado de versión; SOURCE-MANIFEST identifica ambos alcances por separado.
El registro original incluye rutas e imágenes originales y no se puede trasladar
para continuar o reemplazar la campaña desde una máquina nueva. Una generación
independiente necesita otro registro previo y sus propias cuentas y presupuestos.

Para reproducir el análisis descriptivo sin modelos ni nuevos sujetos:
python analyze_recorded.py
El script verifica todos los archivos del manifest y recalcula diferencias y
estratos desde las 42 filas originales. No repite programas, no repara entregas
ni cambia puntuaciones. Los programas sellados están en original/deliveries.

Las aprobaciones locales conservan un mandato declarado. Las pruebas del toolkit
con fixtures y perturbaciones sintéticas se identifican en sus recibos separados;
no cuentan como casos nativos adicionales. Tokens normalizados y coste monetario
son desconocidos. El hito de software no demuestra eficacia alimentaria de campo
ni la tesis general.
''';files['README.md']=notes.encode()
reanalysis='''from pathlib import Path
import hashlib,json,ast,importlib.util
root=Path(__file__).resolve().parent
manifest=json.loads((root/'SOURCE-MANIFEST.json').read_text())['files_sha256']
assert all(hashlib.sha256((root/name).read_bytes()).hexdigest()==sha for name,sha in manifest.items())
definition=root/'frozen-source/experiments/software_comparison_v3/analysis.py'
spec=importlib.util.spec_from_file_location('frozen_analysis',definition);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
tree=ast.parse((root/'frozen-source/experiments/software_comparison_v3/evaluation.py').read_text());function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='comparison_groups')
def require(condition,message):
 if not condition:raise ValueError(message)
namespace={'require':require,'descriptive_differences':module.descriptive_differences}
exec(compile(ast.Module(body=[function],type_ignores=[]),'frozen-comparison-groups','exec'),namespace)
comparison_groups=namespace['comparison_groups']
report=json.loads((root/'original/report.json').read_text());rows=report['cells']
assert len(rows)==42 and comparison_groups(rows,nst_blocks=12,a_blocks=6)==report['comparisons']
for dimension,nst_count,a_count in [('task',4,2),('family',6,3)]:
 for identity,expected in report['strata'][dimension].items():
  assert comparison_groups([r for r in rows if r[dimension]==identity],nst_blocks=nst_count,a_blocks=a_count)==expected
print(json.dumps({'recorded_analysis_matches':True,'cells':42,'new_subjects':0,'new_model_calls':0}))
''';files['analyze_recorded.py']=reanalysis.encode()
manifest={'schema':1,'registration_sha256':sha(registration_raw),'report_sha256':sha(report_raw),'files_sha256':{n:sha(v) for n,v in sorted(files.items())},'native_author_cells':42,'recipe_outcomes':3500,'actual_subject_receipts':subjects,'actual_observer_reports':observer_count,'scope':'sealed original evidence extract; no profiles or full native journals; no reexecution'};files['SOURCE-MANIFEST.json']=(json.dumps(manifest,indent=2)+'\n').encode()
archive=website/'campana-v3-evidencia-publica.zip'
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
 for name,raw in sorted(files.items()):
  info=zipfile.ZipInfo('campana-v3/'+name,date_time=(2026,10,5,20,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o644<<16;z.writestr(info,raw)
(website/'campana-v3-informe.json').write_bytes(report_raw)
receipt={'schema':1,'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':manifest['scope'],'archive':archive.name,'bytes':archive.stat().st_size,'sha256':sha(archive.read_bytes()),'manifest':manifest,'published':False,'source_originals_changed':False,'subjects_or_models_started_by_packager':0};(base/'final-evidence-package-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({k:receipt[k] for k in ['archive','bytes','sha256','published']}))
