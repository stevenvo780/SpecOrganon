"""Synthetic T integration/custody guards, never native qualification or F."""
import copy
import json
from pathlib import Path

import pytest

from specorganon import engine, t_common_controller as M
from specorganon.common_review import checklist
from specorganon.role_jobs import _json, _write, canonical, digest
from specorganon.runner import describe_task
from specorganon.workflow import KIND_TO_PHASE
from test_software_controller_resources import README, put, response


POLICY = {'fixture': True, 'routes': {'author': ['codex', 'fixture'], 'review': ['gemini', 'fixture']}}


class JournalFixture:
    """Explicit fake journal with genuine byte guards, no containers or models."""
    def __init__(self, root, audit_h='pass'):
        self.root = root; self.root.mkdir(mode=0o700, exist_ok=True)
        self.jobs = root / 'fixture-jobs'; self.jobs.mkdir(mode=0o700, exist_ok=True)
        _write(root / 'transport-policy.json', POLICY)
        self.calls = []; self.measures = []; self.audit_h = audit_h

    def call(self, job, role, request):
        existing = self.recover_role(job, role, request)
        if existing is not None:
            return existing
        self.calls.append(job)
        folder = self.jobs / job; folder.mkdir(mode=0o700)
        _write(folder / 'request.json', request)
        if 'review-response-format.json' in request['documents']:
            declared = json.loads(request['documents']['review-response-format.json'])
            result = {'schema': 1, 'verdict': 'reject', 'reason': 'Synthetic separate audit',
                'findings': [], 'tests_executed': False, 'audit': {'binding': declared['binding'], **{
                    group: {name: {'status': self.audit_h if group == 'H' else 'pass',
                        'reason': 'Synthetic assertion only', 'evidence': [declared['locators'][0]]}
                            for name in points} for group, points in checklist('T').items()}}}
        elif role == 'review':
            result = {'schema': 1, 'verdict': 'accept', 'reason': 'Synthetic phase mechanics',
                      'findings': [], 'tests_executed': False}
            if request['documents']['action.txt'] == 'approval':
                result.update(mandate_conformity=True,
                    approval_targets=json.loads(request['documents']['approval-target-ids.json']))
        else:
            state = json.loads(request['documents']['state.json']); phase = describe_task(state)['phase']
            if phase == 'build':
                stage = json.loads(request['documents']['build-stage.json'])['stage']
                if stage == 'program':
                    result = response([put('impl1', 'implementation', ['req1'])],
                                      {'count.py': 'print(10)\n', 'README.md': README})
                else:
                    result = response([put('impl1', 'implementation', ['req1']),
                        put('t1', 'test', ['impl1', 'crit1'],
                            {'argv': ['/usr/bin/python3', '-B', '/input/delivery/test_count.py']})],
                        {'test_count.py': 'import count\n'})
            else:
                steps = _json(Path(__file__).parents[1] / 'workflows/synthetic_full.json')['steps']
                selected = []; current = 'frame'
                for step in steps:
                    if step['op'] == 'advance':
                        if current == phase: break
                        current = {'frame':'critique','critique':'study','study':'observe','observe':'explain',
                            'explain':'compare','compare':'specify','specify':'build','build':'validate'}.get(current, current)
                    elif current == phase:
                        selected.append(step)
                result = response(selected, {})
        packet = {'schema': 1, 'request_sha256': digest(canonical(request)), 'result': result,
                  'actor': 'agent:synthetic-' + role, 'receipt_ref': str(folder / 'receipt.json'),
                  'provenance': 'synthetic', 'usage_reported': None}
        _write(folder / 'packet.json', packet)
        return packet

    def recover_role(self, job, role, request):
        folder = self.jobs / job
        if not (folder / 'packet.json').exists(): return None
        assert canonical(_json(folder / 'request.json')) == canonical(request)
        return _json(folder / 'packet.json')

    def verify_role(self, packet, job, role, request):
        return canonical(packet) == canonical(self.recover_role(job, role, request))

    def measure(self, job, argv, files):
        old = self.recover_test(job, argv, files)
        if old is not None: return old
        self.measures.append(job); folder = self.jobs / job; folder.mkdir(mode=0o700)
        for stream in ('stdout', 'stderr'): (folder / (stream + '.bin')).write_bytes(b'')
        packet = {'provenance': 'synthetic', 'subject_argv': argv,
            'delivery_tree_sha256': digest(canonical(files)), 'exit_code': 0, 'timed_out': False,
            'truncated_streams': [], 'stdout_sha256': digest(b''), 'stderr_sha256': digest(b''),
            'stdout_bytes': 0, 'stderr_bytes': 0, 'passed': True,
            'test_job_ref': str(folder / 'receipt.json')}
        _write(folder / 'receipt.json', packet)
        return packet

    def recover_test(self, job, argv, files):
        path = self.jobs / job / 'receipt.json'
        if not path.exists(): return None
        value = _json(path)
        assert value['subject_argv'] == argv and value['delivery_tree_sha256'] == digest(canonical(files))
        return value

    def verify_test(self, data, files, *, require_passed=True, require_current=True):
        value = _json(Path(data['test_job_ref']))
        if require_current and value['delivery_tree_sha256'] != digest(canonical(files)): return False
        if require_passed and value['passed'] is not True: return False
        return data['argv'] == value['subject_argv']

    def read_test(self, data, files, **kwargs):
        assert self.verify_test(data, files, **kwargs) is True
        path = Path(data['test_job_ref']); value = _json(path)
        streams = {n: (path.parent / (n + '.bin')).read_bytes() for n in ('stdout', 'stderr')}
        assert all(digest(raw) == value[n + '_sha256'] and len(raw) == value[n + '_bytes']
                   for n, raw in streams.items())
        return value, streams

    def reconcile_pending(self, *args):
        return True  # Explicit fixture has no live processes.


