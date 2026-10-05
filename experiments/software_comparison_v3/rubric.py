"""Prospective qualitative rubric and response shape; not a native audit runner.

Parsing an auditor's assertions does not authenticate a reviewer, execute a test,
verify evidence locators or fulfill the actual nine-phase engineering milestone.
The campaign harness must bind actual native receipts/current immutable snapshots.
"""
from __future__ import annotations

import copy
import re

PHASES = ('frame', 'critique', 'study', 'observe', 'compare', 'choose', 'specify', 'build', 'validate')
D = {
    'd1': 'README identifies Python3.12, stdlib-only installation and executable entry file.',
    'd2': 'README gives exact stdin/no-arguments invocation and input/output interface.',
    'd3': 'First public example has a complete reproducible command, input and correct output.',
    'd4': 'Second public example has a complete reproducible command, input and correct output.',
    'd5': 'Exact invalid_input stderr/exit2/empty stdout are documented, with no partial result.',
    'd6': 'All input byte/list/type/value/string bounds and3s/2CPU/1GiB/128pids/streams are stated.',
    'd7': 'Task semantics are accurate: exact rational/canonical/counts; priority/literalsets/ties; or current-index/atomic edits.',
    'd8': 'Own tests have executable reproducible commands and calibrated scope/limitations; no unexecuted tests claimed.',
}
G = {
    'g1': 'Grounding names accessible sources/contract and separates observations, documentary premises and assumptions.',
    'g2': 'Delivery criteria were recorded before actual own execution, proven by captured packet chronology rather than a later assertion.',
    'g3': 'Concrete requirements/criteria connect to design/implementation and pertinent tests in artifacts or useful prose.',
    'g4': 'Actual isolated own test receipts bind argv, captured streams/exit and current delivery; no fabricated execution.',
    'g5': 'A physically separate native reviewer assessed this exact snapshot with substantive reasons and recorded defects/verdict.',
    'g6': 'Conclusion states verified limits, failures and unknown usage/cost honestly, with no comparative/field claim based on local checks.',
}
S = {
    'h1': 'Specification precedes measurements: explicit requirements, bounds, interface and delivery criteria.',
    'h2': 'Design considers substantive alternatives/tradeoffs and records the selected technical rationale.',
    'h3': 'Tasks precede build and connect requirements/criteria to executable work and tests.',
    'h4': 'Build follows the recorded plan or documents material changes and preserves actual file snapshots.',
    'h5': 'Verification uses real isolated own receipts and final docs/source review; unresolved failures remain visible.',
}
T = {f'h{i + 1}': f'{phase}: accepted CURRENT engine phase with substantive content, valid prerequisites and actual independent native review.'
     for i, phase in enumerate(PHASES)}
A = {f'h{i + 1}': f'{phase}: substantive CANDIDATE artifacts with current versioned references under the external nine-phase plan; no fabricated acceptance/review/advance.'
     for i, phase in enumerate(PHASES)}


class RubricError(ValueError):
    pass


def rubric(method):
    if method not in ('N', 'S', 'T', 'A'):
        raise RubricError('unknown treatment')
    return {'schema': 1, 'method': method, 'D': copy.deepcopy(D), 'G': copy.deepcopy(G),
            'H': copy.deepcopy({'N': {}, 'S': S, 'T': T, 'A': A}[method]),
            'H_applicable': method != 'N',
            'rules': [
                'Judge substance and actual snapshot evidence, not field counts or filenames.',
                'Every pass needs a concrete nonempty reason and evidence locators in supplied immutable documents.',
                'Missing content/evidence is fail; unknown infrastructure/receipt availability is inconclusive, not pass.',
                'N has no imposed method guide: H not applicable, never a failure for missing nine phases.',
                'T requires nine accepted phases and native source-bound review/test evidence; A does not require mechanisms removed.',
                'This audit is not blind to method; functional evaluator receives only opaque ID/contract/delivery.',
                'Auditor executes no tests; actual source/execution records are supplied by the trusted coordinator.',
                'Parsing this response is not authentication, proof of locator truth or a package gate by itself.',
                'Report F/D/G/H separately. full_package requires all applicable points and Fcomplete; no compensating weighted total.',
            ]}


def validate_response(value, method, binding):
    definition = rubric(method)
    expected_keys = {'schema', 'binding', 'D', 'G', 'H', 'reason', 'tests_executed'}
    if (type(value) is not dict or set(value) != expected_keys or type(value['schema']) is not int
            or value['schema'] != 1 or value['binding'] != binding or value['tests_executed'] is not False
            or type(value['reason']) is not str or not value['reason'].strip()):
        raise RubricError('invalid bound audit response')
    if (type(binding) is not dict or set(binding) != {'contract_sha256', 'delivery_sha256', 'history_sha256'}
            or any(type(v) is not str or re.fullmatch('[0-9a-f]{64}', v) is None for v in binding.values())):
        raise RubricError('explicit immutable snapshot digests required')
    for group in ('D', 'G', 'H'):
        items = value[group]
        if type(items) is not dict or set(items) != set(definition[group]):
            raise RubricError('audit checklist IDs mismatch: ' + group)
        for entry in items.values():
            if (type(entry) is not dict or set(entry) != {'status', 'reason', 'evidence'}
                    or entry['status'] not in ('pass', 'fail', 'inconclusive')
                    or type(entry['reason']) is not str or not entry['reason'].strip()
                    or type(entry['evidence']) is not list
                    or any(type(e) is not str or not e.strip() for e in entry['evidence'])
                    or entry['status'] == 'pass' and not entry['evidence']):
                raise RubricError('audit point needs a reason and supplied evidence locators for pass')
    return copy.deepcopy(value)


def summarize_assertions(value, method, binding):
    """Descriptive auditor assertions only, deliberately not full_package proof."""
    checked = validate_response(value, method, binding)
    result = {'scope': 'native assertions only; receipt/provenance/current-evidence verification still required',
              'H_applicable': method != 'N'}
    for group in ('D', 'G', 'H'):
        counts = {s: sum(entry['status'] == s for entry in checked[group].values())
                  for s in ('pass', 'fail', 'inconclusive')}
        counts['denominator'] = len(checked[group])
        counts['lower'] = counts['pass']
        counts['upper'] = counts['pass'] + counts['inconclusive']
        result[group] = counts
    return result
