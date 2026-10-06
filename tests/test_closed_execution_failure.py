"""Negative execution custody/recovery guards; no model calls or native evidence."""
import copy

import pytest

from specorganon.docker_roles import ClosedNativeExecutionError, DockerRoleError
from specorganon.role_jobs import _json, _write
from test_closed_native_role import closed
from test_staged_review_regressions import rebind


def fail(closed, *, exit_code=1, timed_out=False, truncated=None, oom=False):
    t, folder, request, packet, result = closed
    receipt = _json(t.store.root/'author-01/receipt.json')
    receipt.update(exit_code=exit_code, timed_out=timed_out, truncated_streams=truncated or [])
    rebind(t.store.root, 'author-01', receipt=receipt)
    terminal = _json(folder/'terminal-container.json')
    terminal.update(exit_code=exit_code, oom_killed=oom)
    _write(folder/'terminal-container.json', terminal)
    return t, folder, request, packet


@pytest.mark.parametrize('options', [
    {'exit_code':1}, {'exit_code':2}, {'exit_code':127}, {'exit_code':-9,'timed_out':True},
    {'exit_code':0,'truncated':['stdout']}, {'exit_code':137,'oom':True}])
def test_original_failed_execution_recovers_read_only_without_accepted_body(closed, options):
    t, folder, request, packet = fail(closed, **options)
    proof = t.recover_execution_failure('author-01','author',request)
    assert proof['acceptance'] is False and proof['native_invocation_established'] is False
    assert 'result' not in proof and 'invocation_metadata' not in proof
    assert t.verify_execution_failure(proof,'author-01','author',request) is True
    # Fixture disables all execution/control calls. Repeated recovery reads only
    # the exact original host journal, regardless of any parseable body in stdout.
    for _ in range(2):
        with pytest.raises(ClosedNativeExecutionError) as caught:
            t.recover_role('author-01','author',request)
        assert caught.value.proof == proof
    with pytest.raises(ValueError): t.verify_role(packet,'author-01','author',request)


def test_successful_execution_cannot_be_converted_to_failure(closed):
    t, _, request, packet, _ = closed
    assert t.recover_execution_failure('author-01','author',request) is None
    assert t.recover_role('author-01','author',request) == packet
    with pytest.raises(DockerRoleError): t.verify_execution_failure({},'author-01','author',request)


@pytest.mark.parametrize('fault', ['proof','request','role','stream','closing_marker','input',
    'terminal_id','terminal_image','terminal_bool_exit','terminal_bool_oom','launch','intent','source'])
def test_failed_execution_requires_all_original_custody_and_exact_proof(closed, fault, monkeypatch):
    t, folder, request, _ = fail(closed)
    proof = t.recover_execution_failure('author-01','author',request); role = 'author'
    if fault == 'proof': proof['failure_reasons'].append('invented')
    elif fault == 'request': request['role_instructions'] = 'replacement'
    elif fault == 'role': role = 'review'
    elif fault == 'stream': (t.store.root/'author-01/stderr.bin').write_bytes(b'changed')
    elif fault == 'closing_marker': _write(t.store.root/'.complete-author-01.json',{'changed':True})
    elif fault == 'input': (folder/'input/request.json').write_bytes(b'{}')
    elif fault.startswith('terminal_'):
        terminal = _json(folder/'terminal-container.json')
        key,value = {'terminal_id':('id','f'*64),'terminal_image':('image_id','sha256:'+'e'*64),
                     'terminal_bool_exit':('exit_code',True),'terminal_bool_oom':('oom_killed',1)}[fault]
        terminal[key] = value; _write(folder/'terminal-container.json',terminal)
    elif fault == 'launch': (folder/'launch.json').unlink()
    elif fault == 'intent': _write(folder/'create-attempt.json',{'changed':True})
    elif fault == 'source': monkeypatch.setattr(t,'_native_source_bytes',lambda:{'changed':b'changed'})
    with pytest.raises((ValueError,KeyError)):
        t.verify_execution_failure(proof,'author-01',role,request)


@pytest.mark.parametrize('missing', ['receipt.json','terminal-container.json'])
def test_unclosed_execution_is_not_a_proven_failure(closed, missing):
    t, folder, request, _ = fail(closed)
    target = (t.store.root/'author-01' if missing == 'receipt.json' else folder)/missing
    target.unlink()
    assert t.recover_execution_failure('author-01','author',request) is None


