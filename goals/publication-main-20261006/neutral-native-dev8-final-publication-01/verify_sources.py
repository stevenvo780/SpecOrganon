from pathlib import Path
import hashlib,json,re,subprocess,datetime,shutil
r=Path(__file__).resolve().parents[3]; out=Path(__file__).parent
w=Path('/datos/workspaces/personal/ViewSpecOrganon/web')
h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
report={'schema':1,'at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
manifests={}
for name in ['neutral-native-dev8-progress-01','neutral-native-dev8-progress-02','t-premeasure-custody-dev9-01','audit-schema-factoring-diagnostic-01','neutral-native-dev8-final-01']:
 d=r/'goals/method-superiority-v1/evidence'/name; count=0
 for line in (d/'SHA256SUMS').read_text().splitlines():
  sha,p=line.split('  ',1); assert h(d/p)==sha,(name,p);count+=1
 manifests[name]={'entries':count,'sha256':h(d/'SHA256SUMS')}
report['manifests']=manifests
pins=json.loads((r/'goals/method-superiority-v1/evidence/t-premeasure-custody-dev9-01/source-final-pins.json').read_text())['files']
assert all(h(r/f)==v for f,v in pins.items());report['source_pins']=pins
for path,sha in {'GOAL.md':'e8341bea380cc357ad9e02ec4689a4ed47fe198ba06e4c98639f29264c314c36','goals/method-superiority-v1/GOAL.md':'5a46a82abbb8af3da82d89f3657bda71a2f170db263188fd4780bc8678195671'}.items(): assert h(r/path)==sha
report['goal_hashes']={p:h(r/p) for p in ['GOAL.md','goals/method-superiority-v1/GOAL.md']}
changed=subprocess.check_output(['git','diff','--name-only','315d24eb','HEAD'],cwd=r,text=True).splitlines()
for p in changed:
 if not (r/p).is_file(): continue
 assert not any(x in Path(p).parts for x in ['.venv','node_modules','.vercel','__pycache__'])
 assert Path(p).name not in ['auth.json','id_rsa','id_ed25519']
 raw=(r/p).read_bytes()
 assert not re.search(rb'\bsk-[A-Za-z0-9_-]{20,}\b|\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\b',raw),p
report['bounded_secret_pattern_scan']={'files':len(changed),'sk_JWT_hits':0,'scope':'Only sk-style/JWT patterns and prohibited file paths; not universal proof'}
# Exact committed source changes of the reviewed T candidate.
source='aee55d713ff05476776675ce9225360abefa54de'; exact=0
for p in subprocess.check_output(['git','diff-tree','--no-commit-id','--name-only','-r',source],cwd=r,text=True).splitlines():
 if p=='goals/method-superiority-v1/checkpoint.json':continue
 assert (r/p).read_bytes()==subprocess.check_output(['git','show',source+':'+p],cwd=r),p
 exact+=1
report['candidate_dev9_changed_paths_exact']=exact
prior=json.loads((r/'goals/publication-main-20261006/request-content-dev8-publication-01/website-source-manifest.json').read_text())['files']
public={p:v for p,v in prior.items() if p.startswith('public/')}
assert all(h(w/p)==v and h(r/'website'/p)==v for p,v in public.items())
report['previous_public_files_byte_equal']=len(public)
dirs=['','cohorte-nativa-01/','cohorte-nativa-02/','avance-dev3/','avance-dev4/','avance-dev5/','avance-dev6/','cohorte-dev4-terminal/','controles-dev6/']
report['historical_manifests']={d:h(w/'public/resultados/software'/d/('descargas-sha256.json' if d else 'descargas-manifest.json')) for d in dirs}
report['previous_public_manifest_count']=len(dirs)
plan=json.loads((r/'goals/method-superiority-v1/evidence/neutral-native-dev8-progress-02/pilot-plan.json').read_text())
bindings=plan['source_sha256']
assert all(h(Path('/home/stev/.codex/worktrees/request-content-v1/SpecOrganon')/p)==sha for p,sha in bindings.items())
report['original_registered_dev8_source_bindings_verified']=len(bindings)
report['plan_sha256']=h(r/'goals/method-superiority-v1/evidence/neutral-native-dev8-progress-02/pilot-plan.json')
for d in ['src','public']:
 for p in (w/d).rglob('*'):
  if p.is_file():dest=r/'website'/p.relative_to(w);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
for f in ['package.json','package-lock.json','tsconfig.json','vite.config.ts','index.html','vercel.json','README.md','.gitignore']:
 if (w/f).is_file():shutil.copyfile(w/f,r/'website'/f)
files={str(p.relative_to(r/'website')):h(p) for p in (r/'website').rglob('*') if p.is_file() and (p.relative_to(r/'website').parts[0] in {'src','public'} or (len(p.relative_to(r/'website').parts)==1 and p.name in {'package.json','package-lock.json','tsconfig.json','vite.config.ts','index.html','vercel.json','README.md','.gitignore'}))}
assert all(h(w/p)==v for p,v in files.items())
(out/'website-source-manifest.json').write_text(json.dumps({'schema':1,'at':report['at'],'files_count':len(files),'files':files},indent=2)+'\n')
report['website_files_exact']=len(files)
(out/'source-verification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ['source_pins']},indent=2))
