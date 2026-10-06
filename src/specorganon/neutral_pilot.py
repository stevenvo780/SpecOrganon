"""Prospective public N/S development driver, never a reserved comparison.

The installed bootstrap is required. A fixed plan owns every attempt and source;
closed journals are reverified without dispatch. Pending cleanup stops the plan.
Functional public checks are separate and cannot complete a comparative package.
"""
from __future__ import annotations

from contextlib import contextmanager
import copy
import fcntl
from pathlib import Path
import os
import re
import stat
import sys

from . import __version__
from .docker_roles import DockerRoles, PendingCleanupError
from .ledger import strict_json_loads
from .neutral_controller import NeutralController, LIMITS, _clock, _elapsed
from .neutral_autonomy import AutonomousNeutralController
from .free_control_policy import CAPS
from .role_jobs import _json, _read, _safe, _write, canonical, digest


CLASSIFICATION = 'prospective public neutral development'
TASKS = ('rangeaudit', 'ledgerfold', 'topoplan')
TEST_FILES = {'rangeaudit': 'test_range_audit.py', 'ledgerfold': 'test_ledger_fold.py',
              'topoplan': 'test_topo_plan.py'}
DEVELOPMENT = 'goals/method-superiority-v1/development/'
CASE_INDEX = DEVELOPMENT + 'neutral-public-v1/case-index.json'
CHECKER_IDENTITY = {
    'rangeaudit': {'classification': 'independent public development checks; not reserved method comparison',
                  'oracle': 'integer-cell occupancy for small intervals; explicit public boundary expectations'},
    'ledgerfold': {'classification': 'independent public development checks; not reserved or blinded', 'task': 'ledgerfold'},
    'topoplan': {'classification': 'independent public development checks; not reserved or blinded', 'task': 'topoplan'}}
CASE_COUNTS = {'rangeaudit': 115, 'ledgerfold': 104, 'topoplan': 105}
CONTRACT_STEMS = {'rangeaudit': 'range-audit', 'ledgerfold': 'ledger-fold', 'topoplan': 'topo-plan'}
ATTEMPTS = [{'id': f'attempt-{n:02d}', 'task': task, 'method': method}
            for n, (task, method) in enumerate(((t, m) for t in TASKS for m in ('N', 'S')), 1)]
POLICY_DEFINITION = 'autonomous-N-and-staged-S-public-development-v2'
CONTROL_PROTOCOL = DEVELOPMENT + 'neutral-autonomy-v2/PROTOCOL.md'
CONTROL_MANDATE = DEVELOPMENT + 'neutral-autonomy-v2/mandate.md'
PLAN_LIMITS = {'common': LIMITS, 'N_effective': CAPS, 'S_effective': CAPS}


class PilotError(ValueError):
    pass


def immutable(path, value):
    if path.exists():
        if _read(path) != canonical(value):
            raise PilotError('immutable pilot record differs: ' + path.name)
    else:
        _write(path, value)


def _relative(name):
    if type(name) is not str or not name:
        raise PilotError('registered relative path required')
    path = Path(name)
    if path.is_absolute() or '..' in path.parts or path.as_posix() != name:
        raise PilotError('registered path must stay inside source root')
    return path


def _private(root, create=False):
    root = _safe(root)
    if create:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = root.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise PilotError('owned private mode0700 directory required')
    return root


@contextmanager
def _lock(root):
    path = root / '.pilot.lock'
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid():
            raise PilotError('invalid private pilot lock')
        fcntl.flock(fd, fcntl.LOCK_EX)
        named = path.lstat()
        if (named.st_ino, named.st_dev) != (info.st_ino, info.st_dev):
            raise PilotError('pilot lock replaced')
        yield
    finally:
        os.close(fd)


