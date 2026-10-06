"""Narrow mechanical archive: twelve test journals, one declared provider simulator."""
import hashlib,json
from pathlib import Path
BASE=Path('/tmp/specorganon-staged-docker-11')
HERE=Path(__file__).resolve().parent
DEST=HERE/'docker-controls-11-raw'
NAMES=['test_real_test_with_synthetic_0','test_real_test_with_synthetic_1',
       'test_real_closed_measure_crash0','test_R3_real_failed_test_canno0',
       'test_real_SIGKILL_during_measu0','test_real_SIGKILL_during_measu1',
       'test_R11_real_closed_measure_w0','test_real_SIGKILL_during_measu2',
       'test_R15_real_measure_SIGKILL_0','test_R15_real_measure_SIGKILL_1',
       'test_real_SIGKILL_during_measu3','test_real_SIGKILL_during_measu4']
ALLOWED={'initial.json','terminal-clock.json','transport/transport-policy.json',
         'transport/actual-tests/transport-policy.json','transport/actual-tests/host-journal/policy.json'}
PREFIXES=('reservations/','results/','generations/','snapshots/','transport/actual-tests/host-journal/',
          'transport/actual-tests/jobs/')
records=[]
def copy_files(root,label,allowed,prefixes):
    assert root.is_dir() and not root.is_symlink()
    for p in sorted(root.rglob('*')):
        assert not p.is_symlink()
        if not p.is_file():continue
        rel=p.relative_to(root).as_posix()
        if p.name.endswith('.lock') or p.name.startswith('.jobs'):continue
        assert rel in allowed or rel.startswith(prefixes),rel
        assert p.name not in {'auth.json','credentials.json','token.json','settings.json'}
        assert p.stat().st_nlink==1
        target=DEST/label/rel;target.parent.mkdir(parents=True,exist_ok=True)
        raw=p.read_bytes()
        if target.exists():assert target.read_bytes()==raw
        else:target.write_bytes(raw)
        records.append({'path':target.relative_to(DEST).as_posix(),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
for name in NAMES:copy_files(BASE/name/'run',name,ALLOWED,PREFIXES)
name='test_R10_real_bridge_closed_em0'
assert not any((BASE/name/'empty-synthetic-profile').iterdir())
copy_files(BASE/name/'actual-simulated-role',name,{'transport-policy.json','host-journal/policy.json'},('jobs/','host-journal/'))
p=BASE/name/'simulated-agy';target=DEST/name/'simulated-agy';raw=p.read_bytes();target.write_bytes(raw)
records.append({'path':target.relative_to(DEST).as_posix(),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
receipt={'schema':1,'scope':'Thirteen real isolated Docker mechanical controls. Synthetic N/S authors/reviews and explicit simulated Gemini executable with empty profile; zero experimental model calls. Existing dev4 image, not installed dev6 release image.',
         'source_runtime_root':str(BASE),'test_log':'docker-controls-11.stdout','passed':13,
         'provider_simulator':'test_R10_real_bridge_closed_em0/simulated-agy','simulator_empty_profile':True,
         'fixture_mode':True,'native_ready':False,'external_F':None,'goal_achieved':False,
         'files':records,'bytes':sum(r['bytes'] for r in records),'experimental_provider_calls':0}
(HERE/'docker-controls-11-archive.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({'files':len(records),'bytes':receipt['bytes'],'passed':13,'experimental_provider_calls':0}))
