"""Continue one registered case serially; stop at first terminal failure.

No replacement generation, account switch, provider substitution or extra budget.
The registered step driver checks frozen source and policy on each invocation.
"""
import argparse
import fcntl
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('registration',type=Path)
    parser.add_argument('--first-step',type=int,required=True)
    args=parser.parse_args()
    registration=json.loads(args.registration.read_text())
    run=Path(registration['run_root'])
    evidence=Path(__file__).resolve().parent.parent/'evidence'
    with (run/'orchestrator.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        for number in range(args.first_step,61):
            name='rangeaudit-step-'+str(number).zfill(2)
            stdout=evidence/(name+'.stdout');stderr=evidence/(name+'.stderr')
            if stdout.exists() or stderr.exists():
                raise RuntimeError('Refuse to overwrite existing action logs: '+name)
            with stdout.open('x') as out,stderr.open('x') as err:
                result=subprocess.run([sys.executable,str(Path(__file__).with_name('run_rangeaudit_step.py')),
                    str(args.registration.resolve())],stdout=out,stderr=err)
            record={'step':number,'exit_code':result.returncode,'stdout':str(stdout),'stderr':str(stderr)}
            print(json.dumps(record),flush=True)
            if result.returncode:
                return result.returncode
            receipt=json.loads(stdout.read_text())
            if receipt['result']['action']=='complete':
                assert receipt['nine_phase_delivery'] is True
                return 0
        raise RuntimeError('Orchestration action bound reached; no automatic expansion')


if __name__=='__main__': sys.exit(main())