def load_plan(path, expected, *, installed_root):
    raw = _read(path)
    if digest(raw) != expected:
        raise PilotError('registered pilot digest differs')
    r = strict_json_loads(raw.decode())
    fields = {'schema', 'classification', 'id', 'registered_at', 'candidate_version', 'source_root',
              'source_commit', 'source_sha256', 'run_root', 'fixture_mode', 'automatic_replacement',
              'controller_limits', 'control_definition', 'transport', 'public_catalog', 'seccomp',
              'mandate', 'control_protocol', 'tasks', 'attempts', 'scope'}
    if (type(r) is not dict or set(r) != fields or type(r['schema']) is not int or r['schema'] != 2
            or r['classification'] != CLASSIFICATION or r['candidate_version'] != __version__
            or r['fixture_mode'] is not False or r['automatic_replacement'] is not False
            or canonical(r['controller_limits']) != canonical(PLAN_LIMITS)
            or r['control_protocol'] != CONTROL_PROTOCOL or r['mandate'] != CONTROL_MANDATE
            or r['control_definition'] != POLICY_DEFINITION or r['attempts'] != ATTEMPTS
            or r['scope'] != {'reserved': False, 'T_qualification': False, 'competence_established': False,
                              'superiority_evaluated': False, 'external_F': None, 'common_complete': None}
            or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', r['id']) is None
            or type(r['registered_at']) is not str or not r['registered_at']
            or re.fullmatch(r'[a-f0-9]{40}', r['source_commit']) is None):
        raise PilotError('exact prospective six-attempt public policy required')
    source = _safe(r['source_root']); runtime = _safe(r['run_root'])
    if (r['source_root'] != str(source) or r['run_root'] != str(runtime)
            or '..' in source.parts or '..' in runtime.parts
            or runtime == source or runtime.is_relative_to(source)):
        raise PilotError('runtime must be outside the registered source checkout')
    pins = r['source_sha256']
    if type(pins) is not dict or not pins or len(pins) > 256:
        raise PilotError('bounded source bindings required')
    required = {'pyproject.toml', 'uv.lock', 'scripts/controller_native_role.py',
                'scripts/register_neutral_pilot.py', 'scripts/index_neutral_public_cases.py',
                r['public_catalog'], r['seccomp'], r['mandate'], r['control_protocol']}
    required.update(str(p.relative_to(source)) for p in (source / 'src/specorganon').glob('*.py'))
    if type(r['tasks']) is not dict or set(r['tasks']) != set(TASKS):
        raise PilotError('three public task types required')
    for name, task in r['tasks'].items():
        expected_checker = DEVELOPMENT + ('check_rangeaudit_public.py' if name == 'rangeaudit' else 'check_cohort_public.py')
        if (type(task) is not dict or set(task) != {'contract', 'checker', 'checker_args', 'public_cases', 'test_file', 'case_index'}
                or type(task['checker_args']) is not list or any(type(a) is not str or '\0' in a for a in task['checker_args'])
                or type(task['public_cases']) is not int or not 1 <= task['public_cases'] <= 10000
                or task['test_file'] != TEST_FILES[name] or task['public_cases'] != CASE_COUNTS[name]
                or task['contract'] != DEVELOPMENT + 'neutral-public-v1/' + CONTRACT_STEMS[name] + '-contract.md'
                or task['checker'] != expected_checker or task['checker_args'] != ([] if name == 'rangeaudit' else [name])
                or task['case_index'] != CASE_INDEX):
            raise PilotError('invalid explicit public task policy')
        required.update([task['contract'], task['checker'], task['case_index']])
    if set(pins) != required:
        raise PilotError('exact registered source inventory required')
    for name, pin in pins.items():
        if type(pin) is not str or re.fullmatch(r'[a-f0-9]{64}', pin) is None or digest(_read(source / _relative(name))) != pin:
            raise PilotError('registered source bytes differ: ' + name)
    package = _safe(installed_root)
    modules = {n for n in pins if Path(n).parent == Path('src/specorganon')}
    if modules != {'src/specorganon/' + p.name for p in package.glob('*.py')}:
        raise PilotError('installed module inventory differs')
    for name in modules:
        if digest(_read(package / Path(name).name)) != pins[name]:
            raise PilotError('installed module bytes differ: ' + name)
    for name, module in tuple(sys.modules.items()):
        if name == 'specorganon' or name.startswith('specorganon.') and name != 'specorganon.neutral_native_entry':
            filename = '__init__.py' if name == 'specorganon' else name.split('.')[1] + '.py'
            rel = 'src/specorganon/' + filename
            if (getattr(module, '__registered_source_sha256__', None) != pins.get(rel)
                    or Path(module.__file__).absolute() != package / filename):
                raise PilotError('fresh registered installed bootstrap required: ' + name)
    transport = r['transport']
    transport_fields = {'native_image', 'test_image', 'author', 'reviewer', 'codex_volume', 'gemini_profile',
                        'gemini_executable', 'gemini_executable_sha256', 'codex_reasoning_effort', 'test_timeout_seconds'}
    if type(transport) is not dict or set(transport) != transport_fields:
        raise PilotError('explicit native transport policy required')
    for role, provider in [('author', 'codex'), ('reviewer', 'gemini')]:
        route = transport[role]
        if (type(route) is not dict or set(route) != {'provider', 'model', 'machine', 'account_attribution'}
                or route['provider'] != provider or route['machine'] != 'Kratos'
                or any(type(v) is not str or not v.strip() for v in route.values())):
            raise PilotError('explicit independent Codex/Gemini attribution required')
    for kind in ('native_image', 'test_image'):
        if type(transport[kind]) is not str or re.fullmatch(r'sha256:[a-f0-9]{64}', transport[kind]) is None:
            raise PilotError('immutable image IDs required')
    if (type(transport['codex_volume']) is not str
            or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', transport['codex_volume']) is None
            or transport['codex_reasoning_effort'] not in ('low', 'medium', 'high', 'xhigh')
            or type(transport['test_timeout_seconds']) is not int or not 1 <= transport['test_timeout_seconds'] <= 120):
        raise PilotError('invalid native effort, timeout or original volume')
    _safe(transport['gemini_profile']); executable = _safe(transport['gemini_executable'])
    if digest(_read(executable, 536870912)) != transport['gemini_executable_sha256']:
        raise PilotError('registered Gemini executable changed')
    for name in TASKS:
        case_index(r, name)
    return r


