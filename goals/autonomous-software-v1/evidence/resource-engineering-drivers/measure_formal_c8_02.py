from pathlib import Path
import json,hashlib,time,subprocess,os,sys
root=Path('/datos/workspaces/personal/SpecOrganon');base=Path('/datos/workspaces/personal/specorganon-validation/autonomous-software-v1');e=root/'goals/autonomous-software-v1/evidence'
files=['src/specorganon/software_controller.py','src/specorganon/docker_roles.py','src/specorganon/role_jobs.py','tests/test_controller_recovery.py','tests/test_docker_roles.py']
def manifests():return {p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in files}
if (e/'formal-c8-02-plan.json').exists():raise SystemExit('refuse control restart')
argv=[str(root/'.venv/bin/python'),'-m','pytest','-q','tests/test_controller_recovery.py::test_sigkill_after_actual_role_receipt_before_puts_reuses_job_and_applies_once','tests/test_docker_roles.py::test_sigkill_owner_before_receipt_stops_exact_container_without_restart','--basetemp='+str(base/'formal-c8-02-test')]
plan={'schema':1,'control':'C8','scope':'synthetic contents, actual SIGKILL processes; no model review or C1 claim','scenarios':['closed actual receipt before puts resumes without invocation or event duplication','SIGKILL before closing stops exact owned Docker container, no second invocation or accepted receipt'],'runs_per_scenario':1,'timeout_seconds':120,'argv':argv,'source_manifest':manifests(),'environment_override':{'SPECORGANON_DOCKER_COMPONENT_TESTS':'1'},'stop_rule':'any failure or timeout fails/inconclusive; no automatic retry','native_model_calls':0}
(e/'formal-c8-02-plan.json').write_text(json.dumps(plan,indent=2)+'\n');started=time.monotonic();timedout=False
with (e/'formal-c8-02.stdout').open('wb') as out,(e/'formal-c8-02.stderr').open('wb') as err:
 try:code=subprocess.run(argv,cwd=root,stdout=out,stderr=err,env={**os.environ,'SPECORGANON_DOCKER_COMPONENT_TESTS':'1'},timeout=120).returncode
 except subprocess.TimeoutExpired:code=124;timedout=True
receipt={**plan,'after_manifest':manifests(),'duration_seconds':time.monotonic()-started,'exit_code':code,'timed_out':timedout,'verdict':'satisfied' if code==0 and not timedout else 'inconclusive' if timedout else 'failed','goal_complete':False,**{s+'_sha256':hashlib.sha256((e/('formal-c8-02.'+s)).read_bytes()).hexdigest() for s in ['stdout','stderr']}}
assert receipt['source_manifest']==receipt['after_manifest']
(e/'formal-c8-02-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print((e/'formal-c8-02.stdout').read_text());sys.exit(code)
