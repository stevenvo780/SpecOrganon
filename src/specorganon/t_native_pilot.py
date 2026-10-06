"""Registered ten-position native T development; no reserved superiority claim.

Run requires installed byte-bound bootstrap. Report only verifies sealed evidence
and never reconstructs controllers or dispatches Docker. The trusted host owns
the evidence; inventory hashes do not authenticate that host or semantic truth.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import sys

from . import __version__
from .common_review import checklist
from .neutral_controller import LIMITS, _clock, _elapsed
from .neutral_pilot import (PilotError, TASKS, TEST_FILES, CASE_COUNTS, CONTRACT_STEMS,
    CASE_INDEX, DEVELOPMENT, _private, _lock, _relative, immutable, bound_source,
    case_index, transport_policy, transport, _public, inventory)
from .role_jobs import _safe, _read, _json, canonical, digest
from .t_common_controller import TCommonController


CLASSIFICATION = 'prospective public T native development'
PROTOCOL = 'T-native-development-v1'
PROTOCOL_FILE = DEVELOPMENT + 't-native-v1/PROTOCOL.md'
MANDATE = DEVELOPMENT + 't-native-v1/mandate.md'
AUTHOR_FORMAT = 'items-v1'
ATTEMPTS = [{'id': f'T-attempt-{n:02d}', 'task': task, 'method': 'T'}
            for n, task in enumerate((*TASKS, *TASKS, *TASKS, TASKS[0]), 1)]
SCOPE = {'reserved': False, 'superiority_evaluated': False, 'external_F': None,
         'common_complete': None, 'goal_achieved': False}


def task_policy():
    return {name: {'contract': DEVELOPMENT + 'neutral-public-v1/' + CONTRACT_STEMS[name] + '-contract.md',
        'test_file': TEST_FILES[name], 'public_cases': CASE_COUNTS[name], 'case_index': CASE_INDEX,
        'checker': DEVELOPMENT + ('check_rangeaudit_public.py' if name == 'rangeaudit' else 'check_cohort_public.py'),
        'checker_args': [] if name == 'rangeaudit' else [name]} for name in TASKS}


def required_sources(source):
    names = {'pyproject.toml', 'uv.lock', 'GOAL.md', 'goals/method-superiority-v1/GOAL.md',
        'scripts/controller_native_role.py', 'scripts/register_t_native_pilot.py',
        'scripts/index_neutral_public_cases.py', 'experiments/software_comparison_v3/public-models.json',
        'docker/codex/seccomp-codex.json', PROTOCOL_FILE, MANDATE}
    names.update(str(p.relative_to(source)) for p in (source / 'src/specorganon').glob('*.py'))
    for task in task_policy().values(): names.update([task['contract'], task['checker'], task['case_index']])
    return names


def validate_registration(r):
    fields = {'schema', 'protocol', 'classification', 'id', 'registered_at', 'candidate_version',
        'source_root', 'source_commit', 'source_sha256', 'run_root', 'fixture_mode', 'automatic_replacement',
        'controller_limits', 'author_format', 'transport', 'public_catalog', 'seccomp', 'mandate',
        'protocol_file', 'tasks', 'attempts', 'scope', 'H_checklist', 'capacity_evidence'}
    if (type(r) is not dict or set(r) != fields or type(r['schema']) is not int or r['schema'] != 1
            or r['protocol'] != PROTOCOL or r['classification'] != CLASSIFICATION
            or r['candidate_version'] != __version__ or r['fixture_mode'] is not False
            or r['automatic_replacement'] is not False or r['author_format'] != AUTHOR_FORMAT
            or canonical(r['controller_limits']) != canonical(LIMITS)
            or canonical(r['attempts']) != canonical(ATTEMPTS) or canonical(r['scope']) != canonical(SCOPE)
            or canonical(r['tasks']) != canonical(task_policy())
            or r['protocol_file'] != PROTOCOL_FILE or r['mandate'] != MANDATE
            or r['public_catalog'] != 'experiments/software_comparison_v3/public-models.json'
            or r['seccomp'] != 'docker/codex/seccomp-codex.json'
            or r['H_checklist'] != checklist('T')['H']
            or type(r['id']) is not str or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', r['id']) is None
            or type(r['registered_at']) is not str or not r['registered_at']
            or type(r['source_commit']) is not str or re.fullmatch(r'[a-f0-9]{40}', r['source_commit']) is None):
        raise PilotError('exact ten-position prospective native T policy required')
    source = _safe(r['source_root']); runtime = _safe(r['run_root'])
    if (r['source_root'] != str(source) or r['run_root'] != str(runtime)
            or '..' in source.parts or '..' in runtime.parts or source == runtime
            or source.is_relative_to(runtime) or runtime.is_relative_to(source)):
        raise PilotError('disjoint source and private runtime required')
    pins = r['source_sha256']
    if type(pins) is not dict or set(pins) != required_sources(source):
        raise PilotError('exact complete T source inventory required')
    for name, pin in pins.items():
        if type(pin) is not str or re.fullmatch(r'[a-f0-9]{64}', pin) is None:
            raise PilotError('exact source digests required')
        bound_source(r, name)
    t = r['transport']
    fields = {'native_image', 'test_image', 'author', 'reviewer', 'codex_volume', 'gemini_profile',
        'gemini_executable', 'gemini_executable_sha256', 'codex_reasoning_effort', 'test_timeout_seconds'}
    if type(t) is not dict or set(t) != fields:
        raise PilotError('exact explicit native transport required')
    for role, provider in [('author', 'codex'), ('reviewer', 'gemini')]:
        route = t[role]
        if (type(route) is not dict or set(route) != {'provider', 'model', 'machine', 'account_attribution'}
                or route['provider'] != provider or route['machine'] != 'Kratos'
                or any(type(v) is not str or not v.strip() for v in route.values())):
            raise PilotError('explicit independent author/reviewer attribution required')
    for name in ('native_image', 'test_image'):
        if type(t[name]) is not str or re.fullmatch(r'sha256:[a-f0-9]{64}', t[name]) is None:
            raise PilotError('immutable native/test images required')
    if (type(t['test_timeout_seconds']) is not int or not 1 <= t['test_timeout_seconds'] <= 120
            or t['codex_reasoning_effort'] not in ('low', 'medium', 'high', 'xhigh')
            or type(t['codex_volume']) is not str or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', t['codex_volume']) is None):
        raise PilotError('invalid registered timeout/effort/volume')
    profile = _safe(t['gemini_profile']); executable = _safe(t['gemini_executable'])
    if any(p == runtime or p.is_relative_to(runtime) or runtime.is_relative_to(p) for p in (profile, executable.parent)):
        raise PilotError('runtime cannot overlap original provider profiles/executable')
    if digest(_read(executable, 536870912)) != t['gemini_executable_sha256']:
        raise PilotError('registered provider executable changed')
    capacity = r['capacity_evidence']
    if (type(capacity) is not dict or set(capacity) != {'observed_at', 'catalog', 'quota', 'scope'}
            or capacity['scope'] != 'Observation only; no availability or admission inferred'
            or type(capacity['observed_at']) is not str or not capacity['observed_at']):
        raise PilotError('dated explicit capacity observation required')
    for name in ('catalog', 'quota'):
        v = capacity[name]
        if (type(v) is not dict or set(v) != {'status', 'source', 'sha256'}
                or v['status'] not in ('known', 'unknown') or type(v['source']) is not str or not v['source']
                or (v['sha256'] is not None and (type(v['sha256']) is not str or re.fullmatch(r'[a-f0-9]{64}', v['sha256']) is None))
                or v['status'] == 'known' and v['sha256'] is None):
            raise PilotError('capacity unknown must remain explicit')
    for name in TASKS: case_index(r, name)
    return r


def load_plan(path, expected, *, installed_root):
    from .ledger import strict_json_loads
    raw = _read(path)
    if digest(raw) != expected: raise PilotError('registered T plan digest changed')
    r = validate_registration(strict_json_loads(raw.decode()))
    package = _safe(installed_root); source = _safe(r['source_root'])
    if package == source / 'src/specorganon' or package.is_relative_to(source):
        raise PilotError('installed wheel required; source/editable execution forbidden')
    modules = {n for n in r['source_sha256'] if Path(n).parent == Path('src/specorganon')}
    if modules != {'src/specorganon/' + p.name for p in package.glob('*.py')}:
        raise PilotError('installed module inventory differs')
    for name in modules:
        if digest(_read(package / Path(name).name)) != r['source_sha256'][name]:
            raise PilotError('installed module differs from registered source')
    for name, module in tuple(sys.modules.items()):
        if name == 'specorganon' or name.startswith('specorganon.') and name != 'specorganon.t_native_entry':
            filename = '__init__.py' if name == 'specorganon' else name.split('.')[1] + '.py'
            if (getattr(module, '__registered_source_sha256__', None) != r['source_sha256'].get('src/specorganon/' + filename)
                    or Path(module.__file__).absolute() != package / filename):
                raise PilotError('fresh registered installed T bootstrap required')
    return r


def controller(r, a, folder):
    return TCommonController(folder / 'controller', attempt_id=a['id'],
        title='Native T development: ' + a['task'], contract=bound_source(r, r['tasks'][a['task']]['contract']).decode(),
        mandate=bound_source(r, r['mandate']).decode(), author_format=r['author_format'],
        fixture_mode=False, transport_policy=transport_policy(r),
        transport_factory=lambda root, **budget: transport(r, root, **budget))


def read_closed(folder, expected, a):
    row = _json(folder / 'outcome.json'); seal = _json(folder / 'closure.json')
    began = _json(folder / 'started.json')
    end = _json(folder / 'terminal-clock.json')
    fields = {'schema', 'plan_sha256', 'attempt', 'controller_report', 'public_development_functionality',
        'whole_driver_seconds', 'clock_error', 'shared_preparation_seconds', 'monetary_cost',
        'external_F', 'common_complete', 'goal_achieved', 'evidence_sha256'}
    if (type(row) is not dict or set(row) != fields or type(row['schema']) is not int or row['schema'] != 1
            or type(began.get('schema')) is not int or type(end.get('schema')) is not int
            or began != {'schema': 1, 'plan_sha256': expected, 'attempt': a, 'clock': began.get('clock')}
            or row.get('plan_sha256') != expected or row.get('attempt') != a
            or row.get('evidence_sha256') != inventory(folder)
            or seal != {'schema': 1, 'outcome_sha256': digest(_read(folder / 'outcome.json')),
                        'evidence_sha256': inventory(folder)}
            or end != {'schema': 1, 'clock': end.get('clock')}
            or row.get('external_F') is not None or row.get('common_complete') is not None
            or row.get('goal_achieved') is not False):
        raise PilotError('original sealed T outcome/clock/evidence changed')
    try:
        elapsed = _elapsed(began['clock'], end['clock']); error = None
    except ValueError as exc:
        elapsed = None; error = str(exc)
    if row.get('whole_driver_seconds') != elapsed or row.get('clock_error') != error:
        raise PilotError('original T driver clock outcome changed')
    terminal = _json(folder / 'controller/terminal.json')
    if (type(terminal.get('schema')) is not int or terminal['schema'] != 1
            or terminal != row.get('controller_report') or terminal != _json(folder / 'controller/terminal-intent.json')
            or terminal.get('fixture_mode') is not False or terminal.get('attempt_id') != a['id']
            or terminal.get('method') != 'T'):
        raise PilotError('original native T terminal differs from sealed report')
    # This is sealed evidence checking, not renewed semantic/native adjudication.
    return row


def run_attempt(r, a, root, expected, verify):
    folder = _private(root / a['id'], create=True)
    if (folder / 'closure.json').exists(): return read_closed(folder, expected, a)
    start = folder / 'started.json'
    if not start.exists():
        if any(folder.iterdir()): raise PilotError('T initialization uncertain; never reset')
        immutable(start, {'schema': 1, 'plan_sha256': expected, 'attempt': a, 'clock': _clock()})
    began = _json(start)
    if began.get('plan_sha256') != expected or began.get('attempt') != a:
        raise PilotError('original T position changed')
    c = controller(r, a, folder)
    if (folder / 'outcome.json').exists():
        # Verify original terminal and physical custody, never step a new role.
        report = c._read_terminal()
    else:
        for _ in range(81):
            verify(); report = c.step()
            if report['status'] != 'running': break
        else: raise PilotError('bounded T controller did not terminate')
    verify()
    if report['status'] == 'running' or report['fixture_mode'] is not False:
        raise PilotError('original terminal native T required')
    # A separate public checker cannot improve readiness or renew original clock.
    public = _public(r, a, folder, c.controller._files(), run=not (folder / 'outcome.json').exists())
    verify(); end = folder / 'terminal-clock.json'
    immutable(end, _json(end) if end.exists() else {'schema': 1, 'clock': _clock()})
    try:
        elapsed = _elapsed(began['clock'], _json(end)['clock']); error = None
    except ValueError as exc:
        elapsed = None; error = str(exc)
    row = {'schema': 1, 'plan_sha256': expected, 'attempt': a, 'controller_report': report,
        'public_development_functionality': public, 'whole_driver_seconds': elapsed, 'clock_error': error,
        'shared_preparation_seconds': None, 'monetary_cost': None, 'external_F': None,
        'common_complete': None, 'goal_achieved': False, 'evidence_sha256': inventory(folder)}
    immutable(folder / 'outcome.json', row)
    immutable(folder / 'closure.json', {'schema': 1, 'outcome_sha256': digest(_read(folder / 'outcome.json')),
                                      'evidence_sha256': inventory(folder)})
    return read_closed(folder, expected, a)


def execute(plan, expected, operation, *, installed_root):
    r = load_plan(plan, expected, installed_root=installed_root)
    root = _safe(r['run_root']); rows = []
    verify = lambda: load_plan(plan, expected, installed_root=installed_root)
    if operation == 'run':
        root = _private(root, create=True)
        with _lock(root):
            if not (root / 'plan.json').exists() and set(p.name for p in root.iterdir()) != {'.pilot.lock'}:
                raise PilotError('T runtime initialization uncertain; never reset')
            immutable(root / 'plan.json', r)
            for a in r['attempts']:
                verify(); rows.append(run_attempt(r, a, root, expected, verify))
    elif operation == 'report':
        if root.exists():
            _private(root)
            if _read(root / 'plan.json') != canonical(r): raise PilotError('original T runtime plan changed')
            for a in r['attempts']:
                folder = root / a['id']
                if (folder / 'closure.json').exists(): rows.append(read_closed(folder, expected, a))
    else: raise PilotError('unknown native T pilot operation')
    closed = {row['attempt']['id']: row for row in rows}
    positions = [{'attempt': a, 'status': 'closed' if a['id'] in closed else
                  'pending_or_unclosed' if (root / a['id'] / 'started.json').exists() else 'not_started',
                  'outcome': closed.get(a['id'])} for a in r['attempts']]
    ready = [row for row in rows if row['controller_report']['native_ready'] is True]
    types = sorted({row['attempt']['task'] for row in ready})
    return {'schema': 1, 'classification': CLASSIFICATION, 'status': 'closed' if len(rows) == 10 else 'incomplete',
        'plan_sha256': expected, 'planned_denominator': 10, 'closed_attempts': len(rows), 'positions': positions,
        'original_native_ready_count': len(ready), 'original_native_ready_types': types,
        'readiness_scope': 'original controller judgments; report verifies sealed evidence only',
        'development_reliability_threshold_observed': len(rows) == 10 and len(ready) >= 9 and len(types) >= 2,
        'development_qualification': False, 'reserved': False, 'external_F': None, 'common_complete': None,
        'comparative_time_ratio': None, 'monetary_cost': None, 'goal_achieved': False}
