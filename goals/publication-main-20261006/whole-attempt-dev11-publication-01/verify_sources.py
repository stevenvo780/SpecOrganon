from pathlib import Path
import json,hashlib,subprocess,datetime,shutil,re
r=Path(__file__).resolve().parents[3]; out=Path(__file__).parent; w=Path('/datos/workspaces/personal/ViewSpecOrganon/web')
h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
source='ef232cb08843850f1c871ca9434274cfbae212d4'; baseline='89726b37edd7d4e58677f9acf8dac59bd25406c2'
report={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'Source/archive/mirror verification only; no model/Docker/test executions','source_commit':subprocess.check_output(['git','rev-parse',source],cwd=r,text=True).strip()}
report['evidence_manifests']={}
for name in ['whole-attempt-recovery-dev11-01','native-envelope-provenance-dev10-prospective-01','t-common-controller-dev10-01','neutral-native-dev8-progress-01','neutral-native-dev8-progress-02','neutral-native-dev8-final-01','t-premeasure-custody-dev9-01']:
 d=r/'goals/method-superiority-v1/evidence'/name;rows=(d/'SHA256SUMS').read_text().splitlines()
 for row in rows:
  sha,p=row.split('  ',1);assert h(d/p)==sha,(name,p)
 report['evidence_manifests'][name]={'entries':len(rows),'manifest_sha256':h(d/'SHA256SUMS')}
e=r/'goals/method-superiority-v1/evidence/whole-attempt-recovery-dev11-01'
receipt=json.loads((e/'engineering-receipt.json').read_text());pins=receipt['final_source_sha256']
for p,sha in pins.items():assert h(r/p)==sha,p
report['final_installed_module_pins_exact']=len(pins);report['final_module_pins']=pins
paths=set()
for commit in ['9aa729f3','ef232cb0']:
 paths.update(subprocess.check_output(['git','diff-tree','--no-commit-id','--name-only','-r',commit],cwd=r,text=True).splitlines())
paths.discard('goals/method-superiority-v1/checkpoint.json');paths.discard('README.md')
for p in sorted(paths):assert (r/p).read_bytes()==subprocess.check_output(['git','show',source+':'+p],cwd=r),p
report['candidate_changed_paths_byte_exact']=len(paths)
reviewpins=json.loads((e/'correction-review-source-pins.json').read_text())
for p,sha in reviewpins.items():assert h(r/p)==sha,p
report['correction_review_pins_exact']=len(reviewpins)
assert h(e/'engineering-receipt.json')=='bc331ab10413b764af121d13689f2c5396fec4a88ce61831a22f736622965ceb'
assert h(e/'review-corrected-installed-source-pins.json')=='5e97c0db0408165b96ff12fdfe7e063ab669aa918076e4984aa17ec0035c05ac'
report['terminal_engineering_receipt_sha256']=h(e/'engineering-receipt.json')
report['review_verdict']=receipt['independent_static_review']['verdict'];assert report['review_verdict']=='reject_component_cut'
report['open_new_findings']=receipt['independent_static_review']['new_open_findings']
goals={'GOAL.md':'e8341bea380cc357ad9e02ec4689a4ed47fe198ba06e4c98639f29264c314c36','goals/method-superiority-v1/GOAL.md':'5a46a82abbb8af3da82d89f3657bda71a2f170db263188fd4780bc8678195671'}
for p,sha in goals.items():assert h(r/p)==sha
report['goal_hashes']=goals
plan=r/'goals/method-superiority-v1/evidence/neutral-native-dev8-progress-02/pilot-plan.json'
assert h(plan)=='30dd4cf8a4050198f2604057099c3c6f9715b197d474527cc3d75801f49c4215'
bindings=json.loads(plan.read_text())['source_sha256'];frozen=Path('/home/stev/.codex/worktrees/request-content-v1/SpecOrganon')
for p,sha in bindings.items():assert h(frozen/p)==sha,p
report['original_dev8_frozen_source_bindings_exact']=len(bindings)
prior=json.loads((r/'goals/publication-main-20261006/t-common-dev10-publication-01/website-source-manifest.json').read_text())['files']
public={p:v for p,v in prior.items() if p.startswith('public/')}
for p,sha in public.items():assert h(w/p)==sha and h(r/'website'/p)==sha,p
report['historical_public_files_exact']=len(public)
for d in ['src','public']:
 for p in (w/d).rglob('*'):
  if p.is_file():dest=r/'website'/p.relative_to(w);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
rootfiles=['package.json','package-lock.json','tsconfig.json','vite.config.ts','index.html','vercel.json','README.md','.gitignore']
for f in rootfiles:
 if (w/f).is_file():shutil.copyfile(w/f,r/'website'/f)
files={str(p.relative_to(w)):h(p) for p in w.rglob('*') if p.is_file() and (p.relative_to(w).parts[0] in {'src','public'} or (len(p.relative_to(w).parts)==1 and p.name in rootfiles))}
for p,sha in files.items():assert h(r/'website'/p)==sha
report['website_files_exact']=len(files)
(out/'website-source-manifest.json').write_text(json.dumps({'files_count':len(files),'files':files},indent=2)+'\n')
scan=set(paths)|set('website/'+p for p in files)|{'README.md'}
for p in scan:
 assert not any(part in {'.vercel','__pycache__','.venv','node_modules'} for part in Path(p).parts),p
 assert Path(p).name not in {'auth.json','id_rsa','id_ed25519'},p
 assert not re.search(rb'\bsk-[A-Za-z0-9_-]{20,}\b|\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\b',(r/p).read_bytes()),p
report['bounded_secret_scan']={'files':len(scan),'sk_JWT_hits':0,'scope':'sk-style/JWT patterns/prohibited file paths; no universal assertion'}
report['native_generations']=0;report['F']=None;report['common_complete']=None
(out/'source-verification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='final_module_pins'},indent=2))