def make(tmp_path, *, audit_h='pass', factory_check=None):
    holders = []
    def factory(root):
        if factory_check: factory_check(root)
        transport = JournalFixture(root, audit_h); holders.append(transport)
        return transport
    ctrl = M.TCommonController(tmp_path / 'T', attempt_id='fixture-T-01', contract='Synthetic count contract',
        mandate='Invented fixture mandate, not operator consent', title='Synthetic nine phase guard',
        transport_policy=POLICY, transport_factory=factory, author_format='manifest-v1', fixture_mode=True)
    return ctrl, holders


def test_clock_is_durable_before_case_and_transport_preparation(tmp_path):
    def observe(root):
        initial = _json(root.parent / 'initial.json')
        assert initial['clock']['boottime_ns'] <= M._clock()['boottime_ns']
        assert engine.get_state(root.parent / 'case')['revision'] == 0
        assert (root.parent / 'case-initial-ledger.json').exists()
    ctrl, holders = make(tmp_path, factory_check=observe)
    assert not holders and not (ctrl.root / 'case').exists()
    assert ctrl.step()['counts']['roles'] == 1
    before = _json(ctrl.root / 'commands/0001/before.json')
    after = _json(ctrl.root / 'commands/0001/after.json')
    assert before['capture']['state']['revision'] == 0
    assert len(after['capture']['state']['items']) == 3
    assert len(holders[0].calls) == 1


def test_crash_after_inner_transition_seals_same_original_without_next_role(tmp_path, monkeypatch):
    ctrl, holders = make(tmp_path)
    original = M._put
    def crash(path, raw):
        if path.name == 'after.json': raise OSError('synthetic crash after engine write')
        return original(path, raw)
    monkeypatch.setattr(M, '_put', crash)
    with pytest.raises(OSError, match='synthetic crash'): ctrl.step()
    assert len(holders[0].calls) == 1
    assert (ctrl.root / 'commands/0001/dispatch.json').exists()
    assert not (ctrl.root / 'commands/0001/after.json').exists()
    monkeypatch.setattr(M, '_put', original)
    assert ctrl.step()['counts']['roles'] == 1
    assert len(holders[0].calls) == 1
    assert _json(ctrl.root / 'commands/0001/after.json')['result']['job_id'] == holders[0].calls[0]
    assert ctrl.step()['counts']['roles'] == 2
    assert len(holders[0].calls) == 2


def test_mutated_original_capture_refuses_before_another_invocation(tmp_path):
    ctrl, holders = make(tmp_path); ctrl.step()
    p = ctrl.root / 'commands/0001/before-ledger.json'; p.write_bytes(b'{}')
    with pytest.raises(M.TCommonError, match='ledger changed'): ctrl.step()
    assert len(holders[0].calls) == 1


