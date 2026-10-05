"""Reproduce review findings with deliberate controls, never study solutions."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from experiments.software_comparison_v1.reserved.docker_evaluator import ReservedDocker, audit_case
from experiments.software_comparison_v1.reserved.evaluator import encoded


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run-root', type=Path, required=True)
    p.add_argument('--image', required=True)
    a = p.parse_args()
    executor = ReservedDocker(a.run_root, a.image)
    case = audit_case()
    emit = 'import sys\nsys.stdout.write(' + repr((encoded(case['expected']) + b'\n').decode()) + ')\n'
    subjects = {
        'stderr-state-spoof': 'import os,sys\nos.chdir("/fixture/root")\nsys.stderr.write(\'chdir("/tmp") = 0\\n\');sys.stderr.flush()\nos.readlink("link")\n' + emit,
        'safe-similar-scratch-path': 'from pathlib import Path\np=Path("/tmp/fixture/root");p.mkdir(parents=True)\n(p/"probe.txt").write_bytes(b"abc")\n(p/"probe.txt").read_bytes()\n' + emit,
        'opath-proc-link-inspection': 'import os\nfd=os.open("/fixture/root/link",os.O_PATH|os.O_NOFOLLOW)\nassert os.readlink("/proc/self/fd/"+str(fd))=="/fixture/root/link"\nos.close(fd)\n' + emit,
    }
    results = []
    for name, source in subjects.items():
        record = executor.run(name, case, {'treemap.py': source})
        results.append({'finding_control': name, 'record': record})
        print(json.dumps({'finding_control': name, 'verdict': record['verdict']}), flush=True)
    (a.run_root / 'findings.json').write_bytes(encoded({'classification': 'adversarial/benign controls; not solutions',
                                                     'native_model_calls': 0, 'results': results}) + b'\n')


if __name__ == '__main__':
    main()
