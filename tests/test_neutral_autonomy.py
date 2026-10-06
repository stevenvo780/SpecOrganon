"""Durable autonomous controller fixtures; never native competence evidence."""
import copy

import pytest

from specorganon.docker_roles import ClosedNativeExecutionError
from specorganon.free_control_policy import NEXT_DOCUMENT
from specorganon.ledger import strict_json_loads
from specorganon.neutral_autonomy import AutonomousNeutralController, BATTERY_DOCUMENT
from specorganon.neutral_controller import NeutralController, NeutralControllerError
from specorganon.request_content import decode_content
from specorganon.request_tree import decode_tree
from specorganon.role_jobs import _json, _write, canonical, digest
from test_closed_execution_failure import negative_fixture
from test_neutral_controller import ARGV, POLICY, PROGRAM, TEST, FixtureTransport


def choice(action, *, files=None, docs=None, battery=None):
    documents = {NEXT_DOCUMENT: canonical({'action': action}).decode(), **(docs or {})}
    if battery is not None: documents[BATTERY_DOCUMENT] = canonical(battery).decode()
    return {'schema': 1, 'files': files or {}, 'documents': documents, 'reason': 'Synthetic autonomous choice'}


PACKAGE = {'program.py': PROGRAM, 'README.md': 'Fixture criterion: result seven, not semantic validation.',
           'test_program.py': TEST, 'fixture.json': '{ "value": 7 }\n'}
PARTITION = {'test_files': ['test_program.py', 'fixture.json'], 'mutable_files': ['program.py', 'README.md']}


class FreeFixture(FixtureTransport):
    def __init__(self, root, responses=None, **options):
        super().__init__(root, **options)
        self.free_responses = copy.deepcopy(responses or [choice('measure', files=PACKAGE, battery=PARTITION), choice('audit')])

    def call(self, job, role, request):
        stage = request['documents']['stage.txt']
        if stage in {'free', 'feedback'}:
            assert _json(self.root.parent / 'reservations' / (job.split('-')[1] + '.json'))['job_id'] == job
            if stage == 'free': value = self.free_responses.pop(0)
            else: value = {'schema': 1, 'verdict': 'reject', 'reason': 'Synthetic useful feedback; no acceptance gate',
                          'findings': [{'problem': 'An actual design defect is not inferred by this fixture'}], 'tests_executed': False}
            self.responses[stage] = value
        return super().call(job, role, request)


def controller(root, responses=None, **options):
    t = None
    def factory(path):
        nonlocal t
        if t is None: t = FreeFixture(path, responses=responses, **options)
        return t
    return AutonomousNeutralController(root, attempt_id='autonomy-fixture-01', method='N',
        contract='Public fixture only: result seven.', mandate='No external effects.',
        argv=ARGV, test_file='test_program.py', transport_policy=POLICY,
        transport_factory=factory, fixture_mode=True)


def last_state(c):
    return _json(sorted((c.root / 'generations').iterdir())[-1])['state']


def test_code_and_battery_together_without_prior_notes_then_current_audit(tmp_path):
    c = controller(tmp_path / 'run'); report = c.run()
    assert report['status'] == 'review_ready' and report['common_review_ready']
    assert report['counts'] == {'authors': 2, 'reviewers': 1, 'roles': 3, 'test_runs': 1}
    assert report['fixture_mode'] and not report['native_ready'] and report['common_complete'] is None
    state = last_state(c)
    assert state['original_criteria']['documents'] == {} # No invented notes or semantic G acceptance.
    assert state['original_criteria']['files'] == PACKAGE
    assert not set(state['documents']) & {NEXT_DOCUMENT, BATTERY_DOCUMENT}
    assert state['original_tests'] == {n: PACKAGE[n] for n in PARTITION['test_files']}
    assert report == c.step()


def test_two_feedbacks_on_code_without_SDD_artifacts_do_not_gate_or_reset_slots(tmp_path):
    c = controller(tmp_path / 'run', [choice('review', files={'program.py': PROGRAM}), choice('review'),
        choice('measure', files=PACKAGE, battery=PARTITION), choice('audit')])
    report = c.run()
    assert report['status'] == 'review_ready' and report['counts']['reviewers'] == 3
    assert report['counts']['authors'] == 4 and report['counts']['roles'] == 7
    assert 'SPEC.md' not in last_state(c)['documents']
    assert [r['action'] for r in last_state(c)['control_history']] == ['review', 'review', 'measure', 'audit']