def test_author_edit_between_transitions_is_never_adopted_as_registered_work(tmp_path):
    ctrl, holders = make(tmp_path); ctrl.step()
    engine.put_item(ctrl.controller.case, 'outside', 'problem', 'Concurrent outside fixture edit', [], {},
                    'author:outside', expected_version=0, expected_deps={})
    with pytest.raises(M.TCommonError, match='last complete captured transition'): ctrl.step()
    assert len(holders[0].calls) == 1


def test_dispatch_budget_is_reserved_before_transport_and_recovery_keeps_it(tmp_path, monkeypatch):
    ctrl, holders = make(tmp_path)
    c = ctrl._get_controller(); original = holders[0].call
    def interrupt(job, role, request):
        assert ctrl._counts()['roles'] == 1
        assert _json(ctrl.root / 'commands/0001/dispatch.json')['pending']['job_id'] == job
        raise KeyboardInterrupt('synthetic interrupted dispatch')
    holders[0].call = interrupt
    with pytest.raises(KeyboardInterrupt): ctrl.step()
    first = (ctrl.root / 'commands/0001/dispatch.json').read_bytes()
    holders[0].call = original
    assert ctrl.step()['counts']['roles'] == 1
    assert (ctrl.root / 'commands/0001/dispatch.json').read_bytes() == first
    assert len(holders[0].calls) == 1


def test_complete_engine_without_common_audit_is_not_native_qualification(tmp_path):
    ctrl, holders = make(tmp_path)
    for _ in range(40):
        ctrl.step()
        closed, pending, _ = ctrl._commands()
        if closed[-1][2]['result']['action'] in ('complete', 'controller_error'): break
    assert closed[-1][2]['result']['action'] == 'complete', closed[-1][2]['result']
    assert ctrl.controller.package_gate() is True
    assert not (ctrl.root / 'audit/0001.json').exists()
    assert not (ctrl.root / 'terminal.json').exists()
    assert len(holders[0].measures) == 1
    assert all(phase['accepted'] for phase in engine.get_state(ctrl.controller.case)['phases'].values())


def test_all_state_members_are_retained_in_shards(tmp_path):
    ctrl, holders = make(tmp_path); ctrl.step()
    capture = _json(ctrl.root / 'commands/0001/after.json')['capture']
    docs = ctrl._documents(capture)
    assert canonical(ctrl.restore_capture(docs)) == canonical(capture)
    assert ctrl.restore_state(docs) == capture['state']



@pytest.mark.parametrize('h_status', ['pass', 'fail'])
def test_separate_common_audit_charged_and_H_never_changes_DG(tmp_path, h_status):
    ctrl, holders = make(tmp_path, audit_h=h_status)
    result = ctrl.run()
    assert result['status'] == 'review_ready', result
    assert result['common_review_ready'] is True
    assert result['method_gate'] is True
    assert result['method_review_ready'] is (h_status == 'pass')
    assert result['native_ready'] is False and result['external_F'] is None
    assert result['common_complete'] is None and result['goal_achieved'] is False
    assert holders[0].calls[-1] == 'T-common-audit-0001'
    assert result['counts']['roles'] == len(holders[0].calls)
    assert result['counts']['common_audits'] == 1
    assert result['whole_attempt_seconds'] >= 0
    assert ctrl.step() == result


@pytest.mark.parametrize('target', ['terminal.json', 'terminal-state.json', 'before-ledger.json', 'packet.json'])
def test_terminal_recovery_revalidates_original_physical_custody(tmp_path, target):
    ctrl, holders = make(tmp_path); ctrl.step()
    original = ctrl._terminal('failed', failure='Explicit synthetic stop')
    assert ctrl.step() == original
    if target in ('terminal.json', 'terminal-state.json'):
        path = ctrl.root / target
    elif target == 'before-ledger.json':
        path = ctrl.root / 'commands/0001' / target
    else:
        path = holders[0].jobs / holders[0].calls[0] / target
    value = _json(path); value['synthetic_tamper'] = True; _write(path, value)
    with pytest.raises(ValueError): ctrl.step()
    assert len(holders[0].calls) == 1


def test_terminal_refuses_changed_current_engine(tmp_path):
    ctrl, holders = make(tmp_path); ctrl.step()
    ctrl._terminal('failed', failure='Explicit synthetic stop')
    engine.put_item(ctrl.controller.case, 'outside', 'problem', 'Altered after closure', [], {},
                    'author:outside', expected_version=0, expected_deps={})
    with pytest.raises(M.TCommonError, match='terminal custody'): ctrl.step()
    assert len(holders[0].calls) == 1


