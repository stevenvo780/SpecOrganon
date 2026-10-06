"""Run and retain local subprocess evidence; standard library only."""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'evidence' / 'v2-budget'


def run(label, argv, timeout=180):
    OUT.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    timed_out = False
    try:
        proc = subprocess.run(argv, capture_output=True, timeout=timeout, cwd=ROOT.parent)
        stdout, stderr, code = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as exc:
        stdout, stderr, code = exc.stdout or b'', exc.stderr or b'', -1
        timed_out = True
    (OUT / (label + '.stdout')).write_bytes(stdout)
    (OUT / (label + '.stderr')).write_bytes(stderr)
    data = {'passed': code == 0 and not timed_out, 'argv': argv,
            'command': shlex.join(argv), 'timeout_seconds': timeout,
            'elapsed_seconds': time.monotonic() - started,
            'receipt': {'argv': argv, 'exit_code': code, 'timed_out': timed_out,
                        'stdout_sha256': hashlib.sha256(stdout).hexdigest(),
                        'stderr_sha256': hashlib.sha256(stderr).hexdigest()},
            'backup_sha256': hashlib.sha256((ROOT / 'backup.py').read_bytes()).hexdigest(),
            'test_sha256': hashlib.sha256((ROOT / 'test_backup.py').read_bytes()).hexdigest()}
    (OUT / (label + '.json')).write_text(json.dumps(data, indent=2) + '\n')
    print(json.dumps(data))
    print(stdout.decode(errors='replace'), end='')
    print(stderr.decode(errors='replace'), end='', file=sys.stderr)
    return code


if __name__ == '__main__':
    label = sys.argv[1] if len(sys.argv) > 1 else 'suite'
    script = ROOT / ('examples.py' if label == 'examples' else 'test_backup.py')
    raise SystemExit(run(label, [sys.executable, str(script)]))
