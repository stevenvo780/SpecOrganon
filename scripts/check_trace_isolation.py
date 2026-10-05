"""Real isolation and adversarial checks; no study solutions or provider calls."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from experiments.software_comparison_v1.reserved.docker_evaluator import ReservedDocker, audit_case
from experiments.software_comparison_v1.reserved.evaluator import encoded


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-root', type=Path, required=True)
    parser.add_argument('--image', required=True)
    args = parser.parse_args()
    transport = ReservedDocker(args.run_root, args.image)
    case = audit_case()
    emit = 'import sys\nsys.stdout.write(' + repr((encoded(case['expected']) + b'\n').decode()) + ')\n'
    boundary = '''import os
from pathlib import Path
assert os.getresuid() == (65534,65534,65534)
assert os.getresgid() == (65534,65534,65534)
assert int(Path('/proc/self/status').read_text().split('CapEff:')[1].splitlines()[0],16) == 0
for operation in [lambda: Path('/collector-output/trace.bin').write_bytes(b'forged'),
                  lambda: os.unlink('/collector-output/trace.bin'),
                  lambda: os.chmod('/collector-output',0o777),
                  lambda: Path('/collector-input/collector.py').read_text(),
                  lambda: os.open('/proc/1/fd/1',os.O_WRONLY),
                  lambda: os.kill(os.getppid(),9)]:
    try: operation()
    except PermissionError: pass
    else: raise AssertionError('collector boundary accessible to subject')
for fd in os.listdir('/proc/self/fd'):
    if int(fd) > 2:
        try: destination = os.readlink('/proc/self/fd/'+fd)
        except FileNotFoundError: continue
        raise AssertionError('unexpected inherited descriptor '+destination)
'''
    sources = [
        ('root-boundary', boundary + emit, 'pass'),
        ('stderr-spoof', 'import os,sys\nos.chdir("/fixture/root")\nsys.stderr.write(\'chdir("/tmp") = 0\\n\');sys.stderr.flush()\nos.readlink("link")\n' + emit, 'fail'),
        ('safe-scratch', 'from pathlib import Path\np=Path("/tmp/fixture/root");p.mkdir(parents=True)\n(p/"probe.txt").write_bytes(b"abc")\n(p/"probe.txt").read_bytes()\n' + emit, 'pass'),
        ('metadata-opath', 'import os\nfd=os.open("/fixture/root/link",os.O_PATH|os.O_NOFOLLOW)\nassert os.readlink("/proc/self/fd/"+str(fd))=="/fixture/root/link"\nos.close(fd)\n' + emit, 'pass'),
        ('decoded-readlinkat', 'import os\nfd=os.open("/fixture/root",os.O_RDONLY|os.O_DIRECTORY)\nos.readlink("link",dir_fd=fd)\nos.close(fd)\n' + emit, 'fail'),
        ('trace-timeout', 'import time\ntime.sleep(20)\n', 'fail'),
    ]
    results = []
    for name, source, expected in sources:
        result = transport.run(name, case, {'treemap.py': source})
        actual = result['verdict']['status']
        results.append({'name':name,'expected':expected,'result':result})
        print(json.dumps({'name':name,'expected':expected,'actual':actual}),flush=True)
        if actual != expected: raise RuntimeError('isolation check failed: '+name)
    folder = args.run_root / 'invocations/stderr-spoof/collector-output'
    assert b'chdir("/tmp") = 0' in (folder/'stderr.bin').read_bytes()
    assert b'chdir("/tmp") = 0' not in (folder/'trace.bin').read_bytes()
    assert b'readlink("link",' in (folder/'trace.bin').read_bytes()
    name, source, _ = sources[0]
    reused = transport.run(name, case, {'treemap.py':source})
    assert reused['reused_closed_receipt']
    (args.run_root/'isolation-controls.json').write_bytes(encoded({
        'controls':results,'isolated_streams_observed':True,'closed_receipt_reused':True,
        'native_model_calls':0,'study_deliveries':0})+b'\n')
    print(json.dumps({'isolation_checks_passed':len(results),'native_model_calls':0,'study_deliveries':0}))


if __name__ == '__main__':
    main()
