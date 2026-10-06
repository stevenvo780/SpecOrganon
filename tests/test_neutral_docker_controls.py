"""Opt-in real isolated test processes with synthetic authors/reviewers only.

No provider is invoked; fixture_mode remains true even when own execution is real.
The existing pinned dev4 Python image validates transport mechanics, not a dev6
installed release or comparative validity. All fixture roles are explicitly so.
"""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

from specorganon.docker_roles import DockerRoles
from specorganon.docker_roles import DockerRoleError
from specorganon.neutral_controller import NeutralController
from specorganon.role_jobs import _json, canonical, digest
from specorganon.role_jobs import _write
from test_neutral_controller import ARGV, POLICY, TEST, FixtureTransport


pytestmark=pytest.mark.skipif(os.environ.get('SPECORGANON_NEUTRAL_DOCKER_CONTROLS')!='1',
                            reason='explicit neutral Docker mechanical controls only')
SOURCE=Path(__file__).resolve().parents[1]
CATALOG=SOURCE/'experiments/software_comparison_v3/public-models.json'
OPTIONS={'native_image':'sha256:aa4eae810628bd2b78bd48ed3059c284a497bdc7c92d81daacdfe906a3bae3ae',
         'test_image':'sha256:6d196a4a021b872e2ea7d799e1797834e23b570e635bd640095f4521cca04ce2',
         'source_root':str(SOURCE),'public_catalog':str(CATALOG),'reviewer_model':'Gemini 3.8 Flash (Medium)'}
COUNTER='\np=Path("/output/own-runs.txt");p.write_text(str(int(p.read_text())+1) if p.exists() else "1")\n'


def make_actual_controller(root,method='N',hold=False):
    real=None;wrapped=None
    def factory(path):
        nonlocal real,wrapped
        if wrapped is None:
            names=[SOURCE/'scripts/controller_native_role.py',*sorted((SOURCE/'src/specorganon').glob('*.py')),CATALOG]
            pins={str(p.relative_to(SOURCE)):digest(p.read_bytes()) for p in names}
            real=DockerRoles(path/'actual-tests',**OPTIONS,source_bindings=pins)
            battery=TEST+COUNTER+('import time\ntime.sleep(90)\n' if hold else '')
            response={'schema':1,'files':{'test_program.py':battery},'documents':{},'reason':'Mechanical battery; synthetic authorship'}
            wrapped=FixtureTransport(path,responses={'tests':response})
            wrapped.store=real.store
            wrapped.measure=real.measure;wrapped.verify_test=real.verify_test;wrapped.recover_test=real.recover_test
            wrapped.reconcile_pending=lambda job,role,request:real.reconcile_pending(job,role,request) if role=="test" else False
            wrapped.actual=real
        return wrapped
    return NeutralController(root,attempt_id='docker-mechanics-01',method=method,
        contract='Public mechanical fixture: result seven.',mandate='Offline mechanical test only.',
        argv=ARGV,test_file='test_program.py',transport_policy=POLICY,transport_factory=factory,fixture_mode=True)


def cleanup(c):
    if c.transport is not None:
        t=c.transport.actual
        for path in (t.root/'jobs').glob('*/launch.json'):
            plan=_json(path)
            if plan['container_id']:t._cli(['rm','--force',plan['container_id']],allow_failure=True)


