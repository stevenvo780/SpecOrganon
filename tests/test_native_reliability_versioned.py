"""Versioned prospective controls; synthetic, no model calls or software efficacy."""
from pathlib import Path
import pytest
from scripts import native_reliability as nr
from tests.test_native_reliability import fake_plan
from specorganon.role_jobs import _read, _write, digest


def versioned(tmp_path):
    r,p,_=fake_plan(tmp_path)
    source=Path(r['source_root'])
    for name in ['scripts/run_registered_native.py','goals/method-superiority-v1/development/register_native_cohort.py']:
        q=source/name;q.parent.mkdir(parents=True,exist_ok=True);q.write_text('synthetic')
        r['source_sha256'][name]=digest(_read(q))
    r.update(schema=2,candidate_version=nr.__version__,admission_repair=True,author_format='items-v1',
             controller_limits={'roles':40,'authors_per_phase':2,'build_authors':3,'phase_reviews':2,
                                'mandate_checks':2,'tests_per_id':2,'items_per_phase':6,
                                'phase_encoded_bytes':6000,'delivery_encoded_bytes':20000,
                                'test_stream_encoded_bytes':4000,'transport_wall_seconds':6000})
    _write(p,r)
    return r,p,digest(_read(p))


def test_registration_parses_same_bytes_it_hashes(tmp_path,monkeypatch):
    r,p,sha=versioned(tmp_path)
    monkeypatch.setattr(nr,'verify_runtime_sources',lambda r:None)
    original=nr._read;reads=[]
    def read(path):
        raw=original(path)
        if Path(path)==p:
            reads.append(path)
            p.write_text('{"schema":999}')
        return raw
    monkeypatch.setattr(nr,'_read',read)
    assert nr.load_plan(p,sha)==r
    assert len(reads)==1


@pytest.mark.parametrize('fault',['version','missing_optin','false_optin','format','budget','bool_budget','legacy_optin'])
def test_version_limits_and_optin_cannot_drift(tmp_path,fault):
    r,p,_=versioned(tmp_path)
    if fault=='version':r['candidate_version']='different'
    elif fault=='missing_optin':del r['admission_repair']
    elif fault=='false_optin':r['admission_repair']=False
    elif fault=='format':r['author_format']='manifest-v1'
    elif fault=='budget':r['controller_limits']['roles']=41
    elif fault=='bool_budget':r['controller_limits']['tests_per_id']=True
    else:r['schema']=1
    _write(p,r)
    with pytest.raises(nr.CohortError):nr.load_plan(p,digest(_read(p)))


def test_controller_receives_only_registered_optin(tmp_path,monkeypatch):
    r,p,sha=versioned(tmp_path)
    monkeypatch.setattr(nr,'verify_runtime_sources',lambda r:None)
    monkeypatch.setattr(nr,'check_effective_limits',lambda *a:None)
    nr.load_plan(p,sha)
    monkeypatch.setattr(nr,'transport',lambda *a:object())
    captured=[]
    def build(*args,**kwargs):captured.append(kwargs);return kwargs
    monkeypatch.setattr(nr,'Controller',build)
    assert nr.controller(r,r['attempts'][0],tmp_path/'attempt')['admission_repair'] is True
    r['schema']=1;r.pop('admission_repair')
    assert nr.controller(r,r['attempts'][0],tmp_path/'legacy')['admission_repair'] is False


def test_direct_versioned_execution_without_bound_bootstrap_rejected(tmp_path):
    r,p,sha=versioned(tmp_path)
    with pytest.raises(nr.CohortError,match='fresh registered bootstrap'):nr.load_plan(p,sha)


def test_helper_binding_required_before_dispatch(tmp_path,monkeypatch):
    r,p,_=versioned(tmp_path)
    del r['source_sha256']['goals/method-superiority-v1/development/register_native_cohort.py']
    _write(p,r)
    monkeypatch.setattr(nr,'verify_runtime_sources',lambda r:pytest.fail('missing helper admitted'))
    with pytest.raises(nr.CohortError,match='helper bindings'):nr.load_plan(p,digest(_read(p)))


def test_contract_bytes_changed_after_plan_cannot_enter_controller(tmp_path,monkeypatch):
    r,p,sha=versioned(tmp_path)
    monkeypatch.setattr(nr,'verify_runtime_sources',lambda r:None)
    nr.load_plan(p,sha)
    (Path(r['source_root'])/'contract').write_text('transient changed content')
    monkeypatch.setattr(nr,'transport',lambda *a:object())
    monkeypatch.setattr(nr,'Controller',lambda *a,**k:pytest.fail('changed contract used'))
    with pytest.raises(nr.CohortError,match='before use'):nr.controller(r,r['attempts'][0],tmp_path/'attempt')


@pytest.mark.parametrize('fault',[None,'roles','wall','optin','format'])
def test_effective_policy_checked_before_dispatch(tmp_path,fault):
    from types import SimpleNamespace
    r,_,_=versioned(tmp_path)
    policy={'max_role_calls':40,'max_author_per_phase':2,'max_build_authors':3,
            'max_review_per_phase':2,'max_approval_per_phase':2,'max_phase_items':6,
            'max_phase_encoded_bytes':6000,'max_files_encoded_bytes':20000,
            'max_test_stream_encoded_bytes':4000,'admission_repair':True,'author_format':'items-v1'}
    wall=6000
    if fault=='roles':policy['max_role_calls']=41
    elif fault=='wall':wall=6001
    elif fault=='optin':policy['admission_repair']=False
    elif fault=='format':policy['author_format']='manifest-v1'
    ctrl=SimpleNamespace(root=tmp_path/'controller');ctrl.root.mkdir();_write(ctrl.root/'controller.json',policy)
    transport=SimpleNamespace(store=SimpleNamespace(policy={'max_elapsed_seconds':wall}))
    if fault:
        with pytest.raises(nr.CohortError,match='effective'):nr.check_effective_limits(r,ctrl,transport)
    else:nr.check_effective_limits(r,ctrl,transport)
