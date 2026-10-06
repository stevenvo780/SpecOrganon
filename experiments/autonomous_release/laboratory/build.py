from pathlib import Path
import subprocess,json,hashlib,time,datetime
base=Path(__file__).parent;root=Path('/home/stev/.codex/worktrees/autonomous-release/SpecOrganon')
files=['pyproject.toml','uv.lock','docker/release/Dockerfile','.dockerignore','compose.yaml']+[str(p.relative_to(root)) for part in ['src','docker/codex','.agents','docs','workflows','scripts'] for p in (root/part).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc']
hashes={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in sorted(files)}
receipts=[]
for name,args in [('release-build',['docker','build','-f','docker/release/Dockerfile','-t','specorganon-release:0.2.0rc2','.']),('codex-build',['docker','compose','build','codex'])]:
 start=time.time()
 with (base/(name+'.stdout')).open('w') as out,(base/(name+'.stderr')).open('w') as err:
  proc=subprocess.run(args,cwd=root,stdout=out,stderr=err,timeout=1200)
 receipt={'name':name,'argv':args,'cwd':str(root),'exit_code':proc.returncode,'timed_out':False,'duration_seconds':time.time()-start,'stdout_sha256':hashlib.sha256((base/(name+'.stdout')).read_bytes()).hexdigest(),'stderr_sha256':hashlib.sha256((base/(name+'.stderr')).read_bytes()).hexdigest(),'input_sha256':hashes,'inputs_unchanged':all(hashlib.sha256((root/n).read_bytes()).hexdigest()==sha for n,sha in hashes.items())}
 receipts.append(receipt);(base/'build-receipt.json').write_text(json.dumps({'schema':1,'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'builds':receipts,'scope':'separate fresh rc2 laboratory; no credentials/models/active cohort changes'},indent=2)+'\n')
 print(json.dumps({k:receipt[k] for k in ['name','exit_code','duration_seconds','inputs_unchanged']}),flush=True)
 if proc.returncode:raise SystemExit(proc.returncode)
print(subprocess.check_output(['docker','image','inspect','specorganon-release:0.2.0rc2','specorganon-codex:0.2.0rc2','--format','{{.Id}}'],text=True))