def test_checked_test_buffers_survive_later_stream_change_and_next_read_rejects(tmp_path):
    """Actual offline test process, synthetic content; no provider/profile mount."""
    t = DockerRoles(tmp_path / 'checked-streams', **OPTIONS)
    files = {'probe.py': 'import sys\nprint("original measured bytes")\nsys.exit(1)\n'}
    argv = ['/opt/specorganon/venv/bin/python', '-I', '-S', '-B', '/input/delivery/probe.py']
    try:
        measured = t.measure('checked-streams', argv, files)
        data = {'argv': argv, 'test_job_ref': measured['test_job_ref']}
        verified, streams = t.read_test(data, files, require_passed=False)
        assert verified == measured and verified['passed'] is False
        assert streams['stdout'] == b'original measured bytes\n' and streams['stderr'] == b''
        assert digest(streams['stdout']) == measured['stdout_sha256']
        path = t.store.root / 'checked-streams/stdout.bin'
        path.write_bytes(b'replacement bytes\n')
        assert streams['stdout'] == b'original measured bytes\n'
        with pytest.raises(ValueError): t.read_test(data, files, require_passed=False)
    finally:
        path = t.root / 'jobs/checked-streams/launch.json'
        if path.exists():
            handle = _json(path)['container_id']
            if handle: t._cli(['rm', '--force', handle], allow_failure=True)


@pytest.mark.parametrize('method',['N','S'])
def test_real_test_with_synthetic_roles_never_claims_native_and_replay_never_reexecutes(tmp_path,method):
    c=make_actual_controller(tmp_path/'run',method)
    try:
        report=c.run();assert report['status']=='review_ready',report
        assert report['fixture_mode'] and report['native_ready'] is False and report['external_F'] is None
        t=c.transport.actual;folders=list((t.root/'jobs').iterdir());assert len(folders)==1
        folder=folders[0];plan=_json(folder/'launch.json');observed=t._inspect(plan)
        assert observed['HostConfig']['NetworkMode']=='none' and observed['HostConfig']['ReadonlyRootfs']
        assert all(m['Destination'] not in {'/home/codex/.codex','/home/stev/.gemini','/var/run/docker.sock'} for m in observed['Mounts'])
        assert (folder/'output/own-runs.txt').read_text()=='1'
        raw=(folder/'measured-test.json').read_bytes()
        assert c.step()==report
        assert (folder/'output/own-runs.txt').read_text()=='1' and (folder/'measured-test.json').read_bytes()==raw
        assert b'guard control passed' in (t.store.root/folder.name/'stdout.bin').read_bytes()
    finally:cleanup(c)


def test_real_closed_measure_crash_before_generation_reuses_receipt_not_run(tmp_path,monkeypatch):
    c=make_actual_controller(tmp_path/'run')
    try:
        for _ in range(3):assert c.step()['status']=='running'
        original=c._apply
        def crash(state,reservation,result,past):
            if reservation['stage']=='measure':
                raise KeyboardInterrupt('injected controller crash after closed Docker measurement')
            return original(state,reservation,result,past)
        monkeypatch.setattr(c,'_apply',crash)
        with pytest.raises(KeyboardInterrupt):c.step()
        folders=list((c.transport.actual.root/'jobs').iterdir());assert len(folders)==1
        assert (folders[0]/'output/own-runs.txt').read_text()=='1'
        monkeypatch.setattr(c,'_apply',original)
        monkeypatch.setattr(c.transport,'measure',lambda *a:(_ for _ in ()).throw(AssertionError('must not redispatch measurement')))
        report=c.step();assert report['stage']=='audit' and report['counts']['test_runs']==1
        assert (folders[0]/'output/own-runs.txt').read_text()=='1'
    finally:cleanup(c)


def test_R3_real_failed_test_cannot_promote_fabricated_passed_true(tmp_path):
    c=make_actual_controller(tmp_path/'run')
    try:
        c.step()
        c.transport.responses['program']={'schema':1,'files':{'program.py':'def result(): return 0\n','README.md':'Known failing mechanical fixture'},'documents':{},'reason':'Synthetic defect'}
        c.step();c.step();report=c.step()
        assert report['stage']=='repair' and report['counts']['test_runs']==1
        t=c.transport.actual;folder=t.root/'jobs/neutral-0004-measure'
        path=folder/'measured-test.json';original=_json(path)
        assert original['passed'] is False and original['exit_code']==1
        changed={**original,'passed':True};_write(path,changed)
        data={'argv':ARGV,'test_job_ref':str(t.store.root/'neutral-0004-measure/receipt.json')}
        files=_json(c.root/'reservations/0004.json')['request']['files']
        with pytest.raises(DockerRoleError,match='fabricated outcome'):t.verify_test(data,files)
        _write(path,original)
        assert t.verify_test(data,files,require_passed=False)
    finally:cleanup(c)


