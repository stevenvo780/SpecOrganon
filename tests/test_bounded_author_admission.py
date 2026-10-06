"""Synthetic admission/recovery controls; these are not native method scores."""
import copy
from pathlib import Path
import pytest
from specorganon import engine
from specorganon.role_jobs import _json, _write, canonical, digest
from specorganon.software_controller import Controller, ControllerError
from test_software_controller import controller, SyntheticTransport, frame_response


def candidate(root, *, enabled=True, typed=False):
    old = controller(root, SyntheticTransport(frame_response()))
    # Construct a NEW bound policy, never reinterpret an existing run.
    return Controller(old.case, root/'candidate', old.transport, contract=old.contract,
                      mandate=old.mandate, fixture_mode=True, admission_repair=enabled,
                      author_format='items-v1' if typed else 'manifest-v1')


def authored(c, response):
    if c.author_format == 'manifest-v1': return response
    return {'schema':1,'items':[{k:v for k,v in s.items() if k!='op'}
        for s in response['manifest']['steps']], 'files':response['files'],'reason':response['reason']}


def oversize(ctrl):
    response = frame_response()
    response['manifest']['steps'][0]['text'] = '\\"' * 4000
    ctrl.transport.result = authored(ctrl,response)


@pytest.mark.parametrize('typed',[False,True])
def test_resource_rejection_consumes_slot_preserves_bytes_and_can_be_authored_again(tmp_path,typed):
    c = candidate(tmp_path,typed=typed); oversize(c)
    before = (c.case/'organon.json').read_bytes(); raw = copy.deepcopy(c.transport.result)
    rejected = c.step()
    assert rejected['status'] == 'rejected_resource_admission' and rejected['admitted'] is False
    assert (c.case/'organon.json').read_bytes() == before and c._files() == {}
    assert _json(Path(rejected['raw_packet_ref']))['result'] == raw
    assert digest(canonical(_json(Path(rejected['raw_packet_ref'])))) == rejected['raw_packet_sha256']
    costs = rejected['rejected_candidate_accounting']
    assert costs['phases']['frame'][1] > 6000 and costs['phase_limit']['encoded_bytes'] == 6000
    progress = _json(c.root/'progress.json')
    assert len(progress['history']) == 1 and progress['pending'] is None
    request = c._request(engine.get_state(c.case), 'author', progress)
    assert 'rejected_resource_admission' in request['documents']['previous-role-history.json']
    c.transport.result = authored(c,frame_response())
    assert c.step()['action'] == 'author'
    assert c.transport.calls == [('role-01-frame-author','author'),('role-02-frame-author','author')]
    assert not engine.get_state(c.case)['phases']['frame']['accepted']


def test_two_rejections_exhaust_original_phase_budget_no_third_call_even_after_resume(tmp_path):
    c = candidate(tmp_path); oversize(c)
    for _ in range(2): assert c.step()['admitted'] is False
    transport = SyntheticTransport(frame_response())
    resumed = Controller(c.case,c.root,transport,contract=c.contract,mandate=c.mandate,
                         fixture_mode=True,admission_repair=True)
    with pytest.raises(ControllerError,match='role budget'): resumed.step()
    assert transport.calls == [] and len(c.transport.calls) == 2
    assert engine.get_state(c.case)['items'] == {}


def test_resource_rejection_counts_against_global_ceiling(tmp_path):
    c = candidate(tmp_path); oversize(c); c.step()
    p=_json(c.root/'progress.json')
    p['history'] += [{'action':'review','phase':'study'} for _ in range(39)]
    _write(c.root/'progress.json',p)
    with pytest.raises(ControllerError,match='role budget'): c.step()
    assert len(c.transport.calls)==1


def test_interrupt_before_charged_rejection_commit_reuses_closed_packet_only(tmp_path,monkeypatch):
    c=candidate(tmp_path);oversize(c)
    finish=c._finish_role
    monkeypatch.setattr(c,'_finish_role',lambda *args: (_ for _ in ()).throw(RuntimeError('Synthetic interruption')))
    with pytest.raises(RuntimeError): c.step()
    assert _json(c.root/'progress.json')['pending']['status']=='closed'
    monkeypatch.setattr(c,'_finish_role',finish)
    assert c.step()['admitted'] is False
    assert len(c.transport.calls)==1
    assert len(_json(c.root/'progress.json')['history'])==1


@pytest.mark.parametrize('fault',['unknown_ref','fabricated_receipt','invalid_manifest','invalid_provenance','invalid_request_binding'])
def test_nonresource_and_integrity_failures_are_never_charged_as_retryable(tmp_path,fault):
    c=candidate(tmp_path)
    if fault=='unknown_ref': c.transport.result['manifest']['steps'][0]['refs']=['absent']
    elif fault=='fabricated_receipt': c.transport.result['manifest']['steps'][0]['data']={'passed':True}
    elif fault=='invalid_manifest': c.transport.result['manifest']['steps'][0]['op']='advance'
    else:
        original=c.transport.call
        def call(*args):
            packet=original(*args)
            packet['provenance' if fault=='invalid_provenance' else 'request_sha256']='invalid'
            return packet
        c.transport.call=call
    before=(c.case/'organon.json').read_bytes()
    with pytest.raises(ControllerError): c.step()
    assert (c.case/'organon.json').read_bytes()==before
    assert _json(c.root/'progress.json')['history']==[] and len(c.transport.calls)==1


def test_policy_cannot_enable_repair_for_historical_run(tmp_path):
    c=candidate(tmp_path,enabled=False);oversize(c)
    with pytest.raises(ControllerError,match='resource admission'):c.step()
    with pytest.raises(ControllerError,match='versioned run'):
        Controller(c.case,c.root,c.transport,contract=c.contract,mandate=c.mandate,
                   fixture_mode=True,admission_repair=True)


def test_applying_packet_is_not_discarded_or_retried_on_resource_error(tmp_path):
    c=candidate(tmp_path);oversize(c)
    # Persist a genuinely closed packet via a controlled interruption, then
    # mark applying to exercise the stricter recovery boundary.
    finish=c._finish_role
    c._finish_role=lambda *args: (_ for _ in ()).throw(RuntimeError('Synthetic interruption'))
    with pytest.raises(RuntimeError):c.step()
    c._finish_role=finish
    p=_json(c.root/'progress.json');p['pending']['status']='applying';_write(c.root/'progress.json',p)
    with pytest.raises(ControllerError,match='resource admission'):c.step()
    assert len(c.transport.calls)==1 and _json(c.root/'progress.json')['history']==[]
