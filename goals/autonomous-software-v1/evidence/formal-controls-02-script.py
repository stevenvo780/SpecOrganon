"""Prospective synthetic C5-C7 mechanisms with an actually executable baseline.

Every argument, mandate and review is invented fixture content, explicitly
marked below. Only test execution is a real clean Docker measurement. This
does not supply C1, model independence, semantic quality or field evidence.
"""
from __future__ import annotations

import argparse
import copy
import json
import signal
import shlex
from pathlib import Path

from specorganon import engine
from specorganon.docker_roles import DockerRoles
from specorganon.role_jobs import _json, _write, canonical, digest
from specorganon.runner import describe_task, run_manifest
from specorganon.software_controller import Controller, ControllerError, fingerprint


class FixtureReviews:
    def __init__(self):
        self.calls = []
        self.verdict = 'accept'

    def call(self, job_id, role, request):
        self.calls.append((job_id, role, request['documents']['action.txt']))
        if role != 'review':
            raise ControllerError('fixture stops at repair request; no replacement reviewer')
        result = {'schema': 1, 'verdict': self.verdict, 'findings': [],
                  'reason': 'Invented synthetic mechanism judgment; no model or owner consent.',
                  'tests_executed': False}
        if request['documents']['action.txt'] == 'approval':
            task = json.loads(request['documents']['next-task.json'])
            result.update(mandate_conformity=True,
                          approval_targets=[item['id'] for item in task['approval_targets']])
        return {'schema': 1, 'result': result,
                'request_sha256': digest(canonical(request)),
                'actor': 'reviewer:synthetic-controls', 'receipt_ref': 'synthetic:' + job_id,
                'provenance': 'synthetic', 'usage_reported': None}


def guarded_put(case, step):
    state = engine.get_state(case)
    return engine.put_item(case, step['id'], step['kind'], step['text'], step['refs'],
                           step['data'], 'author:synthetic-controls',
                           expected_version=state['items'].get(step['id'], {}).get('version', 0),
                           expected_deps={ref: state['items'][ref]['version'] for ref in step['refs']})


def baseline(root, source, executor):
    case = root / 'case'
    engine.create_case(case, 'SYNTHETIC C5-C7 controls; no model approval', 'development',
                       'human:synthetic-fixture', approval_policy='local')
    reviews = FixtureReviews()
    ctrl = Controller(case, root / 'controller', reviews, executor=executor, fixture_mode=True,
                      contract='Invented fixture contract: print constructed count 10.',
                      mandate='Invented test mandate, never real owner approval or C1 evidence.')
    files = {'count.py': '# Synthetic condition: ' + root.name + '\nprint(10)\n', 'README.md':
             '# Synthetic control fixture\n\nRun /opt/specorganon/venv/bin/python '
             '/input/delivery/count.py in the pinned clean Docker executor. '
             'It prints the constructed count 10 and requires no dependencies, credentials '
             'or network. There is no input format or empirical claim. This documentation '
             'and every phase argument/review are invented mechanism fixtures only.\n'}
    ctrl._write_files({'source_files': {}}, files)
    steps = json.loads((source / 'workflows/synthetic_full.json').read_text())['steps']
    for original in steps:
        step = copy.deepcopy(original)
        if step['op'] == 'put':
            if step['kind'] == 'test':
                step['data'] = {'argv': ['/opt/specorganon/venv/bin/python', '-E', '-s', '-B',
                                       '/input/delivery/count.py']}
                step['data']['command'] = shlex.join(step['data']['argv'])
                step['text'] = 'Synthetic criterion, real isolated print-count execution receipt.'
            elif step['kind'] == 'assessment':
                step['refs'] = ['res1', 'base1', 'crit1']
                step['data']['claim_scope'] = 'simulation'
            guarded_put(case, step)
        else:
            for _ in range(4):
                if engine.get_state(case)['phases'][step['phase']]['accepted']:
                    break
                ctrl.step()
            assert engine.get_state(case)['phases'][step['phase']]['accepted'], describe_task(engine.get_state(case))
    assert all(p['accepted'] for p in engine.get_state(case)['phases'].values())
    assert ctrl.package_gate() is True, 'positive package baseline required before perturbation'
    _write(root / 'baseline-ledger.json', _json(case / 'organon.json'))
    _write(root / 'baseline-state.json', engine.get_state(case))
    return ctrl, reviews


def must_fail(operation):
    try:
        operation()
    except (ValueError, OSError) as exc:
        return {'type': type(exc).__name__, 'reason': str(exc)}
    raise AssertionError('operation unexpectedly succeeded')