@pytest.mark.parametrize('late,inspect_timeout,missing_launch',[(False,False,False),(True,False,False),(False,True,False),(False,False,True),(True,False,True)])
def test_real_SIGKILL_during_measure_closes_uncertain_and_preserves_one_execution(tmp_path,monkeypatch,late,inspect_timeout,missing_launch):
    root=tmp_path/'run'
    source=('import sys\n'+f'sys.path.insert(0,{str(SOURCE/"tests")!r})\n'
            'from test_neutral_docker_controls import make_actual_controller\n'+
            f'c=make_actual_controller({str(root)!r},hold=True)\nc.run()\n')
    child=subprocess.Popen([sys.executable,'-c',source],stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,start_new_session=True)
    c=None
    try:
        marker=root/'transport/actual-tests/jobs/neutral-0004-measure/output/own-runs.txt'
        deadline=time.monotonic()+30
        while not marker.exists() and child.poll() is None and time.monotonic()<deadline:time.sleep(.05)
        assert marker.exists(),'mechanical test must actually start before SIGKILL'
        os.kill(child.pid,signal.SIGKILL);child.wait(timeout=5)
        c=make_actual_controller(root,hold=True)
        if late:
            import copy
            import specorganon.neutral_controller as module
            now=copy.deepcopy(c.initial['clock']);now['boottime_ns']+=6001*10**9
            monkeypatch.setattr(module,'_clock',lambda:now)
        if inspect_timeout:
            from specorganon.docker_roles import DockerControlDeadlineError,PendingCleanupError
            t=c._get_transport().actual;original_cli=t._cli
            def expired(argv,**options):
                if argv[0]=='inspect':raise DockerControlDeadlineError('inspect')
                return original_cli(argv,**options)
            monkeypatch.setattr(t,'_cli',expired)
            with pytest.raises(PendingCleanupError):c.step()
            assert not (c.root/'results/0004.json').exists() and not (c.root/'generations/0004.json').exists()
            assert not (c.root/'terminal-clock.json').exists() and marker.read_text()=='1'
            monkeypatch.setattr(t,'_cli',original_cli)
            assert t._inspect(_json(t.root/'jobs/neutral-0004-measure/launch.json'))['State']['Running'] is True
        if missing_launch:
            from specorganon.docker_roles import PendingCleanupError
            t=c._get_transport().actual;path=t.root/'jobs/neutral-0004-measure/launch.json'
            saved=path.read_bytes();plan=_json(path);path.unlink()
            try:
                with pytest.raises(PendingCleanupError):c.step()
                assert not (c.root/'results/0004.json').exists() and not (c.root/'generations/0004.json').exists()
                assert not (c.root/'terminal-clock.json').exists() and marker.read_text()=='1'
                assert t._inspect(plan)['State']['Running'] is True
            finally:path.write_bytes(saved) # Exact original fixture binding, including on a failed guard.
        report=c.step()
        assert report['status']=='failed' and report['counts']['test_runs']==1
        assert ('admission exhausted' if late else 'UncertainJob') in report['failure'] and not report['native_ready']
        t=c.transport.actual;plan=_json(t.root/'jobs/neutral-0004-measure/launch.json')
        assert t._inspect(plan)['State']['Running'] is False
        assert marker.read_text()=='1'
        assert not (t.store.root/'neutral-0004-measure/receipt.json').exists()
        assert c.step()==report and marker.read_text()=='1'
        assert len(list((t.root/'jobs').iterdir()))==1
    finally:
        if child.poll() is None:os.kill(child.pid,signal.SIGKILL);child.wait(timeout=5)
        if child.stderr:child.stderr.close()
        if c:cleanup(c)


