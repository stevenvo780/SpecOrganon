"""Prepare six public development positions without Docker or model calls.

This is a mutable-development plan, not a release freeze or competence judgment.
Use the installed organon-controls bootstrap for execution/reporting afterwards.
"""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import subprocess

from specorganon import __version__
from specorganon.neutral_pilot import ATTEMPTS, CLASSIFICATION, LIMITS, POLICY_DEFINITION, TEST_FILES, CASE_INDEX
from specorganon.role_jobs import _read, _safe, canonical, digest


def prepare(source, runtime, pilot_id, native_image, test_image):
    source = _safe(source); runtime = _safe(runtime)
    base = 'goals/method-superiority-v1/development/'
    tasks = {}
    for name, stem, cases in [('rangeaudit', 'range-audit', 115), ('ledgerfold', 'ledger-fold', 104),
                              ('topoplan', 'topo-plan', 105)]:
        tasks[name] = {'contract': base + 'neutral-public-v1/' + stem + '-contract.md',
                       'test_file': TEST_FILES[name], 'public_cases': cases,
                       'case_index': CASE_INDEX,
                       'checker': base + ('check_rangeaudit_public.py' if name == 'rangeaudit' else 'check_cohort_public.py'),
                       'checker_args': [] if name == 'rangeaudit' else [name]}
    catalog = 'experiments/software_comparison_v3/public-models.json'
    seccomp = 'docker/codex/seccomp-codex.json'
    mandate = base + 'neutral-public-v1/mandate.md'
    paths = {'pyproject.toml', 'uv.lock', 'scripts/controller_native_role.py', 'scripts/register_neutral_pilot.py',
             'scripts/index_neutral_public_cases.py',
             catalog, seccomp, mandate}
    paths.update(str(p.relative_to(source)) for p in (source / 'src/specorganon').glob('*.py'))
    for task in tasks.values():
        paths.update([task['contract'], task['checker'], task['case_index']])
    bindings = {p: digest(_read(source / p)) for p in sorted(paths)}
    executable = '/home/stev/.local/bin/agy'
    return {'schema': 1, 'classification': CLASSIFICATION, 'id': pilot_id,
            'registered_at': datetime.now(timezone.utc).isoformat(), 'candidate_version': __version__,
            'source_root': str(source), 'source_commit': subprocess.check_output(
                ['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip(), 'source_sha256': bindings,
            'run_root': str(runtime), 'fixture_mode': False, 'automatic_replacement': False,
            'controller_limits': LIMITS, 'control_definition': POLICY_DEFINITION,
            'public_catalog': catalog, 'seccomp': seccomp, 'mandate': mandate, 'tasks': tasks,
            'attempts': ATTEMPTS, 'scope': {'reserved': False, 'T_qualification': False,
                'competence_established': False, 'superiority_evaluated': False, 'external_F': None, 'common_complete': None},
            'transport': {'native_image': native_image, 'test_image': test_image,
                'author': {'provider': 'codex', 'model': 'gpt-6.1-sol', 'machine': 'Kratos',
                    'account_attribution': 'Original authorized Docker volume; volume quota unknown'},
                'reviewer': {'provider': 'gemini', 'model': 'Gemini 3.8 Flash (Medium)', 'machine': 'Kratos',
                    'account_attribution': 'Original /home/stev/.gemini profile; no copied credentials'},
                'codex_volume': 'specorganon-lab_codex-home', 'gemini_profile': '/home/stev/.gemini',
                'gemini_executable': executable, 'gemini_executable_sha256': digest(_read(Path(executable), 536870912)),
                'codex_reasoning_effort': 'medium', 'test_timeout_seconds': 120}}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('plan', type=Path)
    p.add_argument('--source-root', type=Path, required=True)
    p.add_argument('--run-root', type=Path, required=True)
    p.add_argument('--pilot-id', required=True)
    p.add_argument('--native-image', required=True)
    p.add_argument('--test-image', required=True)
    a = p.parse_args()
    if a.plan.exists() or a.run_root.exists():
        raise ValueError('fresh plan and runtime required; no overwrite or automatic replacement')
    plan = prepare(a.source_root, a.run_root, a.pilot_id, a.native_image, a.test_image)
    # Publication is exclusive, never replace an existing registration.
    a.plan.parent.mkdir(parents=True, exist_ok=True)
    raw = canonical(plan)
    with a.plan.open('xb') as f:
        f.write(raw)
    print(canonical({'plan': str(a.plan.absolute()), 'sha256': digest(raw), 'source_bindings': len(plan['source_sha256']),
                     'planned_attempts': 6, 'model_calls': 0, 'competence_established': False}).decode())


if __name__ == '__main__':
    main()
