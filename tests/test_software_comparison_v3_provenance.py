"""Real bounded journal integrity and synthetic isolation guards; no model calls.

Synthetic Docker inspection records exercise rejection only. They are never
accepted native role receipts, programmes or nine-phase milestone evidence.
"""
import copy
import sys

import pytest

from experiments.software_comparison_v3.provenance import NativeEvidence,ProvenanceError,journal_receipt
from specorganon.role_jobs import JobStore,JobError,_json,_write,canonical,digest


def closed(root):
    store=JobStore(root/'journal')
    packet=store.execute('control',[sys.executable,'-c',"print('integrity control')"],
        {'scope':'bounded real Python integrity process, not a native role'},cwd=root,timeout_seconds=5)
    return store,packet['receipt']


def inventory(root):
    return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_closed_journal_read_is_pure_and_returns_actual_process_streams(tmp_path):
    store,expected=closed(tmp_path);before=inventory(store.root)
    for _ in range(2):
        receipt,envelope,streams=journal_receipt(store.root,'control')
        assert receipt==expected and envelope['request']['scope'].startswith('bounded real')
        assert streams=={'stdout':b'integrity control\n','stderr':b''}
    assert inventory(store.root)==before


@pytest.mark.parametrize('target',['stdout','request','receipt','closing','started'])
def test_journal_tamper_refuses_read_without_any_new_execution(tmp_path,target):
    store,_=closed(tmp_path);job=store.root/'control'
    if target=='stdout':(job/'stdout.bin').write_bytes(b'forged model success')
    elif target=='request':
        v=_json(job/'request.json');v['request']={'forged':'replacement'};_write(job/'request.json',v)
    elif target=='receipt':
        v=_json(job/'receipt.json');v['timed_out']=True;_write(job/'receipt.json',v)
    elif target=='closing':(store.root/'.complete-control.json').unlink()
    else:
        v=_json(job/'started.json');v['metadata']={'forged':True};_write(job/'started.json',v)
    before=inventory(store.root)
    with pytest.raises((JobError,ProvenanceError)):journal_receipt(store.root,'control')
    assert inventory(store.root)==before


def test_read_rejects_redirected_or_public_writable_journal(tmp_path):
    store,_=closed(tmp_path);link=tmp_path/'redirect';link.symlink_to(store.root,target_is_directory=True)
    with pytest.raises(JobError):journal_receipt(link,'control')
    store.root.chmod(0o777)
    with pytest.raises(ProvenanceError,match='private owned'):journal_receipt(store.root,'control')


class SyntheticInspection:
    """Inspection fixture only; no Docker or native process is invoked."""
    def __init__(self,root):
        self.root=root;self.source=root/'source';self.images={'native':'a','test':'b'}
        self.routes={'author':('codex','model-fixture'),'review':('gemini','model-fixture')}
        self.calls=0
    def _inventory(self,path):return {str(p.relative_to(path)):digest(p.read_bytes()) for p in path.rglob('*') if p.is_file()}
    def _inspect(self,plan):self.calls+=1;return self.observed


def synthetic_transport(root):
    root.mkdir();t=SyntheticInspection(root)
    _write(root/'transport-policy.json',{'schema':3,'source_root':str(t.source),'images':t.images,
        'routes':t.routes,'codex_original_volume':'specorganon-lab_codex-home',
        'gemini_original_profile':'/home/stev/.gemini'})
    return t


@pytest.mark.parametrize('field,value',[
    ('codex_original_volume','unauthorized-account'),('gemini_original_profile','/another/profile'),
    ('source_root','/changed/source'),('routes',{'author':['codex','a'],'review':['codex','b']})])
def test_original_account_family_source_policy_changes_rejected(tmp_path,field,value):
    t=synthetic_transport(tmp_path/'transport');p=_json(t.root/'transport-policy.json');p[field]=value
    _write(t.root/'transport-policy.json',p)
    with pytest.raises(ProvenanceError):NativeEvidence(t)
    assert t.calls==0


def test_native_label_without_physical_receipts_cannot_qualify(tmp_path):
    t=synthetic_transport(tmp_path/'transport');proof=NativeEvidence(t)
    with pytest.raises(JobError):proof.role('invented-label','review',packet={'provenance':'native','actor':'reviewer:gemini'})
    assert t.calls==0


