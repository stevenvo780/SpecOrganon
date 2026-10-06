"""Custody guard fixtures, never comparative or native-generation evidence."""
import copy

import pytest

from specorganon.common_evidence import read_snapshot, validate_bound_audit
from specorganon.common_review import checklist
from specorganon.role_jobs import canonical, digest


def fixture(root, *, receipt=False):
    def put(name, raw):
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        return {'path':name,'sha256':digest(raw)}
    files={'program.py':'print(1)\n','README.md':'Synthetic documentation only'}
    docs={'notes.txt':'Original criterion: prints one'}
    history=[];prev=None
    for i,kind in enumerate(('criteria','delivery','tests','execution','review'),1):
        event={'schema':1,'id':f'cp{i}','sequence':i,'previous_sha256':prev,'kind':kind,
               'job_id':f'job-{i}','request_sha256':'a'*64,
               'delivery_sha256':digest(canonical(files)),'documents_sha256':digest(canonical(docs))}
        ref=put(f'checkpoints/cp{i}.json',canonical(event));history.append({'id':event['id'],**ref});prev=ref['sha256']
    manifest={'schema':1,'method':'N','contract':put('host/contract.txt',b'Public fixture contract'),
              'policy':put('host/policy.json',canonical({'scope':'Fixture policy'})),
              'delivery':{n:put('delivery/'+n,v.encode()) for n,v in files.items()},
              'documents':{n:put('documents/'+n,v.encode()) for n,v in docs.items()},
              'checkpoints':history,'receipts':{}}
    if receipt:
        manifest['receipts']['test-01']={**put('receipts/test-01.json',canonical({'fixture':True})), 'kind':'test'}
    return seal(root,manifest),manifest


def seal(root,manifest):
    raw=canonical(manifest);(root/'snapshot.json').write_bytes(raw);return digest(raw)


def audit(snapshot,locators=None):
    d={'schema':1,'format':'common-audit-v1','method':snapshot['method'],
       'binding':snapshot['binding'],'locators':locators or ['document:notes.txt','checkpoint:cp1','delivery:README.md']}
    r={'schema':1,'verdict':'inconclusive','reason':'Fixture only; no independent generation',
       'findings':[],'tests_executed':False,'audit':{'binding':d['binding'],**{
           group:{name:{'status':'inconclusive','reason':'Fixture','evidence':[]} for name in points}
           for group,points in checklist(snapshot['method']).items()}}}
    return d,r


def test_captured_free_notes_do_not_require_SDD_files_or_prove_completion(tmp_path):
    pin,_=fixture(tmp_path);snapshot=read_snapshot(tmp_path,pin);d,r=audit(snapshot)
    result=validate_bound_audit(snapshot,d,r)
    assert result['review']==r and result['assertions']['H_applicable'] is False
    assert 'common_complete' not in result and 'passed' not in result
    assert snapshot['documents']=={'notes.txt':'Original criterion: prints one'}
    assert result['physical_locators_verified']==d['locators']


@pytest.mark.parametrize('fault',['wrong_pin','mutated_delivery','mutated_documents','extra_key',
    'bool_schema','reordered_chain','duplicate_checkpoint','duplicate_physical_path',
    'unsafe_path','newline_path','symlink','missing_file','stale_final_tree','bad_policy','empty_delivery'])
def test_physical_divergence_or_unsafe_material_fails_closed(tmp_path,fault):
    pin,m=fixture(tmp_path)
    if fault=='wrong_pin':pin='b'*64
    elif fault=='mutated_delivery':(tmp_path/'delivery/program.py').write_text('print(2)')
    elif fault=='mutated_documents':(tmp_path/'documents/notes.txt').write_text('Later criteria')
    elif fault=='extra_key':m['author_declared_pass']=True
    elif fault=='bool_schema':m['schema']=True
    elif fault=='reordered_chain':m['checkpoints'][0],m['checkpoints'][1]=m['checkpoints'][1],m['checkpoints'][0]
    elif fault=='duplicate_checkpoint':m['checkpoints'][1]['id']='cp1'
    elif fault=='duplicate_physical_path':m['documents']['notes.txt']=m['delivery']['README.md']
    elif fault in ('unsafe_path','newline_path'):m['contract']['path']='../outside' if fault=='unsafe_path' else 'host/contract.txt\n'
    elif fault=='symlink':
        p=tmp_path/'delivery/program.py';p.unlink();p.symlink_to(tmp_path/'delivery/README.md')
    elif fault=='missing_file':(tmp_path/'delivery/program.py').unlink()
    elif fault=='stale_final_tree':
        raw=b'print(2)\n';(tmp_path/'delivery/program.py').write_bytes(raw);m['delivery']['program.py']['sha256']=digest(raw)
    elif fault=='bad_policy':
        raw=canonical([]);(tmp_path/'host/policy.json').write_bytes(raw);m['policy']['sha256']=digest(raw)
    elif fault=='empty_delivery':m['delivery']={}
    if fault not in ('wrong_pin','mutated_delivery','mutated_documents','symlink','missing_file'):pin=seal(tmp_path,m)
    with pytest.raises(ValueError):read_snapshot(tmp_path,pin)


@pytest.mark.parametrize('fault',['binding','method','fake_locator','document_as_receipt'])
def test_audit_cannot_rebind_or_promote_document_to_receipt(tmp_path,fault):
    pin,_=fixture(tmp_path);s=read_snapshot(tmp_path,pin);d,r=audit(s)
    if fault=='binding':d['binding']=dict(d['binding'],history_sha256='b'*64);r['audit']['binding']=d['binding']
    if fault=='method':
        d['method']='S';r['audit']['H']={name:{'status':'inconclusive','reason':'Fixture','evidence':[]} for name in checklist('S')['H']}
    if fault=='fake_locator':d['locators']=['delivery:invented.py']
    if fault=='document_as_receipt':d['locators']=['receipt:notes.txt']
    before=copy.deepcopy(r)
    with pytest.raises(ValueError):validate_bound_audit(s,d,r)
    assert r==before


@pytest.mark.parametrize('verifier',[None,False,lambda *args:False,lambda *args:1])
def test_hash_matching_receipt_file_without_trusted_verifier_is_never_execution(tmp_path,verifier):
    pin,_=fixture(tmp_path,receipt=True);s=read_snapshot(tmp_path,pin);d,r=audit(s,['receipt:test-01'])
    with pytest.raises(ValueError):validate_bound_audit(s,d,r,verify_receipt=verifier)


def test_host_verifier_receives_captured_receipt_and_cannot_mutate_review(tmp_path):
    pin,_=fixture(tmp_path,receipt=True);s=read_snapshot(tmp_path,pin);d,r=audit(s,['receipt:test-01']);seen=[]
    def verifier(name,kind,value,snapshot):
        seen.append((name,kind,value));snapshot['binding'].clear();value['fixture']='changed'
        return True
    result=validate_bound_audit(s,d,r,verify_receipt=verifier)
    assert seen[0][:2]==('test-01','test') and s['receipts']['test-01']['value']=={'fixture':True}
    assert s['binding'] and result['review']==r
    assert 'common_complete' not in result


@pytest.mark.parametrize('schema',[1.0,True,'1'])
def test_physical_audit_entry_also_rejects_inexact_schema(tmp_path,schema):
    pin,_=fixture(tmp_path);s=read_snapshot(tmp_path,pin);d,r=audit(s);r['schema']=schema
    with pytest.raises(ValueError):validate_bound_audit(s,d,r)