@pytest.mark.parametrize('action', ['continue', 'review'])
def test_fifth_author_invalid_choice_consumes_slot_without_feedback_or_sixth_author(tmp_path, action):
    c = controller(tmp_path / 'run', [choice('continue')] * 4 + [choice(action)])
    report = c.run()
    assert report['status'] == 'failed' and report['counts']['authors'] == 5
    assert report['counts']['reviewers'] == report['counts']['test_runs'] == 0
    assert len(c.transport.dispatched) == 5 and len(list((c.root / 'reservations').iterdir())) == 5
    assert 'last author' in report['failure']


@pytest.mark.parametrize('passed', [True, False])
def test_fifth_author_measure_chains_final_audit_or_failure_without_director(tmp_path, passed):
    c = controller(tmp_path / 'run', [choice('continue')] * 4 + [choice('measure', files=PACKAGE, battery=PARTITION)],
                   measurements=[passed])
    report = c.run()
    assert report['counts']['authors'] == 5 and report['counts']['test_runs'] == 1
    assert report['counts']['reviewers'] == (1 if passed else 0)
    assert report['status'] == ('review_ready' if passed else 'failed')


@pytest.mark.parametrize('mutation', ['battery', 'fixture', 'shadow', 'partition', 'reserved-file'])
def test_immutable_partition_and_battery_failure_preserves_original_package_and_charges(tmp_path, mutation):
    patch = choice('continue')
    if mutation == 'battery': patch['files'] = {'test_program.py': 'print("PASS")'}
    elif mutation == 'fixture': patch['files'] = {'fixture.json': '{"value":0}'}
    elif mutation == 'shadow': patch['files'] = {'unittest.py': 'pass'}
    elif mutation == 'reserved-file': patch['files'] = {BATTERY_DOCUMENT: '{}'}
    else: patch = choice('measure', battery={**PARTITION, 'test_files': ['test_program.py'],
                                            'mutable_files': ['program.py', 'README.md', 'fixture.json']})
    c = controller(tmp_path / 'run', [choice('measure', files=PACKAGE, battery=PARTITION), patch, choice('audit')])
    report = c.run()
    assert report['status'] == 'review_ready' and report['counts']['authors'] == 3
    assert report['counts']['test_runs'] == 1
    s = last_state(c); assert s['files'] == PACKAGE and s['battery_partition']['test_files'] == sorted(PARTITION['test_files'])
    assert s['control_history'][1]['admitted'] is False


def test_document_change_cannot_use_old_measure_but_idempotent_patch_preserves_receipt(tmp_path):
    invalid = choice('audit', files={'README.md': 'Changed'})
    c = controller(tmp_path / 'invalid', [choice('measure', files=PACKAGE, battery=PARTITION), invalid, choice('audit')])
    assert c.run()['status'] == 'review_ready'
    assert last_state(c)['files']['README.md'] == PACKAGE['README.md']
    assert last_state(c)['control_history'][1]['admitted'] is False
    c = controller(tmp_path / 'same', [choice('measure', files=PACKAGE, battery=PARTITION),
                                     choice('audit', files={'README.md': PACKAGE['README.md']})])
    assert c.run()['counts']['test_runs'] == 1


def test_repair_program_after_actual_failed_outcome_remeasures_same_sealed_tests(tmp_path):
    broken = {**PACKAGE, 'program.py': PROGRAM.replace('return 7', 'return 0')}
    c = controller(tmp_path / 'run', [choice('measure', files=broken, battery=PARTITION),
        choice('measure', files={'program.py': PROGRAM}), choice('audit')], measurements=[False, True])
    report = c.run()
    assert report['status'] == 'review_ready' and report['counts']['test_runs'] == 2
    measurements = [_json(p) for p in (c.root / 'reservations').iterdir() if _json(p)['stage'] == 'measure']
    assert len(measurements) == 2
    for name in PARTITION['test_files']:
        assert measurements[0]['request']['files'][name] == measurements[1]['request']['files'][name]


