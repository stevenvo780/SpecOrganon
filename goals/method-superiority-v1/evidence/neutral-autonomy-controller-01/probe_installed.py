"""Local installed-console guards only; no Docker or provider commands."""
import hashlib
import importlib.util
import json
from pathlib import Path
import py_compile
import struct
import subprocess
import sys


def main():
    base = Path(__file__).absolute().parent
    sequence = sys.argv[1] if len(sys.argv) == 2 else '01'
    assert sequence in ('01', '02', '03')
    local = base / 'local-install'; plan = local / 'plan.json'
    r = json.loads(plan.read_text()); pin = hashlib.sha256(plan.read_bytes()).hexdigest()
    console = local / 'venv/bin/organon-controls'
    python = local / 'venv/bin/python'
    result = subprocess.run([str(python), '-I', '-c',
        'import pathlib,sysconfig; print(pathlib.Path(sysconfig.get_path("purelib"))/"specorganon")'],
        capture_output=True, timeout=10, check=True)
    package = Path(result.stdout.decode().strip())
    modules = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in package.glob('*.py')}
    assert {f'src/specorganon/{name}': pin for name, pin in modules.items()} == {
        name: pin for name, pin in r['source_sha256'].items() if name.startswith('src/specorganon/')}
    logs = {}
    def call(name, argv):
        p = subprocess.run(argv, capture_output=True, timeout=30, cwd=local)
        (base / (name + '.stdout')).write_bytes(p.stdout)
        (base / (name + '.stderr')).write_bytes(p.stderr)
        logs[name] = {'argv': argv, 'exit_code': p.returncode,
                      'stdout_sha256': hashlib.sha256(p.stdout).hexdigest(),
                      'stderr_sha256': hashlib.sha256(p.stderr).hexdigest()}
        return p
    argv = [str(console), 'report', str(plan), '--plan-sha256', pin]
    assert call('installed-help-' + sequence, [str(console), '--help']).returncode == 0
    p = call('installed-report-' + sequence, argv)
    assert p.returncode == 2 and json.loads(p.stdout)['closed_attempts'] == 0
    assert len(json.loads(p.stdout)['positions']) == 6 and not Path(r['run_root']).exists()
    # Give normal import a valid timestamp pyc carrying deliberately wrong code.
    # The registered loader must compile the original checked .py bytes instead.
    target = package / 'neutral_pilot.py'
    cache = Path(importlib.util.cache_from_source(str(target)))
    cache.parent.mkdir(exist_ok=True)
    dummy = local / 'mutant.py'; dummy.write_text('raise RuntimeError("stale pyc must never execute")\n')
    py_compile.compile(str(dummy), cfile=str(cache), dfile=str(target), doraise=True)
    raw = cache.read_bytes(); info = target.stat()
    cache.write_bytes(raw[:8] + struct.pack('<II', int(info.st_mtime) & 0xffffffff, info.st_size & 0xffffffff) + raw[16:])
    p = call('installed-stale-pyc-' + sequence, argv)
    assert p.returncode == 2 and json.loads(p.stdout)['status'] == 'incomplete' and not p.stderr
    original = target.read_bytes()
    try:
        target.write_bytes(original + b'\n# substituted installed source\n')
        p = call('installed-mutated-source-' + sequence, argv)
        assert p.returncode == 2 and json.loads(p.stderr)['status'] == 'rejected'
    finally:
        target.write_bytes(original); cache.unlink(missing_ok=True)
    extra = package / 'unregistered_fixture.py'
    try:
        extra.write_text('raise RuntimeError("unregistered module")\n')
        p = call('installed-extra-module-' + sequence, argv)
        assert p.returncode == 2 and json.loads(p.stderr)['status'] == 'rejected'
    finally:
        extra.unlink(missing_ok=True)
    assert not Path(r['run_root']).exists()
    wheel = next((local / 'dist').glob('*.whl'))
    receipt = {'schema': 1, 'scope': 'Local installed N/S console/bootstrap guards; no Docker/provider generation',
               'wheel_sha256': hashlib.sha256(wheel.read_bytes()).hexdigest(), 'installed_modules_byte_equal': len(modules),
               'modules_sha256': modules, 'plan_sha256': pin, 'commands': logs,
               'runtime_created': False, 'native_generations': 0, 'external_F': None, 'goal_achieved': False}
    (base / ('installed-receipt-' + sequence + '.json')).write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'modules': len(modules), 'guards': len(logs), 'native_generations': 0}))


if __name__ == '__main__': main()