def inspection_fixture(root,monkeypatch):
    """Simulated terminal inspection with mocked receipt; no physical evidence."""
    from experiments.software_comparison_v3 import provenance
    t=synthetic_transport(root);folder=root/'jobs'/'test-control';(folder/'input').mkdir(parents=True)
    request={'schema':1,'argv':['/opt/test/python','test_control.py']}
    _write(folder/'input/request.json',request)
    label=digest(canonical({'root':str(root),'job_id':'test-control'}))[:24]
    plan={'job_id':'test-control','role':'test','provider':None,'model':None,'image_id':'b',
        'container_id':'synthetic-container','request_sha256':digest(canonical(request)),
        'label':label,'name':'specorganon-role-'+label,'input_manifest':t._inventory(folder/'input')}
    _write(folder/'launch.json',plan)
    _write(folder/'terminal-container.json',{'id':'synthetic-container','exit_code':0,'image_id':'b','oom_killed':False})
    t.observed={'Id':'synthetic-container','Image':'b','State':{'Running':False,'OOMKilled':False,'ExitCode':0},
        'HostConfig':{'ReadonlyRootfs':True,'Privileged':False,'CapDrop':['ALL'],'SecurityOpt':['no-new-privileges'],
            'Memory':1073741824,'NanoCpus':2000000000,'PidsLimit':128,'NetworkMode':'none'},
        'Mounts':[{'Destination':'/input','Source':str(folder/'input'),'RW':False},
                  {'Destination':'/output','Source':str(folder/'output'),'RW':True}],
        'Config':{'User':'ubuntu','Cmd':request['argv'],'Entrypoint':[],'WorkingDir':'/input/delivery'}}
    receipt={'metadata':{k:plan[k] for k in ('role','provider','model','image_id','container_id','input_manifest')},
        'argv':['/usr/bin/docker','start','--attach','synthetic-container'],'cwd':str(root),
        'timed_out':False,'truncated_streams':[],'exit_code':0}
    env={'request':request,'cancel_argv':['/usr/bin/docker','kill','synthetic-container']}
    monkeypatch.setattr(provenance,'journal_receipt',lambda *a:(receipt,env,{}))
    return t,NativeEvidence(t)


@pytest.mark.parametrize('change',['memory','cpu','pids','root','network','credentials','writable_input','command','running','exit'])
def test_altered_inspection_cannot_pass_isolation_layer(tmp_path,monkeypatch,change):
    t,proof=inspection_fixture(tmp_path/'transport',monkeypatch)
    # This is only an inspection-layer schema control. A native role would still
    # need real inner/outer journal closures, sources, stream parsing and catalog.
    assert proof._execution('test-control','test')[1]['container_id']=='synthetic-container'
    o=t.observed
    if change=='memory':o['HostConfig']['Memory']=0
    elif change=='cpu':o['HostConfig']['NanoCpus']=0
    elif change=='pids':o['HostConfig']['PidsLimit']=0
    elif change=='root':o['Config']['User']='0'
    elif change=='network':o['HostConfig']['NetworkMode']='bridge'
    elif change=='credentials':o['Mounts'].append({'Destination':'/auth','Source':'/credential-fixture','RW':True})
    elif change=='writable_input':o['Mounts'][0]['RW']=True
    elif change=='command':o['Config']['Cmd']=['/unregistered/python','replacement.py']
    elif change=='running':o['State']['Running']=True
    else:o['State']['ExitCode']=3
    with pytest.raises(ProvenanceError):proof._execution('test-control','test')


def test_read_only_test_verifies_full_measurement_without_constructing_transport_journal(tmp_path,monkeypatch):
    t=synthetic_transport(tmp_path/'transport');proof=NativeEvidence(t)
    folder=t.root/'jobs'/'test-control';(folder/'input').mkdir(parents=True)
    files={'test_control.py':'print("mechanics only")\n'}
    request={'schema':1,'argv':['/opt/test/python','/input/delivery/test_control.py'],'delivery_tree_sha256':digest(canonical(files))}
    receipt={'exit_code':0,'timed_out':False,'truncated_streams':[]}
    plan={'image_id':'b','container_id':'synthetic-container','input_manifest':{'delivery/test_control.py':digest(files['test_control.py'].encode())}}
    _write(folder/'terminal-container.json',{'exit_code':0})
    measured={**receipt,'subject_argv':request['argv'],'attachment_exit_code':0,'exit_code':0,
        'test_job_ref':str(t.root/'host-journal'/'test-control'/'receipt.json'),
        'delivery_tree_sha256':digest(canonical(files)),'image_id':'b','container_id':'synthetic-container',
        'provenance':'actual_isolated_container','passed':True}
    _write(folder/'measured-test.json',measured)
    monkeypatch.setattr(proof,'_execution',lambda *a,**k:(folder,plan,request,receipt,{}))
    # This fixture explicitly bypasses physical execution; tests only the second
    # strict measurement layer. Its returned dict is NOT native milestone proof.
    assert proof.test('test-control',files)['passed'] is True and not hasattr(t,'store')
    measured['stdout_sha256']='invented';_write(folder/'measured-test.json',measured)
    with pytest.raises(ProvenanceError,match='measured test'):proof.test('test-control',files)
