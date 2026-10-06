"""Schema2 content/stream custody and stale-audit guard fixtures only."""
import copy

import pytest

from specorganon.common_evidence import read_snapshot
from specorganon.common_review import checklist
from specorganon.ledger import strict_json_loads
from specorganon.role_jobs import canonical,digest,_json,_write
from test_common_evidence import fixture,seal
from test_neutral_controller import controller,PROGRAM


def upgraded(root):
    _,m=fixture(root);m['schema']=2;m['streams']={}
    value={'delivery':{n:(root/ref['path']).read_text() for n,ref in m['delivery'].items()},
           'documents':{n:(root/ref['path']).read_text() for n,ref in m['documents'].items()}}
    raw=canonical(value);sha=digest(raw);(root/'captures').mkdir();(root/'captures'/f'{sha}.json').write_bytes(raw)
    m['captures']={sha:{'path':f'captures/{sha}.json','sha256':sha}}
    return seal(root,m),m


def test_every_historical_checkpoint_has_accessible_unchanged_content(tmp_path):
    pin,m=upgraded(tmp_path);s=read_snapshot(tmp_path,pin)
    assert len(s['captures'])==1
    assert s['captures'][next(iter(s['captures']))]['documents']=={'notes.txt':'Original criterion: prints one'}
    assert any(n.startswith('capture:') for n in s['locators'])


@pytest.mark.parametrize('fault',['removed','wrong_name','changed_old_content','no_stream_map','unbound_stream','missing_cp_capture'])
def test_unavailable_or_rewritten_original_content_cannot_become_order_proof(tmp_path,fault):
    _,m=upgraded(tmp_path);name=next(iter(m['captures']));ref=m['captures'][name]
    if fault=='removed':m['captures']={}
    elif fault=='wrong_name':m['captures']['b'*64]=m['captures'].pop(name)
    elif fault=='changed_old_content':(tmp_path/ref['path']).write_bytes(b'{}')
    elif fault=='no_stream_map':del m['streams']
    elif fault=='unbound_stream':m['streams']['unknown/stdout']=m['contract']
    elif fault=='missing_cp_capture':
        cp=m['checkpoints'][0];value=_json(tmp_path/cp['path']);value['delivery_sha256']='c'*64
        raw=canonical(value);(tmp_path/cp['path']).write_bytes(raw);cp['sha256']=digest(raw)
        previous=cp['sha256']
        for cp in m['checkpoints'][1:]:
            value=_json(tmp_path/cp['path']);value['previous_sha256']=previous;raw=canonical(value)
            (tmp_path/cp['path']).write_bytes(raw);cp['sha256']=digest(raw);previous=cp['sha256']
    with pytest.raises(ValueError):read_snapshot(tmp_path,seal(tmp_path,m))


def test_DG_refusal_then_repair_requires_second_measure_and_second_bound_audit(tmp_path):
    c=controller(tmp_path/'run')
    for _ in range(4):c.step()
    t=c.transport;original=t.call
    def refuse_once(job,role,request):
        packet=original(job,role,request)
        if request['documents']['stage.txt']=='audit' and job=='neutral-0005-audit':
            packet['result']['audit']['D']['d8']['status']='fail'
            _write(t.store.root/job/'fixture-packet.json',packet)
        return packet
    t.call=refuse_once
    c.step()
    assert _json(c.root/'generations/0005.json')['state']['stage']=='repair'
    repair={'schema':1,'files':{'README.md':'Corrected synthetic documentation'},'documents':{},'reason':'DG documentary defect correction'}
    t.responses['repair']=repair
    report=c.run();assert report['status']=='review_ready',report
    assert report['counts']['test_runs']==report['counts']['stages']['audit']==2
    audits=[_json(p) for p in sorted((c.root/'reservations').iterdir()) if _json(p)['stage']=='audit']
    bindings=[strict_json_loads(r['request']['documents']['review-response-format.json'])['binding'] for r in audits]
    assert bindings[0]['delivery_sha256']!=bindings[1]['delivery_sha256']
    assert bindings[0]['history_sha256']!=bindings[1]['history_sha256']


def test_stale_audit_binding_fails_without_promoting_old_assertions(tmp_path):
    c=controller(tmp_path/'run')
    for _ in range(4):c.step()
    t=c.transport;original=t.call
    def stale(job,role,request):
        packet=original(job,role,request)
        packet['result']['audit']['binding']['delivery_sha256']='d'*64
        _write(t.store.root/job/'fixture-packet.json',packet)
        return packet
    t.call=stale;report=c.step()
    assert report['status']=='failed' and not report['common_review_ready']
    assert report['counts']['stages']['audit']==1 and report['native_ready'] is False


def test_atomic_snapshot_preserves_invalid_JSON_authored_as_plain_document(tmp_path):
    c=controller(tmp_path/'run');t=c._get_transport()
    t.responses['plan']={'schema':1,'files':{},'documents':{'own.json':'Plain evidence, deliberately not valid JSON'},'reason':'Own prose in arbitrary safe filename'}
    report=c.run();assert report['status']=='review_ready',report
    reservation=_json(c.root/'reservations/0005.json')
    s=read_snapshot(reservation['snapshot']['path'],reservation['snapshot']['manifest_sha256'])
    assert s['documents']['own.json']=='Plain evidence, deliberately not valid JSON'