def test_R11_real_closed_measure_without_summary_recovers_after_cutoff(tmp_path,monkeypatch):
    import copy
    import specorganon.neutral_controller as module
    c=make_actual_controller(tmp_path/'run')
    try:
        for _ in range(3):c.step()
        t=c.transport.actual;original=t.measure
        def closed_without_summary(job,argv,files):
            result=original(job,argv,files)
            (t.root/'jobs'/job/'measured-test.json').unlink()
            raise KeyboardInterrupt('after native receipt/terminal before derived summary or controller result')
        c.transport.measure=closed_without_summary
        with pytest.raises(KeyboardInterrupt):c.step()
        now=copy.deepcopy(c.initial['clock']);now['boottime_ns']+=6001*10**9
        monkeypatch.setattr(module,'_clock',lambda:now)
        report=c.step();assert report['stage']=='audit' and report['counts']['test_runs']==1
        assert (t.root/'jobs/neutral-0004-measure/output/own-runs.txt').read_text()=='1'
        assert not (t.root/'jobs/neutral-0004-measure/measured-test.json').exists()
    finally:cleanup(c)


def test_R10_real_bridge_closed_empty_body_classified_without_accepted_role(tmp_path):
    from specorganon.docker_roles import ClosedResponseContractError
    # An explicit simulator replaces the provider executable; no existing session
    # or account is mounted. Real Docker/bridge/inner JobStore, zero model calls.
    simulator=tmp_path/'simulated-agy'
    simulator.write_text('''#!/opt/specorganon/.venv/bin/python
import json,sys
sys.stdin.buffer.read()
text=json.dumps({"schema":1,"files":{},"documents":{},"reason":"Closed empty body fixture"})
c="synthetic-native-stream"
for event in [
 {"event":"init","conversation_id":c,"init":{}},
 {"event":"step_update","step_update":{"conversation_id":c,"step_index":0,"state":"DONE","step_type":"user_input"}},
 {"event":"step_update","step_update":{"conversation_id":c,"step_index":1,"state":"DONE","step_type":"agent_response","text_delta":text}},
 {"event":"result","result":{"conversation_id":c,"status":"SUCCESS","num_turns":1,"response":text,"usage":{"fixture":True}}}]:
 print(json.dumps(event))
''');simulator.chmod(0o755)
    profile=tmp_path/'empty-synthetic-profile';profile.mkdir()
    names=[SOURCE/'scripts/controller_native_role.py',*sorted((SOURCE/'src/specorganon').glob('*.py')),CATALOG]
    pins={str(p.relative_to(SOURCE)):digest(p.read_bytes()) for p in names}
    t=DockerRoles(tmp_path/'actual-simulated-role',**{**OPTIONS,'author_provider':'gemini','author_model':'fixture-model',
        'gemini_profile':profile,'gemini_executable':simulator},source_bindings=pins)
    request={'schema':1,'role':'author','role_instructions':'Author simulator: emit the declared fixture body, never tools.',
        'documents':{'action.txt':'author','author-response-format.json':canonical({'schema':1,'format':'files-v1'}).decode()}}
    try:
        with pytest.raises(ClosedResponseContractError) as caught:t.call('empty-body-control','author',request)
        proof=caught.value.proof
        assert proof['provenance']=='closed_native_invalid_response' and proof['result']['files']==proof['result']['documents']=={}
        assert t.verify_response_failure(proof,'empty-body-control','author',request)
        plan=_json(t.root/'jobs/empty-body-control/launch.json');observed=t._inspect(plan)
        assert observed['State']['ExitCode']==2
        assert all(m.get('Name')!='specorganon-lab_codex-home' for m in observed['Mounts'])
        assert not any(profile.iterdir()),'simulator must never create auth/session state'
    finally:
        path=t.root/'jobs/empty-body-control/launch.json'
        if path.exists() and _json(path)['container_id']:t._cli(['rm','--force',_json(path)['container_id']],allow_failure=True)


