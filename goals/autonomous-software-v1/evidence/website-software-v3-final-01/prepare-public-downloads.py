from pathlib import Path
import json,hashlib,zipfile,shutil,datetime
base=Path(__file__).parent;public=base/'web/public/resultados/software';release=base.parent/'software-v3-clean-release-01';run=base.parent/'software-comparison-v3';root=Path('/datos/workspaces/personal/SpecOrganon/goals/autonomous-software-v1')
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
report=json.loads((base/'report-posthoc-v1.json').read_text())
shutil.copy2(release/'dist-a/specorganon-0.2.0rc2-py3-none-any.whl',public/'specorganon-0.2.0rc2-py3-none-any.whl')
shutil.copy2(release/'specorganon-autonomous-candidate-0.2.0rc2.zip',public/'specorganon-autonomous-candidate-0.2.0rc2.zip')
assert sha(public/'specorganon-0.2.0rc2-py3-none-any.whl')=='343bf555a92f911209bef98786a9241b3a3feb3282fca88407147cbd64cafd31'
assert sha(public/'specorganon-autonomous-candidate-0.2.0rc2.zip')=='4ea547052bc1497fd851535ec891a980b334363a84e0dae3dde491bb76723c56'
verification={'schema':1,'scope':'measured rc2 candidate; no whole-platform or field proof'}
for key,name in [('installed_release','comparison-v3-rc2-clean-release-03.json'),('Docker_Codex','comparison-v3-rc2-codex-lab-01.json'),('actual_extracted_ZIP_build','comparison-v3-rc2-source-kit-build-01.json'),('copied_ledger_controls','comparison-v3-rc2-method-controls-01.json'),('originals_preservation','comparison-v3-final-preservation-01.json')]:
    verification[key]=json.loads((root/'evidence'/name).read_text())
(public/'rc2-verificacion.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2)+'\n')
criteria={'schema':1,'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'local software milestone; complete recorded finite campaign with explicit post-campaign aggregation repair','goal_status':'pending_publication_verification','original_GOAL_unchanged':True,'field_or_general_thesis_proven':False,'clean_primary_pipeline_completion':False,'criteria':[
    {'id':1,'criterion':'Base técnica e integridad PDF','verdict':'verified_scoped','evidence':'145 targeted technical checks;235 source-mounted candidate checks;rc2 installed69;20 PDF pages,bad pins rejected','limit':'whole-platform suite not green; old host/historical fixture failures remain outside targeted profile'},
    {'id':2,'criterion':'Método operable y entrega nueva','verdict':'fulfilled_local','evidence':'cell01/06 FractionMix:9 current phases, separate Gemini reviews, alternatives/links, actual own Docker receipts,README;F84/84,D8/8,G6/6,H9/9 each','limit':'2/12 T full packages; declared local mandate, not authenticated external identity or field efficacy'},
    {'id':3,'criterion':'Controles, reapertura y reanudación','verdict':'verified_instrument','evidence':'copies of real ledger: declared synthetic contradiction,removed receipt,premise changed27 stale descendants; installedCLI/MCP SIGKILL/replay without duplicates','limit':'synthetic perturbations/fixtures; no semantic contradiction detector or extra native successes'},
    {'id':4,'criterion':'Comparación prospectiva','verdict':'fulfilled','evidence':'registered before generation42cells,3types,2families,2rep;N12/S12/T12/A6,fixedbudgets/stopping,physical author/reviewer/evaluator separation','limit':'trusted original profiles/OS custody;absolute Gemini internal tools off not proven'},
    {'id':5,'criterion':'Evaluación y transferencia','verdict':'completed_adverse_with_aggregation_deviation','evidence':'all42closed,3500outcomes,916actualsubjects,11pairedcomparisons,5strata;PolicyPick/ListPatch transfer with same toolkit failed; no replacements','limit':'primaryreportexit1;companion zero rule for2 invalidpasslocators,universal verification,separate rawassertions,externalstaticreview;F:N75%,T16.67%,S/A0'},
    {'id':6,'criterion':'Release y publicación','verdict':'prepared_pending_public_verification','evidence':'versionedrc2,wheel/sourceZIP,actualZIPbuild,DockerCodexMCP24,CLI15/MCP15;portableevidence reanalysis F3500/allpasslocators/pairs/strata','limit':'installed69 applies samewheel;oldersource69 appliesolderZIP;currentZIPactualbuild/MCP measuredseparately'}],
    'comparison':{'cells':42,'recipes':3500,'actual_subjects':916,'complete_generation':6,'T9':2,'full_packages':2,'native_attempts':sum(c['resources']['admitted_native_attempts'] for c in report['cells']),'own_tests':sum(c['resources']['admitted_own_tests'] for c in report['cells']),'tokens_normalized':None,'money':None},
    'aggregation_deviation':{'original_report_exit_code':1,'primary_report_present':False,'companion_sha256':sha(base/'report-posthoc-v1.json'),'invalid_pass_points':report['aggregation']['invalid_points'],'static_reviewer':'Gemini3.8Flash','review_job_id':'a6337dc6c90744a49202480f28495eab','review_verdict':'accept','review_tests_executed':False},'remaining':['Verify final private rendering and downloads','Deploy existing authorized Vercelproject and verify public page/downloads']}