def bound_source(r, name):
    raw = _read(Path(r['source_root']) / _relative(name))
    if digest(raw) != r['source_sha256'][name]:
        raise PilotError('registered source changed before use: ' + name)
    return raw


def case_index(r, task):
    index = strict_json_loads(bound_source(r, CASE_INDEX).decode())
    if type(index) is not dict or set(index) != {'schema', 'tasks'} or type(index['schema']) is not int or index['schema'] != 1 or set(index['tasks']) != set(TASKS):
        raise PilotError('invalid public case index')
    item = index['tasks'][task]; policy = r['tasks'][task]
    if (type(item) is not dict or set(item) != {'checker', 'checker_sha256', 'checker_args', 'identity', 'cases'}
            or item['checker'] != policy['checker'] or item['checker_sha256'] != r['source_sha256'][policy['checker']]
            or item['checker_args'] != policy['checker_args'] or item['identity'] != CHECKER_IDENTITY[task]
            or type(item['cases']) is not list or len(item['cases']) != CASE_COUNTS[task]):
        raise PilotError('case index task/identity/checker binding differs')
    names = {}
    for entry in item['cases']:
        if (type(entry) is not dict or set(entry) != {'name', 'input_sha256'}
                or type(entry['name']) is not str or not entry['name'] or entry['name'] in names
                or type(entry['input_sha256']) is not str or re.fullmatch(r'[a-f0-9]{64}', entry['input_sha256']) is None):
            raise PilotError('public case identity must be unique and hash-bound')
        names[entry['name']] = entry['input_sha256']
    return names


def validate_public_result(r, a, result, measured, stderr):
    task = a['task']; identities = CHECKER_IDENTITY[task]; cases = case_index(r, task)
    required = {'cases', 'passed', 'failed', 'observations_sha256', *identities}
    if (type(result) is not dict or set(result) != required
            or any(result[k] != v or type(result[k]) is not str for k, v in identities.items())
            or type(result.get('cases')) is not int or result['cases'] != len(cases)
            or type(result.get('passed')) is not int or not 0 <= result['passed'] <= result['cases']
            or type(result['failed']) is not list or len(result['failed']) != result['cases'] - result['passed']
            or type(result['observations_sha256']) is not str or re.fullmatch(r'[a-f0-9]{64}', result['observations_sha256']) is None
            or measured['exit_code'] != int(result['passed'] != result['cases']) or stderr != b''
            or measured['timed_out'] or measured['truncated_streams']):
        raise PilotError('public checker identity, counts or measured closure differs')
    seen = set()
    for failure in result['failed']:
        if type(failure) is not dict:
            raise PilotError('invalid failed-case record')
        normal = {'name', 'passed', 'exit_code', 'input_sha256', 'stdout_sha256', 'stderr_sha256'}
        exceptional = {'name', 'passed', 'error', 'input_sha256'}
        if (set(failure) not in (normal, exceptional) or type(failure.get('name')) is not str
                or failure['name'] not in cases or failure['name'] in seen or failure['passed'] is not False
                or failure['input_sha256'] != cases[failure['name']]):
            raise PilotError('failed-case schema, identity, uniqueness or input binding differs')
        if set(failure) == normal:
            if (type(failure['exit_code']) is not int or any(type(failure[k]) is not str
                    or re.fullmatch(r'[a-f0-9]{64}', failure[k]) is None for k in ('stdout_sha256', 'stderr_sha256'))):
                raise PilotError('invalid failed-case measured fields')
        elif task == 'rangeaudit' or failure['error'] not in ('TimeoutExpired', 'ValueError', 'JSONDecodeError', 'UnicodeError', 'UnicodeDecodeError', 'UnicodeEncodeError'):
            raise PilotError('invalid failed-case exception fields')
        seen.add(failure['name'])


