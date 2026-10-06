"""Export finite engineering/native development evidence; preserve old downloads.

Allowlisted artifacts only. No profiles, tokens, environment or private receipts.
Run once the native development attempt is terminal for a stable publication.
"""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile
from specorganon import engine

BASE=Path(__file__).resolve().parent
CANDIDATE=Path('/home/stev/.codex/worktrees/method-superiority/SpecOrganon')
WEB=Path('/datos/workspaces/personal/ViewSpecOrganon/web')
OUT=BASE/'evidence/website-engineering-02'
RUN=Path('/datos/workspaces/personal/specorganon-validation/method-superiority-v1/development-rangeaudit-01')
PREFIX='specorganon-candidate-0.2.0rc3.dev2'


def sha(data): return hashlib.sha256(data).hexdigest()
def read(path): return json.loads(path.read_text())
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def main():
    if (OUT/'preparation-receipt.json').exists():
        raise RuntimeError('Publication export is already sealed; create a versioned export instead')
    registration=read(BASE/'development/registration-rangeaudit-01.json')
    assert all(sha((CANDIDATE/p).read_bytes())==h for p,h in registration['source_sha256'].items())
    progress=read(RUN/'controller/progress.json');state=engine.get_state(RUN/'case')
    history=progress['history'];terminal=read(RUN/'terminal-failure.json') if (RUN/'terminal-failure.json').exists() else None
    actions=[read(p) for p in sorted(RUN.glob('action-*.json'))]
    complete=bool(actions and actions[-1]['result'].get('package_allowed'))
    assert terminal is not None or complete, 'Wait for terminal native attempt before export'
    independent=None
    if complete:
        measured=read(RUN/'independent-public-checks/result.json')
        independent=read(Path(measured['test_job_ref']).with_name('stdout.bin'))
        independent['actual_isolated_container']=measured['provenance']=='actual_isolated_container'
        independent['exit_code']=measured['exit_code']
        independent['timed_out']=measured['timed_out']
        independent['truncated_streams']=measured['truncated_streams']
    installed=read(BASE/'evidence/installed-typed-runtime-01.stdout')
    assert installed['version']=='0.2.0rc3.dev2' and installed['actual_stdio']
    assert all(registration['source_sha256']['src/specorganon/'+p]==h
               for p,h in installed['installed_core_source_sha256'].items())
    historical=read(Path('/datos/workspaces/personal/specorganon-validation/autonomous-software-v1/software-comparison-v3-preparation/registration-04.json'))
    assert all(sha((Path(historical['source_root'])/p).read_bytes())==h for p,h in historical['source_sha256'].items())
    assert sha((BASE.parent.parent/'GOAL.md').read_bytes())=='e8341bea380cc357ad9e02ec4689a4ed47fe198ba06e4c98639f29264c314c36'
    public=OUT/'web/public/resultados/software';public.mkdir(parents=True,exist_ok=True)
    prior=read(WEB/'public/resultados/software/descargas-manifest.json')
    for name,h in prior['files'].items():
        assert sha((WEB/'public/resultados/software'/name).read_bytes())==h
    native={
        'case':'RangeAudit development 01','classification':'public native development, not reserved comparison',
        'format':'items-v1','status':'complete' if complete else 'failed',
        'nine_phase_delivery':complete,'accepted_phases':[p for p,v in state['phases'].items() if v['accepted']],
        'author_calls_completed':sum(h['action']=='author' for h in history),
        'peer_calls_completed':sum(h['action'] in {'review','approval'} for h in history),
        'phase_reviews_completed':sum(h['action']=='review' for h in history),
        'mandate_checks_completed':sum(h['action']=='approval' for h in history),
        'native_test_jobs_completed':sum(h['action']=='test' for h in history),
        'author_corrections':sum(h['action']=='author' and h['phase']=='validate' for h in history)-1,
        'controller_actions_completed':len(actions),
        'pending_action':{k:progress['pending'].get(k) for k in ['job_id','phase','action','status']} if progress['pending'] else None,
        'terminal_failure':terminal,
        'stop_reason':terminal['reason'] if terminal else 'nine accepted phases and verified isolated tests',
        'independent_public_checks':independent,
        'model_routes':{'author':'Codex gpt-6.1-sol medium','reviewer':'Gemini 3.8 Flash medium'},
        'usage_reported':[{'job_id':h['job_id'],'role':h['action'],'usage':h.get('usage_reported')} for h in history],
        'reserved_subjects':0,'F_evaluated':False,'comparison_performed':False,
        'execution_summary':[]}
    for path in sorted((RUN/'transport/host-journal').glob('*/receipt.json')):
        receipt=read(path)
        native['execution_summary'].append({k:receipt.get(k) for k in ['job_id','duration_seconds','exit_code','timed_out','truncated_streams']})
    native['sum_isolated_job_seconds']=sum(r['duration_seconds'] for r in native['execution_summary'])
    native['registration_to_completion_seconds']=(datetime.datetime.fromisoformat(actions[-1]['at'])-
        datetime.datetime.fromisoformat(registration['registered_at'])).total_seconds()
    native['resource_limits']='Resource observations of one development attempt; no free/SDD timing comparison'
    candidate={
        'schema':1,'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'classification':'engineering candidate and native development; no method superiority claim',
        'version':'0.2.0rc3.dev2','candidate_commit':registration['candidate_commit'],
        'docker_image':'sha256:3b984512f460b9cb9cddac6cdb55634515b4831d1183684d7e7b557f86170131',
        'host_tests_passed':186,'host_subtests_passed':46,'installed_runtime':installed,
        'static_code_review':{'model':'gemini/3.8-flash','verdict':'accept','tests_executed':False},
        'new_format':'explicit items-v1; legacy SDK manifest-v1 remains available',
        'semantics_preserved':['nine current accepted phases','meaningful author content','valid existing dependencies',
            'independent current review','actual isolated test provenance','original resource bounds'],
        'custody':['immutable original packet','derived manifest and metadata attribution','source snapshot verification','dual hash replay guard'],
        'historical_sources_unchanged':len(historical['source_sha256']),'native_sources_frozen':len(registration['source_sha256']),
        'historical_v3_reopened':False,'historical_scores_changed':False,'native_development':native,
        'goal_status':'active','method_superiority_proven':False,
        'next_stage':'Resolve observed development blockers, then reliability cases and preregistered common comparison with replication'}
    # Public receipt excludes host path and exact account identity.
    installed_public=dict(installed);installed_public.pop('installed_module',None)
    candidate['installed_runtime']=installed_public
    write(public/'candidato-rc3-dev2-verificacion.json',candidate)
    write(OUT/'engineering-02-public-receipt.json',candidate)
    goal=(BASE/'GOAL.md').read_text()
    (public/'meta-mejor-metodo.md').write_text(goal)
    (public/'rangeaudit-desarrollo-01-contrato.md').write_text((BASE/'development/range-audit-contract.md').read_text())
    if complete:
        with zipfile.ZipFile(public/'rangeaudit-desarrollo-01-entrega.zip','w',zipfile.ZIP_DEFLATED) as archive:
            for path in sorted((RUN/'controller/delivery').rglob('*')):
                if path.is_file():archive.write(path,str(path.relative_to(RUN/'controller/delivery')))
            archive.write(BASE/'development/check_rangeaudit_public.py','check_rangeaudit_public.py')
            archive.write(BASE/'development/range-audit-contract.md','CONTRACT.md')
            archive.writestr('native-case-state-public.json',json.dumps(state,ensure_ascii=False,indent=2).replace(str(RUN),'<native-development-run>'))
            archive.writestr('development-verification.json',json.dumps(native,ensure_ascii=False,indent=2))
    wheel='specorganon-0.2.0rc3.dev2-py3-none-any.whl'
    (public/wheel).write_bytes((BASE/'evidence'/wheel).read_bytes())
    # Preserve the previous public source allowlist; append new reviewed contract and controls.
    with zipfile.ZipFile(WEB/'public/resultados/software/specorganon-autonomous-candidate-0.2.0rc2.zip') as old:
        allow={name.split('/',1)[1] for name in old.namelist() if '/' in name and not name.endswith('/')}
    allow.update({'src/specorganon/author_contract.py','docs/software_author_contract.md',
                  'tests/test_author_contract.py','tests/test_typed_author_content.py',
                  'tests/test_runner.py','tests/test_runner_manifest_schema.py','tests/test_controller_native_role.py',
                  'tests/conftest.py','workflows/synthetic_full.json'})
    # Historical parser controls: no prompts/profiles; both stream and expected result are redacted identically.
    parser_controls=['gemini-stream-surface-03-native.stdout.jsonl','component-review-03-native.stdout.jsonl',
        'component-review-03.stdout.json','controller-codex-effective-features.stdout',
        'component-review-04-native-call.stdout.jsonl','component-review-04-textual-verdict.json',
        'native-surface-01-native-call.stdout.jsonl','native-surface-01-receipt.json']
    public_parser_hashes={}
    source_names=[]
    with zipfile.ZipFile(public/(PREFIX+'.zip'),'w',zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(allow):
            path=CANDIDATE/name
            if path.is_file(): archive.write(path,PREFIX+'/'+name);source_names.append(name)
        archive.write(BASE/'verify_installed_typed.py',PREFIX+'/verify_installed_typed.py')
        for name in parser_controls:
            path=CANDIDATE/'goals/autonomous-software-v1/evidence'/name
            text=path.read_text().replace(str(CANDIDATE),'<candidate-source>').replace(str(BASE.parent.parent),'<project>')
            archive.writestr(PREFIX+'/goals/autonomous-software-v1/evidence/'+name,text)
            public_parser_hashes[name]={'original_sha256':sha(path.read_bytes()),'public_sha256':sha(text.encode()),
                'scope':'historical parser regression data; private root paths redacted'}
        archive.writestr(PREFIX+'/CANDIDATE.md',
            '# Candidato de desarrollo 0.2.0rc3.dev2\n\n'
            'La campaña v3 queda cerrada; este paquete contiene código posterior. No demuestra superioridad.\n\n'
            'Instalación: `uv sync --frozen --extra dev`. Docker: '
            '`docker build -f docker/release/Dockerfile -t specorganon-dev2 .`.\n\n'
            'Pruebas del cambio: `uv run pytest tests/test_typed_author_content.py tests/test_author_contract.py '
            'tests/test_software_controller.py tests/test_software_controller_resources.py '
            'tests/test_artifact_guidance.py tests/test_controller_native_role.py '
            'tests/test_software_comparison_v3_cells.py tests/test_runner.py tests/test_runner_manifest_schema.py`.\n\n'
            'El SDK Controller conserva manifest-v1; seleccionar explícitamente `author_format="items-v1"` '
            'en un caso nuevo. Las celdas nuevas T/A usan el contrato tipado.\n\n'
            'No reanudar archivos frozen de v3 con este candidato. Las credenciales no están incluidas; '
            'cada usuario debe iniciar su propia sesión en un volumen propio. '
            'El Docker de instalación y el runtime del autor nativo son imágenes distintas.\n')
    # Engineering controls contain only fixed logs and reviews, never native profiles/host receipts.
    with zipfile.ZipFile(public/'rc3-dev2-evidencia-ingenieria.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for name in ['typed-content-tests-01.stdout','typed-content-tests-01.stderr',
                     'typed-content-tests-02.stdout','typed-content-tests-02.stderr',
                     'typed-content-tests-03.stdout','typed-content-tests-03.stderr',
                     'typed-content-tests-04.stdout','typed-content-tests-04.stderr',
                     'typed-design-review.json','typed-code-review.json','typed-capacity-preflight.json']:
            text=(BASE/'evidence'/name).read_text().replace(str(CANDIDATE),'<candidate-source>').replace(str(BASE.parent.parent),'<project>')
            archive.writestr(name,text)
        archive.write(public/'candidato-rc3-dev2-verificacion.json','verificacion.json')
    manifest=dict(prior);manifest['files']=dict(prior['files'])
    manifest['scope']=prior['scope']+'; appended typed engineering candidate and terminal native development'
    for path in sorted(public.iterdir()):
        if path.is_file(): manifest['files'][path.name]=sha(path.read_bytes())
    write(public/'descargas-manifest.json',manifest)
    write(OUT/'preparation-receipt.json',{'at':candidate['at'],'prior_downloads_preserved':len(prior['files']),
        'new_files':[p.name for p in public.iterdir() if p.name not in prior['files'] and p.name!='descargas-manifest.json'],
        'candidate_source_paths':source_names,'source_manifest':{n:sha((CANDIDATE/n).read_bytes()) for n in source_names},
        'historical_parser_controls':public_parser_hashes,
        'native_development_terminal':True,'method_superiority_proven':False})
    print(json.dumps(candidate))


if __name__=='__main__':main()
