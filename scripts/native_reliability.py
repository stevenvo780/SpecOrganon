"""Fixed prospective development cohort; actual native roles, no substitutions.

This orchestrates the existing nine-phase controller without changing its gates.
Closed attempts are never regenerated. An interrupted attempt resumes only via
the controller/transport's exact persistent handles; uncertain calls fail closed.
The public checker is measured separately and never edits or repairs a delivery.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import datetime
import fcntl
import json
import math
import os
from pathlib import Path
import time

from specorganon import engine
from specorganon.docker_roles import DockerRoles
from specorganon.report import case_report
from specorganon.role_jobs import _json, _read, _safe, _write, canonical, digest
from specorganon.runner import describe_task
from specorganon.software_controller import Controller


class CohortError(ValueError):
    pass


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def immutable(path, value):
    if path.exists():
        if _read(path) != canonical(value):
            raise CohortError('closed cohort record changed: ' + path.name)
    else:
        _write(path, value)


def load_plan(path, expected):
    raw = _read(path)
    if digest(raw) != expected:
        raise CohortError('registration digest differs')
    r = _json(path)
    if (type(r) is not dict or type(r.get('schema')) is not int or r.get('schema') != 1
            or r.get('classification') != 'prospective public development reliability'
            or r.get('fixture_mode') is not False or r.get('automatic_replacement') is not False
            or r.get('max_actions_per_attempt') != 60 or len(r.get('attempts', [])) != 10):
        raise CohortError('requires fixed ten-attempt native development policy')
    ids = [a['id'] for a in r['attempts']]
    if len(set(ids)) != 10 or any(i != f'attempt-{n:02d}' for n, i in enumerate(ids, 1)):
        raise CohortError('attempt identities/order differ')
    counts = {t: sum(a['task'] == t for a in r['attempts']) for t in r['tasks']}
    if counts != {'rangeaudit': 4, 'ledgerfold': 3, 'topoplan': 3}:
        raise CohortError('requires registered three-task allocation')
    if (r['author']['provider'], r['reviewer']['provider']) != ('codex', 'gemini'):
        raise CohortError('independent provider routes required')
    source = _safe(r['source_root'])
    for name, sha in r['source_sha256'].items():
        p = Path(name)
        if p.is_absolute() or '..' in p.parts or digest(_read(source / p)) != sha:
            raise CohortError('registered source changed: ' + name)
    required = {'scripts/native_reliability.py', 'scripts/controller_native_role.py',
                r['mandate'], r['public_catalog'], r['seccomp'], 'pyproject.toml', 'uv.lock'}
    required.update(str(p.relative_to(source)) for p in source.glob('src/specorganon/*.py'))
    for task in r['tasks'].values():
        required.update([task['contract'], task['checker']])
    if not required <= r['source_sha256'].keys():
        raise CohortError('missing required source bindings')
    return r


def transport(r, root):
    source = Path(r['source_root'])
    return DockerRoles(root, native_image=r['native_image'], test_image=r['test_image'],
                       source_root=source, public_catalog=source / r['public_catalog'],
                       author_provider=r['author']['provider'], author_model=r['author']['model'],
                       reviewer_provider=r['reviewer']['provider'], reviewer_model=r['reviewer']['model'],
                       codex_volume=r['author']['original_volume'],
                       gemini_profile=r['reviewer']['original_profile'],
                       gemini_executable=r['reviewer']['executable'],
                       seccomp=source / r['seccomp'], codex_reasoning_effort=r['author']['effort'])


def controller(r, a, folder):
    t = transport(r, folder / 'transport')
    source = Path(r['source_root'])
    task = r['tasks'][a['task']]
    return Controller(folder / 'case', folder / 'controller', t,
                      contract=_read(source / task['contract']).decode(),
                      mandate=_read(source / r['mandate']).decode(), executor=t,
                      author_format='items-v1')


def bound_source(r, name):
    raw = _read(Path(r['source_root']) / name)
    if digest(raw) != r['source_sha256'][name]:
        raise CohortError('registered source changed before use: ' + name)
    return raw


def public_check(r, a, folder, ctrl):
    task = r['tasks'][a['task']]
    files = ctrl._files()
    files['check_public.py'] = bound_source(r, task['checker']).decode()
    t = transport(r, folder / 'independent-check-transport')
    measured = t.measure('public-contract-check',
                         ['/opt/specorganon/venv/bin/python', '-B', '/input/delivery/check_public.py',
                          *task['checker_args']], files)
    # A host receipt's argv is docker start/attach; engine test data use the
    # exact subject argv. Keep the original receipt intact for custody.
    t.verify_test({**measured, 'argv': measured['subject_argv']}, files, require_passed=False)
    receipt = Path(measured['test_job_ref'])
    result = None
    if not measured['timed_out'] and not measured['truncated_streams']:
        try:
            result = _json(receipt.parent / 'stdout.bin')
        except ValueError:
            if measured['passed']:
                raise CohortError('passing independent checker has no valid report')
    if measured['passed'] and type(result) is not dict:
        raise CohortError('passing independent checker needs an object report')
    # Exit zero alone cannot promote an empty/invalid/miscounted public report.
    if (result is not None and (type(result) is not dict or type(result.get('cases')) is not int
            or result['cases'] != task['public_cases'] or type(result.get('passed')) is not int
            or not 0 <= result['passed'] <= result['cases'] or type(result.get('failed')) is not list
            or len(result['failed']) != result['cases'] - result['passed']
            or measured['passed'] != (result['passed'] == result['cases']))):
        raise CohortError('independent checker report invalid')
    return {'passed': measured['passed'], 'measurement': measured, 'report': result}


def resources(folder):
    rows = []
    receipts = sorted((folder / 'transport/host-journal').glob('*/receipt.json'))
    receipts += sorted((folder / 'independent-check-transport/host-journal').glob('*/receipt.json'))
    for p in receipts:
        r = _json(p)
        rows.append({'job_id': r['job_id'], 'duration_seconds': r['duration_seconds'],
                     'exit_code': r['exit_code'], 'timed_out': r['timed_out'],
                     'receipt_sha256': digest(_read(p))})
    return {'measured_jobs': rows, 'job_seconds_sum': sum(x['duration_seconds'] for x in rows),
            'token_cost_comparability': 'unknown; heterogeneous provider counters',
            'monetary_cost': None}


def closure(folder, result):
    case = folder / 'case/organon.json'
    return {'schema': 1, 'registration_sha256': result['registration_sha256'],
            'outcome_sha256': digest(_read(folder / 'outcome.json')),
            'start_sha256': digest(_read(folder / 'started.json')),
            'case_sha256': digest(_read(case)) if case.exists() else None,
            'actions_sha256': {p.name: digest(_read(p)) for p in sorted(folder.glob('action-*.json'))}}


def close_attempt(folder, result):
    immutable(folder / 'outcome.json', result)
    immutable(folder / 'outcome-closure.json', closure(folder, result))


def read_closed(folder):
    result = _json(folder / 'outcome.json')
    if not (folder / 'outcome-closure.json').exists():
        raise CohortError('outcome without closed seal; retain uncertain record, no regeneration')
    if _json(folder / 'outcome-closure.json') != closure(folder, result):
        raise CohortError('closed attempt evidence changed')
    return result


def run_attempt(path, expected, r, a, root):
    folder = root / a['id']; folder.mkdir(mode=0o700, exist_ok=True)
    end = folder / 'outcome.json'
    if end.exists():
        return read_closed(folder)  # No controller or native call for a closed attempt.
    began = folder / 'started.json'
    if not began.exists():
        if any(folder.iterdir()):
            raise CohortError('pre-existing attempt artifacts without registered start; no adoption')
        immutable(began, {'schema': 1, 'registration_sha256': expected, 'attempt': a,
                          'at': now(), 'epoch': time.time()})
    start = _json(began)
    if start['registration_sha256'] != expected or start['attempt'] != a:
        raise CohortError('attempt binding differs')
    result = {'schema': 1, 'attempt': a, 'registration_sha256': expected,
              'generation_complete': False, 'independent_public_checks_passed': False}
    try:
        case = folder / 'case'
        if not case.exists():
            engine.create_case(case, 'Native reliability ' + a['id'] + ' ' + a['task'],
                               'development', 'human:owner', approval_policy='local')
        ctrl = controller(r, a, folder)
        for n in range(60):
            action_path = folder / f'action-{n+1:02d}.json'
            if action_path.exists():
                previous = _json(action_path)
                if previous['result'].get('action') == 'complete':
                    break
                continue
            # Read authoritative sources/state before every external action.
            load_plan(path, expected)
            state = engine.get_state(case)
            _write(folder / 'last-read-status.json', state)
            _write(folder / 'last-read-report.json', case_report(case))
            _write(folder / 'last-read-next-task.json', describe_task(state))
            started = time.time()
            action = ctrl.step()
            immutable(action_path, {'schema': 1, 'at': now(), 'result': action,
                                    'wall_seconds': time.time() - started})
            print(json.dumps({'at': now(), 'attempt': a['id'], 'task': a['task'],
                              'action_index': n+1, 'action': action.get('action'),
                              'phase': action.get('phase')}), flush=True)
            if action.get('action') == 'complete':
                break
        else:
            raise CohortError('fixed controller action ceiling exhausted')
        ctrl.package_gate()  # Verify fresh state, exact delivery and actual test receipts.
        load_plan(path, expected)
        result['generation_complete'] = True
        result['independent_public_check'] = public_check(r, a, folder, ctrl)
        load_plan(path, expected)
        ctrl.package_gate()
        result['independent_public_checks_passed'] = result['independent_public_check']['passed']
        result['accepted_phases'] = [k for k, v in engine.get_state(case)['phases'].items() if v['accepted']]
        result['status'] = 'complete'
    except Exception as exc:
        result.update(status='failed', error_type=type(exc).__name__, reason=str(exc))
    try:
        measured_resources = resources(folder)
    except Exception as exc:
        measured_resources = {'job_seconds_sum': None, 'error_type': type(exc).__name__, 'reason': str(exc),
                              'scope': 'resource evidence incomplete; no inferred zero cost'}
        result.update(status='failed', generation_complete=False, independent_public_checks_passed=False)
        result['resource_error'] = measured_resources
    result.update(at=now(), wall_seconds=time.time() - start['epoch'], resources=measured_resources)
    close_attempt(folder, result)
    return result


def wilson(success, n):
    z = 1.959963984540054
    p = success / n; den = 1 + z*z/n
    center = (p + z*z/(2*n)) / den
    half = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / den
    return [max(0, center-half), min(1, center+half)]


def report(r, expected, root, *, verify=True):
    rows = []
    for a in r['attempts']:
        folder = root / a['id']; p = folder / 'outcome.json'
        if not p.exists():
            rows.append({'attempt': a, 'status': 'in_progress' if (folder/'started.json').exists() else 'not_started',
                         'generation_complete': False, 'independent_public_checks_passed': False})
            continue
        row = read_closed(folder)
        if (row['attempt'] != a or row['registration_sha256'] != expected
                or row.get('status') not in {'complete', 'failed'}
                or type(row.get('generation_complete')) is not bool
                or type(row.get('independent_public_checks_passed')) is not bool
                or row['independent_public_checks_passed'] and not row['generation_complete']):
            raise CohortError('outcome binding differs')
        if verify and row.get('generation_complete'):
            ctrl = controller(r, a, folder)
            ctrl.package_gate()
            c = row.get('independent_public_check')
            if row['independent_public_checks_passed'] and c is None:
                raise CohortError('independent success has no measured evidence')
            if c is not None:
                task = r['tasks'][a['task']]; files = ctrl._files()
                files['check_public.py'] = bound_source(r, task['checker']).decode()
                t = transport(r, folder / 'independent-check-transport')
                t.verify_test({**c['measurement'], 'argv': c['measurement']['subject_argv']},
                              files, require_passed=False)
                measured = c['measurement']
                if (row['independent_public_checks_passed'] != measured['passed']
                        or c['passed'] != measured['passed']):
                    raise CohortError('independent check claim differs')
                if c['report'] is not None:
                    actual = _json(Path(measured['test_job_ref']).parent / 'stdout.bin')
                    if actual != c['report']:
                        raise CohortError('checker report differs from measured stdout')
                    if measured['passed'] and (type(actual.get('cases')) is not int
                            or actual['cases'] != task['public_cases']
                            or type(actual.get('passed')) is not int or actual['passed'] != actual['cases']
                            or actual.get('failed') != []):
                        raise CohortError('checker success report invalid')
                elif measured['passed']:
                    raise CohortError('checker success report missing')
        rows.append(row)
    closed = sum(row['status'] in {'complete', 'failed'} for row in rows)
    complete = sum(row['generation_complete'] is True for row in rows)
    functional = sum(row['independent_public_checks_passed'] is True for row in rows)
    tasks = {row['attempt']['task'] for row in rows if row['generation_complete'] is True}
    return {'schema': 1, 'at': now(), 'registration_sha256': expected, 'rows': rows,
            'classification': 'prospective public development reliability; not reserved comparison',
            'planned_attempts': 10, 'closed_attempts': closed, 'generation_complete': complete,
            'independent_public_checks_passed': functional, 'task_types_with_nine_phases': sorted(tasks),
            'generation_rate_planned_denominator': complete / 10,
            'generation_rate_wilson_95_descriptive': wilson(complete, 10) if closed == 10 else None,
            'development_reliability_observed_met': closed == 10 and complete >= 9 and len(tasks) >= 2,
            'superiority_achieved': False, 'goal_achieved': False,
            'reserved_subjects': 0, 'failures_replaced': 0}


def write_report(r, expected, root):
    try:
        summary = report(r, expected, root)
    except Exception as exc:
        raw = {}
        for a in r['attempts']:
            p = root / a['id'] / 'outcome.json'
            if p.exists():
                try:
                    raw[a['id']] = {'sha256': digest(_read(p)), 'unverified_outcome': _json(p)}
                except Exception as read_error:
                    raw[a['id']] = {'read_error': type(read_error).__name__}
        error = {'schema': 1, 'at': now(), 'classification': 'aggregation failed; raw labels are unverified',
                 'error_type': type(exc).__name__, 'reason': str(exc), 'raw_outcomes': raw,
                 'registration_sha256': expected, 'goal_achieved': False, 'verified': False}
        immutable(root / ('aggregation-error-' + str(time.time_ns()) + '.json'), error)
        raise
    _write(root / 'report.json', summary)
    return summary


@contextmanager
def lock(root):
    from specorganon.ledger import _open_regular_file
    root = _safe(root); root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.stat().st_uid != os.geteuid() or root.stat().st_mode & 0o022:
        raise CohortError('private owned cohort directory required')
    fd = _open_regular_file(root / '.cohort.lock', os.O_RDWR | os.O_CREAT)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation', choices=['run', 'report'])
    p.add_argument('registration', type=Path)
    p.add_argument('--registration-sha256', required=True)
    args = p.parse_args()
    r = load_plan(args.registration, args.registration_sha256)
    root = Path(r['run_root'])
    with lock(root):
        immutable(root / 'registration.json', r)
        if args.operation == 'run':
            for a in r['attempts']:
                load_plan(args.registration, args.registration_sha256)
                run_attempt(args.registration, args.registration_sha256, r, a, root)
                write_report(r, args.registration_sha256, root)
        summary = write_report(r, args.registration_sha256, root)
        print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
