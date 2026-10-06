"""Real installed T report/registration only; zero model calls or admission."""
from pathlib import Path
import datetime
import importlib.util
import json
import subprocess

from specorganon.role_jobs import canonical, digest, _read

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent


def main():
    assert ROOT.name == 'SpecOrganon'
    spec = importlib.util.spec_from_file_location('register_probe', ROOT / 'scripts/register_t_native_pilot.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    def image(name):
        return subprocess.check_output(['docker', 'image', 'inspect', name, '--format', '{{.Id}}'], text=True).strip()
    native = image('specorganon-codex:0.2.0rc3.dev12'); release = image('specorganon-release:0.2.0rc3.dev12')
    exe = '/home/stev/.local/bin/agy'
    transport = {'native_image': native, 'test_image': release,
        'author': {'provider': 'codex', 'model': 'gpt-6.1-sol', 'machine': 'Kratos',
                   'account_attribution': 'Original authorized Docker volume; quota/account unverified by this mechanical probe'},
        'reviewer': {'provider': 'gemini', 'model': 'Gemini 3.8 Flash (Medium)', 'machine': 'Kratos',
                     'account_attribution': 'Original authorized Gemini profile; no profile mounted or invoked by this probe'},
        'codex_volume': 'specorganon-lab_codex-home', 'gemini_profile': '/home/stev/.gemini',
        'gemini_executable': exe, 'gemini_executable_sha256': digest(_read(Path(exe), 536870912)),
        'codex_reasoning_effort': 'medium', 'test_timeout_seconds': 120}
    observation = OUT / 'review-capacity-observation.json'
    capacity = {'observed_at': json.loads(observation.read_text())['captured_at'],
        'scope': 'Observation only; no availability or admission inferred',
        'catalog': {'status': 'known', 'source': str(observation), 'sha256': digest(observation.read_bytes())},
        'quota': {'status': 'unknown', 'source': 'Original Docker volume quota is not inferred from desktop account', 'sha256': None}}
    runtime = Path('/tmp/specorganon-dev12-installed-T-preview')
    assert not runtime.exists()
    plan = module.prepare(ROOT, runtime, 'installed-T-preview-dev12', transport, capacity)
    raw = canonical(plan); target = OUT / 'installed-T-preview-plan.json'
    with target.open('xb') as f: f.write(raw)
    flags = ['docker', 'run', '--rm', '--network=none', '--read-only', '--tmpfs', '/tmp:rw,mode=1777',
             '-v', str(ROOT) + ':' + str(ROOT) + ':ro', '-v', exe + ':' + exe + ':ro']
    argv = [*flags, 'specorganon-release:0.2.0rc3.dev12', 'python', '-I', '-B', '-m',
            'specorganon.t_native_entry', 'report', str(target), '--plan-sha256', digest(raw)]
    result = subprocess.run(argv, capture_output=True, timeout=60)
    (OUT / 'installed-T-report.stdout').write_bytes(result.stdout)
    (OUT / 'installed-T-report.stderr').write_bytes(result.stderr)
    record = {'schema': 1, 'argv': argv, 'exit_code': result.returncode,
        'at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'stdout_sha256': digest(result.stdout), 'stderr_sha256': digest(result.stderr),
        'plan_sha256': digest(raw), 'source_module_count': 48, 'native_image': native, 'release_image': release,
        'runtime_created': runtime.exists(), 'native_model_calls': 0, 'credential_mounts': [],
        'scope': 'Installed wheel T bootstrap and read-only report; no native admission or qualification'}
    (OUT / 'installed-T-report.receipt.json').write_text(json.dumps(record, indent=2) + '\n')
    assert result.returncode == 2, result.stderr.decode()
    report = json.loads(result.stdout)
    assert report['status'] == 'incomplete' and report['planned_denominator'] == 10 and report['closed_attempts'] == 0
    assert all(p['status'] == 'not_started' for p in report['positions'])
    assert report['external_F'] is None and not report['goal_achieved'] and not runtime.exists()
    print(json.dumps({'installed_T_report': True, 'planned_positions': 10, 'native_model_calls': 0,
                      'runtime_created': False, 'development_qualification': False}))


if __name__ == '__main__': main()