@pytest.mark.parametrize('journal',['results','generations'])
def test_R15_real_measure_SIGKILL_during_atomic_controller_write_recovers_no_new_execution(tmp_path,journal):
    root=tmp_path/'run'
    source=('import sys,os,uuid\n'+f'sys.path.insert(0,{str(SOURCE/"tests")!r})\n'
            'from test_neutral_docker_controls import make_actual_controller\n'
            'import specorganon.neutral_controller as module\n'+
            f'c=make_actual_controller({str(root)!r})\noriginal=module._write\n'+
            f'target=c.root/{journal!r}/"0004.json"\n'+
            'def interrupted(path,value,**options):\n'
            ' if path==target:\n'
            '  p=path.parent/("."+path.name+"."+uuid.uuid4().hex)\n'
            '  with p.open("wb") as f:f.write(b"unpublished partial controller record");f.flush();os.fsync(f.fileno())\n'
            '  os.kill(os.getpid(),9)\n'
            ' return original(path,value,**options)\n'
            'module._write=interrupted\nc.run()\n')
    child=subprocess.run([sys.executable,'-c',source],stdin=subprocess.DEVNULL,capture_output=True,timeout=30)
    assert child.returncode==-signal.SIGKILL,child.stderr.decode()
    c=make_actual_controller(root)
    try:
        report=c.step();assert report['stage']=='audit' and report['counts']['test_runs']==1
        t=c.transport.actual;folders=list((t.root/'jobs').iterdir());assert len(folders)==1
        assert (folders[0]/'output/own-runs.txt').read_text()=='1'
        assert len(list((root/journal).glob('.0004.json.*')))==1
        assert (root/journal/'0004.json').exists()
        report=c.step();assert report['status']=='review_ready' and report['counts']['test_runs']==1
        assert (folders[0]/'output/own-runs.txt').read_text()=='1'
    finally:cleanup(c)


@pytest.mark.parametrize('provider_exit',[1,37])
def test_real_failed_bridge_closed_before_controller_capture_recovers_negative_without_provider_retry(tmp_path,provider_exit):
    from specorganon.docker_roles import ClosedNativeExecutionError
    # Actual Docker and measured inner Python process. Provider is an explicit
    # simulator with an empty disposable profile; zero accounts/model calls.
    simulator = tmp_path/'simulated-failing-agy'
    simulator.write_text('''#!/opt/specorganon/.venv/bin/python
import sys
from pathlib import Path
sys.stdin.buffer.read()
p=Path('/output/provider-fixture-count.txt')
p.write_text(str(int(p.read_text())+1) if p.exists() else '1')
print('synthetic provider failure without a parseable accepted response',file=sys.stderr)
sys.exit('''+str(provider_exit)+''')
''');simulator.chmod(0o755)
    profile = tmp_path/'empty-simulator-profile';profile.mkdir()
    names = [SOURCE/'scripts/controller_native_role.py',*sorted((SOURCE/'src/specorganon').glob('*.py')),CATALOG]
    pins = {str(p.relative_to(SOURCE)):digest(p.read_bytes()) for p in names}
    t = DockerRoles(tmp_path/'actual-failed-role',**{**OPTIONS,'author_provider':'gemini',
        'author_model':'fixture-model','gemini_profile':profile,'gemini_executable':simulator},source_bindings=pins)
    request = {'schema':1,'role':'author','role_instructions':'Explicit failure simulator only.',
        'documents':{'action.txt':'author','author-response-format.json':canonical({'schema':1,'format':'files-v1'}).decode()}}
    job = 'failed-role-control'
    try:
        with pytest.raises(ClosedNativeExecutionError) as caught: t.call(job,'author',request)
        proof = caught.value.proof
        folder = t.root/'jobs'/job; plan = _json(folder/'launch.json')
        assert proof['receipt']['exit_code'] == 2 and proof['acceptance'] is False
        assert proof['native_invocation_established'] is False and 'result' not in proof
        assert _json(folder/'output/native/call/receipt.json')['exit_code'] == provider_exit
        marker = folder/'output/provider-fixture-count.txt'
        assert marker.read_text() == '1'
        observed = t._inspect(plan)
        assert not observed['State']['Running']
        assert all(m.get('Name') != 'specorganon-lab_codex-home' for m in observed['Mounts'])
        original_cli = t._cli
        t._cli = lambda *a,**k: (_ for _ in ()).throw(AssertionError('recovery must be pure, no daemon control'))
        try:
            for _ in range(2):
                with pytest.raises(ClosedNativeExecutionError) as recovered: t.recover_role(job,'author',request)
                assert recovered.value.proof == proof
                assert t.verify_execution_failure(proof,job,'author',request) is True
        finally: t._cli = original_cli
        assert marker.read_text() == '1' and not any(profile.iterdir())
    finally:
        path = t.root/'jobs'/job/'launch.json'
        if path.exists() and _json(path)['container_id']:
            t._cli(['rm','--force',_json(path)['container_id']],allow_failure=True)


