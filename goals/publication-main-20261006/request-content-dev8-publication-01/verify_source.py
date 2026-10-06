from pathlib import Path
import hashlib,json,subprocess,re,datetime
root=Path(__file__).resolve().parents[3]; out=Path(__file__).resolve().parent
source='5c75cf9802c1ae09155ba98ac8f58ff70eda6133'; ev=root/'goals/method-superiority-v1/evidence/request-content-dev8-01'
hash=lambda b:hashlib.sha256(b).hexdigest()
entries=[]
for line in (ev/'SHA256SUMS').read_text().splitlines():
 expected,name=line.split('  ',1); raw=(ev/name).read_bytes(); assert hash(raw)==expected,name; entries.append({'file':name,'sha256':expected,'bytes':len(raw)})
assert len(entries)==380
pins=json.loads((ev/'source-resource-final-pins.json').read_text())['files']; assert len(pins)==12
for name,expected in pins.items(): assert hash((root/name).read_bytes())==expected,name
paths=subprocess.check_output(['git','diff','--name-only','63ffe002',source],cwd=root,text=True).splitlines(); exact=[]; changed=[]
for name in paths:
 if name=='goals/method-superiority-v1/checkpoint.json':continue
 expected=subprocess.check_output(['git','show',source+':'+name],cwd=root); current=(root/name).read_bytes()
 if current==expected:exact.append(name)
 else:changed.append(name)
assert not changed,changed
expected_goals={'GOAL.md':'e8341bea380cc357ad9e02ec4689a4ed47fe198ba06e4c98639f29264c314c36','goals/method-superiority-v1/GOAL.md':'5a46a82abbb8af3da82d89f3657bda71a2f170db263188fd4780bc8678195671'}
for name,expected in expected_goals.items():assert hash((root/name).read_bytes())==expected,name
cp=json.loads((root/'goals/method-superiority-v1/checkpoint.json').read_text()); assert cp['status']=='active' and cp['goal_achieved'] is False
bad=[];patterns=[rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',rb'\bgh[pousr]_[A-Za-z0-9]{30,}\b',rb'\bsk-[A-Za-z0-9_-]{20,}\b',rb'\beyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\b']
for name in exact:
 raw=(root/name).read_bytes()
 if any(re.search(p,raw) for p in patterns):bad.append(name)
assert not bad,bad
report={'schema':1,'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_commit':source,'manifest_entries_verified':len(entries),'manifest_sha256':hash((ev/'SHA256SUMS').read_bytes()),'source_pins_verified':12,'pins':pins,'source_paths_exact':len(exact),'source_paths':exact,'checkpoint_excluded_for_publication_metadata':True,'goal_hashes':expected_goals,'bounded_secret_scan':{'matching_files':bad,'not_universal_absence_proof':True},'local_install_scope':'63 tracked historical snapshots and four restored historical smokes preserved; new private wheel/venv/runtime excluded','new_model_or_native_calls':0,'tests_reexecuted':False,'evidence_files':entries}
(out/'source-verification.json').write_text(json.dumps(report,indent=2)+'\n'); print(json.dumps({k:v for k,v in report.items() if k in ['manifest_entries_verified','source_paths_exact','source_pins_verified','manifest_sha256']}))
