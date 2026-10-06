"""Lossless shared transport checks; fixtures never establish native competence."""
import copy
import json

import pytest

from specorganon.neutral_controller import LIMITS, NeutralController, NeutralControllerError
from specorganon.neutral_autonomy import AutonomousNeutralController
from specorganon.request_content import decode_content
from specorganon.request_tree import decode_tree
from specorganon.role_jobs import canonical
from test_neutral_controller import controller


def restore(text):
    document = json.loads(text)
    assert document['format'] == 'lossless-package-context-v1'
    if document['encoding'] == 'tree-refs-v1': return decode_tree(document['context'])
    return (decode_content(document['context']) if document['encoding'] == 'content-refs-v1'
            else document['context'])


@pytest.mark.parametrize('method', ['N', 'S'])
def test_request_preserves_all_historical_packets_and_captures_below_same_cap(tmp_path, method):
    c = controller(tmp_path / method, method)
    state = c._initial_state()
    state['stage'] = 'program'
    text = 'unicode Ω\\\nquote" actual program criterion and feedback\n' * 190
    state['files'] = {'program.py': text}
    state['documents'] = {'arbitrary-original-criteria.txt': text}
    packet = {'schema': 1, 'value': {'reason': text, 'result': {'files': state['files']}},
              'kind': 'role', 'receipt_metadata': {'observed': False, 'nullable': None}}
    past = [{'reservation': {'stage': 'plan', 'job_id': f'job-{n}'},
             'result': copy.deepcopy(packet), 'state': copy.deepcopy(state)} for n in range(4)]
    previous = canonical([state, past])
    req, snapshot = c._request(state, past, 5)
    restored = restore(req['documents']['package-context.json'])
    expected = {'files': state['files'], 'documents': state['documents'],
                'history': [{'stage': p['reservation']['stage'], 'job_id': p['reservation']['job_id'],
                             'result': p['result'], 'capture': {'files': p['state']['files'],
                                                              'documents': p['state']['documents']}}
                            for p in past]}
    assert len(canonical(expected)) > LIMITS['request_bytes']
    assert canonical(restored) == canonical(expected)
    assert previous == canonical([state, past])
    assert len(canonical(req)) < LIMITS['request_bytes'] == 110000
    assert snapshot is None
    assert c.policy['request_context_format'] == 'lossless-package-context-v1'


def test_large_unique_content_still_fails_exact_request_guard(tmp_path):
    c = controller(tmp_path / 'S', 'S')
    state = c._initial_state(); state['stage'] = 'program'
    state['files'] = {'program.py': 'x' * 115000}
    with pytest.raises(NeutralControllerError, match='exact canonical request exceeds budget'):
        c._request(state, [], 1)
    # Codec cannot confer additional author/test slots or enlarge limits.
    assert c.policy['limits'] == LIMITS
    assert c.policy['limits']['files_encoded_bytes'] == 20000


def test_autonomous_additions_preserve_context_and_original_finite_caps(tmp_path):
    from test_neutral_autonomy import controller as free_controller
    c = free_controller(tmp_path / 'N')
    state = c._initial_state()
    req, snapshot = c._request(state, [], 1)
    assert restore(req['documents']['package-context.json']) == {
        'files': {}, 'documents': {}, 'history': [], 'controller_context': {'control_history': []}}
    assert req['documents']['stage.txt'] == 'free'
    budget = json.loads(req['documents']['remaining-budget.json'])
    assert budget['charged']['authors'] == 1
    assert snapshot is None


def test_audit_context_restores_every_physical_locator_including_noncanonical_json(tmp_path):
    from specorganon.common_evidence import read_snapshot
    from specorganon.role_jobs import digest
    from test_neutral_controller import PROGRAM
    response = {'schema': 1, 'files': {'program.py': PROGRAM, 'README.md': 'Original documentation.' * 80},
                'documents': {'author-json.txt': '{ "criterion": true }\n'}, 'reason': 'Synthetic transport check'}
    c = controller(tmp_path / 'S', 'S', responses={'program': response})
    original = c._request
    observed = {}

    def capture(state, past, sequence):
        req, snapshot = original(state, past, sequence)
        if state['stage'] == 'audit':
            observed['context'] = restore(req['documents']['evidence-context.json'])
            observed['snapshot'] = read_snapshot(snapshot['path'], snapshot['manifest_sha256'])
        return req, snapshot

    c._request = capture
    report = c.run()
    assert report['common_review_ready'] and report['native_ready'] is False
    value = observed['context']; expected = observed['snapshot']['locators']
    assert set(value['locator_index']) == set(expected)
    encodings = set()
    for name, raw in expected.items():
        sha = value['locator_index'][name]; item = value['content_by_sha256'][sha]
        restored_raw = canonical(item['value']) if item['encoding'] == 'canonical-json' else item['value'].encode()
        assert restored_raw == raw and digest(restored_raw) == sha
        encodings.add(item['encoding'])
    assert encodings == {'canonical-json', 'utf8-text'}
    assert b'{ "criterion": true }\n' in expected.values()


def test_autonomous_control_history_preserved_with_shared_file_strings(tmp_path):
    from test_neutral_autonomy import controller as free_controller
    c = free_controller(tmp_path / 'N')
    state = c._initial_state(); state['stage'] = 'feedback'
    text = 'Actual criteria and feedback with Unicode ñ\n' * 300
    state['files'] = {'program.py': text}
    state['control_history'] = [{'job_id': 'original-job', 'admitted': True, 'reason': text}]
    req, snapshot = c._request(state, [], 1)
    context = restore(req['documents']['package-context.json'])
    assert context['files'] == state['files']
    assert context['controller_context']['control_history'] == state['control_history']
    assert len(canonical(req)) < LIMITS['request_bytes']
    assert snapshot is None
