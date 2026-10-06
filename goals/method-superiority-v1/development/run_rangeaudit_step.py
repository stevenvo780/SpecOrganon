"""One recorded native development action; never substitutes a failed attempt."""
from __future__ import annotations
import argparse
import datetime
import hashlib
import json
from pathlib import Path

from specorganon import engine
from specorganon.docker_roles import DockerRoles
from specorganon.report import case_report
from specorganon.runner import describe_task
from specorganon.role_jobs import _json, _write
from specorganon.software_controller import Controller


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('registration', type=Path)
    args = parser.parse_args()
    r = _json(args.registration)
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    source = Path(r['source_root'])
    for name, expected in r['source_sha256'].items():
        assert sha(source/name) == expected, 'registered development source changed'
    assert sha(Path(r['contract'])) == r['contract_sha256']
    assert sha(Path(r['mandate'])) == r['mandate_sha256']
    run = Path(r['run_root']); case = run/'case'
    if (run/'terminal-failure.json').exists():
        raise RuntimeError('development attempt is terminal; no automatic replacement')
    if not case.exists():
        engine.create_case(case, 'RangeAudit native development 01', 'development',
                           'human:owner', approval_policy='local')
    _write(run/'last-read-status.json', engine.get_state(case))
    _write(run/'last-read-report.json', case_report(case))
    _write(run/'last-read-next-task.json', describe_task(engine.get_state(case)))
    transport = DockerRoles(run/'transport', native_image=r['native_image'], test_image=r['test_image'],
        source_root=source, public_catalog=source/'experiments/software_comparison_v3/public-models.json',
        author_provider='codex', author_model='gpt-6.1-sol',
        reviewer_provider='gemini', reviewer_model='Gemini 3.8 Flash (Medium)',
        codex_volume='specorganon-lab_codex-home', gemini_profile='/home/stev/.gemini',
        gemini_executable='/home/stev/.local/bin/agy',
        seccomp=source/'docker/codex/seccomp-codex.json', codex_reasoning_effort='medium')
    controller = Controller(case, run/'controller', transport,
        contract=Path(r['contract']).read_text(), mandate=Path(r['mandate']).read_text(),
        executor=transport, author_format='items-v1')
    try:
        result = controller.step()
    except Exception as error:
        _write(run/'terminal-failure.json', {'schema':1,'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'error_type':type(error).__name__,'reason':str(error),'automatic_retry':False,
            'classification':'native development attempt, not confirmatory result'})
        raise
    receipt = {'schema':1,'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
               'classification':'native development action, not method superiority',
               'registration_sha256':sha(args.registration),'result':result,
               'nine_phase_delivery':result.get('package_allowed',False),'reserved_subjects':0}
    path = run/('action-'+receipt['at'].replace(':','_')+'.json')
    _write(path, receipt)
    print(json.dumps(receipt))


if __name__ == '__main__': main()
