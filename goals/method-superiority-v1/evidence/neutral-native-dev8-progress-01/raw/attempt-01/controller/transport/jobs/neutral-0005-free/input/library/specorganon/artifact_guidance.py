"""Read-only role hints. Engine validators and the complete state stay authoritative.

These documents contain field names and dependency diagnostics, never scientific
arguments, measurements, approvals or automatically rewritten references.
"""
from __future__ import annotations

import copy
from .role_jobs import canonical


DATA_CONTRACT = {
    'schema': 1,
    'scope': 'Advisory field names, not an exhaustive validator or semantic acceptance',
    'authority': ['engine._item_issues', 'engine._decisive_indicator_has_evidence', 'engine._success_claim_issues'],
    'evidence': {
        'required': ['origin', 'source', 'date', 'locator'],
        'origins': ['published', 'observed', 'derived', 'simulated'],
        'observed_requires': {'method': 'nonempty string describing actual collection'},
        'collection_method': 'Does not substitute for data.method; do not invent collection',
        'measured_indicator_support': {
            'fields': ['metric_key', 'scope', 'unit', 'value'],
            'meaning': 'Metric/unit match the indicator; scope identifies the actual measured population',
            'value': 'Finite engine-supported numeric measurement supplied by a real source; no extrapolation',
            'trace': 'Current evidence/protocol/norm must share the same problem',
        },
    },
    'protocol': {'required': ['population', 'method', 'comparison', 'uncertainty']},
    'indicator': {'required': ['metric', 'unit'], 'meaning': 'Prespecification metric/unit grounded by linked evidence'},
    'criterion': {
        'required': ['metric', 'threshold', 'reject'],
        'decisive_threshold': {'fields': ['operator', 'statistic', 'value'],
                              'operators': ['>=', '<='], 'statistics': ['estimate', 'lower_ci', 'upper_ci']},
        'decisive_reject_test': 'Structured preregistered reject_test is needed for an incumplido assessment',
    },
    'test_draft': {'required': ['argv'], 'argv': 'Explicit absolute executable vector with real delivery tests',
                   'forbidden_author_results': ['passed', 'receipt', 'test_job_ref']},
    'baseline_result': {'origins': ['field', 'simulation', 'technical', 'published'],
                        'required': ['origin', 'source', 'date']},
    'decisive_assessment': {
        'verdicts': ['cumplido', 'incumplido'],
        'ancestry': 'Exactly one criterion, one baseline and one result for each decisive assessment',
        'result_test': 'Current actually passed test directly linked by result; test refers criterion and implementing requirement',
        'effect_fields': ['metric', 'unit', 'estimate', 'interval'],
        'baseline_fields': ['metric', 'unit', 'value'],
        'numeric_rule': 'Effect estimate and finite two-sided interval are supported by actual measurements; metric/unit agree',
        'uncertainty': 'no_demostrado when support is missing; never invent zero baseline, precision, field benefit or success',
    },
}

PHASE_GUIDANCE = {
    'frame': 'Problem identifies operational need, actor identifies affected/delegated actor, boundary limits scope and observation.',
    'critique': 'Norm traces problem and actor. Distinct rival frame_options and a discussed assumption/concept are substantive, not renamings.',
    'study': 'Question traces problem; hypothesis traces question; protocol traces both. Indicator metric/unit traces approved norm, problem and protocol-grounded evidence. '
             'Documentary or supplied observed evidence may accompany study; preserve actual source/date/locator and measured population, no inferred benefit.',
    'observe': 'Evidence traces protocol/hypothesis/question/problem and uses exact data field names in artifact-data-contract.json. '
               'Inference traces evidence and protocol for the same problem. No invented numeric measurements.',
    'explain': 'Synthesis traces evidence and inference, separates findings/assumptions. Uncertainty traces synthesis and bounds conclusions.',
    'compare': 'Two substantively different options trace synthesis/norm; comparison directly references both; risk references options. '
               'Include a feasible alternative without new software. Do not infer superiority before measurement.',
    'specify': 'Decision traces comparison/norm/evidence. Requirements and criteria trace problem/norm/evidence/protocol/decision. '
               'Each criterion links a requirement and same-metric indicator. Criteria precede all outcome measurements.',
    'build': 'Implementation traces requirements; test traces criterion AND current implementation. Only build supplies program/test/README files. '
             'Absolute Python executable /opt/specorganon/venv/bin/python; delivery /input/delivery. No profiles/network/mutable inputs. '
             'Follow build-stage.json; never supply passed/receipt/test_job_ref.',
    'validate': 'Baseline/result have actual supplied values and scope. Assessment traces result,baseline,criterion,risk; declare uncertainty, adverse_effects and cost '
                '(unknown when unobserved). A decisive assessment follows artifact-data-contract.json and supplied actually measured test records. '
                'No field efficacy or comparative superiority from a local technical contract pass.',
}


