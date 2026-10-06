#!/usr/bin/env python3
"""Run actual local commands with a timeout and retain streams and receipts."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=180)
    parser.add_argument('argv', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    argv = args.argv[1:] if args.argv[:1] == ['--'] else args.argv
    if not argv:
        parser.error('an explicit argv is required')
    args.output.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    timed_out = False
    try:
        process = subprocess.run(argv, capture_output=True, timeout=args.timeout)
        code, stdout, stderr = process.returncode, process.stdout, process.stderr
    except subprocess.TimeoutExpired as error:
        timed_out = True
        code, stdout, stderr = None, error.stdout or b'', error.stderr or b''
    (args.output / 'stdout.txt').write_bytes(stdout)
    (args.output / 'stderr.txt').write_bytes(stderr)
    receipt = dict(argv=argv, exit_code=code, timed_out=timed_out,
                   stdout_sha256=hashlib.sha256(stdout).hexdigest(),
                   stderr_sha256=hashlib.sha256(stderr).hexdigest())
    data = dict(passed=code == 0 and not timed_out, command=shlex.join(argv), argv=argv,
                receipt=receipt, timeout_seconds=args.timeout,
                elapsed_seconds=time.monotonic()-start)
    # Kept independently of SpecOrganon; a separate helper seals the local receipt.
    (args.output / 'execution.json').write_text(json.dumps(data, indent=2), encoding='utf-8')
    print(json.dumps(data, sort_keys=True))
    return code if code is not None and code >= 0 else 1


if __name__ == '__main__':
    sys.exit(main())