def negative_fixture(transport):
    """A deliberately synthetic negative journal for controller crash guards."""
    from specorganon.role_jobs import canonical, digest
    original_call = transport.call; original_recover = transport.recover_role
    proofs = {}; dispatched = []
    def recover(job,role,request):
        if job in proofs:
            proof = proofs[job]
            assert proof['role'] == role and proof['request_sha256'] == digest(canonical(request))
            raise ClosedNativeExecutionError(copy.deepcopy(proof))
        return original_recover(job,role,request)
    def failed_call(job,role,request):
        if job in proofs: return recover(job,role,request)
        dispatched.append(job)
        proof = {'schema':1,'provenance':'fixture_closed_execution_failure','job_id':job,
                 'role':role,'request_sha256':digest(canonical(request)),
                 'acceptance':False,'native_invocation_established':False}
        proofs[job] = proof
        raise ClosedNativeExecutionError(copy.deepcopy(proof))
    def verify(proof,job,role,request):
        return (proof == proofs.get(job) and proof['role'] == role
                and proof['request_sha256'] == digest(canonical(request)))
    transport.recover_role = recover; transport.verify_execution_failure = verify
    return failed_call, original_call, dispatched, proofs


@pytest.mark.parametrize('method',['N','S'])
def test_N_S_crash_after_closed_failure_never_redispatches_or_replaces(tmp_path, monkeypatch, method):
    import specorganon.neutral_controller as module
    from test_neutral_controller import controller
    c = controller(tmp_path/'run',method); t = c._get_transport()
    t.call, _, dispatched, _ = negative_fixture(t)
    write = module._write
    def crash(path,value,**kwargs):
        if path == c.root/'results/0001.json': raise KeyboardInterrupt('cut after failure before capture')
        return write(path,value,**kwargs)
    monkeypatch.setattr(module,'_write',crash)
    with pytest.raises(KeyboardInterrupt): c.step()
    assert len(dispatched) == 1
    monkeypatch.setattr(module,'_write',write)
    t.call = lambda *args: (_ for _ in ()).throw(AssertionError('must recover exact failed journal'))
    report = c.step()
    assert report['status'] == 'failed' and report['counts']['roles'] == 1
    assert report['fixture_mode'] and report['native_ready'] is False
    assert report['common_review_ready'] is False and report['method_review_ready'] is False
    assert c.step() == report and len(dispatched) == 1
    assert _json(c.root/'results/0001.json')['kind'] == 'execution_error'


def test_T_crash_after_closed_failure_captures_original_without_redispatch(tmp_path,monkeypatch):
    from test_t_common_controller import make
    import specorganon.t_common_controller as module
    c,_ = make(tmp_path); c._get_controller(); t = c.transport
    t.call, _, dispatched, _ = negative_fixture(t)
    write = module._put
    def crash(path,raw):
        if path.name == 'after.json': raise KeyboardInterrupt('cut after negative journal before command closure')
        return write(path,raw)
    monkeypatch.setattr(module,'_put',crash)
    with pytest.raises(KeyboardInterrupt): c.step()
    assert len(dispatched) == 1
    monkeypatch.setattr(module,'_put',write)
    t.call = lambda *args: (_ for _ in ()).throw(AssertionError('must recover exact failure'))
    report = c.run()
    assert report['status'] == 'failed' and report['counts']['roles'] == 1
    assert report['native_ready'] is False and report['external_F'] is None
    assert c.step() == report and len(dispatched) == 1
    assert _json(c.root/'commands/0001/after.json')['closed_result']['kind'] == 'execution_error'


def test_common_T_auditor_failure_is_bound_and_verified_after_terminal_cut(tmp_path,monkeypatch):
    from test_t_common_controller import make
    import specorganon.t_common_controller as module
    c,_ = make(tmp_path); c._get_controller(); t = c.transport
    failed_call, original_call, dispatched, proofs = negative_fixture(t)
    def call(job,role,request):
        return failed_call(job,role,request) if 'evidence-context.json' in request['documents'] else original_call(job,role,request)
    t.call = call; write = module._put
    def crash(path,raw):
        if path.name == 'terminal-intent.json': raise KeyboardInterrupt('cut after failed auditor before terminal')
        return write(path,raw)
    monkeypatch.setattr(module,'_put',crash)
    with pytest.raises(KeyboardInterrupt): c.run()
    assert len(dispatched) == 1 and (c.root/'audit/failure-0001.json').exists()
    monkeypatch.setattr(module,'_put',write)
    t.call = lambda *args: (_ for _ in ()).throw(AssertionError('failed auditor must not be invoked again'))
    report = c.run()
    assert report['status'] == 'failed' and not report['native_ready']
    assert not report['common_review_ready'] and not report['method_review_ready']
    assert report['audit_failure_sha256'] and report['audit_reservation_sha256']
    assert c.step() == report and len(dispatched) == 1
    next(iter(proofs.values()))['acceptance'] = True
    with pytest.raises(ValueError,match='failure does not verify'): c.step()