def phase_guidance(phase):
    if not isinstance(phase, str) or phase not in PHASE_GUIDANCE:
        raise ValueError('unknown phase for artifact guidance')
    return ('All puts use {op:"put",id,kind,text,refs:[existing IDs],data:{...}}. '
            'References include earlier explicit puts and their resulting versions; reconsider stale ancestors before descendants. '
            + PHASE_GUIDANCE[phase])


def data_contract():
    return copy.deepcopy(DATA_CONTRACT)


def _encoded(value):
    return canonical(value)


def reference_maintenance(state, *, max_bytes=4096):
    """Explain version maintenance without mutating state or choosing new content.

    Full dependency maps are already in state.json. If details exceed the fixed
    hint ceiling, publish explicit summary counts/locators instead of a partial
    list pretending to be complete. The original state is never shortened.
    """
    if type(max_bytes) is not int or max_bytes < 512:
        raise ValueError('reference hint ceiling must be an integer >=512')
    if not isinstance(state, dict) or not isinstance(state.get('items'), dict):
        raise ValueError('reference guidance requires authoritative item mapping')
    items = state['items']
    for identity, item in items.items():
        if (not isinstance(identity, str) or not isinstance(item, dict)
                or not isinstance(item.get('deps'), dict)
                or type(item.get('version')) is not int or item['version'] < 1
                or type(item.get('stale')) is not bool
                or not isinstance(item.get('issues'), list)
                or any(not isinstance(issue, str) for issue in item['issues'])
                or any(not isinstance(dep, str) or type(version) is not int or version < 1
                       for dep, version in item['deps'].items())):
            raise ValueError('reference guidance requires validated item fields')
    dependents = {identity: [] for identity in items}
    indegree = {identity: 0 for identity in items}
    mismatches = []
    missing = set()
    for identity in sorted(items):
        for dependency, used in sorted(items[identity]['deps'].items()):
            current = items[dependency]['version'] if dependency in items else None
            if current != used: mismatches.append([identity, dependency, used, current])
            if dependency not in items: missing.add(identity)
            if dependency in items:
                dependents[dependency].append(identity); indegree[identity] += 1
    available = sorted(identity for identity, degree in indegree.items() if degree == 0)
    order = []
    while available:
        identity = available.pop(0); order.append(identity)
        for child in sorted(dependents[identity]):
            indegree[child] -= 1
            if indegree[child] == 0: available.append(child)
        available.sort()
    ordered = set(order)
    unresolved = sorted({identity for identity in items if identity not in ordered} | missing)
    stale = sorted(identity for identity, item in items.items() if item['stale'])
    invalid = sorted(identity for identity, item in items.items() if item['issues'])
    base = {'schema': 1, 'scope': 'Read-only advisory; not a repair, source authenticity check or phase acceptance',
            'authority': 'state.json/items: complete text, data, deps, versions, stale and issues',
            'instructions': 'For every changed upstream item, reconsider all descendants using complete deps. '
                            'Explicitly put justified corrections in dependency order. Updating a leaf cannot clear an older ancestor. '
                            'Do not refresh versions without semantic reconsideration; never fabricate evidence or approvals.',
            'counts': {'items': len(items), 'direct_version_mismatches': len(mismatches),
                       'stale_items': len(stale), 'invalid_items': len(invalid),
                       'unresolved_dependency_nodes': len(unresolved)}}
    detail = {**base, 'mode': 'complete_hint', 'direct_version_mismatches': mismatches,
              'stale_item_ids': stale, 'invalid_item_ids': invalid,
              'dependency_order': order if not unresolved else None,
              'unresolved_dependency_node_ids': unresolved}
    if len(_encoded(detail)) <= max_bytes: return detail
    summary = {**base, 'mode': 'summary_only', 'details_omitted': True, 'truncated': True,
               'details_locator': 'state.json/items/*/deps; compare each recorded version with state.json/items/<dep>/version',
               'order_locator': 'Derive dependency order from the complete state.json/items graph; a cycle has no total order'}
    if len(_encoded(summary)) > max_bytes:
        # Explicitly preserve the ceiling even for caller-supplied small limits.
        summary = {'schema': 1, 'mode': 'summary_only', 'details_omitted': True, 'truncated': True,
                   'counts': base['counts'], 'details_locator': 'state.json/items',
                   'scope': 'Read-only advisory; derive full version/cycle details from authoritative state'}
    return summary
