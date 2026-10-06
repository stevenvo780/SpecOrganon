"""Register ten fixed new development attempts before any generation."""
import argparse
import datetime
import json
from pathlib import Path
import subprocess

from specorganon.role_jobs import _read, _write, digest
from specorganon import __version__


def main():
    p = argparse.ArgumentParser()
    p.add_argument('registration', type=Path)
    p.add_argument('--run-root', type=Path, required=True)
    p.add_argument('--cohort-id', required=True)
    p.add_argument('--native-image', required=True)
    p.add_argument('--test-image', required=True)
    args = p.parse_args()
    if args.registration.exists() or args.run_root.exists():
        raise ValueError('new cohort registration and runtime required; no overwrite')
    source = Path(__file__).resolve().parents[3]
    base = 'goals/method-superiority-v1/development/'
    paths = list(source.glob('src/specorganon/*.py'))
    paths += [source / n for n in ['pyproject.toml', 'uv.lock', 'scripts/controller_native_role.py',
              'scripts/native_reliability.py', 'scripts/run_registered_native.py', 'docker/codex/seccomp-codex.json',
              'experiments/software_comparison_v3/public-models.json',
              base + 'register_native_cohort.py', base + 'range-audit-contract.md',
              base + 'ledger-fold-contract.md', base + 'topo-plan-contract.md',
              base + 'cohort-mandate.md', base + 'check_rangeaudit_public.py', base + 'check_cohort_public.py']]
    sha = {str(f.relative_to(source)): digest(_read(f)) for f in sorted(set(paths))}
    if not args.cohort_id or '/' in args.cohort_id:
        raise ValueError('explicit new cohort ID required')
    for image in [args.native_image, args.test_image]:
        if len(image) != 71 or not image.startswith('sha256:') or any(c not in '0123456789abcdef' for c in image[7:]):
            raise ValueError('image digest required')
    r = {'schema': 2, 'id': args.cohort_id, 'candidate_version': __version__,
         'admission_repair': True, 'author_format': 'items-v1',
         'registered_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
         'classification': 'prospective public development reliability',
         'source_root': str(source), 'source_commit': subprocess.check_output(
             ['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip(),
         'source_sha256': sha, 'run_root': str(args.run_root.absolute()),
         'fixture_mode': False, 'automatic_replacement': False, 'max_actions_per_attempt': 60,
         'controller_limits': {'roles': 40, 'authors_per_phase': 2, 'build_authors': 3,
                               'phase_reviews': 2, 'mandate_checks': 2, 'tests_per_id': 2,
                               'items_per_phase': 6, 'phase_encoded_bytes': 6000,
                               'delivery_encoded_bytes': 20000, 'test_stream_encoded_bytes': 4000,
                               'transport_wall_seconds': 6000},
         'author': {'machine': 'Kratos', 'provider': 'codex', 'model': 'gpt-6.1-sol', 'effort': 'medium',
                    'original_volume': 'specorganon-lab_codex-home',
                    'account_attribution': 'Original authorized Docker volume; no account/profile copies',
                    'volume_specific_quota': 'unknown; app quota cannot be attributed to this volume'},
         'reviewer': {'machine': 'Kratos', 'provider': 'gemini', 'model': 'Gemini 3.8 Flash (Medium)',
                      'original_profile': '/home/stev/.gemini', 'executable': '/home/stev/.local/bin/agy'},
         'native_image': args.native_image,
         'test_image': args.test_image,
         'public_catalog': 'experiments/software_comparison_v3/public-models.json',
         'seccomp': 'docker/codex/seccomp-codex.json', 'mandate': base + 'cohort-mandate.md',
         'tasks': {
             'rangeaudit': {'contract': base + 'range-audit-contract.md',
                            'checker': base + 'check_rangeaudit_public.py', 'checker_args': [], 'public_cases': 115},
             'ledgerfold': {'contract': base + 'ledger-fold-contract.md',
                            'checker': base + 'check_cohort_public.py', 'checker_args': ['ledgerfold'], 'public_cases': 104},
             'topoplan': {'contract': base + 'topo-plan-contract.md',
                          'checker': base + 'check_cohort_public.py', 'checker_args': ['topoplan'], 'public_cases': 105}},
         'attempts': [{'id': f'attempt-{i+1:02d}', 'task': task} for i, task in enumerate(
             ['rangeaudit', 'ledgerfold', 'topoplan'] * 3 + ['rangeaudit'])],
         'criteria': {'generation_complete_rate': .90, 'planned_denominator': 10,
                      'problem_types': 3, 'types_with_nine_phases': 2,
                      'public_functional_check_separate': True},
         'scope_limits': {'reserved': False, 'blinded': False, 'superiority_result': False,
                          'previous_single_case_excluded_from_denominator': True,
                          'same_public_contract_repeated': True, 'closed_v3_reopened': False,
                          'new_software_candidate_version': True,
                          'previous_cohorts_preserved': True}}
    args.registration.parent.mkdir(parents=True, exist_ok=True)
    _write(args.registration, r)
    print(json.dumps({'registration': str(args.registration), 'sha256': digest(_read(args.registration)),
                      'source_bindings': len(sha), 'planned_attempts': 10, 'new_model_calls': 0}))


if __name__ == '__main__':
    main()
