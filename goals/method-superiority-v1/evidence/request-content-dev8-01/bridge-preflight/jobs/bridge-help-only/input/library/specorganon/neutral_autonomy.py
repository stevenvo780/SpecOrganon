"""Durable autonomous-text N development controller; never reserved F.

Reuses guarded transport, immutable generations and exact-job recovery from the
staged controller. It does not impose notes before code or SDD artifacts. Every
author turn, feedback and audit is charged to the same finite resource pools.
Semantic G judgments belong to the independent bound auditor, not this host.
"""
from __future__ import annotations

import copy
from pathlib import Path

from .free_control_policy import (
    CAPS, GLOBAL_ROLE_CEILING, NEXT_DOCUMENT, admit_action, counters,
    decode_update, following_measure, remaining, reserve,
)
from .ledger import strict_json_loads
from .native_response_contract import render_prompt, response_schema, validate_response_schema
from .neutral_controller import LIMITS, NeutralController, NeutralControllerError, _fingerprint, _context_document
from .request_content import decode_content
from .role_jobs import _read, canonical, digest
from .software_controller import encoded_contribution, safe_file


BATTERY_DOCUMENT = 'controller-test-files.json'
RESERVED = frozenset({NEXT_DOCUMENT, BATTERY_DOCUMENT})


def partition(raw, files, test_file):
    """Validate physical partition, not pertinence or complete dependency truth."""
    if type(raw) is not str or len(raw.encode()) > 16384:
        raise NeutralControllerError('bounded explicit battery declaration required')
    value = strict_json_loads(raw)
    if type(value) is not dict or set(value) != {'test_files', 'mutable_files'}:
        raise NeutralControllerError('exact test/mutable partition required')
    for names in value.values():
        if (type(names) is not list or not 1 <= len(names) <= 256
                or any(type(n) is not str for n in names) or len(set(names)) != len(names)):
            raise NeutralControllerError('distinct explicit partition names required')
        for name in names:
            safe_file(name)
    tests = set(value['test_files']); mutable = set(value['mutable_files'])
    if tests & mutable or tests | mutable != set(files) or test_file not in tests:
        raise NeutralControllerError('battery partition must exhaust delivery and seal fixed script')
    return {'test_files': sorted(tests), 'mutable_files': sorted(mutable)}