@pytest.mark.parametrize('declaration', [
    None, {'test_files': ['test_program.py'], 'mutable_files': ['program.py', 'README.md']},
    {'test_files': ['test_program.py', 'fixture.json'], 'mutable_files': ['program.py', 'fixture.json', 'README.md']},
    {'test_files': ['fixture.json'], 'mutable_files': ['program.py', 'README.md', 'test_program.py']},
    {'test_files': ['test_program.py', 'test_program.py', 'fixture.json'], 'mutable_files': ['program.py', 'README.md']},
])
def test_first_partition_invalid_never_partially_admits_code_or_measures(tmp_path, declaration):
    c = controller(tmp_path / 'run', [choice('measure', files=PACKAGE, battery=declaration)] * 5)
    report = c.run()
    assert report['status'] == 'failed' and report['counts']['authors'] == 5
    assert report['counts']['test_runs'] == 0 and last_state(c)['files'] == {}


def test_closed_role_crash_reconstruction_uses_same_reservation_without_second_dispatch(tmp_path, monkeypatch):
    c = controller(tmp_path / 'run'); original = c._apply
    monkeypatch.setattr(c, '_apply', lambda *a: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt): c.step()
    assert len(c.transport.dispatched) == 1
    monkeypatch.setattr(c, '_apply', original)
    monkeypatch.setattr(c.transport, 'call', lambda *a: pytest.fail('must not dispatch twice'))
    assert c.step()['stage'] == 'measure' and len(c.transport.dispatched) == 1


def test_closed_measure_crash_preserves_actual_outcome_and_no_second_measure(tmp_path, monkeypatch):
    c = controller(tmp_path / 'run'); c.step(); original = c._apply
    def crash(state, reservation, result, past):
        if reservation['stage'] == 'measure': raise KeyboardInterrupt()
        return original(state, reservation, result, past)
    monkeypatch.setattr(c, '_apply', crash)
    with pytest.raises(KeyboardInterrupt): c.step()
    assert (c.root / 'results/0002.json').exists() # Measurement closed before crash.
    calls = len(c.transport.dispatched)
    monkeypatch.setattr(c, '_apply', original)
    monkeypatch.setattr(c.transport, 'measure', lambda *a: pytest.fail('must recover closed measurement'))
    report = c.step(); assert report['counts']['test_runs'] == 1 and len(c.transport.dispatched) == calls


def test_rebound_generation_and_decision_tampering_cannot_reset_history_or_budget(tmp_path):
    c = controller(tmp_path / 'run'); c.step(); path = c.root / 'generations/0001.json'; value = _json(path)
    value['state']['counts']['authors'] = 0; _write(path, value)
    with pytest.raises(NeutralControllerError): c.step()


def test_policy_and_original_sources_cannot_silently_change_on_resume(tmp_path):
    c = controller(tmp_path / 'run'); c.step(); path = c.root / 'initial.json'; value = _json(path)
    value['policy']['effective_caps']['authors'] = 99; _write(path, value)
    with pytest.raises(NeutralControllerError): controller(c.root)


def test_repetitive_context_guarantees_compact_tree_winner_and_lossless_roundtrip(tmp_path):
    # Mechanical test: 30 modules with repetitive function template (<256 bytes)
    # guaranteeing that compact_tree compresses while compact_content does not,
    # so tree-refs-v1 wins in super()._request and in AutonomousNeutralController._request.
    snippet = '# Standard repetitive module template for mechanical testing\ndef calculate():\n    return 100\n'
    files = {f'mod_{i:02d}.py': snippet for i in range(30)}
    c = controller(tmp_path / 'run', [choice('continue', files=files), choice('continue')])
    c.step()  # step 1: free, author introduces files
    state, past, prev, pending = c._load()
    assert state['files'] == files

    # Verify NeutralController._request produces tree-refs-v1
    adapted = copy.deepcopy(state)
    adapted['stage'] = 'program'
    base_req, _ = NeutralController._request(c, adapted, past, 2)
    base_doc = strict_json_loads(base_req['documents']['package-context.json'])
    assert base_doc['encoding'] == 'tree-refs-v1'

    # Verify AutonomousNeutralController._request correctly decodes tree-refs-v1,
    # adds controller_context, and re-serializes losslessly.
    req, _ = c._request(state, past, 2)
    final_doc = strict_json_loads(req['documents']['package-context.json'])
    assert final_doc['encoding'] == 'tree-refs-v1'

    decoded = decode_tree(final_doc['context'])
    assert set(decoded.keys()) == {'files', 'documents', 'history', 'controller_context'}
    assert decoded['files'] == files
    assert decoded['documents'] == {}
    assert decoded['controller_context'] == {'control_history': state['control_history']}
    assert len(decoded['history']) == 1
    assert decoded['history'][0]['stage'] == 'free'
    assert decoded['history'][0]['capture']['files'] == files

    # Exact canonical roundtrip check
    expected = {
        'files': files,
        'documents': {},
        'history': [{'stage': i['reservation']['stage'], 'job_id': i['reservation']['job_id'],
                     'result': i['result'],
                     'capture': {'files': i['state']['files'], 'documents': i['state']['documents']}}
                    for i in past],
        'controller_context': {'control_history': state['control_history']},
    }
    assert canonical(decoded) == canonical(expected)


