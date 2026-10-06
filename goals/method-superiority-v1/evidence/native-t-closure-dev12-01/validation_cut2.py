from pathlib import Path
import subprocess, json, hashlib, datetime, time, os
root=Path('/home/stev/.codex/worktrees/native-t-closure-v1/SpecOrganon')
out=root/'goals/method-superiority-v1/evidence/native-t-closure-dev12-01'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def pins():
    paths=[*sorted((root/'src/specorganon').glob('*.py')), root/'scripts/controller_native_role.py',root/'pyproject.toml',root/'uv.lock',root/'compose.yaml',root/'docker/codex/Dockerfile',root/'docker/release/Dockerfile',root/'docker/codex/seccomp-codex.json',*sorted((root/'tests').glob('test_*.py'))]
    return {str(p.relative_to(root)):sha(p) for p in paths}
def run(name, argv, env=None, timeout=600):
    before=pins();start=time.time(); r=subprocess.run(argv,cwd=root,env={**os.environ,**(env or {})},capture_output=True,timeout=timeout)
    (out/(name+'.stdout')).write_bytes(r.stdout);(out/(name+'.stderr')).write_bytes(r.stderr)
    record={'schema':1,'argv':argv,'exit_code':r.returncode,'seconds':time.time()-start,'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_sha256':before,'source_unchanged':before==pins(),'stdout_sha256':hashlib.sha256(r.stdout).hexdigest(),'stderr_sha256':hashlib.sha256(r.stderr).hexdigest(),'scope':'engineering controls; zero native model calls, no qualification or superiority','native_model_calls':0}
    (out/(name+'.receipt.json')).write_text(json.dumps(record,indent=2,sort_keys=True)+'\n');print(json.dumps({'name':name,'exit_code':r.returncode,'seconds':record['seconds'],'unchanged':record['source_unchanged'],'tail':r.stdout.decode(errors='replace')[-1600:]}),flush=True)
    if r.returncode or not record['source_unchanged']:raise SystemExit(1)
    return r
if __name__=='__main__':
    selection=['test_attempt_deadline','test_closed_execution_failure','test_closed_native_role','test_t_common_controller','test_neutral_controller','test_staged_review_regressions','test_role_jobs','test_neutral_pilot','test_native_source_custody','test_software_controller_resources','test_t_common_snapshot','test_t_measurement_custody','test_neutral_autonomy','test_dev11_review_regressions','test_request_tree','test_request_content','test_dev12_terminal_custody','test_t_native_pilot','test_t_native_entry','test_docker_create_recovery','test_dev12_partition_regressions','test_software_controller','test_software_study_harness']
    run('final-2-targeted',['uv','run','--extra','dev','python','-m','pytest','-q',*[f'tests/{s}.py' for s in selection]])
    run('final-2-actual-docker',['uv','run','--extra','dev','python','-m','pytest','-q','tests/test_neutral_docker_controls.py'],{'SPECORGANON_NEUTRAL_DOCKER_CONTROLS':'1'})
    run('final-2-build-release',['docker','build','-f','docker/release/Dockerfile','-t','specorganon-release:0.2.0rc3.dev12','.'])
    run('final-2-build-codex',['docker','build','-f','docker/codex/Dockerfile','-t','specorganon-codex:0.2.0rc3.dev12','.'])
    # Historical installed probes remain tied to their own earlier source cut.
    probe=out/'probe_installed.py'
    text=probe.read_text().replace('installed-probe-final-source-pins.json','final-2-installed-source-pins.json').replace('installed-release-receipt.json','final-2-installed-release-receipt.json')
    final=out/'probe_installed_cut2.py';final.write_text(text)
    (out/'final-2-installed-source-pins.json').write_text(json.dumps({str(p.relative_to(root)):sha(p) for p in sorted((root/'src/specorganon').glob('*.py'))},indent=2,sort_keys=True)+'\n')
    run('final-2-installed-release',['uv','run','--extra','dev','python',str(final)])
    run('final-2-codex-version',['docker','run','--rm','--network=none','--read-only','--tmpfs','/tmp:rw,mode=1777','--entrypoint','codex','specorganon-codex:0.2.0rc3.dev12','--version'])
    result=run('final-2-codex-modules',['docker','run','--rm','--network=none','--read-only','--tmpfs','/tmp:rw,mode=1777','--entrypoint','python','specorganon-codex:0.2.0rc3.dev12','-I','-B','-c',"import specorganon,pathlib,hashlib,json,importlib.metadata;r=pathlib.Path(specorganon.__file__).parent;print(json.dumps({'version':importlib.metadata.version('specorganon'),'path':str(r),'modules':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in r.glob('*.py')}}))"])
    value=json.loads(result.stdout);expected={p.name:sha(p) for p in (root/'src/specorganon').glob('*.py')}
    assert value['version']=='0.2.0rc3.dev12' and value['modules']==expected and 'site-packages' in value['path'];print('CODEX_ALL_MODULES_EQUAL',flush=True)
    run('final-2-installed-guards',['docker','run','--rm','--network=none','--read-only','--tmpfs','/tmp:rw,mode=1777','-v',str(root/'tests')+':/checks:ro','-v',str(root/'workflows')+':/workflows:ro','specorganon-release:0.2.0rc3.dev12','python','-I','-B','-m','pytest','-q','-p','no:cacheprovider','/checks/test_attempt_deadline.py','/checks/test_closed_execution_failure.py','/checks/test_closed_native_role.py'])
