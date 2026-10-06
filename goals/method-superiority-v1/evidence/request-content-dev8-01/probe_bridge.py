"""Offline bridge entrypoint and test receipt preflight; no profiles/inference."""
from pathlib import Path
import hashlib,json,subprocess
from specorganon.docker_roles import DockerRoles
from specorganon.native_response_contract import native_command
from specorganon.role_jobs import digest
B=Path(__file__).resolve().parent;R=B.parents[3]
image=(B/'native-image-id.txt').read_text().strip();test='sha256:5357232868157b9dce5a7783076f865c2fb6736232434b61300023d7d0ea1325'
paths=[R/'scripts/controller_native_role.py',*sorted((R/'src/specorganon').glob('*.py')),R/'experiments/software_comparison_v3/public-models.json',R/'docker/codex/seccomp-codex.json']
pins={str(p.relative_to(R)):digest(p.read_bytes()) for p in paths}
t=DockerRoles(B/'bridge-preflight',native_image=image,test_image=test,source_root=R,public_catalog=R/'experiments/software_comparison_v3/public-models.json',seccomp=R/'docker/codex/seccomp-codex.json',source_bindings=pins,codex_reasoning_effort='medium')
f,plan=t._prepare('bridge-help-only','author',{'scope':'No inference; bridge help preflight only'})
records=[]
def run(name,args):
 r=subprocess.run(args,capture_output=True,timeout=120)
 (B/(name+'.stdout')).write_bytes(r.stdout);(B/(name+'.stderr')).write_bytes(r.stderr)
 records.append({'argv':args,'exit_code':r.returncode,'stdout_sha256':digest(r.stdout),'stderr_sha256':digest(r.stderr)})
 (B/'bridge-commands.json').write_text(json.dumps(records,indent=2)+'\n')
 assert r.returncode==0,(name,r.stderr.decode()[:1500])
 return r.stdout
common=['docker','run','--rm','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','--security-opt','seccomp='+str(R/'docker/codex/seccomp-codex.json'),'--security-opt','apparmor:unconfined','--tmpfs','/tmp:rw,nosuid,nodev','--mount','type=bind,src='+str(f/'input')+',dst=/input,readonly','-e','HOME=/tmp','-e','CODEX_HOME=/tmp','-e','PYTHONPATH=/input/library','-w','/input']
# Use the exact transport's hard-coded interpreter; no original credential mounts.
python=plan['create_argv'][plan['create_argv'].index('--entrypoint')+1]
run('bridge-help',common+['--entrypoint',python,image,'/input/bridge.py','--help'])
code='import pathlib,hashlib,json,specorganon; p=pathlib.Path(specorganon.__file__).parent; print(json.dumps({f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in p.glob("*.py")}))'
modules=json.loads(run('bridge-modules',common+['--entrypoint',python,image,'-B','-c',code]))
expected={p.name:digest(p.read_bytes()) for p in (R/'src/specorganon').glob('*.py')};assert modules==expected and len(modules)==41
native=native_command('codex','gpt-6.1-sol',model_catalog='/input/public-models.json',reasoning_effort='medium')
features=[native[0]]
for i,v in enumerate(native[:-1]):
 if v in {'--disable','-c'}:features.extend([v,native[i+1]])
raw=run('codex-disabled-features',common+['--entrypoint',features[0],image,*features[1:],'features','list'])
from specorganon.native_response_contract import CODEX_TEXT_ONLY_DISABLED
rows={line.split()[0]:line.split()[-1] for line in raw.decode().splitlines() if line.split()}
assert all(rows.get(n)=='false' for n in CODEX_TEXT_ONLY_DISABLED),rows
files={'probe.py':'print("native-admission-offline-measure")\n'};argv=['/opt/specorganon/venv/bin/python','-I','-B','/input/delivery/probe.py']
try:
 measured=t.measure('offline-test-only',argv,files)
 assert measured['passed'];assert t.verify_test({'argv':argv,'test_job_ref':measured['test_job_ref']},files)
 assert t.measure('offline-test-only',argv,files)==measured
finally:
 launch=B/'bridge-preflight/jobs/offline-test-only/launch.json'
 if launch.exists():
  cid=json.loads(launch.read_text())['container_id']
  if cid:subprocess.run(['docker','rm','--force',cid],capture_output=True,check=True)
receipt={'schema':1,'scope':'Exact DockerRoles interpreter and captured source bridge --help, features and actual offline test; no inference or original profile mounts','native_image':image,'test_image':test,'native_python':python,'captured_modules_byte_equal':41,'disabled_features_verified':list(CODEX_TEXT_ONLY_DISABLED),'measurement':measured,'replay_equal_no_second_run':True,'provider_calls':0,'native_admission':False,'goal_achieved':False}
(B/'bridge-preflight-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({'image':image,'bridge_help':True,'modules':41,'offline_test_and_replay':True,'provider_calls':0}))
