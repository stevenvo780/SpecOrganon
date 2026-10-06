"""Autonomous N wire policy and shared resource accounting, not a controller.

The staged v1 driver does not consume this module. No dispatch, file mutation,
methodological acceptance or experimental admission is performed here. Charging
belongs in a durable reservation BEFORE author/reviewer transport is called;
decoding a returned response cannot refund its slot.
"""
from __future__ import annotations

import copy

from .ledger import strict_json_loads
from .neutral_author import neutral_author_content
from .role_jobs import canonical


NEXT_DOCUMENT = 'controller-next.json'
ACTIONS = frozenset({'continue', 'review', 'measure', 'audit'})
GLOBAL_ROLE_CEILING = 40
# Actual capacity is 5 authors + 4 reviewers; the shared nominal ceiling does
# not grant 31 additional roles when those pools have already been exhausted.
CAPS = {'authors': 5, 'reviewers': 4, 'roles': 9, 'test_runs': 2}


def counters():
    return {'authors': 0, 'reviewers': 0, 'roles': 0, 'test_runs': 0}


def _counts(value):
    if (type(value) is not dict or set(value) != set(CAPS)
            or any(type(v) is not int or not 0 <= v <= CAPS[k] for k, v in value.items())
            or value['roles'] != value['authors'] + value['reviewers']):
        raise ValueError('autonomous role counters are inconsistent')
    return copy.deepcopy(value)


def reserve(value, kind):
    """Return charged counters; callers must persist them before dispatch.

    Test execution is charged independently of text roles. Feedback and common
    audits both use reviewer slots. No per-stage extra pool or uncharged director.
    Caller retains this reservation if transport or decoding subsequently fails.
    """
    result = _counts(value)
    if type(kind) is not str or kind not in {'author', 'review', 'measure'}:
        raise ValueError('unknown autonomous reservation kind')
    field = {'author': 'authors', 'review': 'reviewers', 'measure': 'test_runs'}[kind]
    if result[field] >= CAPS[field] or kind != 'measure' and result['roles'] >= CAPS['roles']:
        raise ValueError('autonomous resource budget exhausted')
    result[field] += 1
    if kind != 'measure':
        result['roles'] += 1
    return result


def remaining(value):
    c = _counts(value)
    return {k: CAPS[k] - c[k] for k in CAPS}


def admit_action(action, charged):
    """Check a choice BEFORE applying its patch or dispatching another operation.

    A caller supplies the already-reserved author counters. This only checks
    resource feasibility: physical package/current-receipt gates remain separate.
    The fifth author cannot spend a useless feedback turn or request a sixth author.
    Its measure route reserves enough space for the automatic common audit.
    """
    c = _counts(charged)
    if type(action) is not str or action not in ACTIONS or c['authors'] == 0:
        raise ValueError('choice requires a charged author reservation')
    if c['authors'] == CAPS['authors'] and action in {'continue', 'review'}:
        raise ValueError('last author must measure or audit without extra director')
    if action in {'review', 'audit'} and c['reviewers'] >= CAPS['reviewers']:
        raise ValueError('no reviewer slot remains for chosen action')
    if action == 'measure' and (c['test_runs'] >= CAPS['test_runs']
            or c['authors'] == CAPS['authors'] and c['reviewers'] >= CAPS['reviewers']):
        raise ValueError('chosen measure or its final audit exceeds budget')
    return action


def decode_update(value):
    """Separate an exact operational decision from authored scientific content.

    Raw input remains in the caller's closed result. Removing this document from
    a copy does not transform it into criteria, review, approval or test evidence.
    A control-only turn is valid but consumes an author reservation just like one
    producing code. Duplicate/nonfinite JSON and ambiguous delivery collisions
    cannot admit either a patch or a partial action.
    """
    packet = neutral_author_content(value)
    if NEXT_DOCUMENT in packet['files'] or NEXT_DOCUMENT not in packet['documents']:
        raise ValueError('one operational document required outside the delivery')
    raw = packet['documents'].pop(NEXT_DOCUMENT)
    if len(raw.encode('utf-8')) > 1024:
        raise ValueError('operational decision exceeds bounded size')
    choice = strict_json_loads(raw)
    if (type(choice) is not dict or set(choice) != {'action'}
            or type(choice['action']) is not str or choice['action'] not in ACTIONS):
        raise ValueError('exact autonomous action required')
    return {'action': choice['action'], 'files': packet['files'],
            'documents': packet['documents'], 'reason': packet['reason'],
            'control_raw': raw}


def following_measure(value, *, passed):
    """Specify the exhausted-author route without another free director turn.

    Preconditions, current immutable battery and closed execution proof belong
    to the future controller, not to this function. Boolean passed here is an
    input to policy, never an authenticated measurement or completion judgment.
    """
    c = _counts(value)
    if type(passed) is not bool or c['test_runs'] == 0:
        raise ValueError('charged measurement and exact outcome required')
    if c['authors'] < CAPS['authors']:
        return 'author'
    return 'audit' if passed and c['reviewers'] < CAPS['reviewers'] else 'failed'


def policy():
    result = {'definition': 'autonomous-text-N-development-v2', 'caps': copy.deepcopy(CAPS),
              'global_role_ceiling': GLOBAL_ROLE_CEILING,
              'operational_document': NEXT_DOCUMENT, 'actions': sorted(ACTIONS),
              'implemented_controller': False, 'experimental_admission': False,
              'competence_established': False, 'superiority_achieved': False}
    canonical(result)
    return result
