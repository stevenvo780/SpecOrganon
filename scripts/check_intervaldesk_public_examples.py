"""Independent clean execution of the two already-public IntervalDesk examples.

This is C4 reproducibility evidence, not a reserved comparative evaluation.
It never invokes native providers, updates the delivery or approves a phase.
"""
import argparse
import json
from pathlib import Path

from specorganon.docker_roles import DockerRoles
from specorganon.role_jobs import _write, canonical, digest


EXAMPLES = [
    ({'intervals': [[5, 10], [0, 7], [10, 12], [20, 25]]},
     {'merged': [[0, 12], [20, 25]], 'covered_minutes': 17, 'input_count': 4}),
    ({'intervals': [[1, 3], [1, 3]]},
     {'merged': [[1, 3]], 'covered_minutes': 2, 'input_count': 2}),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--delivery', type=Path, required=True)
    parser.add_argument('--run-root', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--native-image', required=True)
    parser.add_argument('--test-image', required=True)
    parser.add_argument('--public-catalog', type=Path, required=True)
    args = parser.parse_args()
    args.run_root.mkdir(parents=True, exist_ok=False)
    files = {}
    for path in sorted(args.delivery.rglob('*')):
        if path.is_symlink(): raise ValueError('symlinks are not a clean delivery')
        if path.is_file(): files[str(path.relative_to(args.delivery))] = path.read_text()
    if 'cover.py' not in files: raise ValueError('public CLI delivery missing')
    plan = {'schema': 1, 'scope': 'two examples frozen in the public contract before author generation; C4 only',
            'examples': EXAMPLES, 'delivery_tree_sha256': digest(canonical(files)),
            'image_id': args.test_image, 'max_executions': 1, 'timeout_seconds': 120,
            'native_model_calls': 0, 'reserved_comparative_evaluation': False,
            'stop_rule': 'keep any error/timeout; no restart or replacement'}
    _write(args.run_root / 'plan.json', plan)
    code = '''import json,subprocess,tempfile,hashlib
from pathlib import Path
examples=EXAMPLES
def pairs(items):
 d={}
 for k,v in items:
  if k in d: raise ValueError('duplicate output key')
  d[k]=v
 return d
def finite(value): raise ValueError('nonfinite output')
results=[]
with tempfile.TemporaryDirectory() as temporary:
 for number,(sample,expected) in enumerate(examples):
  path=Path(temporary)/('example-'+str(number)+'.json')
  path.write_text(json.dumps(sample),encoding='utf-8');before=hashlib.sha256(path.read_bytes()).hexdigest()
  argv=['/opt/specorganon/venv/bin/python','-E','-s','-B','/input/delivery/cover.py',str(path)]
  measured=subprocess.run(argv,capture_output=True,timeout=30)
  result={'argv':argv,'exit_code':measured.returncode,'stdout':measured.stdout.decode(),'stderr':measured.stderr.decode(),
          'input_before_sha256':before,'input_after_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
  results.append(result);print(json.dumps(result),flush=True)
  assert measured.returncode==0 and result['input_before_sha256']==result['input_after_sha256']
  observed=json.loads(measured.stdout,object_pairs_hook=pairs,parse_constant=finite)
  assert type(observed) is dict and set(observed)==set(expected) and observed==expected
  assert type(observed['covered_minutes']) is int and type(observed['input_count']) is int
  assert type(observed['merged']) is list and all(type(p) is list and len(p)==2 and all(type(v) is int for v in p) for p in observed['merged'])
'''.replace('EXAMPLES', repr(EXAMPLES))
    executor = DockerRoles(args.run_root / 'executor', native_image=args.native_image,
                          test_image=args.test_image, source_root=args.source_root,
                          public_catalog=args.public_catalog)
    measured = executor.measure('public-examples-01',
                               ['/opt/specorganon/venv/bin/python', '-E', '-s', '-B', '-c', code], files)
    verdict = {**plan, 'measurement': measured, 'passed': measured['passed'], 'goal_complete': False}
    _write(args.run_root / 'verdict.json', verdict)
    print(json.dumps(verdict, indent=2))
    return 0 if measured['passed'] else 2


if __name__ == '__main__': raise SystemExit(main())
