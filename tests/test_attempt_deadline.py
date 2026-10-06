"""Original budget/process guards; all clocks/identities used as explicit fixtures."""
import copy
import signal
import subprocess
import sys
import time

import pytest

from specorganon import attempt_deadline as M
from specorganon.attempt_deadline import AttemptBudget, AttemptDeadlineError, DEADLINE_POLICY
from specorganon.docker_roles import DockerRoles, DockerRoleError
from specorganon.role_jobs import JobStore, JobError, _json
from test_native_source_custody import transport


def budget(monkeypatch, remaining):
    start = M.clock(); now = copy.deepcopy(start)
    now['boottime_ns'] += int((6000-remaining)*10**9)
    monkeypatch.setattr(M,'clock',lambda:copy.deepcopy(now))
    return AttemptBudget(start,'a'*64), now


def test_original_timestamp_is_retained_when_jobstore_is_created_later(tmp_path,monkeypatch):
    b,now = budget(monkeypatch,100)
    store = JobStore(tmp_path/'jobs',attempt_budget=b)
    assert store.policy['schema'] == 4 and store.policy['whole_attempt_binding'] == b.binding
    captured = []
    original = store._run
    def run(path,argv,cwd,env,timeout,*args):
        captured.append(timeout); return original(path,argv,cwd,env,timeout,*args)
    monkeypatch.setattr(store,'_run',run)
    command = [sys.executable,'-c','print("actual local process; no provider")']
    result = store.execute('first',command,{},cwd=tmp_path,timeout_seconds=180)
    assert result['receipt']['exit_code'] == 0
    assert captured == [40]  #100remaining - SAME60s cleanup reserve; not a new6000s.
    resumed = JobStore(store.root,attempt_budget=AttemptBudget(b.start,'a'*64))
    now['boottime_ns'] += 100*10**9
    assert resumed.execute('first',command,{},cwd=tmp_path,timeout_seconds=180)['reused']
    with pytest.raises(JobError,match='budget'): resumed.execute('new',command,{},cwd=tmp_path)
    assert not (store.root/'new').exists()
    with pytest.raises(JobError,match='policy'): JobStore(store.root,attempt_budget=AttemptBudget(b.start,'b'*64))


@pytest.mark.parametrize('fault',['boot','host','backward'])
def test_changed_boot_or_host_cannot_buy_a_new_attempt_window(monkeypatch,fault):
    b,now = budget(monkeypatch,100)
    if fault == 'boot': now['boot_id_sha256'] = 'b'*64
    elif fault == 'host': now['host_id_sha256'] = 'b'*64
    else: now['boottime_ns'] = b.start['boottime_ns']-1
    with pytest.raises(AttemptDeadlineError,match='never reset'): b.admit()


def test_suspend_consumes_original_budget_and_terminates_actual_child(tmp_path,monkeypatch):
    b,now = budget(monkeypatch,100);store = JobStore(tmp_path/'jobs',attempt_budget=b)
    original = store._run
    def suspend(path,*args):
        # Admission happened under the original remaining100s. Simulate suspend
        # before the selector begins: monotonic process time has not advanced.
        now['boottime_ns'] += 41*10**9
        return original(path,*args)
    monkeypatch.setattr(store,'_run',suspend)
    began = time.monotonic()
    result = store.execute('suspended',[sys.executable,'-c','import time;time.sleep(30)'],{},cwd=tmp_path)
    assert result['receipt']['timed_out'] is True and result['receipt']['exit_code'] == -signal.SIGKILL
    assert time.monotonic()-began < 3


def test_control_deadline_stops_actual_cli_child_on_boottime_cutoff(monkeypatch):
    original = subprocess.Popen; processes = []
    def cli(argv,**options):
        process = original([sys.executable,'-c','import time;time.sleep(30)'],**options)
        processes.append(process); return process
    monkeypatch.setattr(subprocess,'Popen',cli)
    from specorganon.docker_roles import DockerControlDeadlineError
    began = time.monotonic()
    with pytest.raises(DockerControlDeadlineError):
        DockerRoles._cli(['synthetic-cli'],boottime_deadline_ns=time.clock_gettime_ns(time.CLOCK_BOOTTIME)+50_000_000)
    assert time.monotonic()-began < 3 and processes[0].poll() == -signal.SIGKILL


def bound_transport(tmp_path,monkeypatch):
    _,_,options = transport(tmp_path,monkeypatch)
    monkeypatch.setattr(DockerRoles,'_image',staticmethod(lambda ref,**kwargs:ref))
    b,now = budget(monkeypatch,100)
    t = DockerRoles(tmp_path/'bound',**options,attempt_clock=b.start,attempt_initial_sha256=b.initial_sha256)
    return t,b,now,options


def test_expired_preparation_rejected_before_job_or_docker_creation(tmp_path,monkeypatch):
    t,b,now,_ = bound_transport(tmp_path,monkeypatch)
    now['boottime_ns'] += 11*10**9  #89s insufficient for original SAME prep rule.
    monkeypatch.setattr(t,'_cli',lambda *a,**k:(_ for _ in ()).throw(AssertionError('must not call Docker')))
    with pytest.raises(AttemptDeadlineError): t._prepare('new','author',{'fixture':True})
    assert not (t.root/'jobs/new').exists()
    assert _json(t.root/'attempt-deadline.json') == b.binding


