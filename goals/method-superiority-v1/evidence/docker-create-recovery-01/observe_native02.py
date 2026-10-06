"""Verify closed dev4 outcomes using their frozen driver, without taking its run lock.

No run/step/call/measure is invoked. Existing transports verify their receipts.
Only this observer's result file is written; the campaign report is not replaced.
"""
import hashlib
import json
from pathlib import Path
import sys

SOURCE = Path('/home/stev/.codex/worktrees/strong-comparators-v1/SpecOrganon')
REG = SOURCE/'goals/method-superiority-v1/development/registration-native-cohort-02.json'
EXPECTED = '923d5f1d6dac9b9271d1f311c5c714c848782e0bd40afe6f49ef87ba87552055'


def sha(raw): return hashlib.sha256(raw).hexdigest()


def main():
    if any(n == 'specorganon' or n.startswith('specorganon.') for n in sys.modules):
        raise ValueError('fresh observer process required')
    raw = REG.read_bytes()
    assert sha(raw) == EXPECTED
    r = json.loads(raw); bindings = r['source_sha256']
    captured = {name: (SOURCE/name).read_bytes() for name in bindings}
    assert all(sha(value) == bindings[name] for name,value in captured.items())
    bootstrap = SOURCE/'scripts/run_registered_native.py'
    ns = {'__name__': 'registered_observer_bootstrap', '__file__': str(bootstrap)}
    exec(compile(captured['scripts/run_registered_native.py'],str(bootstrap),'exec'),ns)
    sys.meta_path.insert(0, ns['RegisteredLoader'](SOURCE,bindings))
    driver = SOURCE/'scripts/native_reliability.py'
    dn = {'__name__': 'registered_read_observer', '__file__': str(driver),
          '__registered_runtime__': {'driver_sha256': bindings['scripts/native_reliability.py'], 'source_root': str(SOURCE)}}
    exec(compile(captured['scripts/native_reliability.py'],str(driver),'exec'),dn)
    plan = dn['load_plan'](REG,EXPECTED)
    result = dn['report'](plan,EXPECTED,Path(plan['run_root']),verify=True)
    result['observer'] = {'source_bindings_verified': len(bindings), 'registration_sha256': EXPECTED,
                          'script_sha256': sha(Path(__file__).read_bytes()),
                          'driver_package_receipts_verified': True, 'new_role_or_test_calls': 0,
                          'closed_driver_source_sha256': bindings['scripts/native_reliability.py']}
    Path(sys.argv[1]).write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
    print(json.dumps({k: v for k,v in result.items() if k != 'rows'},ensure_ascii=False))


if __name__ == '__main__': main()
