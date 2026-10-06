"""Orchestration/aggregate adversaries; these synthetic checks are not native runs."""
import importlib.util
from pathlib import Path

import pytest

from scripts import native_reliability as nr
from specorganon.role_jobs import _write, digest, _read


def checker():
    path = Path(__file__).parents[1] / 'goals/method-superiority-v1/development/check_cohort_public.py'
    spec = importlib.util.spec_from_file_location('cohort_oracle', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def fake_plan(tmp_path):
    source = tmp_path / 'source'; source.mkdir()
    names = ['scripts/native_reliability.py', 'scripts/controller_native_role.py', 'mandate',
             'pyproject.toml', 'uv.lock', 'contract', 'checker', 'catalog', 'seccomp', 'src/specorganon/engine.py']
    for name in names:
        path = source / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text('synthetic')
    r = {'schema': 1, 'classification': 'prospective public development reliability',
         'source_root': str(source), 'source_sha256': {n: digest(_read(source/n)) for n in names},
         'run_root': str(tmp_path / 'runtime'), 'fixture_mode': False, 'automatic_replacement': False,
         'max_actions_per_attempt': 60, 'author': {'provider': 'codex'}, 'reviewer': {'provider': 'gemini'},
         'mandate': 'mandate', 'public_catalog': 'catalog', 'seccomp': 'seccomp',
         'tasks': {t: {'contract': 'contract', 'checker': 'checker'} for t in ['rangeaudit','ledgerfold','topoplan']},
         'attempts': [{'id': f'attempt-{i+1:02d}', 'task': t} for i,t in enumerate(
             ['rangeaudit','ledgerfold','topoplan']*3+['rangeaudit'])]}
    p = tmp_path/'registration.json'; _write(p, r)
    return r, p, digest(_read(p))


def save_outcome(folder, result):
    if not (folder/'started.json').exists():
        _write(folder/'started.json',{'registration_sha256':result['registration_sha256'],'attempt':result['attempt']})
    nr.close_attempt(folder,result)


@pytest.mark.parametrize('fault', ['source', 'binding', 'core_binding', 'ids', 'denominator', 'retry', 'fixture', 'provider', 'path'])
def test_preregistration_drift_rejected_before_controller_or_native_call(tmp_path, fault):
    r, p, sha = fake_plan(tmp_path)
    if fault == 'source': (Path(r['source_root']) / 'checker').write_text('changed')
    elif fault == 'binding': del r['source_sha256']['mandate']
    elif fault == 'core_binding': del r['source_sha256']['src/specorganon/engine.py']
    elif fault == 'ids': r['attempts'][1]['id'] = 'attempt-01'
    elif fault == 'denominator': r['attempts'].pop()
    elif fault == 'retry': r['automatic_replacement'] = True
    elif fault == 'fixture': r['fixture_mode'] = True
    elif fault == 'provider': r['reviewer']['provider'] = 'codex'
    else: r['source_sha256']['../outside'] = digest(b'anything')
    if fault != 'source': _write(p, r); sha = digest(_read(p))
    with pytest.raises(nr.CohortError): nr.load_plan(p, sha)


def test_failed_attempt_is_terminal_and_never_dispatched_again(tmp_path, monkeypatch):
    r, p, sha = fake_plan(tmp_path); root = Path(r['run_root']); root.mkdir()
    a = r['attempts'][0]; folder = root/a['id']; folder.mkdir()
    failure = {'schema': 1, 'attempt': a, 'registration_sha256': sha, 'status': 'failed',
               'generation_complete': False, 'independent_public_checks_passed': False,
               'reason': 'Synthetic uncertain native handle'}
    save_outcome(folder, failure)
    monkeypatch.setattr(nr, 'controller', lambda *a: pytest.fail('closed attempt dispatched'))
    assert nr.run_attempt(p, sha, r, a, root) == failure
    summary = nr.report(r, sha, root)
    assert summary['closed_attempts'] == 1 and summary['planned_attempts'] == 10
    assert summary['generation_rate_planned_denominator'] == 0
    assert summary['development_reliability_observed_met'] is False
    assert summary['rows'][1]['status'] == 'not_started'


def test_nine_passes_do_not_meet_rate_until_tenth_attempt_is_closed(tmp_path):
    r, _, sha = fake_plan(tmp_path); root = Path(r['run_root']); root.mkdir()
    for a in r['attempts'][:9]:
        folder = root/a['id']; folder.mkdir(); save_outcome(folder,
          {'schema': 1,'attempt':a,'registration_sha256':sha,'status':'complete',
           'generation_complete':True,'independent_public_checks_passed':False})
    s = nr.report(r, sha, root, verify=False)
    assert s['generation_complete'] == 9 and s['independent_public_checks_passed'] == 0
    assert not s['development_reliability_observed_met'] and s['generation_rate_wilson_95_descriptive'] is None
    a=r['attempts'][9]; folder=root/a['id'];folder.mkdir();save_outcome(folder,
      {'attempt':a,'registration_sha256':sha,'status':'failed','generation_complete':False,
       'independent_public_checks_passed':False})
    s=nr.report(r,sha,root,verify=False)
    assert s['development_reliability_observed_met'] and s['generation_rate_planned_denominator']==.9
    assert s['generation_rate_wilson_95_descriptive'][0] < .90
    assert not s['goal_achieved'] and not s['superiority_achieved']


def test_aggregate_checks_completed_native_package_instead_of_trusting_label(tmp_path, monkeypatch):
    r, _, sha = fake_plan(tmp_path); root = Path(r['run_root']);root.mkdir()
    a=r['attempts'][0];folder=root/a['id'];folder.mkdir();save_outcome(folder,
      {'attempt':a,'registration_sha256':sha,'status':'complete','generation_complete':True,
       'independent_public_checks_passed':True})
    class Invalid:
        def package_gate(self): raise nr.CohortError('actual current phase rejected')
    monkeypatch.setattr(nr,'controller',lambda *a:Invalid())
    with pytest.raises(nr.CohortError,match='phase rejected'):nr.report(r,sha,root)


def test_lossless_closed_outcomes_cannot_be_overwritten(tmp_path):
    path=tmp_path/'outcome.json';nr.immutable(path,{'status':'failed'})
    with pytest.raises(nr.CohortError):nr.immutable(path,{'status':'complete'})
    assert _read(path)==b'{"status":"failed"}'


def test_cohort_has_one_writer_and_rejects_competing_invocation(tmp_path):
    with nr.lock(tmp_path/'run'):
        with pytest.raises(BlockingIOError):
            with nr.lock(tmp_path/'run'): pytest.fail('second writer admitted')


def test_independent_graph_oracle_distinguishes_order_from_rounds():
    m=checker();r=m.topo_oracle({'nodes':['z','b','a'],'edges':[['a','b']]})
    assert r=={'order':['a','b','z'],'layers':[['a','z'],['b']],'roots':['a','z']}
    assert m.topo_oracle({'nodes':[],'edges':[]})=={'order':[],'layers':[],'roots':[]}


def test_public_corpus_counts_atomicity_and_integer_types():
    m=checker()
    assert len(m.corpus('ledgerfold'))==104 and len(m.corpus('topoplan'))==105
    assert not m.exact({'value':True},{'value':1}) and not m.exact([1.0],[1])
    for t in ['ledgerfold','topoplan']:
        c=m.corpus(t);assert len([n for n,_,_ in c if n.startswith('atomic')])==6
        assert next(len(b) for n,b,_ in c if n=='byte-limit-exact')==131072
    assert m.ledger_oracle([{'account':'a','delta':10**12}]*2000)['total']==2*10**15


def test_mismatched_registered_digest_rejected(tmp_path):
    _,p,_=fake_plan(tmp_path)
    with pytest.raises(nr.CohortError,match='digest'):nr.load_plan(p,'0'*64)


def test_false_public_success_cannot_hide_missing_external_receipt(tmp_path, monkeypatch):
    r,_,sha=fake_plan(tmp_path);root=Path(r['run_root']);root.mkdir()
    a=r['attempts'][0];folder=root/a['id'];folder.mkdir();save_outcome(folder,
      {'attempt':a,'registration_sha256':sha,'status':'complete','generation_complete':True,
       'independent_public_checks_passed':True})
    class Valid:
        def package_gate(self): return True
    monkeypatch.setattr(nr,'controller',lambda *a:Valid())
    with pytest.raises(nr.CohortError,match='no measured evidence'):nr.report(r,sha,root)


def test_aggregation_error_preserves_raw_failure_and_previous_report(tmp_path, monkeypatch):
    r,_,sha=fake_plan(tmp_path);root=Path(r['run_root']);root.mkdir()
    a=r['attempts'][0];folder=root/a['id'];folder.mkdir();save_outcome(folder,
      {'attempt':a,'registration_sha256':sha,'status':'complete','generation_complete':True,
       'independent_public_checks_passed':False})
    _write(root/'report.json',{'classification':'previous verified report'})
    class Invalid:
        def package_gate(self):raise nr.CohortError('receipt adulterated')
    monkeypatch.setattr(nr,'controller',lambda *a:Invalid())
    with pytest.raises(nr.CohortError):nr.write_report(r,sha,root)
    assert nr._json(root/'report.json')=={'classification':'previous verified report'}
    error=nr._json(next(root.glob('aggregation-error-*.json')))
    assert not error['verified'] and not error['goal_achieved']
    assert error['raw_outcomes'][a['id']]['unverified_outcome']['status']=='complete'


def test_prior_case_without_registered_start_is_not_adopted(tmp_path, monkeypatch):
    r,p,sha=fake_plan(tmp_path);root=Path(r['run_root']);root.mkdir()
    a=r['attempts'][0];folder=root/a['id'];(folder/'case').mkdir(parents=True)
    monkeypatch.setattr(nr,'controller',lambda *a:pytest.fail('historical case adopted'))
    with pytest.raises(nr.CohortError,match='no adoption'):nr.run_attempt(p,sha,r,a,root)
    assert not (folder/'started.json').exists()


def test_checker_exit_zero_json_null_cannot_count_success(tmp_path, monkeypatch):
    r,_,_=fake_plan(tmp_path);r['tasks']['rangeaudit'].update(checker_args=[],public_cases=1)
    folder=tmp_path/'checker-job';folder.mkdir();(folder/'stdout.bin').write_text('null')
    class Executor:
        def measure(self,*a):return {'passed':True,'test_job_ref':str(folder/'receipt.json'),
                                     'timed_out':False,'truncated_streams':[],
                                     'argv':['/docker','start'],'subject_argv':['/python','/checker']}
        def verify_test(self,data,*a,**kw):
            assert data['argv']==data['subject_argv']==['/python','/checker']
            return True
    class Ctrl:
        def _files(self):return {}
    monkeypatch.setattr(nr,'transport',lambda *a:Executor())
    with pytest.raises(nr.CohortError,match='object report'):
        nr.public_check(r,r['attempts'][0],tmp_path,Ctrl())


def test_checker_source_drift_rejected_before_measurement(tmp_path, monkeypatch):
    r,_,_=fake_plan(tmp_path);(Path(r['source_root'])/'checker').write_text('changed')
    class Ctrl:
        def _files(self):return {}
    monkeypatch.setattr(nr,'transport',lambda *a:pytest.fail('unbound checker dispatched'))
    with pytest.raises(nr.CohortError,match='source changed'):
        nr.public_check(r,r['attempts'][0],tmp_path,Ctrl())


def test_resource_corruption_does_not_lose_original_terminal_error(tmp_path, monkeypatch):
    r,p,sha=fake_plan(tmp_path);root=Path(r['run_root']);root.mkdir()
    class Failed:
        def step(self):raise nr.CohortError('original controller failure')
    monkeypatch.setattr(nr,'controller',lambda *a:Failed())
    def corrupt(*args):raise ValueError('corrupt resource receipt')
    monkeypatch.setattr(nr,'resources',corrupt)
    a=r['attempts'][0];outcome=nr.run_attempt(p,sha,r,a,root)
    assert outcome['status']=='failed' and outcome['reason']=='original controller failure'
    assert outcome['resources']['job_seconds_sum'] is None
    assert nr.read_closed(root/a['id'])==outcome
    monkeypatch.setattr(nr,'controller',lambda *a:pytest.fail('closed failure replaced'))
    assert nr.run_attempt(p,sha,r,a,root)==outcome


def test_closed_outcome_and_action_adulteration_fail_seal(tmp_path):
    r,_,sha=fake_plan(tmp_path);a=r['attempts'][0];folder=tmp_path/'attempt';folder.mkdir()
    outcome={'attempt':a,'registration_sha256':sha,'status':'failed','generation_complete':False,
             'independent_public_checks_passed':False}
    _write(folder/'action-01.json',{'action':'synthetic'})
    save_outcome(folder,outcome);_write(folder/'action-01.json',{'action':'adulterated'})
    with pytest.raises(nr.CohortError,match='evidence changed'):nr.read_closed(folder)


def test_allocation_cannot_move_fourth_rangeaudit_to_ledgerfold(tmp_path):
    r,p,_=fake_plan(tmp_path);r['attempts'][-1]['task']='ledgerfold';_write(p,r)
    with pytest.raises(nr.CohortError,match='allocation'):nr.load_plan(p,digest(_read(p)))