def test_repeated_content_guarantees_compact_content_winner_and_lossless_roundtrip(tmp_path):
    # Mechanical test: 100 unique small files + 2 files with 4000-char string,
    # where compact_content compresses with less overhead than compact_tree DAG,
    # guaranteeing content-refs-v1 wins.
    rep = 'A' * 4000
    files = {f'file_{i:03d}.txt': f'content_data_unique_{i:04d}' for i in range(100)}
    files['r1.txt'] = rep
    files['r2.txt'] = rep
    c = controller(tmp_path / 'run')
    state = c._initial_state()
    state['files'] = files
    state['control_history'] = [{'job_id': 'job-01', 'admitted': True, 'action': 'continue'}]

    # Base request produces content-refs-v1
    adapted = copy.deepcopy(state)
    adapted['stage'] = 'program'
    base_req, _ = NeutralController._request(c, adapted, [], 1)
    base_doc = strict_json_loads(base_req['documents']['package-context.json'])
    assert base_doc['encoding'] == 'content-refs-v1'

    # AutonomousNeutralController._request decodes content-refs-v1 and re-serializes
    req, _ = c._request(state, [], 1)
    final_doc = strict_json_loads(req['documents']['package-context.json'])
    assert final_doc['encoding'] == 'content-refs-v1'

    decoded = decode_content(final_doc['context'])
    assert set(decoded.keys()) == {'files', 'documents', 'history', 'controller_context'}
    assert decoded['files'] == files
    assert decoded['documents'] == {}
    assert decoded['history'] == []
    assert decoded['controller_context'] == {'control_history': state['control_history']}

    expected = {
        'files': files,
        'documents': {},
        'history': [],
        'controller_context': {'control_history': state['control_history']},
    }
    assert canonical(decoded) == canonical(expected)


def test_audit_stage_evidence_context_roundtrip_with_controller_context(tmp_path):
    # Autonomous package through measure to audit
    c = controller(tmp_path / 'run')
    c.step()  # free -> measure
    c.step()  # measure -> free
    c.step()  # free -> audit
    state, past, prev, pending = c._load()
    assert state['stage'] == 'audit'
    req, _ = c._request(state, past, 4)
    doc = strict_json_loads(req['documents']['evidence-context.json'])

    # Decode evidence-context using either tree-refs-v1 or content-refs-v1 or plain
    if doc['encoding'] == 'tree-refs-v1':
        decoded = decode_tree(doc['context'])
    elif doc['encoding'] == 'content-refs-v1':
        decoded = decode_content(doc['context'])
    else:
        decoded = doc['context']

    assert set(decoded.keys()) == {'locator_index', 'content_by_sha256', 'controller_context'}
    assert 'battery_partition' in decoded['controller_context']
    assert decoded['controller_context']['battery_partition']['test_files'] == sorted(PARTITION['test_files'])
    assert decoded['controller_context']['prior_measurement_binding']['passed'] is True
    assert decoded['controller_context']['prior_measurement_binding']['job_id'] == state['measure_job']
    assert isinstance(decoded['locator_index'], dict)
    assert isinstance(decoded['content_by_sha256'], dict)
    for sha, entry in decoded['content_by_sha256'].items():
        assert entry['encoding'] in ('canonical-json', 'utf8-text')
        assert 'value' in entry


