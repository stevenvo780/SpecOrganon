"""Trusted T driver with durable transition custody and a separate common audit.

The engine owns the nine phases. This host wrapper owns the whole-attempt clock,
original dispatch reservations and their physical captures. A crash after an
engine transition seals that same transition, rather than starting the next role.
Fixture mode exercises guards only and never establishes native readiness or F.
Private journals must stay outside every role/container mount. Hashes do not
authenticate a host able to rewrite the entire journal coherently.
"""
from __future__ import annotations

from contextlib import contextmanager
import copy
import fcntl
import os
from pathlib import Path
import re
import stat
import tempfile
import shlex

from . import engine
from .common_evidence import read_snapshot, validate_bound_audit
from .common_review import checklist, declaration
from .docker_roles import DockerRoles, ClosedResponseContractError, PendingCleanupError
from .ledger import strict_json_loads
from .native_response_contract import render_prompt, native_stdin_payload
from .neutral_controller import LIMITS, _clock, _elapsed, _context_document, CONTEXT_FORMAT, AUDIT_CONTEXT_FORMAT
from .role_jobs import _safe, _read, _json, canonical, digest
from .runner import describe_task, run_manifest
from .software_controller import Controller, fingerprint, encoded_contribution
from .t_measurement_custody import _put, _load as criteria_seal


class TCommonError(ValueError):
    pass


def _plain(value):
    return strict_json_loads(canonical(value).decode())