def test_terminal_commit_cut_resumes_only_original_intent(tmp_path, monkeypatch):
    ctrl, holders = make(tmp_path); ctrl.step(); original = M._put
    def interrupt(path, raw):
        if path.name == 'terminal.json': raise OSError('synthetic terminal commit cut')
        return original(path, raw)
    monkeypatch.setattr(M, '_put', interrupt)
    with pytest.raises(OSError, match='terminal commit cut'):
        ctrl._terminal('failed', failure='Explicit synthetic stop')
    intended = _json(ctrl.root / 'terminal-intent.json')
    monkeypatch.setattr(M, '_put', original)
    assert ctrl.step() == intended
    assert (ctrl.root / 'terminal.json').read_bytes() == canonical(intended)
    assert len(holders[0].calls) == 1


def test_closed_transition_binds_original_dispatch_clock_and_budget(tmp_path):
    ctrl, holders = make(tmp_path); ctrl.step()
    path = ctrl.root / 'commands/0001/dispatch.json'; record = _json(path)
    record['clock']['boottime_ns'] += 1; _write(path, record)
    with pytest.raises(M.TCommonError, match='dispatch reservation changed'): ctrl.step()
    assert len(holders[0].calls) == 1


@pytest.mark.parametrize('mutate', ['none', 'other-actor', 'delivery', 'unrelated-event'])
def test_recovered_advance_must_match_original_event_and_unchanged_delivery(tmp_path, mutate):
    ctrl, holders = make(tmp_path); ctrl.step(); c = ctrl.controller
    # Explicit synthetic setup creates the mechanical advance boundary only.
    engine.review_phase(c.case, 'frame', 'accept', 'Synthetic boundary', 'agent:synthetic-separate')
    folder = ctrl.root / 'advance-probe'; folder.mkdir(mode=0o700)
    capture = ctrl._capture(folder, 'before')
    before = {'capture': capture, 'expected_task': describe_task(capture['state'])}
    assert before['expected_task']['action'] == 'advance_phase'
    if mutate == 'unrelated-event':
        engine.put_item(c.case, 'outside', 'concept', 'Synthetic unrelated event', [], {},
                        'agent:outside', expected_version=0, expected_deps={})
    else:
        engine.advance(c.case, 'frame', 'agent:outside' if mutate == 'other-actor' else 'agent:software-controller')
    if mutate == 'delivery':
        c._write_files({'source_files': c._files()}, {'foreign.txt': 'outside original operation'})
    if mutate == 'none':
        assert ctrl._completed_inner(folder, before) == {'action': 'advance', 'phase': 'frame'}
    else:
        with pytest.raises(M.TCommonError): ctrl._completed_inner(folder, before)
    assert len(holders[0].calls) == 1


def test_complete_T_audit_context_reconstructs_every_physical_locator(tmp_path):
    from specorganon.common_evidence import read_snapshot
    from specorganon.request_tree import encode_tree, decode_tree
    from specorganon.request_content import decode_content
    ctrl, holders = make(tmp_path); result = ctrl.run()
    assert result['common_review_ready'] is True
    reservation = _json(ctrl.root / 'audit/0001.json')
    envelope = json.loads(reservation['request']['documents']['evidence-context.json'])
    context = (decode_tree(envelope['context']) if envelope['encoding'] == 'tree-refs-v1' else
               decode_content(envelope['context']) if envelope['encoding'] == 'content-refs-v1' else envelope['context'])
    snapshot = read_snapshot(reservation['snapshot']['path'], reservation['snapshot']['manifest_sha256'])
    assert set(context['locator_index']) == set(snapshot['locators'])
    for name, raw in snapshot['locators'].items():
        sha = context['locator_index'][name]; assert sha == digest(raw)
        content = context['content_by_sha256'][sha]; value = copy.deepcopy(content['value'])
        if content['encoding'] == 'T-capture-tree-json':
            rebuilt = canonical(encode_tree(value))
        elif content['encoding'] == 'T-capture-container-json':
            value['documents']['T-capture.json'] = canonical(encode_tree(value['documents']['T-capture.json'])).decode()
            rebuilt = canonical(value)
        elif content['encoding'] == 'canonical-json': rebuilt = canonical(value)
        else:
            assert content['encoding'] == 'utf8-text'; rebuilt = value.encode()
        assert rebuilt == raw
    assert len(canonical(reservation['request'])) <= 110000
    assert len(snapshot['history']) == result['counts']['commands'] + 1
    assert len(snapshot['receipts']) == result['counts']['roles'] - 1 + result['counts']['test_runs']