def transport_policy(r):
    """Derive prospective schema6 without inspecting images before attempt clock."""
    from .attempt_deadline import DEADLINE_POLICY
    from .docker_roles import TERMINAL_CONTAINER_POLICY
    t = r['transport']; pins = r['source_sha256']
    native = {n: p for n, p in pins.items()
              if n == 'scripts/controller_native_role.py' or Path(n).parent == Path('src/specorganon')}
    return {'schema': 6, 'whole_attempt_budget':dict(DEADLINE_POLICY), 'terminal_container_policy': TERMINAL_CONTAINER_POLICY,
            'create_recovery': 'owned-never-started-after-create-deadline-v1',
            'images': {'native': t['native_image'], 'test': t['test_image']},
            'routes': {target: [t[role]['provider'], t[role]['model']]
                       for target, role in [('author', 'author'), ('review', 'reviewer')]},
            'test_timeout_seconds': t['test_timeout_seconds'], 'source_root': r['source_root'],
            'public_catalog_sha256': pins[r['public_catalog']], 'native_source_sha256': native,
            'registered_source_bindings_sha256': digest(canonical(pins)),
            'codex_original_volume': t['codex_volume'], 'gemini_original_profile': t['gemini_profile'],
            'gemini_executable_sha256': t['gemini_executable_sha256'],
            'codex_reasoning_effort': t['codex_reasoning_effort'], 'seccomp_sha256': pins[r['seccomp']]}


def transport(r, root, *, attempt_clock, attempt_initial_sha256):
    t = r['transport']; source = Path(r['source_root'])
    return DockerRoles(root, native_image=t['native_image'], test_image=t['test_image'],
        source_root=source, public_catalog=source / r['public_catalog'],
        author_provider=t['author']['provider'], author_model=t['author']['model'],
        reviewer_provider=t['reviewer']['provider'], reviewer_model=t['reviewer']['model'],
        codex_volume=t['codex_volume'], gemini_profile=t['gemini_profile'],
        gemini_executable=t['gemini_executable'], seccomp=source / r['seccomp'],
        test_timeout_seconds=t['test_timeout_seconds'], codex_reasoning_effort=t['codex_reasoning_effort'],
        source_bindings=r['source_sha256'],attempt_clock=attempt_clock,attempt_initial_sha256=attempt_initial_sha256)


def controller(r, a, folder):
    task = r['tasks'][a['task']]
    implementation = AutonomousNeutralController if a['method'] == 'N' else NeutralController
    contract = bound_source(r, task['contract']).decode()
    if a['method'] == 'N':
        # Keep all historical functional/document requirements byte-for-byte.
        # Explicit precedence applies to generation AND the auditor's contract.
        contract += ('\n\nN procedural override v2 — effective prospectively for N only. '
            'The functional requirements and required delivery documents remain unchanged. '
            'The neutral-autonomy-v2 protocol supersedes exclusively the legacy v1 staging rules above: '
            'code may precede notes; program and battery may be authored together. '
            'No mandatory pre-code notes or separate program-before-battery seal is imposed on N. '
            'All required notes, criteria, README, tests and real evidence must still exist before common completion. '
            'Criteria and battery are fixed before their first actual measurement; repairs retain them and the original budget. '
            'Both generation and common audit apply this explicit precedence. '
            'This override neither changes functional expectations nor applies to S or T.\n')
    return implementation(folder / 'controller', attempt_id=a['id'], method=a['method'],
        contract=contract, mandate=bound_source(r, r['mandate']).decode(),
        argv=['/opt/specorganon/venv/bin/python', '-I', '-B', '/input/delivery/' + task['test_file']],
        test_file=task['test_file'], transport_policy=transport_policy(r),
        transport_factory=lambda root,**budget: transport(r, root,**budget), fixture_mode=False)


