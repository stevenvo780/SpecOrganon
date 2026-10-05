"""One preregistered CSVShape engineering identity. No automatic replacement."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import re

from specorganon import engine
from specorganon.docker_roles import DockerRoles, DockerRoleError
from specorganon.report import case_report
from specorganon.role_jobs import JobError, _read, _json, _write, _safe, canonical, digest
from specorganon.runner import describe_task
from specorganon.software_controller import Controller, ControllerError
from scripts.study_cell_budget import CellBudget, StudyBudgetError, StudyClockPause
from scripts.study_campaign import current_quota, CampaignPause


class RegistrationError(ValueError):
    pass


def verify_registration(path, *, check_sources=True):
    raw = _read(path, 128000); value = _json(path)
    required = {'schema', 'identity', 'registered_at', 'source_root', 'case', 'run_root',
                'source_sha256', 'images', 'routes', 'profiles', 'limits', 'public_catalog',
                'public_context', 'mandate', 'review', 'review_sha256', 'matrix_sha256', 'matrix_count'}
    if (type(value) is not dict or set(value) != required or value['schema'] != 1
            or value['identity'] != 'csvshape-delivery-v1' or value['matrix_count'] != 48):
        raise RegistrationError('immutable CSVShape registration schema required')
    source = _safe(value['source_root']); case = _safe(value['case']); root = _safe(value['run_root'])
    try:
        registered = dt.datetime.fromisoformat(value['registered_at'])
        if registered.utcoffset() != dt.timedelta(0) or registered > dt.datetime.now(dt.timezone.utc):
            raise ValueError('registration timestamp is future-dated or not UTC')
    except (TypeError, ValueError) as exc:
        raise RegistrationError('prior UTC registration timestamp required') from exc
    if (str(source) != value['source_root'] or case != source / 'cases/csvshape_v1'
            or str(root) != value['run_root'] or source == root or source in root.parents):
        raise RegistrationError('fixed canonical source/case/private root required')
    expected_routes = {'author': {'provider': 'gemini', 'model': 'Gemini 3.8 Flash (Medium)'},
                       'review': {'provider': 'codex', 'model': 'gpt-6.1-sol', 'effort': 'low'}}
    expected_profiles = {'codex_volume': 'specorganon-lab_codex-home',
                         'gemini_profile': '/home/stev/.gemini', 'gemini_executable': '/home/stev/.local/bin/agy'}
    if value['routes'] != expected_routes or value['profiles'] != expected_profiles:
        raise RegistrationError('fixed original routes/profiles required')
    if value['limits'] != {'max_calls': 40, 'max_total_input_bytes': 3145728, 'max_elapsed_seconds': 6000}:
        raise RegistrationError('fixed prospective limits required')
    if (type(value['images']) is not dict or set(value['images']) != {'native', 'test'}
            or any(type(v) is not str or not re.fullmatch('sha256:[0-9a-f]{64}', v) for v in value['images'].values())):
        raise RegistrationError('immutable images required')
    sources = value['source_sha256']
    if type(sources) is not dict or not sources: raise RegistrationError('source bindings required')
    core = {'scripts/csvshape_delivery.py', 'scripts/study_cell_budget.py', 'scripts/study_campaign.py',
            'scripts/controller_native_role.py', 'experiments/csvshape_delivery_v1/reserved.py',
            'experiments/csvshape_delivery_v1/subjects.py', 'experiments/csvshape_delivery_v1/protocol.md',
            'experiments/csvshape_delivery_v1/contract.md', 'experiments/csvshape_delivery_v1/public-evidence.md'}
    core |= {str(p.relative_to(source)) for p in (source / 'src/specorganon').rglob('*.py')}
    core |= {str(p.relative_to(source)) for p in (source / 'scripts').rglob('*.py')}
    core |= {str(p.relative_to(source)) for p in (source / 'experiments/software_comparison_v1').rglob('*.py')}
    core |= {str(p.relative_to(source)) for p in (source / 'experiments/csvshape_delivery_v1').rglob('*.py')}
    core |= {value[key] for key in ('public_catalog', 'public_context', 'mandate')}
    if not core <= sources.keys(): raise RegistrationError('incomplete source freeze')
    for name, checksum in sources.items():
        p = Path(name)
        if (p.is_absolute() or '..' in p.parts or type(checksum) is not str
                or not re.fullmatch('[0-9a-f]{64}', checksum)):
            raise RegistrationError('unsafe source binding')
        if check_sources and digest(_read(source / name, 2097152)) != checksum:
            raise RegistrationError('registered source changed: ' + name)
    review_path = Path(value['review'])
    if review_path.is_absolute() or '..' in review_path.parts:
        raise RegistrationError('unsafe review path')
    if digest(_read(source / review_path, 128000)) != value['review_sha256']:
        raise RegistrationError('accepted review receipt changed')
    review = _json(source / review_path)
    if (review.get('verdict') != 'accept' or review.get('native_tests_executed') is not False
            or review.get('reviewed_source_sha256') != sources or not review.get('job_id')):
        raise RegistrationError('actual independent accepted review binding required')
    from experiments.csvshape_delivery_v1.reserved import recipes
    if digest(canonical(recipes())) != value['matrix_sha256']: raise RegistrationError('reserved matrix changed')
    return value, digest(raw)


@contextmanager
def run_lock(root):
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = root.stat()
    if info.st_uid != os.geteuid() or info.st_mode & 0o022: raise RegistrationError('private owned run root required')
    fd = os.open(root / '.delivery.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally: os.close(fd)


DOC_IDS = ['installation', 'stdin_argv', 'example_1', 'example_2', 'error_framing', 'limits', 'value_semantics', 'tests_scope']
METHOD_IDS = ['nine_phases', 'current_traces', 'substantive_alternatives', 'actual_test_receipts', 'separate_reviews', 'honest_scope']


def final_audit(controller, budget, root):
    """One physically separate native rubric judgment, inside the same call cap."""
    state = engine.get_state(controller.case)
    history = _json(controller.root / 'progress.json')['history']
    request = {'schema': 1, 'role': 'review', 'role_instructions':
        'Final documentation/method audit after nine-phase package gate, BEFORE reserved evaluation. '
        'Do not generate/repair files or invent execution. All execution evidence is supplied. '
        'Return ONLY {"schema":1,"verdict":"accept"|"reject"|"inconclusive","findings":[],"tests_executed":false,'
        '"doc_checks":[{"id":ID,"passed":BOOL,"reason":TEXT}],'
        '"method_checks":[{"id":ID,"passed":BOOL,"reason":TEXT}],"reason":TEXT}. '
        'Accept only when every point is true. Findings are nonempty JSON objects identifying problems; '
        'use an empty findings array only when there are none. '
        'Use exactly the ordered IDs in rubric.json. Pass each only on concrete supplied evidence; '
        'missing or uncertain evidence means false. doc_checks: installation=Python3.12 stdlib usable install; '
        'stdin_argv=exact delimiter/argv semantics; example_1 and example_2=complete runnable commands plus '
        'correct expected output for each public example (actual execution is externally judged later); '
        'error_framing=exact exit/stdout/stderr documented; limits=all contractual limits documented; '
        'value_semantics=empty/distinct/Unicode exactness; tests_scope=real usable tests and honest scope. '
        'method_checks: nine_phases=current accepted9/9; current_traces=valid requirement/criterion '
        'grounding; substantive_alternatives=two meaningfully different feasible choices, one without '
        'new software; actual_test_receipts=verified actual isolated successful test supplied for exact '
        'delivery; separate_reviews=all nine independently accepted by isolated different-provider '
        'reviewer in supplied history; honest_scope=assessments make no invented reserved/field/causal '
        'claims and declare uncertainty/cost unknown. A technical pass never proves method superiority.',
        'documents': {'rubric.json': canonical({'doc_ids': DOC_IDS, 'method_ids': METHOD_IDS}).decode(),
                      'contract.txt': controller.contract, 'state.json': canonical(state).decode(),
                      'report.json': canonical(case_report(controller.case)).decode(),
                      'files.json': canonical(controller._files()).decode(),
                      'controller-history.json': canonical(history).decode(),
                      'verified-tests.json': canonical([{'id': i['id'], 'data': i['data'],
                          'receipt': _json(i['data']['test_job_ref'])}
                          for i in state['items'].values() if i['kind'] == 'test']).decode()}}
    packet = budget.call('final-doc-method-audit', 'review', request)
    result = packet.get('result')
    if (type(result) is not dict or set(result) != {'schema', 'verdict', 'findings', 'tests_executed', 'doc_checks', 'method_checks', 'reason'}
            or type(result['schema']) is not int or result['schema'] != 1 or result['tests_executed'] is not False
            or type(result['reason']) is not str or not result['reason'].strip()):
        raise ControllerError('invalid native final audit response')
    from scripts.controller_native_role import validate_result
    validate_result(result, 'review')
    for name, ids in [('doc_checks', DOC_IDS), ('method_checks', METHOD_IDS)]:
        checks = result[name]
        if (type(checks) is not list or len(checks) != len(ids)
                or any(type(c) is not dict or set(c) != {'id', 'passed', 'reason'} or c['id'] != identity
                    or type(c['passed']) is not bool or type(c['reason']) is not str or not c['reason'].strip()
                    for identity, c in zip(ids, checks))):
            raise ControllerError('invalid native final audit checklist')
    if result['verdict'] == 'accept' and not all(c['passed'] for c in result['doc_checks'] + result['method_checks']):
        raise ControllerError('audit acceptance contradicts failed checklist')
    audited = {'schema': 1, 'packet': packet, 'documentation_passed': result['verdict'] == 'accept' and all(c['passed'] for c in result['doc_checks']),
               'method_passed': result['verdict'] == 'accept' and all(c['passed'] for c in result['method_checks']),
               'documentation_score': sum(c['passed'] for c in result['doc_checks']), 'documentation_denominator': 8,
               'delivery_sha256': digest(canonical(controller._files()))}
    _write(root / 'final-doc-method-audit.json', audited)
    return audited


def run(path, quota, *, initialize=False, steps=1):
    value, checksum = verify_registration(path, check_sources=False)
    root = Path(value['run_root']); case = Path(value['case']); source = Path(value['source_root'])
    with run_lock(root):
        binding_path = root / 'registration-binding.json'
        binding = {'registration_sha256': checksum, 'identity': value['identity']}
        if binding_path.exists() and _json(binding_path) != binding: raise RegistrationError('running identity changed')
        if not binding_path.exists(): _write(binding_path, binding)
        terminal = root / 'terminal.json'
        if terminal.exists(): return _json(terminal)
        budget = None
        try:
            verify_registration(path)
            observation = current_quota(quota)
            _write(root / 'last-quota-observation.json', observation)
            if initialize:
                if case.exists() or (root / 'initialized.json').exists():
                    raise RegistrationError('existing identity cannot be reinitialized')
                engine.create_case(case, 'CSVShape v1 prospective engineering delivery', 'development',
                                   'human:owner', approval_policy='local')
                _write(root / 'initialized.json', {'registration_sha256': checksum,
                       'at': dt.datetime.now(dt.timezone.utc).isoformat(), 'case': str(case),
                       'artifact_generation_calls': 0})
                return {'status': 'initialized', 'artifact_generation_calls': 0}
            if not (root / 'initialized.json').exists() or not case.exists():
                raise RegistrationError('explicit one-time initialization required before generation')
            def validate():
                verify_registration(path)
                _write(root / 'last-quota-observation.json', current_quota(quota))
            transport = DockerRoles(root / 'transport', source_root=source,
                native_image=value['images']['native'], test_image=value['images']['test'],
                public_catalog=source / value['public_catalog'], author_provider='gemini',
                author_model=value['routes']['author']['model'], reviewer_provider='codex',
                reviewer_model=value['routes']['review']['model'], codex_reasoning_effort='low',
                **value['profiles'])
            budget = CellBudget(root / 'budget', protocol_sha256=checksum,
                                transport=transport, validate=validate, **value['limits'])
            controller = Controller(case, root / 'controller', budget, executor=budget,
                contract=_read(source / value['public_context'], 64000).decode(),
                mandate=_read(source / value['mandate'], 16000).decode())
            for _ in range(steps):
                validate()
                state = engine.get_state(case); report = case_report(case); task = describe_task(state)
                _write(root / 'last-before-step.json', {'state': state, 'report': report, 'task': task})
                result = controller.step()
                print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
                _write(root / 'last-step.json', result)
                if result['action'] == 'complete':
                    audit = final_audit(controller, budget, root)
                    if not (audit['documentation_passed'] and audit['method_passed']):
                        raise ControllerError('final independent documentation/method checklist failed')
                    result = {'status': 'package_gate_passed', 'package_allowed': result['package_allowed'],
                              'state': engine.get_state(case), 'report': case_report(case),
                              'budget': budget.summary(), 'delivery': str(controller.delivery),
                              'reserved_evaluation': 'pending', 'method_superiority': 'not demonstrated',
                              'documentation_score': audit['documentation_score'], 'method_checklist_passed': True}
                    _write(terminal, result); return result
            return {'status': 'bounded_steps_finished', 'budget': budget.summary(), 'terminal': False}
        except (CampaignPause, StudyClockPause) as exc:
            result = {'status': 'paused', 'reason': str(exc), 'budget_renewed': False,
                      'budget': budget.summary() if budget else None}
            _write(root / 'last-pause.json', result); return result
        except (ControllerError, DockerRoleError, JobError, StudyBudgetError, RegistrationError, OSError, ValueError) as exc:
            result = {'status': 'delivery_stopped', 'reason': str(exc), 'replacement': False,
                      'budget': budget.summary() if budget else None, 'reserved_evaluation': 'pending'}
            _write(terminal, result); return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registration', required=True); parser.add_argument('--quota', required=True)
    parser.add_argument('--initialize', action='store_true'); parser.add_argument('--steps', type=int, default=1)
    args = parser.parse_args()
    if not 1 <= args.steps <= 80: parser.error('steps must be 1..80')
    try: result = run(args.registration, args.quota, initialize=args.initialize, steps=args.steps)
    except (RegistrationError, JobError, OSError, ValueError) as exc:
        print(json.dumps({'status': 'registration_rejected', 'reason': str(exc)}), flush=True); return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
    return 2 if result['status'] in {'delivery_stopped', 'registration_rejected'} else 0


if __name__ == '__main__': raise SystemExit(main())