def run_condition(name, root, source, executor):
    ctrl, reviews = baseline(root, source, executor)
    before = _json(ctrl.case / 'organon.json')
    state = engine.get_state(ctrl.case)
    outcomes = {'positive_baseline_package_allowed': True,
                'baseline_nine_accepted': True, 'synthetic_arguments_and_reviews': True}
    if name == 'C5-withdrawal':
        item = state['items']['e1']
        guarded_put(ctrl.case, {'id': 'e1', 'kind': 'evidence', 'text': 'Withdrawn synthetic support.',
                               'refs': list(item['deps']), 'data': {}})
        outcomes['advance_error'] = must_fail(lambda: engine.advance(ctrl.case, 'observe', 'executor:synthetic'))
        assert engine.get_state(ctrl.case)['items']['e1']['issues']
    elif name == 'C5-rejection':
        # Apply an explicit negative judgment to the current accepted snapshot;
        # keep the old accept and advance as history, not current authority.
        request = ctrl._request(state, 'review', {'history': []})
        reviews.verdict = 'reject'
        pending = {'job_id': 'synthetic-terminal-rejection', 'action': 'review', 'phase': 'validate',
                   'source_state': state, 'source_fingerprint': fingerprint(state),
                   'source_files': ctrl._files(), 'request': request, 'status': 'closed',
                   'packet': reviews.call('synthetic-terminal-rejection', 'review', request)}
        progress = _json(ctrl.root / 'progress.json'); progress['pending'] = pending
        _write(ctrl.root / 'progress.json', progress)
        ctrl._apply(progress, pending)
        assert engine.get_state(ctrl.case)['phase_review_history'][-1]['verdict'] == 'reject'
        calls_before = len(reviews.calls)
        outcomes['repair_required_error'] = must_fail(ctrl.step)
        assert len(reviews.calls) == calls_before + 1 and reviews.calls[-1][1] == 'author'
        outcomes['replacement_review_calls'] = 0
        outcomes['advance_error'] = must_fail(lambda: engine.advance(ctrl.case, 'validate', 'executor:synthetic'))
    elif name == 'C6-challenge':
        engine.challenge(ctrl.case, 'e1', 'h1', 'Synthetic support conflicts with hypothesis.', 'challenger:synthetic')
        after = engine.get_state(ctrl.case)
        assert after['open_challenges'] and after['items']['inf1']['contested']
        outcomes['controller_error'] = must_fail(ctrl.step)
        outcomes['advance_error'] = must_fail(lambda: engine.advance(ctrl.case, 'observe', 'executor:synthetic'))
    elif name == 'C7-premise':
        old_item = state['items']['p1']
        old_request = ctrl._request(state, 'review', {'history': []})
        old_packet = reviews.call('old-snapshot', 'review', old_request)
        guarded_put(ctrl.case, {'id': 'p1', 'kind': 'problem', 'text': 'Changed synthetic premise.',
                               'refs': [], 'data': old_item['data']})
        after = engine.get_state(ctrl.case)
        assert after['items']['req1']['stale'] and not after['phases']['validate']['accepted']
        outcomes['old_put_error'] = must_fail(lambda: run_manifest(ctrl.case, {'schema': 1, 'steps': [{
            'op': 'put', 'id': 'p1', 'kind': 'problem', 'text': old_item['text'], 'refs': [],
            'data': old_item['data'], 'expected_version': 1, 'expected_deps': {}}]}, 'author:synthetic-controls'))
        pending = {'job_id': 'old-snapshot', 'action': 'review', 'phase': 'validate',
                   'source_state': state, 'source_fingerprint': fingerprint(state),
                   'source_files': ctrl._files(), 'request': old_request, 'status': 'closed', 'packet': old_packet}
        outcomes['old_review_error'] = must_fail(lambda: ctrl._apply(_json(ctrl.root / 'progress.json'), pending))
        outcomes['advance_error'] = must_fail(lambda: engine.advance(ctrl.case, 'validate', 'executor:synthetic'))
    else:
        raise ValueError('unknown preregistered condition')
    outcomes['package_error'] = must_fail(ctrl.package_gate)
    after = _json(ctrl.case / 'organon.json')
    assert after['events'][:len(before['events'])] == before['events'], 'history rewritten'
    appended = after['events'][len(before['events']):]
    assert not any(e['kind'] == 'phase_advance' for e in appended), 'unjustified advance'
    outcomes.update(history_prefix_preserved=True, new_advance_events=0,
                    verdict='satisfied', scope='synthetic mechanism, not C1 or independent model review')
    _write(root / 'after-ledger.json', after)
    _write(root / 'after-state.json', engine.get_state(ctrl.case))
    _write(root / 'outcome.json', outcomes)
    return outcomes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-root', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--native-image', required=True)
    parser.add_argument('--test-image', required=True)
    parser.add_argument('--public-catalog', type=Path, required=True)
    args = parser.parse_args()
    args.run_root.mkdir(parents=True, exist_ok=False)
    plan = {'schema': 1, 'classification': 'prospective synthetic C5-C7 engineering controls',
            'engineering_version': 2, 'prior_attempt': 'formal-controls-01 stopped before Docker: fixture missing command; retained',
            'conditions': ['C5-withdrawal', 'C5-rejection', 'C6-challenge', 'C7-premise'],
            'runs_per_condition': 1, 'timeout_seconds_per_condition': 120,
            'native_model_calls': 0, 'positive_baseline_required': 'nine accepted synthetic phases and package gate true',
            'rejection_rule': 'any unexpected success, history change or advance fails; no overwrite/retry',
            'baseline_test': 'actual clean pinned Docker print-count execution',
            'fixture_sha256': digest((args.source_root / 'workflows/synthetic_full.json').read_bytes()),
            'script_sha256': digest(Path(__file__).read_bytes()), 'test_image': args.test_image,
            'semantic_approval': False, 'C1_satisfied': False}
    _write(args.run_root / 'plan.json', plan)
    transport = DockerRoles(args.run_root / 'executor', native_image=args.native_image,
                            test_image=args.test_image, source_root=args.source_root,
                            public_catalog=args.public_catalog)
    outcomes = {}
    def timed_out(signum, frame):
        raise TimeoutError('preregistered condition timeout; no replacement execution')
    signal.signal(signal.SIGALRM, timed_out)
    for condition in plan['conditions']:
        signal.alarm(plan['timeout_seconds_per_condition'])
        try:
            outcomes[condition] = run_condition(condition, args.run_root / condition, args.source_root, transport)
        finally:
            signal.alarm(0)
    _write(args.run_root / 'results.json', {'plan': plan, 'conditions': outcomes, 'goal_complete': False})
    print(json.dumps(outcomes, indent=2))


if __name__ == '__main__':
    main()
