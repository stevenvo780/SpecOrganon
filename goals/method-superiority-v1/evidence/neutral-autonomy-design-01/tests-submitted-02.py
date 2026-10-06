"""Autonomous wire/accounting negatives; no transport or efficacy evidence."""
import copy

import pytest

from specorganon.free_control_policy import (
    CAPS, NEXT_DOCUMENT, admit_action, counters, decode_update, following_measure, remaining, reserve,
)


def update(raw='{"action":"measure"}', **changes):
    value = {'schema': 1, 'files': {'program.py': 'print(7)\n'},
             'documents': {NEXT_DOCUMENT: raw}, 'reason': 'Choice after code, before notes'}
    value.update(changes)
    return value


def test_code_before_notes_and_control_only_turn_keep_transport_bytes_and_input():
    packet = update(); captured = copy.deepcopy(packet)
    v = decode_update(packet)
    assert v['files'] == {'program.py': 'print(7)\n'} and v['documents'] == {}
    assert packet == captured and v['control_raw'] == captured['documents'][NEXT_DOCUMENT]
    only = decode_update(update(files={}))
    assert only['action'] == 'measure' and not only['files'] and not only['documents']


@pytest.mark.parametrize('raw', [
    '{"action":"measure","action":"audit"}', '{"action":"measure","cost":NaN}',
    '{"action":true}', '{"action":"admit"}', '{"action":"review","free":true}',
    '["measure"]', '{"action":"measure"} trailing', ' ' * 1025 + '{"action":"review"}',
])
def test_invalid_or_ambiguous_control_never_admits_a_partial_patch(raw):
    with pytest.raises(ValueError):
        decode_update(update(raw))


def test_reserved_operational_delivery_collision_and_missing_choice_are_rejected():
    with pytest.raises(ValueError):
        decode_update(update(files={NEXT_DOCUMENT: '{}', 'program.py': 'pass'}))
    with pytest.raises(ValueError):
        decode_update(update(documents={'notes': 'Substantive criteria'}))


def test_invalid_closed_author_turn_is_still_charged_without_refund_or_extra_director():
    charged = reserve(counters(), 'author')
    with pytest.raises(ValueError):
        decode_update(update('{"action":"measure","action":"audit"}'))
    assert charged['authors'] == charged['roles'] == 1
    for _ in range(4): charged = reserve(charged, 'author')
    before = copy.deepcopy(charged)
    with pytest.raises(ValueError): reserve(charged, 'author')
    assert charged == before and remaining(charged)['authors'] == 0


def test_feedback_and_final_audits_share_four_slots_and_executions_have_no_role_slot():
    c = counters()
    for _ in range(4): c = reserve(c, 'review')
    assert c['roles'] == c['reviewers'] == 4
    with pytest.raises(ValueError): reserve(c, 'review')
    for _ in range(2): c = reserve(c, 'measure')
    assert c['roles'] == 4 and c['test_runs'] == 2
    with pytest.raises(ValueError): reserve(c, 'measure')


def test_last_author_can_measure_then_audit_without_sixth_author_and_no_false_success():
    c = counters()
    for _ in range(5): c = reserve(c, 'author')
    c = reserve(c, 'measure')
    assert following_measure(c, passed=True) == 'audit'
    assert following_measure(c, passed=False) == 'failed'
    for _ in range(4): c = reserve(c, 'review')
    assert following_measure(c, passed=True) == 'failed'
    assert c['authors'] == CAPS['authors'] and c['roles'] == 9
    assert remaining(c)['roles'] == 0


@pytest.mark.parametrize('action', ['continue', 'review'])
def test_fifth_author_cannot_dispatch_feedback_or_a_sixth_director(action):
    c = counters()
    for _ in range(5): c = reserve(c, 'author')
    packet = decode_update(update('{"action":"' + action + '"}'))
    before = copy.deepcopy(c)
    with pytest.raises(ValueError): admit_action(packet['action'], c)
    assert c == before and c['authors'] == 5


def test_last_measure_requires_both_a_measure_and_a_remaining_audit_slot():
    c = counters()
    for _ in range(5): c = reserve(c, 'author')
    assert admit_action('measure', c) == 'measure'
    for _ in range(4): c = reserve(c, 'review')
    with pytest.raises(ValueError): admit_action('measure', c)
    with pytest.raises(ValueError): admit_action('audit', c)


def test_choice_without_an_author_reservation_cannot_use_any_resource():
    for action in ['continue', 'review', 'measure', 'audit']:
        with pytest.raises(ValueError): admit_action(action, counters())


@pytest.mark.parametrize('field,raw', [('authors', True), ('roles', 1), ('test_runs', -1), ('reviewers', 5)])
def test_forged_counters_or_boolean_integer_are_rejected_before_reservation(field, raw):
    c = counters(); c[field] = raw
    with pytest.raises(ValueError): reserve(c, 'author')