@pytest.mark.parametrize('stage_under_test', ['free', 'feedback'])
def test_closed_execution_failure_crash_recovery_and_replay_in_free_and_feedback(tmp_path, monkeypatch, stage_under_test):
    import specorganon.neutral_controller as module
    if stage_under_test == 'free':
        c = controller(tmp_path / 'run')
        seq = 1
        expected_roles = 1
        expected_authors = 1
        expected_reviewers = 0
    else:
        c = controller(tmp_path / 'run', [choice('review', files={'program.py': PROGRAM})])
        rep1 = c.step()
        assert rep1['stage'] == 'feedback'
        seq = 2
        expected_roles = 2
        expected_authors = 1
        expected_reviewers = 1

    t = c._get_transport()
    failed_call, original_call, dispatched, proofs = negative_fixture(t)
    verified = []
    original_verify = t.verify_execution_failure
    def verify(proof, job, role, request):
        verified.append(job)
        return original_verify(proof, job, role, request)
    t.verify_execution_failure = verify
    t.call = failed_call
    write = module._write
    def crash(path, value, **kwargs):
        if path == c.root / f'results/{seq:04d}.json':
            raise KeyboardInterrupt('cut after failure before capture')
        return write(path, value, **kwargs)
    monkeypatch.setattr(module, '_write', crash)
    with pytest.raises(KeyboardInterrupt):
        c.step()
    assert len(dispatched) == 1
    monkeypatch.setattr(module, '_write', write)

    t.call = lambda *a: pytest.fail('must recover exact failed journal without second call')
    report = c.step()
    assert report['status'] == 'failed'
    assert report['counts']['roles'] == expected_roles
    assert report['counts']['authors'] == expected_authors
    assert report['counts']['reviewers'] == expected_reviewers
    assert report['failure'] == 'verified original stopped native execution failed; no replacement'
    assert (c.root / f'results/{seq:04d}.json').exists()
    assert _json(c.root / f'results/{seq:04d}.json')['kind'] == 'execution_error'
    before = len(verified)
    assert c.step() == report
    assert len(dispatched) == 1 and len(verified) > before
    assert set(verified) == set(dispatched)
    # The terminal read must revalidate the same stored original proof.
    original_verify_before_mutation = t.verify_execution_failure
    t.verify_execution_failure = lambda *args: False
    with pytest.raises(NeutralControllerError): c.step()
    t.verify_execution_failure = original_verify_before_mutation


def test_altered_negative_proof_rejected_when_validator_false_or_raises(tmp_path):
    # Subtest 1: validator returns False -> rejected
    c1 = controller(tmp_path / 'false_val')
    t1 = c1._get_transport()
    failed_call1, _, _, _ = negative_fixture(t1)
    t1.call = failed_call1
    t1.verify_execution_failure = lambda proof, job, role, req: False
    rep1 = c1.step()
    assert rep1['status'] == 'failed'
    assert rep1['failure'] != 'verified original stopped native execution failed; no replacement'
    assert 'original stopped native execution failure proof required' in rep1['failure']

    # Subtest 2: validator raises ValueError -> rejected
    c2 = controller(tmp_path / 'raising_val')
    t2 = c2._get_transport()
    failed_call2, _, _, _ = negative_fixture(t2)
    t2.call = failed_call2
    def raising_verify(proof, job, role, req):
        raise ValueError('tampered negative proof')
    t2.verify_execution_failure = raising_verify
    rep2 = c2.step()
    assert rep2['status'] == 'failed'
    assert rep2['failure'] != 'verified original stopped native execution failed; no replacement'
    assert 'tampered negative proof' in rep2['failure']

    # Subtest 3: proof data altered before error raised -> rejected
    c3 = controller(tmp_path / 'altered_proof')
    t3 = c3._get_transport()
    failed_call3, _, _, _ = negative_fixture(t3)
    def tampered_call(job, role, request):
        try:
            failed_call3(job, role, request)
        except ClosedNativeExecutionError as exc:
            exc.proof['acceptance'] = True
            raise
    t3.call = tampered_call
    rep3 = c3.step()
    assert rep3['status'] == 'failed'
    assert rep3['failure'] != 'verified original stopped native execution failed; no replacement'
    assert 'original stopped native execution failure proof required' in rep3['failure']