class AutonomousNeutralController(NeutralController):
    def __init__(self, root, **options):
        if options.get('method') != 'N':
            raise NeutralControllerError('autonomous controller only owns the N process')
        super().__init__(root, **options)

    def _policy_extra(self):
        return {'protocol': 'autonomous-text-N-development-v2',
                'autonomy_source_sha256': digest(_read(Path(__file__), 128000)),
                'wire_policy_source_sha256': digest(_read(Path(__file__).with_name('free_control_policy.py'))),
                'effective_caps': copy.deepcopy(CAPS), 'global_role_ceiling': GLOBAL_ROLE_CEILING,
                'battery_declaration': BATTERY_DOCUMENT}

    @staticmethod
    def _initial_state():
        state = NeutralController._initial_state()
        state.update(stage='free', counts=counters(), battery_partition=None,
                     measurement_binding=None, measurement_passed=False,
                     control_history=[], last_admission_failure=None)
        return state

    def _charged(self, state):
        stage = state['stage']
        if stage not in {'free', 'feedback', 'measure', 'audit'}:
            raise NeutralControllerError('unknown autonomous stage')
        return reserve(state['counts'], {'free': 'author', 'measure': 'measure'}.get(stage, 'review'))

    def _request(self, state, past, sequence):
        stage = state['stage']
        if stage == 'measure':
            return super()._request(state, past, sequence)
        adapted = copy.deepcopy(state)
        adapted['stage'] = {'free': 'program', 'feedback': 'plan-review'}.get(stage, stage)
        req, snapshot = super()._request(adapted, past, sequence)
        req['documents']['stage.txt'] = stage
        req['documents']['remaining-budget.json'] = canonical({
            'current_invocation_already_reserved': True,
            'charged': self._charged(state), 'remaining': remaining(self._charged(state)),
            'caps': CAPS, 'nominal_global_role_ceiling': GLOBAL_ROLE_CEILING}).decode()
        controller_context = {'control_history': state['control_history']}
        if stage == 'free':
            req['role_instructions'] = (
                'Solve the supplied functional contract with your own strategy. You may start with code, '
                'plan first or combine code, README, criteria and tests. No SDD artifacts or prior notes required. '
                'Return schema1/files/documents/reason patches. Include documents/controller-next.json with '
                'exact JSON {"action":"continue"|"review"|"measure"|"audit"}; it is operational, not notes. '
                'Every invocation, including a control-only or invalid response, consumes an author slot. '
                'Five authors total, four shared feedback/audit reviewers, two own measures; see exact remaining budget. '
                'After the fifth author, continue/review are invalid and fail without dispatch; measure chains a final '
                'audit if it passes, or fails; audit requires an already passed current measure and remaining reviewer. '
                'Choose review for independent feedback on any current ideas/code, without an acceptance gate. '
                'Choose measure only with Python program, README and the fixed test script. Its first request must '
                'also include documents/controller-test-files.json: exact {"test_files":[paths],"mutable_files":[paths]}. '
                'The nonempty disjoint lists cover ALL delivery files, fixed script in test_files, including all test '
                'fixtures/dependencies. No extension inference. All test_files bytes and the partition are immutable '
                'from first measurement; never add delivery files afterwards. A false dependency declaration is '
                'an audit defect, not truth proven by the partition. Neither reserved document is allowed in files. '
                'The partition document is allowed only for measure; subsequent measure may omit it or send same lists. '
                'Own argv uses Python -I -B: stdlib and absolute runpy/importlib paths, no sys.path assumptions. '
                'Document substantive criteria before actual own execution; host capture is not semantic G acceptance. '
                'Any file/document change after a measure requires a new measure before audit. Empty/idempotent '
                'patches preserve current measurement. Original functional contract cannot be weakened. '
                'Use actual feedback/receipts, never invent execution, independent F, complete package or superiority. '
                'README needs environment/interface/bounds, two reproducible examples with outputs, '
                'errors/exit/atomicity, and honest scope/limits of tests and unknown costs.')
        elif stage == 'feedback':
            req['role_instructions'] = (
                'Independently review this exact captured current N package/ideas and original functional contract. '
                'Find actual defects and useful improvements in its chosen strategy. Code before notes is allowed; '
                'do not impose SDD artifacts or a planning phase. Return schema1/verdict/reason/findings/'
                'tests_executed=false. This is feedback, not final D/G, no acceptance gate or test execution. '
                'Use supplied files/documents/history and exact resource limits; do not claim competence or F.')
        else:
            controller_context.update(battery_partition=state['battery_partition'], prior_measurement_binding={
                'binding': state['measurement_binding'], 'passed': state['measurement_passed'],
                'job_id': state['measure_job'], 'criteria_capture': state['original_criteria']})
        # Preserve all autonomous metadata while sharing repeated strings with
        # the captured package/evidence; the complete journals remain unchanged.
        name = 'evidence-context.json' if stage == 'audit' else 'package-context.json'
        document = strict_json_loads(req['documents'][name])
        context = (decode_content(document['context']) if document['encoding'] == 'content-refs-v1'
                   else document['context'])
        context['controller_context'] = controller_context
        req['documents'][name] = _context_document(context)
        if len(canonical(req)) > LIMITS['request_bytes']:
            raise NeutralControllerError('autonomous exact request exceeds budget')
        render_prompt(canonical(req))
        return req, snapshot

    def _can_repair(self, state):
        c = remaining(state['counts'])
        return c['authors'] > 0 and c['reviewers'] > 0 and c['test_runs'] > 0

    @staticmethod
    def _binding(state):
        return _fingerprint({'files': state['files'], 'documents': state['documents']})

    def _checkpoint(self, state, reservation, kind):
        seq = len(state['history']) + 1
        state['history'].append({'schema': 1, 'id': f'cp{seq:04d}', 'sequence': seq,
            'previous_sha256': None, 'kind': kind, 'job_id': reservation['job_id'],
            'request_sha256': _fingerprint(reservation['request']),
            'delivery_sha256': _fingerprint(state['files']),
            'documents_sha256': _fingerprint(state['documents'])})
        return state

    def _invalid(self, state, reservation, message):
        s = copy.deepcopy(state); s['counts'] = copy.deepcopy(reservation['counts'])
        s['last_admission_failure'] = message
        s['control_history'].append({'job_id': reservation['job_id'], 'admitted': False, 'reason': message})
        if s['counts']['authors'] < CAPS['authors']:
            s['stage'] = 'free'
        else:
            self._failure(s, 'autonomous admission failed; no author slot remains: ' + message)
        return self._checkpoint(s, reservation, 'planning' if reservation['stage'] == 'free' else 'review')

    def _apply_valid(self, state, r, result, past):
        if r['halt'] is not None or result['kind'] == 'error':
            return super()._apply_valid(state, r, result, past)
        if result['kind'] == 'response_error':
            if r['stage'] == 'measure':
                raise NeutralControllerError('measurement cannot carry a native role response error')
            self._verify_result(r, result, state)
            return self._invalid(state, r, 'Closed native response contract failed; exact slot retained')
        stage = r['stage']
        if stage == 'audit':
            if (not state['measurement_passed'] or state['measurement_binding'] != self._binding(state)):
                raise NeutralControllerError('audit requires a passed current file/document measurement')
            s = super()._apply_valid(state, r, result, past)
            if s['stage'] == 'repair': s['stage'] = 'free'
            return s
        if result['kind'] != ('test' if stage == 'measure' else 'role'):
            raise NeutralControllerError('autonomous stage/result role mismatch')
        self._verify_result(r, result, state)
        value = result['value'] if stage == 'measure' else result['value']['result']
        s = copy.deepcopy(state); s['counts'] = copy.deepcopy(r['counts'])
        if stage == 'measure':
            if type(value.get('passed')) is not bool:
                raise NeutralControllerError('measured test requires exact Boolean outcome')
            s['measure_job'] = r['job_id']; s['measurement_passed'] = value['passed']
            s['measurement_binding'] = self._binding(state)
            route = following_measure(s['counts'], passed=value['passed'])
            s['stage'] = 'free' if route == 'author' else route
            if route == 'failed': self._failure(s, 'own measurement failed or final audit budget exhausted')
            return self._checkpoint(s, r, 'execution')
        if stage == 'feedback':
            if type(value) is not dict or type(value.get('schema')) is not int or value['schema'] != 1:
                raise NeutralControllerError('feedback requires exact schema1')
            validate_response_schema(value, response_schema('review'))
            s['stage'] = 'free'
            return self._checkpoint(s, r, 'review')
        try:
            v = decode_update(value); action = admit_action(v['action'], s['counts'])
            declaration = v['documents'].pop(BATTERY_DOCUMENT, None)
            if RESERVED & set(v['files']) or declaration is not None and action != 'measure':
                raise NeutralControllerError('reserved partition is documents-only and measure-only')
            for name in v['files']: safe_file(name)
            files = {**state['files'], **v['files']}; docs = {**state['documents'], **v['documents']}
            if (len(files) > 256 or len(docs) > 256 or encoded_contribution(files) > LIMITS['files_encoded_bytes']
                    or encoded_contribution(docs) > LIMITS['documents_encoded_bytes']):
                raise NeutralControllerError('autonomous complete candidate exceeds common byte budget')
            battery = state['battery_partition']
            if battery is not None and (set(files) != set(state['files']) or
                    any(files[name] != text for name, text in state['original_tests'].items())):
                raise NeutralControllerError('sealed test package changed or new delivery file added')
            candidate = {**s, 'files': files, 'documents': docs}
            if action == 'measure':
                if not files.get('README.md', '').strip() or not files.get(self.policy['test_file'], '').strip() or not any(
                        n.endswith('.py') and n != self.policy['test_file'] for n in files):
                    raise NeutralControllerError('own measurement needs program, README and fixed script')
                if battery is None:
                    battery = partition(declaration, files, self.policy['test_file'])
                elif declaration is not None and partition(declaration, files, self.policy['test_file']) != battery:
                    raise NeutralControllerError('original battery partition cannot change')
                candidate['battery_partition'] = battery
                candidate['original_tests'] = {n: files[n] for n in battery['test_files']}
                if state['original_criteria'] is None:
                    candidate['original_criteria'] = {'files': copy.deepcopy(files), 'documents': copy.deepcopy(docs)}
            if action == 'audit' and (not state['measurement_passed'] or state['measurement_binding'] != self._binding(candidate)):
                raise NeutralControllerError('changed or unmeasured candidate cannot audit with stale receipt')
            changed = self._binding(candidate) != self._binding(state)
            if changed:
                candidate['measure_job'] = None; candidate['audit_job'] = None
                candidate['measurement_passed'] = False; candidate['measurement_binding'] = None
            candidate['stage'] = {'continue': 'free', 'review': 'feedback'}.get(action, action)
            candidate['last_admission_failure'] = None
            candidate['control_history'].append({'job_id': r['job_id'], 'admitted': True,
                'action': action, 'control_raw': v['control_raw'], 'partition_raw': declaration})
            kind = 'criteria' if action == 'measure' and state['original_criteria'] is None else 'delivery'
            return self._checkpoint(candidate, r, kind)
        except ValueError as exc:
            return self._invalid(state, r, type(exc).__name__ + ': ' + str(exc))

    def _report(self, state):
        report = super()._report(state)
        report.update(control_definition=self.policy['protocol'],
                      remaining_budget=remaining(state['counts']),
                      last_admission_failure=state['last_admission_failure'])
        return report
