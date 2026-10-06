"""Install the image-built wheel on the host; report only, no providers."""
from pathlib import Path
import hashlib
import json
import subprocess
import time

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
HOST = Path('/tmp/specorganon-dev12-cut2-wheel-host')


def run(name, argv, expected=0):
    started = time.monotonic()
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=180)
    (OUT / (name + '.stdout')).write_bytes(result.stdout)
    (OUT / (name + '.stderr')).write_bytes(result.stderr)
    record = {'argv': argv, 'exit_code': result.returncode, 'seconds': time.monotonic() - started,
              'stdout_sha256': hashlib.sha256(result.stdout).hexdigest(),
              'stderr_sha256': hashlib.sha256(result.stderr).hexdigest(), 'native_model_calls': 0}
    (OUT / (name + '.receipt.json')).write_text(json.dumps(record, indent=2) + '\n')
    assert result.returncode == expected, result.stderr.decode(errors='replace')[-3000:]
    return result


def main():
    HOST.mkdir(mode=0o700, exist_ok=False)
    argv = ['docker', 'run', '--rm', '--network=none', '--read-only', '--tmpfs', '/tmp:rw,mode=1777',
            'specorganon-release:0.2.0rc3.dev12', '/usr/bin/cat',
            '/opt/specorganon/dist/specorganon-0.2.0rc3.dev12-py3-none-any.whl']
    r = subprocess.run(argv, capture_output=True, timeout=30)
    assert r.returncode == 0, r.stderr.decode()
    wheel = HOST / 'specorganon-0.2.0rc3.dev12-py3-none-any.whl'; wheel.write_bytes(r.stdout)
    (OUT / 'cut2-host-wheel-extraction.json').write_text(json.dumps({'schema': 1, 'argv': argv,
        'exit_code': r.returncode, 'wheel_sha256': hashlib.sha256(r.stdout).hexdigest(),
        'wheel_bytes': len(r.stdout), 'path': str(wheel), 'scope': 'Image-built wheel bytes only; no auth or provider execution'}, indent=2) + '\n')
    run('cut2-host-wheel-venv', ['uv', 'venv', '--python', '3.13', str(HOST / 'venv')])
    req = HOST / 'requirements.txt'
    run('cut2-host-wheel-export', ['uv', 'export', '--frozen', '--extra', 'dev', '--no-emit-project',
                             '--format', 'requirements-txt', '-o', str(req)])
    run('cut2-host-wheel-dependencies', ['uv', 'pip', 'install', '--python', str(HOST / 'venv/bin/python'),
                                    '--require-hashes', '-r', str(req)])
    run('cut2-host-wheel-package', ['uv', 'pip', 'install', '--python', str(HOST / 'venv/bin/python'), '--no-deps', str(wheel)])
    run('cut2-host-wheel-check', ['uv', 'pip', 'check', '--python', str(HOST / 'venv/bin/python')])
    plan = OUT / 'cut2-installed-T-preview-plan.json'
    pin = hashlib.sha256(plan.read_bytes()).hexdigest()
    result = run('cut2-host-installed-T-report', [str(HOST / 'venv/bin/python'), '-I', '-B', '-m',
        'specorganon.t_native_entry', 'report', str(plan), '--plan-sha256', pin], expected=2)
    report = json.loads(result.stdout)
    assert report['status'] == 'incomplete' and report['planned_denominator'] == 10 and report['closed_attempts'] == 0
    assert not report['development_qualification'] and not report['goal_achieved']
    assert not Path('/tmp/specorganon-dev12-cut2-installed-T-preview').exists()
    print(json.dumps({'host_installed_T_report': True, 'native_model_calls': 0,
                      'wheel_sha256': hashlib.sha256(wheel.read_bytes()).hexdigest()}))


if __name__ == '__main__': main()