def test_real_bound_attempt_cutoff_stops_one_test_and_recovers_same_closed_result(tmp_path,monkeypatch):
    import copy
    import threading
    from specorganon import attempt_deadline as deadline
    start = deadline.clock(); now = copy.deepcopy(start)
    now['boottime_ns'] += 5900*10**9  # Explicit simulated clock:100s remain.
    monkeypatch.setattr(deadline,'clock',lambda:copy.deepcopy(now))
    t = DockerRoles(tmp_path/'bounded-actual-test',**OPTIONS,attempt_clock=start,attempt_initial_sha256='a'*64)
    files = {'probe.py':'''from pathlib import Path
import time
p=Path('/output/attempt-cutoff-count.txt');p.write_text(str(int(p.read_text())+1) if p.exists() else '1')
print('actual single isolated measurement, simulated attempt clock',flush=True)
time.sleep(30)
'''}
    argv = ['/opt/specorganon/venv/bin/python','-I','-B','/input/delivery/probe.py']
    marker = t.root/'jobs/attempt-cutoff/output/attempt-cutoff-count.txt'
    stopped = threading.Event()
    def expire_after_dispatch():
        end = time.monotonic()+10
        while not stopped.is_set() and not marker.exists() and time.monotonic()<end:
            stopped.wait(.01)
        if marker.exists(): now['boottime_ns'] += 41*10**9  #59s remain: payload must stop, cleanup reserve begins.
    watcher = threading.Thread(target=expire_after_dispatch);watcher.start()
    try:
        measured = t.measure('attempt-cutoff',argv,files)
        assert marker.read_text() == '1' and measured['passed'] is False and measured['timed_out'] is True
        plan = _json(t.root/'jobs/attempt-cutoff/launch.json')
        with t._cleanup_controls(): observed = t._inspect(plan)
        assert observed['State']['Running'] is False and observed['HostConfig']['NetworkMode'] == 'none'
        assert not any(m['Destination'] in {'/home/codex/.codex','/home/stev/.gemini','/var/run/docker.sock'} for m in observed['Mounts'])
        assert _json(t.root/'transport-policy.json')['schema'] == 6
        assert t.store.policy['schema'] == 4
        now['boottime_ns'] += 100*10**9  # Even after expiry, recovery is pure.
        original_cli = t._cli
        t._cli = lambda *a,**k:(_ for _ in ()).throw(AssertionError('closed measurement must not control Docker'))
        try:
            assert t.measure('attempt-cutoff',argv,files) == measured
            assert t.recover_test('attempt-cutoff',argv,files) == measured
            assert t.verify_test({'argv':argv,'test_job_ref':measured['test_job_ref']},files,require_passed=False)
        finally:t._cli = original_cli
        assert marker.read_text() == '1'
    finally:
        stopped.set();watcher.join(timeout=3)
        path=t.root/'jobs/attempt-cutoff/launch.json'
        if path.exists() and _json(path)['container_id']:
            t._cli(['rm','--force',_json(path)['container_id']],allow_failure=True)