def test_expired_constructor_resume_does_not_reset_clock_or_inspect_images(tmp_path,monkeypatch):
    t,b,now,options = bound_transport(tmp_path,monkeypatch)
    now['boottime_ns'] += 200*10**9
    monkeypatch.setattr(DockerRoles,'_image',staticmethod(lambda *a,**k:(_ for _ in ()).throw(AssertionError('closed custody needs no daemon'))))
    resumed = DockerRoles(t.root,**options,attempt_clock=b.start,attempt_initial_sha256=b.initial_sha256)
    assert resumed.attempt_budget.binding == b.binding
    assert _json(t.root/'transport-policy.json')['schema'] == 6
    assert resumed.attempt_budget.remaining() < 0
    with pytest.raises(AttemptDeadlineError): resumed._prepare('new','author',{'fixture':True})


def test_bounded_owned_cleanup_still_runs_after_original_deadline(tmp_path,monkeypatch):
    t,b,now,_ = bound_transport(tmp_path,monkeypatch)
    now['boottime_ns'] += 200*10**9
    calls = []
    monkeypatch.setattr(t,'_cli',lambda argv,**options:calls.append((argv,options)))
    with pytest.raises(AttemptDeadlineError): t._control(['inspect','owned'])
    assert not calls
    with t._cleanup_controls(): t._control(['kill','owned'],allow_failure=True)
    assert calls == [(['kill','owned'],{'allow_failure':True})]
    assert t.attempt_budget.remaining() < 0


def test_changed_deadline_binding_refuses_closed_or_new_provenance(tmp_path,monkeypatch):
    from specorganon.role_jobs import _write
    t,b,now,_ = bound_transport(tmp_path,monkeypatch)
    changed = b.binding;changed['initial_sha256'] = 'b'*64
    _write(t.root/'attempt-deadline.json',changed)
    with pytest.raises(DockerRoleError,match='binding changed'): t._verify_attempt_binding()


@pytest.mark.parametrize('method',['N','S','T'])
def test_N_S_T_forward_original_clock_before_transport_image_preparation(tmp_path,monkeypatch,method):
    from test_native_source_custody import registered_transport
    from specorganon.role_jobs import digest, canonical
    from specorganon.neutral_controller import NeutralController
    from specorganon.t_common_controller import TCommonController
    t0,_,options = registered_transport(tmp_path,monkeypatch)
    policy = _json(t0.root/'transport-policy.json'); policy.update(schema=6,whole_attempt_budget=DEADLINE_POLICY)
    probes = []
    def image(ref,*,attempt_budget):
        # Actual original clock/initial SHA exist BEFORE the first image probe.
        initial = _json(root/'initial.json')
        assert attempt_budget.start == initial['clock']
        assert attempt_budget.initial_sha256 == digest((root/'initial.json').read_bytes())
        probes.append(attempt_budget.binding); return ref
    monkeypatch.setattr(DockerRoles,'_image',staticmethod(image))
    root = tmp_path/'controller'
    def factory(path,**binding): return DockerRoles(path,**options,**binding)
    common = dict(attempt_id='mechanical-binding',contract='Explicit synthetic policy interface control',
                  mandate='Synthetic fixture; no operator consent',transport_policy=policy,transport_factory=factory,fixture_mode=False)
    if method == 'T':
        c = TCommonController(root,title='Synthetic argument forwarding only',**common)
        c._get_controller()
    else:
        c = NeutralController(root,method=method,test_file='test_program.py',
            argv=['/opt/specorganon/venv/bin/python','-I','-B','/input/delivery/test_program.py'],**common)
        c._get_transport()
    assert len(probes) == 2 and probes[0] == probes[1]
    assert c.transport.store.policy['whole_attempt_binding'] == probes[0]
    # No role dispatch, test execution or native-ready result occurred.
    assert not (c.transport.root/'jobs').exists()


@pytest.mark.parametrize('method',['N','S'])
def test_late_terminal_audit_never_reports_native_or_common_readiness(tmp_path,monkeypatch,method):
    from test_neutral_controller import controller
    import specorganon.neutral_controller as module
    c = controller(tmp_path/'run',method)
    c.run()
    state,_,_,_ = c._load()
    # Preserve original state while exercising terminal closure time guard.
    path = c.root/'terminal-clock.json'; path.unlink()
    late = copy.deepcopy(c.initial['clock']);late['boottime_ns'] += 6001*10**9
    monkeypatch.setattr(module,'_clock',lambda:late)
    report = c._report(state)
    assert report['status'] == 'failed' and report['whole_attempt_seconds'] == 6001
    assert not any(report[k] for k in ('common_review_ready','method_review_ready','native_ready'))
    assert c._report(state) == report


def test_missing_original_deadline_custody_cannot_be_recreated_on_resume(tmp_path,monkeypatch):
    t,b,now,options = bound_transport(tmp_path,monkeypatch)
    (t.root/'attempt-deadline.json').unlink()
    with pytest.raises(DockerRoleError,match='binding missing'):
        DockerRoles(t.root,**options,attempt_clock=b.start,attempt_initial_sha256=b.initial_sha256)
    assert not (t.root/'attempt-deadline.json').exists()


@pytest.mark.parametrize('options',[{'timeout_seconds':float('nan')},{'timeout_seconds':True},
    {'timeout_seconds':0},{'timeout_seconds':'bad'},{'boottime_deadline_ns':True},
    {'boottime_deadline_ns':0}])
def test_invalid_or_already_expired_control_options_cannot_spawn_cli(monkeypatch,options):
    monkeypatch.setattr(subprocess,'Popen',lambda *a,**k:(_ for _ in ()).throw(AssertionError('must not spawn invalid control')))
    with pytest.raises(DockerRoleError): DockerRoles._cli(['synthetic-control'],**options)