(public/'hito-software-criterios.json').write_text(json.dumps(criteria,ensure_ascii=False,indent=2)+'\n')
notes='''# Las 42 entregas originales

Todos los archivos sellados conservan sus bytes, incluso entregas parciales o
ausentes. Cada metadata.json conserva el estado de generación, F y full_package.
No se selecciona la mejor repetición. cell-01 y cell-06 son las dos entregas T9
FractionMix completas: F84/84, D8/8, G6/6, H9/9. Las otras conservan su resultado.
Los ledgers y revisiones están en el ZIP de evidencia separado.

Uso de FractionMix: CPython3.12 y biblioteca estándar, desde cell-01:
python3 -E -s -B fractionmix.py < entrada.json
Su README original explica contrato, errores, recursos y ejemplos. La campaña
ejecutó estos mismos archivos en Docker con CPython3.12.3. El ZIP del toolkit
permite construir ese entorno; no se promete corrección para otras versiones.

La comparación completa está en campana-v3-informe.json. Se reparó sólo la
agregación tras exit1 primario, sin repetir casos ni modificar sus fuentes.
El hito local no demuestra superioridad general ni eficacia alimentaria de campo.
'''
files={'LEEME.md':notes.encode()}
for row in report['cells']:
    payload=json.loads((run/'exports'/row['opaque_id']/'delivery.json').read_text())
    for name,content in payload['files'].items():
        assert Path(name).name==name;files[row['id']+'/'+name]=content.encode()
    files[row['id']+'/metadata.json']=(json.dumps({k:row[k] for k in ['id','task','family','method','rep','generation_status','functional','full_package']},ensure_ascii=False,indent=2)+'\n').encode()
files['MANIFEST.json']=(json.dumps({'schema':1,'report_companion_sha256':sha(base/'report-posthoc-v1.json'),'files_sha256':{name:hashlib.sha256(raw).hexdigest() for name,raw in files.items()}},indent=2)+'\n').encode()
with zipfile.ZipFile(public/'campana-v3-entregas.zip','w',compression=zipfile.ZIP_DEFLATED) as z:
    for name,raw in sorted(files.items()):
        i=zipfile.ZipInfo('entregas/'+name,date_time=(2026,10,5,20,0,0));i.compress_type=zipfile.ZIP_DEFLATED;i.external_attr=0o644<<16;z.writestr(i,raw)
old=json.loads((public/'descargas-manifest.json').read_text())
for name,digest in old['files'].items():
    if name!='avance.json':assert sha(public/name)==digest
new=['campana-v3.json','campana-v3-informe.json','campana-v3-informe.md','campana-v3-resumen.json','campana-v3-evidencia-publica.zip','campana-v3-entregas.zip','specorganon-0.2.0rc2-py3-none-any.whl','specorganon-autonomous-candidate-0.2.0rc2.zip','hito-software-criterios.json','rc2-verificacion.json']
manifest={'schema':1,'scope':'Complete recorded finite campaign and rc2;companion aggregation after primaryexit1;11 historical immutable downloads preserved','files':{name:sha(public/name) for name in dict.fromkeys([*old['files'],*new])}}
(public/'descargas-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
p=base/'web/src/components/SoftwareCampaign.tsx';s=p.read_text().replace("['campana-v3-evidencia-publica.zip','Evidencia y reanálisis']","['campana-v3-evidencia-publica.zip','Evidencia y reanálisis'],['campana-v3-entregas.zip','Las 42 entregas originales']").replace('Informe original completo','Informe complementario completo');p.write_text(s)
print(json.dumps({'files':len(manifest['files']),'historical_immutable_preserved':11,'criteria':6,'all42_deliveries_zip':sha(public/'campana-v3-entregas.zip')}))
