"""Offline hash verification of selected original closed bytes; no rerun/attestation."""
from pathlib import Path,PurePosixPath
import json,hashlib
base=Path(__file__).resolve().parent; root=base.parent
h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
s=json.loads((base/'summary.json').read_text());report=json.loads((base/'report.json').read_text())
assert s['closed_in_this_cut']==6 and report['closed_attempts']==6 and report['status']=='closed'
assert h(base/'pilot-plan.json')==s['plan_sha256']=='30dd4cf8a4050198f2604057099c3c6f9715b197d474527cc3d75801f49c4215'
checked=0;omitted_locks=0
for row in s['observations']:
 a=root/row['raw_archive'];o=json.loads((a/'outcome.json').read_text());c=json.loads((a/'closure.json').read_text())
 assert h(a/'outcome.json')==c['outcome_sha256']==row['outcome_sha256'];assert h(a/'closure.json')==row['closure_sha256'];assert o in report['rows']
 assert o['common_complete'] is None and o['external_F'] is None
 for p,sha in c['evidence_sha256'].items():
  key=PurePosixPath(p);assert not key.is_absolute() and '..' not in key.parts
  target=a/p
  if not target.exists():assert key.name.endswith('.lock') and sha==hashlib.sha256(b'').hexdigest();omitted_locks+=1
  else:assert not target.is_symlink() and h(target)==sha;checked+=1
 for p,sha in o['evidence_sha256'].items():assert c['evidence_sha256'][p]==sha
for folder in ['neutral-native-dev8-progress-01','neutral-native-dev8-progress-02','neutral-native-dev8-final-01']:
 d=root/folder
 for line in (d/'SHA256SUMS').read_text().splitlines():
  sha,p=line.split('  ',1);assert h(d/p)==sha
print(json.dumps({'six_closures_verified':True,'sealed_runtime_entries':checked+omitted_locks,'archived_sealed_files_verified':checked,'omitted_empty_locks':omitted_locks,'public_checks_descriptive':sum(x['public_passed'] for x in s['observations']),'common_complete':None,'external_F':None,'models_docker_tests_executed':False}))