def _public(r, a, folder, files, run):
    task = r['tasks'][a['task']]
    if not any(n.endswith('.py') for n in files):
        return {'status': 'unavailable', 'reason': 'No Python delivery to evaluate', 'score': None}
    if 'check_public.py' in files:
        return {'status': 'unavailable', 'reason': 'Delivery collides with independent checker path', 'score': None}
    evaluated = {**files, 'check_public.py': bound_source(r, task['checker']).decode()}
    argv = ['/opt/specorganon/venv/bin/python', '-I', '-S', '-B', '/input/delivery/check_public.py', *task['checker_args']]
    request = {'schema': 1, 'attempt': a, 'job_id': 'independent-public-check', 'argv': argv,
               'files_sha256': digest(canonical(evaluated)), 'delivery_sha256': digest(canonical(files)),
               'checker_sha256': r['source_sha256'][task['checker']], 'test_image': r['transport']['test_image']}
    intent = folder / 'public-check-intent.json'
    # This independently measured observation is outside the candidate's native
    # generation. It cannot renew that generation's original clock or readiness.
    # Keep its own original pre-factory timestamp for recovery; subject timeout
    # remains the same registered <=120s and driver total time includes this work.
    original_clock = _json(intent)['measurement_clock'] if intent.exists() else _clock()
    request.update(measurement_clock=original_clock,
                   clock_scope='independent-public-observation-not-a-generation')
    if run:
        immutable(intent, request)
    elif not intent.exists() or _json(intent) != request:
        raise PilotError('public checker intent binding differs')
    observed = folder / 'public-check-outcome.json'
    t = transport(r, folder / 'public-check',attempt_clock=original_clock,
                  attempt_initial_sha256=digest(_read(intent)))
    job = 'independent-public-check'
    measured = t.recover_test(job, argv, evaluated)
    if measured is None:
        if observed.exists():
            old = _json(observed)
            if old.get('intent_sha256') != digest(_read(intent)) or old.get('status') != 'failed' or old.get('score') is not None:
                raise PilotError('public failure binding differs')
            return old
        if not run:
            raise PilotError('public evaluation is not closed; report cannot dispatch or reconcile')
        try:
            measured = t.measure(job, argv, evaluated)
        except PendingCleanupError:
            raise
        except (ValueError, OSError) as exc:
            owned = (any((t.root / 'jobs' / job / n).exists() for n in ('launch.json', 'create-attempt.json'))
                     or (t.store.root / job / 'started.json').exists())
            if owned and t.reconcile_pending(job, 'test', {'argv': argv, 'files': evaluated}) is not True:
                raise PendingCleanupError('public-check cleanup remains uncertain') from exc
            value = {'status': 'failed', 'error_type': type(exc).__name__, 'score': None,
                     'reason': str(exc), 'intent_sha256': digest(_read(intent)),
                     'cleanup_confirmed': owned}
            immutable(observed, value)
            return value
    measured, streams = t.read_test({'argv': argv, 'test_job_ref': measured['test_job_ref']}, evaluated,
                                   require_passed=False, require_current=True)
    result = None; failure = None
    try:
        result = strict_json_loads(streams['stdout'].decode())
        validate_public_result(r, a, result, measured, streams['stderr'])
    except (ValueError, UnicodeError) as exc:
        failure = type(exc).__name__ + ': ' + str(exc)
    value = {'status': 'observed' if failure is None else 'failed',
            'score': result['passed'] / result['cases'] if failure is None else None,
            'result': result, 'measurement': measured, 'failure': failure,
            'scope': 'Public development functionality; not independent reserved F',
            'intent_sha256': digest(_read(intent))}
    immutable(observed, value)
    return value


def inventory(folder):
    values = {}; total = 0
    for path in sorted(folder.rglob('*')):
        if path.name in ('outcome.json', 'closure.json') and path.parent == folder:
            continue
        info = path.lstat()
        if stat.S_ISDIR(info.st_mode):
            continue
        raw = _read(path); total += len(raw)
        if len(values) >= 20000 or total > 268435456:
            raise PilotError('attempt evidence inventory exceeds bound')
        values[str(path.relative_to(folder))] = digest(raw)
    return values


def _closed(folder, expected, a):
    row = _json(folder / 'outcome.json'); seal = _json(folder / 'closure.json')
    if (row.get('plan_sha256') != expected or row.get('attempt') != a
            or row.get('evidence_sha256') != inventory(folder)
            or seal != {'schema': 1, 'outcome_sha256': digest(_read(folder / 'outcome.json')),
                        'evidence_sha256': inventory(folder)}):
        raise PilotError('closed attempt evidence changed')
    return row