def test_first_capture_cannot_inherit_unreserved_initial_work(tmp_path):
    ctrl, holders = make(tmp_path); c = ctrl._get_controller()
    engine.put_item(c.case, 'outside', 'problem', 'Unreserved initial work', [], {},
                    'agent:outside', expected_version=0, expected_deps={})
    with pytest.raises(M.TCommonError, match='untouched baseline'): ctrl.step()
    assert not holders[0].calls


def test_changed_completed_package_cannot_dispatch_common_auditor(tmp_path):
    ctrl, holders = make(tmp_path)
    for _ in range(40):
        ctrl.step(); closed, _, _ = ctrl._commands()
        if closed[-1][2]['result']['action'] == 'complete': break
    engine.put_item(ctrl.controller.case, 'outside', 'concept', 'Foreign state after complete', [], {},
                    'agent:outside', expected_version=0, expected_deps={})
    result = ctrl.step()
    assert result['native_ready'] is False and result['common_review_ready'] is False
    assert 'last original closed transition' in result['failure']
    assert 'T-common-audit-0001' not in holders[0].calls


def test_late_terminal_closure_cannot_confer_readiness(tmp_path, monkeypatch):
    ctrl, holders = make(tmp_path)
    for _ in range(40):
        ctrl.step(); closed, _, _ = ctrl._commands()
        if closed[-1][2]['result']['action'] == 'complete': break
    else: pytest.fail('synthetic nine-phase controller did not complete')
    # Prepare the original common audit before expiring only its terminal endpoint.
    original = ctrl._terminal
    monkeypatch.setattr(ctrl, '_terminal', lambda *args, **kwargs: None)
    ctrl._audit(closed, True, None)
    reservation = _json(ctrl.root / 'audit/0001.json')
    monkeypatch.setattr(ctrl, '_terminal', original)
    old = M._clock; start = ctrl.initial['clock']
    def late():
        value = old(); value['boottime_ns'] = start['boottime_ns'] + 6001 * 10**9; return value
    monkeypatch.setattr(M, '_clock', late)
    result = ctrl._terminal('review_ready', common_ready=True, method_ready=True, method_gate=True,
        audit_reservation_sha256=digest((ctrl.root / 'audit/0001.json').read_bytes()), snapshot=reservation['snapshot'])
    assert result['status'] == 'failed' and result['whole_attempt_seconds'] == 6001
    assert not result['native_ready'] and not result['common_review_ready'] and not result['method_review_ready']


def test_closed_inner_history_cannot_adopt_edit_after_original_closure(tmp_path, monkeypatch):
    ctrl, holders = make(tmp_path); original = M._put
    def cut(path, raw):
        if path.name == 'after.json': raise KeyboardInterrupt('synthetic post-closure cut')
        return original(path, raw)
    monkeypatch.setattr(M, '_put', cut)
    with pytest.raises(KeyboardInterrupt): ctrl.step()
    assert (ctrl.root / 'commands/0001/inner-close.json').exists()
    engine.put_item(ctrl.controller.case, 'outside', 'concept', 'Foreign edit after original closure', [], {},
                    'agent:outside', expected_version=0, expected_deps={})
    monkeypatch.setattr(M, '_put', original)
    with pytest.raises(ValueError): ctrl.step()
    assert len(holders[0].calls) == 1


def test_foreign_event_during_application_fails_exact_semantic_replay(tmp_path, monkeypatch):
    ctrl, holders = make(tmp_path); original = M.Controller._finish_role
    def inject(c, progress, pending, result, response):
        engine.put_item(c.case, 'outside', 'concept', 'Foreign edit during original application', [], {},
                        'agent:outside', expected_version=0, expected_deps={})
        return original(c, progress, pending, result, response)
    monkeypatch.setattr(M.Controller, '_finish_role', inject)
    ctrl.step(); after = _json(ctrl.root / 'commands/0001/after.json')
    assert after['result']['action'] == 'controller_error'
    assert 'outside original measured operation' in after['result']['reason']
    assert not (ctrl.root / 'commands/0001/inner-close.json').exists()
    assert len(holders[0].calls) == 1