class TCommonController:
    def __init__(self, root, *, attempt_id, contract, mandate, transport_policy,
                 transport_factory, title, domain='development', author_format='items-v1',
                 fixture_mode=False):
        start = _clock()
        if (type(attempt_id) is not str or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', attempt_id) is None
                or any(type(x) is not str or not x.strip() for x in (contract, mandate, title, domain))
                or type(fixture_mode) is not bool or type(transport_policy) is not dict
                or not callable(transport_factory) or author_format not in ('manifest-v1', 'items-v1')):
            raise TCommonError('explicit versioned T attempt policy required')
        if not fixture_mode and (transport_policy.get('schema') != 5
                or not transport_policy.get('registered_source_bindings_sha256')):
            raise TCommonError('native T requires a registered source-bound transport')
        self.root = _safe(root); self.factory = transport_factory
        self.fixture_mode = fixture_mode; self.transport = None; self.controller = None
        self.current = None
        self.policy = _plain({'schema': 1, 'protocol': 'T-common-development-v1', 'method': 'T',
            'attempt_id': attempt_id, 'contract': contract, 'mandate': mandate, 'title': title,
            'domain': domain, 'author_format': author_format, 'fixture_mode': fixture_mode,
            'limits': LIMITS, 'max_commands': 80, 'common_audits': 2,
            'transport_policy': transport_policy,
            'controller_source_sha256': digest(_read(Path(__file__), 128000)),
            'software_controller_source_sha256': digest(_read(Path(__file__).with_name('software_controller.py'), 128000)),
            'snapshot_source_sha256': digest(_read(Path(__file__).with_name('t_common_snapshot.py'), 128000)),
            'request_tree_source_sha256': digest(_read(Path(__file__).with_name('request_tree.py'), 128000)),
            'shared_context_source_sha256': digest(_read(Path(__file__).with_name('neutral_controller.py'), 128000)),
            'measurement_custody_source_sha256': digest(_read(Path(__file__).with_name('t_measurement_custody.py'), 128000))})
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        info = self.root.stat()
        if info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise TCommonError('owned private mode0700 T root required')
        with self._lock():
            path = self.root / 'initial.json'
            if path.exists():
                self.initial = _json(path)
                if set(self.initial) != {'schema', 'policy', 'clock'} or self.initial['schema'] != 1:
                    raise TCommonError('invalid original T attempt')
                if canonical(self.initial['policy']) != canonical(self.policy):
                    raise TCommonError('T policy/source changed; no silent replacement')
            else:
                if {p.name for p in self.root.iterdir()} != {'.t-common.lock'}:
                    raise TCommonError('uncertain T initialization cannot reset an existing attempt')
                self.initial = {'schema': 1, 'policy': self.policy, 'clock': start}
                _put(path, canonical(self.initial))
            for name in ('commands', 'audit', 'snapshots'):
                (self.root / name).mkdir(exist_ok=True, mode=0o700)

    @contextmanager
    def _lock(self):
        path = self.root / '.t-common.lock'
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(fd); named = path.lstat()
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or (info.st_dev, info.st_ino) != (named.st_dev, named.st_ino)):
                raise TCommonError('invalid T custody lock')
            fcntl.flock(fd, fcntl.LOCK_EX)
            named = path.lstat()
            if (info.st_dev, info.st_ino) != (named.st_dev, named.st_ino):
                raise TCommonError("T custody lock changed during acquisition")
            yield
        finally:
            os.close(fd)

    def _time_admission(self):
        if _elapsed(self.initial['clock'], _clock()) >= LIMITS['elapsed_admission_seconds']:
            raise TCommonError('whole T attempt elapsed admission exhausted')

    def _get_controller(self):
        if self.controller is not None:
            return self.controller
        # initial.json is durable before case creation and factory/image probes.
        if not (self.root / 'transport').exists():
            self._time_admission()
        case = self.root / 'case'; intent = self.root / 'case-intent.json'
        if not intent.exists() and case.exists():
            raise TCommonError('preexisting case is not a fresh registered T generation')
        _put(intent, canonical({'schema': 1, 'initial_sha256': digest(_read(self.root / 'initial.json'))}))
        if not case.exists():
            engine.create_case(case, self.policy['title'], self.policy['domain'],
                               'human:owner', approval_policy='local')
        baseline = self.root / 'case-initial-ledger.json'
        if not baseline.exists():
            state = engine.get_state(case)
            if state['revision'] != 0 or state['items'] or state['project']['approval_policy'] != 'local':
                raise TCommonError('uncaptured initial case cannot inherit authored state')
            _put(baseline, _read(case / 'organon.json', 64 * 1024 * 1024))
        original = strict_json_loads(_read(baseline, 64 * 1024 * 1024).decode())
        current = strict_json_loads(_read(case / 'organon.json', 64 * 1024 * 1024).decode())
        if (current['project'] != original['project'] or current['schema'] != original['schema']
                or current['events'][:len(original['events'])] != original['events']):
            raise TCommonError('case no longer extends its original initial ledger')
        t = self.factory(self.root / 'transport')
        if _safe(t.root) != self.root / 'transport':
            raise TCommonError('T transport must belong to this original attempt')
        if not self.fixture_mode and type(t) is not DockerRoles:
            raise TCommonError('native T requires the guarded Docker transport')
        if canonical(_json(t.root / 'transport-policy.json')) != canonical(self.policy['transport_policy']):
            raise TCommonError('actual T transport policy differs from registration')
        self.transport = t
        self.controller = Controller(case, self.root / 'software', t,
            contract=self.policy['contract'], mandate=self.policy['mandate'], executor=t,
            fixture_mode=self.fixture_mode, author_format=self.policy['author_format'],
            admission_repair=True, dispatch_guard=self._before_dispatch, completion_guard=self._before_close)
        return self.controller

    def _capture(self, folder, label):
        c = self._get_controller()
        state = _plain(engine.get_state(c.case)); files = c._files()
        ledger = _read(c.case / 'organon.json', 64 * 1024 * 1024)
        progress = _json(c.root / 'progress.json')
        value = {'state': state, 'files': files, 'progress': progress,
                 'ledger_sha256': digest(ledger),
                 'build_seals': {stage: c._checkpoint(stage) for stage in ('program', 'tests')},
                 'criteria_seal': criteria_seal(c)}
        if (fingerprint(engine.get_state(c.case)) != fingerprint(state) or c._files() != files
                or _read(c.case / 'organon.json', 64 * 1024 * 1024) != ledger):
            raise TCommonError('case/delivery changed while capturing T transition')
        if folder is not None:
            _put(folder / (label + '-ledger.json'), ledger)
        return value

    def _capture_read(self, folder, label, capture):
        raw = _read(folder / (label + '-ledger.json'), 64 * 1024 * 1024)
        if digest(raw) != capture['ledger_sha256']:
            raise TCommonError('immutable transition ledger changed')
        if not isinstance(capture['state'], dict) or type(capture['files']) is not dict:
            raise TCommonError('invalid complete transition capture')

    def _commands(self):
        if canonical(_json(self.root / 'initial.json')) != canonical(self.initial):
            raise TCommonError('original attempt changed')
        folders = sorted((self.root / 'commands').iterdir())
        if len(folders) > 80 or [p.name for p in folders] != [f'{i:04d}' for i in range(1, len(folders) + 1)]:
            raise TCommonError('T command sequence gap or budget exceeded')
        previous = digest(_read(self.root / 'initial.json')); closed = []; pending = None
        for i, folder in enumerate(folders, 1):
            _safe(folder)
            if not (folder / 'before.json').exists():
                if i != len(folders):
                    raise TCommonError('uncertain capture precedes another transition')
                pending = (folder, None); break
            before = _json(folder / 'before.json')
            if (set(before) != {'schema', 'sequence', 'previous_sha256', 'capture', 'expected_task'}
                    or before['schema'] != 1 or before['sequence'] != i
                    or before['previous_sha256'] != previous):
                raise TCommonError('T before-transition chain diverged')
            self._capture_read(folder, 'before', before['capture'])
            if closed and canonical(before['capture']) != canonical(closed[-1][2]['capture']):
                raise TCommonError('unregistered mutation between T transitions')
            after_path = folder / 'after.json'
            if not after_path.exists():
                if i != len(folders):
                    raise TCommonError('open T transition precedes another command')
                pending = (folder, before); break
            after = _json(after_path)
            if (set(after) != {'schema', 'before_sha256', 'dispatch_sha256', 'capture', 'result', 'closed_result'}
                    or after['schema'] != 1 or after['before_sha256'] != digest(_read(folder / 'before.json'))):
                raise TCommonError('T after-transition binding diverged')
            dispatch = folder / 'dispatch.json'
            actual_dispatch = digest(_read(dispatch)) if dispatch.exists() else None
            if after['dispatch_sha256'] != actual_dispatch:
                raise TCommonError('original dispatch reservation changed after transition closure')
            self._capture_read(folder, 'after', after['capture'])
            closed.append((folder, before, after)); previous = digest(_read(after_path))
        return closed, pending, previous

    def _dispatches(self):
        records = []
        for folder in sorted((self.root / 'commands').iterdir()):
            path = folder / 'dispatch.json'
            if path.exists():
                records.append((folder, _json(path)))
        return records

    def _counts(self):
        jobs = self._dispatches()
        audits = sorted((self.root / 'audit').glob('[0-9][0-9][0-9][0-9].json'))
        return {'roles': sum(d['pending']['action'] != 'test' for _, d in jobs) + len(audits),
                'test_runs': sum(d['pending']['action'] == 'test' for _, d in jobs),
                'common_audits': len(audits), 'commands': len(list((self.root / 'commands').iterdir()))}

    def _before_dispatch(self, pending):
        if self.current is None:
            raise TCommonError('T dispatch has no original wrapper reservation')
        folder, before = self.current
        source = before['capture']
        if (fingerprint(pending['source_state']) != fingerprint(source['state'])
                or pending['source_files'] != source['files']):
            raise TCommonError('dispatch source differs from original complete transition capture')
        path = folder / 'dispatch.json'
        if path.exists():
            d = _json(path)
            if canonical(d['pending']) != canonical(pending) or d['before_sha256'] != digest(_read(folder / 'before.json')):
                raise TCommonError('recovered dispatch differs from original reservation')
            if self._recover_closed(folder) is None:
                self._time_admission()  # A reserved but unstarted job is not a free late execution.
            return  # Same charged operation/clock, never charge or replace it.
        self._time_admission()
        counts = self._counts(); field = 'test_runs' if pending['action'] == 'test' else 'roles'
        if counts[field] >= LIMITS[field]:
            raise TCommonError('shared T role/test budget exhausted before dispatch')
        _put(path, canonical({'schema': 1, 'before_sha256': digest(_read(folder / 'before.json')),
                              'pending': pending, 'clock': _clock()}))

    def _recover_closed(self, folder):
        path = folder / 'dispatch.json'
        if not path.exists():
            return None
        d = _json(path); p = d['pending']; t = self.transport
        if p['action'] == 'test':
            value = t.recover_test(p['job_id'], p['source_state']['items'][p['test_id']]['data']['argv'], p['source_files'])
            kind = 'test'
        else:
            try:
                value = t.recover_role(p['job_id'], p['request']['role'], p['request']); kind = 'role'
            except ClosedResponseContractError as exc:
                value = exc.proof; kind = 'response_error'
        return None if value is None else {'kind': kind, 'value': value}

    def _verify_closed(self, folder, captured):
        original = self._recover_closed(folder)
        if captured is None or original is None or canonical(original) != canonical(captured):
            raise TCommonError('closed T result differs from original transport journal')
        p = _json(folder / 'dispatch.json')['pending']; t = self.transport
        if captured['kind'] == 'test':
            data = {'argv': p['source_state']['items'][p['test_id']]['data']['argv'],
                    'test_job_ref': captured['value']['test_job_ref'],
                    'delivery_tree_sha256': digest(canonical(p['source_files']))}
            verified = t.verify_test(data, p['source_files'], require_passed=False, require_current=True)
        elif captured['kind'] == 'response_error':
            verified = t.verify_response_failure(captured['value'], p['job_id'], p['request']['role'], p['request'])
        else:
            verified = t.verify_role(captured['value'], p['job_id'], p['request']['role'], p['request'])
        if verified is not True:
            raise TCommonError('actual complete T receipt verification required')
        return True

    def _finish_command(self, folder, before, result, *, allow_unclosed=False):
        capture = self._capture(folder, 'after')
        closed = self._recover_closed(folder)
        if (folder / 'dispatch.json').exists() and closed is None and not allow_unclosed:
            raise TCommonError('T dispatch has no closed original result; cannot promote transition')
        if closed is not None:
            self._verify_closed(folder, closed)
        dispatch = folder / 'dispatch.json'
        record = {'schema': 1, 'before_sha256': digest(_read(folder / 'before.json')),
                  'dispatch_sha256': digest(_read(dispatch)) if dispatch.exists() else None,
                  'capture': capture, 'result': result, 'closed_result': closed}
        _put(folder / 'after.json', canonical(record))
        return record

    def _before_close(self, progress, pending):
        if self.current is None:
            raise TCommonError('inner closure has no original T reservation')
        folder, before = self.current
        captured = self._capture(folder, 'inner-close')
        captured['progress'] = _plain(progress)
        original = strict_json_loads(_read(folder / 'before-ledger.json', 64 * 1024 * 1024).decode())
        actual = strict_json_loads(_read(folder / 'inner-close-ledger.json', 64 * 1024 * 1024).decode())
        if actual['events'][:len(original['events'])] != original['events']:
            raise TCommonError('inner closure does not extend original reserved ledger')
        # Replay only the measured packet on the original private ledger. This
        # is deterministic bookkeeping, never a model call or a software test.
        with tempfile.TemporaryDirectory(prefix='.closure-replay-', dir=self.root) as temporary:
            case = Path(temporary)
            _put(case / 'organon.json', canonical(original))
            action = pending['action']; packet = pending['packet']
            files = pending['source_files']
            if action == 'author':
                response = packet['result']
                if progress['history'][-1].get('admitted') is not False:
                    manifest = self.controller._author_manifest(pending, response)
                    run_manifest(case, manifest, actor=packet['actor'])
                    files = {**files, **response['files']}
            elif action == 'review':
                response = packet['result']
                engine.review_phase(case, pending['phase'], response['verdict'],
                    response['reason'] + ' [role receipt: ' + packet['receipt_ref'] + ']', packet['actor'])
                if response['verdict'] == 'accept':
                    engine.advance(case, pending['phase'], 'agent:software-controller')
            elif action == 'approval':
                response = packet['result']
                for item in describe_task(pending['source_state'])['approval_targets']:
                    engine.approve(case, item['id'],
                        'Existing local owner mandate; technical conformity judged separately by '
                        + packet['actor'] + ' (' + packet['receipt_ref'] + '): ' + response['reason'],
                        pending['source_state']['project']['created_by'])
            elif action == 'test':
                item = pending['source_state']['items'][pending['test_id']]
                data = {**item['data'], 'passed': progress['history'][-1]['passed'],
                    'command': shlex.join(item['data']['argv']), 'test_job_ref': packet['test_job_ref'],
                    'delivery_tree_sha256': packet['delivery_tree_sha256'],
                    'receipt': {'argv': item['data']['argv'], **{key: packet[key] for key in
                        ('exit_code', 'timed_out', 'stdout_sha256', 'stderr_sha256')}}}
                data['receipt']['result_sha256'] = engine.local_test_result_sha256(data)
                manifest = {'schema': 1, 'steps': [{'op': 'put', 'id': item['id'], 'kind': 'test',
                    'text': item['text'], 'refs': list(item['deps']), 'data': data,
                    'expected_version': item['version'], 'expected_deps': item['deps']}]}
                run_manifest(case, manifest, actor='executor:isolated-software-controller')
            else:
                raise TCommonError('unknown original inner closure action')
            expected = strict_json_loads(_read(case / 'organon.json', 64 * 1024 * 1024).decode())
        def semantic(events):
            return [{key: event[key] for key in ('seq', 'kind', 'actor', 'payload')} for event in events]
        offset = len(original['events'])
        if (semantic(actual['events'][offset:]) != semantic(expected['events'][offset:])
                or captured['files'] != files):
            raise TCommonError('inner closure includes mutation outside original measured operation')
        _put(folder / 'inner-close.json', canonical({'schema': 1,
            'dispatch_sha256': digest(_read(folder / 'dispatch.json')), 'capture': captured}))

    def _completed_inner(self, folder, before):
        c = self.controller; progress = _json(c.root / 'progress.json')
        prior = before['capture']['progress']; old = prior['history']; new = progress['history']
        if new[:len(old)] != old or len(new) > len(old) + 1:
            raise TCommonError('inner T history diverged during recovery')
        if len(new) == len(old) + 1:
            dispatch = _json(folder / 'dispatch.json')['pending']
            if progress['pending'] is not None or new[-1]['job_id'] != dispatch['job_id']:
                raise TCommonError('closed inner transition differs from reserved T job')
            closure_path = folder / 'inner-close.json'
            if not closure_path.exists():
                raise TCommonError('closed inner history lacks original post-operation custody')
            closure = _json(closure_path)
            if closure['dispatch_sha256'] != digest(_read(folder / 'dispatch.json')):
                raise TCommonError('inner post-operation custody dispatch changed')
            self._capture_read(folder, 'inner-close', closure['capture'])
            if canonical(self._capture(None, None)) != canonical(closure['capture']):
                raise TCommonError('closed inner operation differs from original post-operation custody')
            return new[-1]
        if progress['pending'] is not None:
            return None  # Existing prepared/closed/applying packet; inner resumes it.
        current = _plain(engine.get_state(c.case))
        if current != before['capture']['state']:
            ledger = strict_json_loads(_read(c.case / 'organon.json', 64 * 1024 * 1024).decode())
            original = strict_json_loads(_read(folder / 'before-ledger.json', 64 * 1024 * 1024).decode())
            delta = ledger['events'][len(original['events']):]
            if (before['expected_task']['action'] != 'advance_phase' or len(delta) != 1
                    or ledger['events'][:len(original['events'])] != original['events']):
                raise TCommonError('unregistered state mutation without a completed T role')
            # A valid unrelated ledger event is not the reserved phase advance.
            expected = before['expected_task']['phase']
            event = delta[0]
            if (event['kind'] != 'phase_advance' or event['actor'] != 'agent:software-controller'
                    or event['payload']['phase'] != expected
                    or event['payload']['snapshot'] != before['capture']['state']['phases'][expected]['snapshot']
                    or c._files() != before['capture']['files']
                    or canonical(progress) != canonical(prior)):
                raise TCommonError('recovered event is not the exact reserved phase advance')
            if not current['phases'][expected]['accepted']:
                raise TCommonError('recovered advance has no accepted original phase')
            return {'action': 'advance', 'phase': expected}
        if c._files() != before['capture']['files']:
            raise TCommonError('delivery changed outside an existing T operation')
        return None

    def _seal_failure(self, folder, before, exc):
        # A live/uncertain original owned container is reconciled, never replaced.
        if (folder / 'dispatch.json').exists() and self._recover_closed(folder) is None:
            p = _json(folder / 'dispatch.json')['pending']
            req = ({'argv': p['source_state']['items'][p['test_id']]['data']['argv'], 'files': p['source_files']}
                   if p['action'] == 'test' else p['request'])
            confirmed = self.transport.reconcile_pending(p['job_id'], 'test' if p['action'] == 'test' else req['role'], req)
            launch = self.root / 'transport/jobs' / p['job_id']
            if (launch / 'create-attempt.json').exists() and confirmed is not True:
                raise PendingCleanupError('owned T dispatch cleanup is unconfirmed; retain exact reservation') from exc
        return self._finish_command(folder, before,
            {'action': 'controller_error', 'error_type': type(exc).__name__, 'reason': str(exc)}, allow_unclosed=True)

    def _documents(self, capture):
        # One lossless tree retains EVERY captured member, including full state,
        # progress, criteria, ancestors, seals, delivery bytes and ledger SHA.
        from .request_tree import encode_tree, decode_tree
        value = encode_tree(capture)
        if canonical(decode_tree(value)) != canonical(capture):
            raise TCommonError('full T capture reconstruction diverged')
        return {'T-capture.json': canonical(value).decode()}

    @staticmethod
    def restore_capture(documents):
        from .request_tree import decode_tree
        return decode_tree(strict_json_loads(documents['T-capture.json']))

    @classmethod
    def restore_state(cls, documents):
        return cls.restore_capture(documents)['state']

    @classmethod
    def restore_criteria(cls, documents, captures):
        return cls.restore_capture(documents)['criteria_seal']

    def _snapshot(self, closed):
        from .t_common_snapshot import export_snapshot
        captures = []; receipts = {}; streams = {}
        # Initial pre-state plus every complete post-state retain the original
        # before-state of the next transition. Private journals also retain both.
        first = closed[0][1]['capture']
        captures.append({'id': 'initial', 'kind': 'planning', 'job_id': 'initial',
            'request_sha256': digest(_read(self.root / 'initial.json')),
            'delivery': first['files'], 'documents': self._documents(first)})
        for sequence, (folder, before, after) in enumerate(closed, 1):
            r = after['result']; action = r['action']; d = _json(folder / 'dispatch.json') if (folder / 'dispatch.json').exists() else None
            p = d['pending'] if d else None
            request = (p['request'] if p and p['action'] != 'test' else
                       {'argv': p['source_state']['items'][p['test_id']]['data']['argv'], 'files': p['source_files']}
                       if p else before['expected_task'])
            kind = ('execution' if action == 'test' else 'review' if action in ('review', 'approval')
                    else 'delivery' if r.get('phase') == 'build' else 'criteria' if r.get('phase') == 'specify' else 'planning')
            captures.append({'id': f'cp{sequence:04d}', 'kind': kind, 'job_id': p['job_id'] if p else f'step-{sequence:04d}',
                'request_sha256': digest(canonical(request)),
                'delivery': after['capture']['files'], 'documents': self._documents(after['capture'])})
            result = after['closed_result']
            if result is not None:
                self._verify_closed(folder, result)
                receipts[p['job_id']] = {'kind': 'test' if result['kind'] == 'test' else 'role', 'value': result['value']}
                if result['kind'] == 'test':
                    for stream in ('stdout', 'stderr'):
                        streams[p['job_id'] + '/' + stream] = _read(Path(result['value']['test_job_ref']).parent / (stream + '.bin'), 128000)
        root = self.root / 'snapshots' / digest(canonical({'captures': captures, 'receipts': receipts}))
        snapshot, reference = export_snapshot(root, contract=self.policy['contract'], policy=self.policy,
                               captures=captures, receipts=receipts, streams=streams)
        if (self.restore_state(snapshot['documents']) != closed[-1][2]['capture']['state']
                or self.restore_criteria(snapshot['documents'], list(snapshot['captures'].values()))
                    != closed[-1][2]['capture']['criteria_seal']):
            raise TCommonError('common snapshot no longer reconstructs complete original T state/custody')
        return snapshot, reference

    def _physical_ready(self, closed):
        c = self.controller; seal = criteria_seal(c)
        if seal is None:
            raise TCommonError('common T audit requires original pre-measurement criteria custody')
        c._check_sealed_battery(c._files())
        tests = [(folder, after) for folder, _, after in closed
                 if after['closed_result'] is not None and after['closed_result']['kind'] == 'test']
        if not tests:
            raise TCommonError('common T audit has no original closed measurement')
        folder, after = tests[-1]; self._verify_closed(folder, after['closed_result'])
        measured = after['closed_result']['value']
        if measured.get('passed') is not True or measured['delivery_tree_sha256'] != digest(canonical(c._files())):
            raise TCommonError('common T audit requires a passed current original measurement')
        return True

    def _audit_request(self, closed):
        self._physical_ready(closed)
        snapshot, reference = self._snapshot(closed)
        declared = declaration({'schema': 1, 'format': 'common-audit-v1', 'method': 'T',
            'binding': snapshot['binding'], 'locators': sorted(snapshot['locators'])})
        index = {}; content = {}
        for name, raw in snapshot['locators'].items():
            sha = digest(raw); index[name] = sha
            try:
                value = strict_json_loads(raw.decode()); exact_json = canonical(value) == raw
            except (ValueError, UnicodeError):
                exact_json = False
            if exact_json and name == 'document:T-capture.json':
                from .request_tree import encode_tree, decode_tree
                expanded = decode_tree(value)
                if canonical(encode_tree(expanded)) != raw:
                    raise TCommonError('typed T tree locator cannot reconstruct its exact physical bytes')
                content[sha] = {'encoding': 'T-capture-tree-json', 'value': expanded}
            elif exact_json and name.startswith('capture:'):
                from .request_tree import encode_tree
                expanded = copy.deepcopy(value)
                expanded['documents'] = {'T-capture.json': self.restore_capture(value['documents'])}
                restored = copy.deepcopy(expanded)
                restored['documents']['T-capture.json'] = canonical(encode_tree(expanded['documents']['T-capture.json'])).decode()
                if canonical(restored) != raw:
                    raise TCommonError('typed historical T capture cannot reconstruct original bytes')
                content[sha] = {'encoding': 'T-capture-container-json', 'value': expanded}
            else:
                content[sha] = {'encoding': 'canonical-json', 'value': value} if exact_json else {'encoding': 'utf8-text', 'value': raw.decode()}
        docs = {'action.txt': 'review', 'contract.txt': self.policy['contract'],
                'review-response-format.json': canonical(declared).decode(),
                'checklist.json': canonical(checklist('T')).decode(),
                'evidence-context.json': _context_document({'locator_index': index, 'content_by_sha256': content}),
                'context-format.txt': CONTEXT_FORMAT + AUDIT_CONTEXT_FORMAT +
                    'T-capture.json is a complete lossless specorganon-tree-refs-v1 capture of all original members. '
                    'Typed T-capture-tree-json content.value is the expanded original capture; encode it with the supplied tree grammar '
                    'and canonical JSON to reconstruct its exact physical locator bytes. T-capture-container-json content.value '
                    'is the full historical delivery/documents map with documents[T-capture.json] expanded likewise; encode that member '
                    'and replace it with its canonical JSON string, then canonicalize the container to reconstruct its original bytes. '
                    'The independent audit receipt stays outside this audited snapshot.'}
        request = {'schema': 1, 'role': 'review', 'role_instructions':
            'Independently audit complete original T evidence using the common D/G and separate nine H points. '
            'Judge substantive artifacts, original criteria, chronological captures, actual receipts and current delivery. '
            'An engine acceptance or a hash does not establish semantic truth. You did not execute tests. '
            'D/G readiness is independent of H and root verdict. Preserve failures and unknown F/costs. '
            'Use only provided typed evidence locators; no forced verdict or invented completion.', 'documents': docs}
        if len(canonical(request)) > LIMITS['request_bytes']:
            raise TCommonError('complete common T request exceeds original admission budget')
        _, prompt = render_prompt(canonical(request))
        native_stdin_payload(self.policy['transport_policy'].get('routes', {}).get('review', ['gemini'])[0], prompt)
        return request, reference

    def _current_closed(self, closed):
        if canonical(self._capture(None, None)) != canonical(closed[-1][2]['capture']):
            raise TCommonError('current T package differs from last original closed transition')

    def _audit(self, closed, method_gate, method_failure):
        self._current_closed(closed)
        if method_gate and self.controller.package_gate() is not True:
            raise TCommonError('current T package gate does not verify')
        path = self.root / 'audit/0001.json'
        if path.exists():
            reservation = _json(path)
        else:
            self._time_admission()
            if self._counts()['roles'] >= LIMITS['roles']:
                raise TCommonError('common audit must fit shared original T role budget')
            request, reference = self._audit_request(closed)
            reservation = {'schema': 1, 'job_id': 'T-common-audit-0001', 'request': request,
                'snapshot': reference, 'clock': _clock(), 'method_gate': method_gate,
                'method_failure': method_failure, 'last_command_sha256': digest(_read(closed[-1][0] / 'after.json'))}
            _put(path, canonical(reservation))
        if (reservation['last_command_sha256'] != digest(_read(closed[-1][0] / 'after.json'))
                or reservation['method_gate'] is not method_gate):
            raise TCommonError('audit reservation no longer belongs to this exact T package')
        result_path = self.root / 'audit/result-0001.json'
        if result_path.exists():
            packet = _json(result_path)
        else:
            packet = self.transport.recover_role(reservation['job_id'], 'review', reservation['request'])
            if packet is None:
                self._time_admission()
                packet = self.transport.call(reservation['job_id'], 'review', reservation['request'])
            _put(result_path, canonical(packet))
        if self.transport.verify_role(packet, reservation['job_id'], 'review', reservation['request']) is not True:
            raise TCommonError('common auditor has no verified independent original invocation')
        if any(_json(folder / 'dispatch.json')['pending']['job_id'] == reservation['job_id']
               for folder, _ in self._dispatches()):
            raise TCommonError('common audit reuses an author/phase/executor invocation')
        self._current_closed(closed)
        if method_gate and self.controller.package_gate() is not True:
            raise TCommonError('audited current T package gate no longer verifies')
        self._physical_ready(closed)
        snapshot = read_snapshot(reservation['snapshot']['path'], reservation['snapshot']['manifest_sha256'])
        if snapshot['delivery'] != self.controller._files() or snapshot['documents'] != self._documents(closed[-1][2]['capture']):
            raise TCommonError('audited T bytes differ from current final capture')
        declared = strict_json_loads(reservation['request']['documents']['review-response-format.json'])
        def verify(name, kind, value, ignored):
            match = next(((folder, after) for folder, _, after in closed
                if (folder / 'dispatch.json').exists() and _json(folder / 'dispatch.json')['pending']['job_id'] == name), None)
            if match is None or match[1]['closed_result'] is None:
                raise TCommonError('snapshot receipt lacks an original T command')
            original = match[1]['closed_result']
            if kind != ('test' if original['kind'] == 'test' else 'role') or canonical(value) != canonical(original['value']):
                raise TCommonError('snapshot receipt differs from complete original T packet')
            return self._verify_closed(match[0], original)
        # Verify ALL receipts even if the reviewer cites only documents.
        for name, receipt in snapshot['receipts'].items():
            verify(name, receipt['kind'], receipt['value'], snapshot)
        validated = validate_bound_audit(snapshot, declared, packet['result'], verify_receipt=verify)
        dg = all(point['status'] == 'pass' for group in ('D', 'G') for point in validated['review']['audit'][group].values())
        h = all(point['status'] == 'pass' for point in validated['review']['audit']['H'].values())
        return self._terminal('review_ready' if dg else 'failed', common_ready=dg,
            method_ready=method_gate and h, method_gate=method_gate,
            failure=None if dg else 'common D/G audit did not pass', method_failure=method_failure,
            audit_reservation_sha256=digest(_read(path)), snapshot=reservation['snapshot'])

    def _terminal(self, status, *, common_ready=False, method_ready=False, method_gate=False,
                  failure=None, method_failure=None, audit_reservation_sha256=None, snapshot=None):
        path = self.root / 'terminal.json'
        record = {'schema': 1, 'attempt_id': self.policy['attempt_id'], 'method': 'T', 'status': status,
            'counts': self._counts(), 'common_review_ready': common_ready, 'method_review_ready': method_ready,
            'method_gate': method_gate, 'fixture_mode': self.fixture_mode,
            'native_ready': not self.fixture_mode and common_ready and method_ready,
            'failure': failure, 'method_failure': method_failure,
            'audit_reservation_sha256': audit_reservation_sha256, 'snapshot': snapshot,
            'clock': _clock(), 'external_F': None, 'common_complete': None, 'goal_achieved': False,
            'monetary_cost': None, 'token_cost_comparability': 'unknown'}
        intent = self.root / 'terminal-intent.json'
        if intent.exists():
            return self._read_terminal()
        try:
            record['whole_attempt_seconds'] = _elapsed(self.initial['clock'], record['clock']); record['clock_error'] = None
        except ValueError as exc:
            record.update(whole_attempt_seconds=None, clock_error=str(exc), native_ready=False,
                          common_review_ready=False, method_review_ready=False)
        state = self._capture(None, None)
        _put(self.root / 'terminal-state.json', canonical(state))
        closed, pending, last = self._commands()
        if pending is not None:
            raise TCommonError('cannot close T with an unfinished original command')
        record.update(terminal_state_sha256=digest(canonical(state)),
                      last_command_sha256=last,
                      audit_result_sha256=digest(_read(self.root / 'audit/result-0001.json'))
                          if (self.root / 'audit/result-0001.json').exists() else None)
        if record['whole_attempt_seconds'] is not None and record['whole_attempt_seconds'] >= LIMITS['elapsed_admission_seconds']:
            record.update(native_ready=False, common_review_ready=False, method_review_ready=False,
                          status='failed', failure='whole T attempt closure exceeded original 6000-second budget')
        _put(intent, canonical(record))
        _put(path, canonical(record))
        return record

    def _read_terminal(self):
        # Original intent precedes the terminal commit. Never trust cached flags
        # without checking current physical state and every original receipt.
        record = _json(self.root / 'terminal-intent.json')
        path = self.root / 'terminal.json'
        if path.exists() and _read(path) != canonical(record):
            raise TCommonError('terminal record changed from original intent')
        self._get_controller()
        closed, pending, last = self._commands()
        if pending is not None or last != record['last_command_sha256']:
            raise TCommonError('terminal command chain changed')
        raw = _read(self.root / 'terminal-state.json', 64 * 1024 * 1024)
        if digest(raw) != record['terminal_state_sha256']:
            raise TCommonError('terminal state custody changed')
        if canonical(self._capture(None, None)) != raw:
            raise TCommonError('current T state differs from terminal custody')
        if self._counts() != record['counts']:
            raise TCommonError('terminal original dispatch counts changed')
        for folder, _, after in closed:
            if after['closed_result'] is not None:
                self._verify_closed(folder, after['closed_result'])
        audit_result = self.root / 'audit/result-0001.json'
        pin = record['audit_result_sha256']
        if pin is None:
            if audit_result.exists():
                raise TCommonError('unregistered audit result appeared after terminal closure')
        else:
            if digest(_read(audit_result)) != pin:
                raise TCommonError('terminal audit result changed')
            reservation_path = self.root / 'audit/0001.json'
            reservation = _json(reservation_path)
            if record['audit_reservation_sha256'] is not None and digest(_read(reservation_path)) != record['audit_reservation_sha256']:
                raise TCommonError('terminal audit reservation changed')
            packet = _json(audit_result)
            if self.transport.verify_role(packet, reservation['job_id'], 'review', reservation['request']) is not True:
                raise TCommonError('terminal auditor receipt no longer verifies')
        if record['common_review_ready'] or record['method_review_ready']:
            if not closed or canonical(closed[-1][2]['capture']) != raw:
                raise TCommonError('terminal readiness does not bind the original closed capture')
            if record['method_review_ready'] and self.controller.package_gate() is not True:
                raise TCommonError('terminal T package gate does not verify')
        if record['snapshot'] is not None:
            snapshot = read_snapshot(record['snapshot']['path'], record['snapshot']['manifest_sha256'])
            if snapshot['delivery'] != self.controller._files() or snapshot['documents'] != self._documents(closed[-1][2]['capture']):
                raise TCommonError('terminal audited snapshot changed')
        _put(path, canonical(record))
        return record

    def step(self):
        with self._lock():
            if (self.root / 'terminal.json').exists() or (self.root / 'terminal-intent.json').exists():
                return self._read_terminal()
            c = self._get_controller(); closed, pending, previous = self._commands()
            if closed:
                latest = closed[-1][2]
                if pending is None and (latest['result']['action'] in ('complete', 'controller_error')):
                    method_gate = latest['result'].get('package_allowed') is True
                    failure = latest['result'].get('reason')
                    try:
                        return self._audit(closed, method_gate, failure)
                    except PendingCleanupError:
                        raise
                    except (ValueError, OSError) as exc:
                        # No false closure while a reserved audit may still run.
                        audit = self.root / 'audit/0001.json'
                        if audit.exists() and not (self.root / 'audit/result-0001.json').exists():
                            r = _json(audit)
                            confirmed = self.transport.reconcile_pending(r['job_id'], 'review', r['request'])
                            if (self.root / 'transport/jobs' / r['job_id'] / 'create-attempt.json').exists() and confirmed is not True:
                                raise PendingCleanupError('common auditor cleanup unconfirmed; retain same reservation') from exc
                        return self._terminal('failed', failure=type(exc).__name__ + ': ' + str(exc),
                                              method_gate=method_gate, method_failure=failure)
            if pending is None:
                if len(closed) >= 80:
                    return self._terminal('failed', failure='original T command budget exhausted')
                folder = self.root / 'commands' / f'{len(closed)+1:04d}'; folder.mkdir(mode=0o700)
                before = None
            else:
                folder, before = pending
            if before is None:
                if not closed:
                    if (_read(c.case / 'organon.json', 64 * 1024 * 1024) != _read(self.root / 'case-initial-ledger.json', 64 * 1024 * 1024)
                            or c._files() or _json(c.root / 'progress.json') != {'schema': 1, 'history': [], 'pending': None}
                            or any(c._checkpoint(stage) is not None for stage in ('program', 'tests'))
                            or criteria_seal(c) is not None):
                        raise TCommonError('first T capture must be the exact original untouched baseline')
                capture = self._capture(folder, 'before')
                if closed and canonical(capture) != canonical(closed[-1][2]['capture']):
                    raise TCommonError('current T state differs from last complete captured transition')
                before = {'schema': 1, 'sequence': len(closed)+1, 'previous_sha256': previous,
                          'capture': capture, 'expected_task': describe_task(capture['state'])}
                _put(folder / 'before.json', canonical(before))
            self.current = (folder, before)
            try:
                result = self._completed_inner(folder, before)
                if result is None:
                    result = c.step()
                    recovered = self._completed_inner(folder, before)
                    if recovered is not None:
                        result = recovered
            except PendingCleanupError:
                raise
            except (ValueError, OSError) as exc:
                self._seal_failure(folder, before, exc)
            else:
                # Storage failure after a successful engine write is recoverable
                # custody uncertainty, not a replacement or synthetic rejection.
                self._finish_command(folder, before, result)
            finally:
                self.current = None
            return {'schema': 1, 'attempt_id': self.policy['attempt_id'], 'method': 'T', 'status': 'running',
                    'counts': self._counts(), 'common_review_ready': False, 'method_review_ready': False,
                    'native_ready': False, 'fixture_mode': self.fixture_mode, 'external_F': None,
                    'common_complete': None, 'goal_achieved': False}

    def run(self):
        for _ in range(82):
            report = self.step()
            if report['status'] != 'running':
                return report
        raise TCommonError('bounded T controller did not reach a terminal state')