def run_attempt(r, a, root, expected, verify_sources):
    folder = _private(root / a['id'], create=True)
    if (folder / 'closure.json').exists():
        return _closed(folder, expected, a)
    start = folder / 'started.json'
    if not start.exists():
        if any(folder.iterdir()):
            raise PilotError('attempt initialization uncertain; cannot reset')
        immutable(start, {'schema': 1, 'plan_sha256': expected, 'attempt': a, 'clock': _clock()})
    began = _json(start)
    if began.get('plan_sha256') != expected or began.get('attempt') != a:
        raise PilotError('attempt identity changed')
    c = controller(r, a, folder)
    for _ in range(81):
        verify_sources()
        if (folder / 'outcome.json').exists():
            state, _, _, pending = c._load()
            if state['status'] == 'running' or pending is not None:
                raise PilotError('outcome exists without an actual terminal controller')
            break
        report = c.step()
        if report['status'] != 'running':
            break
    else:
        raise PilotError('bounded pilot controller did not terminate')
    state, _, _, pending = c._load()
    if state['status'] == 'running' or pending is not None:
        raise PilotError('terminal controller with no pending reservation required')
    report = c._report(state)
    verify_sources()
    public = _public(r, a, folder, state['files'], run=not (folder / 'outcome.json').exists())
    verify_sources()
    # Terminal time is preserved across a crash before outcome/closure publication.
    end = folder / 'terminal-clock.json'
    immutable(end, _json(end) if end.exists() else {'schema': 1, 'clock': _clock()})
    elapsed = None; clock_error = None
    try:
        elapsed = _elapsed(began['clock'], _json(end)['clock'])
    except ValueError as exc:
        clock_error = str(exc)
    row = {'schema': 1, 'plan_sha256': expected, 'attempt': a, 'controller_report': report,
           'public_development_functionality': public, 'whole_attempt_seconds': elapsed,
           'clock_error': clock_error, 'shared_preparation_seconds': None, 'monetary_cost': None,
           'external_F': None, 'common_complete': None, 'competence_established': False,
           'goal_achieved': False, 'evidence_sha256': inventory(folder)}
    immutable(folder / 'outcome.json', row)
    immutable(folder / 'closure.json', {'schema': 1, 'outcome_sha256': digest(_read(folder / 'outcome.json')),
                                      'evidence_sha256': inventory(folder)})
    return _closed(folder, expected, a)


def execute(plan, expected, operation, *, installed_root):
    r = load_plan(plan, expected, installed_root=installed_root)
    root = _safe(r['run_root']); rows = []
    verify = lambda: load_plan(plan, expected, installed_root=installed_root)
    if operation not in ('run', 'report'):
        raise PilotError('unknown pilot operation')
    if operation == 'run':
        root = _private(root, create=True)
        with _lock(root):
            if not (root / 'plan.json').exists() and set(p.name for p in root.iterdir()) != {'.pilot.lock'}:
                raise PilotError('runtime initialization uncertain; cannot reset')
            immutable(root / 'plan.json', r)
            for a in r['attempts']:
                verify()
                rows.append(run_attempt(r, a, root, expected, verify))
    elif root.exists():
        _private(root)
        if _read(root / 'plan.json') != canonical(r):
            raise PilotError('runtime plan differs')
        # No directory creation, lock creation, controller construction, Docker
        # inspection, reconciliation or dispatch in this read-only operation.
        for a in r['attempts']:
            folder = root / a['id']
            if (folder / 'closure.json').exists():
                rows.append(_closed(folder, expected, a))
    closed = {row['attempt']['id']: row for row in rows}
    positions = []
    for a in r['attempts']:
        if a['id'] in closed:
            positions.append({'attempt': a, 'status': 'closed', 'outcome': closed[a['id']]})
        else:
            started = root / a['id'] / 'started.json'
            positions.append({'attempt': a, 'status': 'pending_or_unclosed' if started.exists() else 'not_started',
                              'outcome': None})
    return {'schema': 1, 'classification': CLASSIFICATION, 'status': 'closed' if len(rows) == 6 else 'incomplete',
            'plan_sha256': expected, 'planned_denominator': 6, 'closed_attempts': len(rows), 'rows': rows,
            'positions': positions,
            'external_F': None, 'common_complete': None, 'comparative_time_ratio': None,
            'competence_established': False, 'goal_achieved': False}
