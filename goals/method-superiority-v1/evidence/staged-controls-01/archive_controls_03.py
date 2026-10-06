"""Archive only the five closed mechanical fixtures, never account state."""
import hashlib,json,shutil
from pathlib import Path

BASE=Path('/tmp/pytest-of-stev/pytest-354')
DEST=Path(__file__).resolve().parent/'docker-controls-03-raw'
NAMES=['test_real_test_with_synthetic_0','test_real_test_with_synthetic_1',
       'test_real_closed_measure_crash0','test_real_SIGKILL_during_measu0','test_R3_real_failed_test_canno0']
ALLOWED={'initial.json','terminal-clock.json','transport/transport-policy.json',
         'transport/actual-tests/transport-policy.json','transport/actual-tests/host-journal/policy.json'}
PREFIXES=('reservations/','results/','generations/','snapshots/','transport/actual-tests/host-journal/',
          'transport/actual-tests/jobs/')
records=[]
for name in NAMES:
    root=BASE/name/'run'
    assert root.is_dir() and not root.is_symlink()
    for p in sorted(root.rglob('*')):
        assert not p.is_symlink()
        if not p.is_file():continue
        rel=p.relative_to(root).as_posix()
        if p.name.endswith('.lock') or p.name.startswith('.jobs'):continue
        assert rel in ALLOWED or rel.startswith(PREFIXES),rel
        assert p.name not in {'auth.json','credentials.json','token.json'}
        assert p.stat().st_nlink==1
        target=DEST/name/rel;target.parent.mkdir(parents=True,exist_ok=True)
        raw=p.read_bytes()
        if target.exists():assert target.read_bytes()==raw
        else:target.write_bytes(raw)
        records.append({'path':target.relative_to(DEST).as_posix(),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
receipt={'schema':1,'scope':'Five real offline Docker mechanical controls; fixture authors/reviews, zero provider calls, no dev6 installed image verification',
         'source_runtime_root':str(BASE),'test_log':'docker-controls-03.stdout','passed':5,
         'fixture_mode':True,'native_ready':False,'external_F':None,'goal_achieved':False,
         'files':records,'bytes':sum(r['bytes'] for r in records)}
(DEST.parent/'docker-controls-03-archive.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({'files':len(records),'bytes':receipt['bytes'],'passed':5,'provider_calls':0}))
