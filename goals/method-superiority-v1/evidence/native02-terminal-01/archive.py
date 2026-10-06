"""Archive explicit closed public-development evidence, never profiles or mounts.

Private runtime is retained. This is an inspection archive, not a relocated run.
Large repeated source/catalog/runtime copies in each role input are excluded;
one hash-checked registered source snapshot is saved separately.
"""
import hashlib
import json
from pathlib import Path

RUN=Path('/datos/workspaces/personal/specorganon-validation/method-superiority-v1/native-reliability-02')
SOURCE=Path('/home/stev/.codex/worktrees/strong-comparators-v1/SpecOrganon')
DEST=Path(__file__).resolve().parent
PIN='923d5f1d6dac9b9271d1f311c5c714c848782e0bd40afe6f49ef87ba87552055'


def sha(raw):return hashlib.sha256(raw).hexdigest()


def allowed(parts):
    if len(parts)==1:return parts[0] in ('registration.json','report.json')
    if not parts[0].startswith('attempt-'):return False
    if len(parts)==2:return parts[1].endswith('.json')
    if parts[1]=='case':return not parts[-1].endswith('.lock')
    if parts[1]=='controller':return True
    if parts[1] not in ('transport','independent-check-transport'):return False
    if len(parts)==3:return parts[2]=='transport-policy.json'
    if parts[2]=='host-journal':return not parts[-1].endswith('.lock')
    if parts[2]!='jobs':return False
    tail=parts[4:]
    if len(tail)==1:return tail[0] in ('launch.json','create-attempt.json','control-recovery.json',
        'terminal-container.json','measured-test.json','reconciliation.json')
    return (tail[:2]==('output','native') or tail==('output','role-response-schema.json')) and not parts[-1].endswith('.lock')


def main():
    registration=(RUN/'registration.json').read_bytes();assert sha(registration)==PIN
    r=json.loads(registration)
    verified=json.loads((DEST/'verified-report.stdout').read_text())
    assert verified['closed_attempts']==10 and verified['registration_sha256']==PIN
    assert verified==json.loads((RUN/'report.json').read_bytes())
    manifests={}
    for path in sorted(RUN.rglob('*')):
        rel=path.relative_to(RUN)
        if not path.is_file() or not allowed(rel.parts):continue
        assert not path.is_symlink() and 'auth.json' not in rel.parts
        raw=path.read_bytes();target=DEST/rel;target.parent.mkdir(parents=True,exist_ok=True)
        assert not target.exists() or target.read_bytes()==raw
        target.write_bytes(raw);manifests[str(rel)]={'sha256':sha(raw),'bytes':len(raw)}
    for name,expected in r['source_sha256'].items():
        raw=(SOURCE/name).read_bytes();assert sha(raw)==expected
        target=DEST/'source'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        manifests[str(target.relative_to(DEST))]={'sha256':sha(raw),'bytes':len(raw)}
    summary={k:v for k,v in verified.items() if k!='rows'}
    summary.update({'status':'terminal','verified_report_exit_code':0,'original_run_exit_code':0,
        'source_bindings_verified':len(r['source_sha256']),'new_role_or_test_calls_by_verification':0,
        'archive_scope':'Selected raw closed receipts, checkpoints, deliveries and one registered source snapshot; repeated input source/catalog copies and provider runtime caches excluded; not a relocated run'})
    (DEST/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
    (DEST/'source-verification.json').write_text(json.dumps({'registration_sha256':PIN,
        'source_root':str(SOURCE),'source_sha256':r['source_sha256'],'all_sources_match':True},sort_keys=True,indent=2)+'\n')
    (DEST/'manifest.sha256.json').write_text(json.dumps(manifests,sort_keys=True,indent=2)+'\n')
    print(json.dumps({'archived_files':len(manifests),'archived_bytes':sum(v['bytes'] for v in manifests.values()),
                      'closed':summary['closed_attempts'],'complete':summary['generation_complete'],'goal_achieved':False}))


if __name__=='__main__':main()
