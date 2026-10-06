"""Standalone archive hash/link inspection; no Docker/model/test execution.

Trusted manifest and original bound-driver physical report remain required.
Consistent copied records do not independently attest an untrusted operator.
"""
import hashlib
import json
from pathlib import Path

BASE=Path(__file__).resolve().parent


def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()


def read(name):
    rel=Path(name)
    if rel.is_absolute() or '..' in rel.parts:raise ValueError('unsafe archive name')
    path=BASE/rel
    if any(p.is_symlink() for p in [path,*path.parents]):raise ValueError('symlink in archive path')
    if not path.resolve().is_relative_to(BASE) or path.stat().st_nlink!=1:raise ValueError('unsafe archive file')
    return path.read_bytes()


def data(name):return json.loads(read(name))


def main():
    manifest=data('manifest.sha256.json')
    for name,expected in manifest.items():
        raw=read(name);assert sha(raw)==expected['sha256'] and len(raw)==expected['bytes'],name
    registration=data('registration.json')
    assert sha(read('registration.json'))=='923d5f1d6dac9b9271d1f311c5c714c848782e0bd40afe6f49ef87ba87552055'
    for name,expected in registration['source_sha256'].items():assert sha(read('source/'+name))==expected
    for i in range(1,11):
        prefix=f'attempt-{i:02d}/';closed=data(prefix+'outcome-closure.json')
        assert sha(read(prefix+'outcome.json'))==closed['outcome_sha256']
        assert sha(read(prefix+'started.json'))==closed['start_sha256']
        assert sha(read(prefix+'case/organon.json'))==closed['case_sha256']
        actual={p.name:sha(read(str(p.relative_to(BASE)))) for p in (BASE/prefix).glob('action-*.json')}
        assert actual==closed['actions_sha256']
    receipts=0
    for p in sorted(BASE.glob('attempt-*/**/host-journal/*/receipt.json')):
        folder=p.parent;receipt=json.loads(p.read_bytes());req=json.loads((folder/'request.json').read_bytes())
        assert sha(canonical(req))==receipt['request_sha256']
        for name in ('stdout','stderr'):
            raw=(folder/(name+'.bin')).read_bytes()
            assert sha(raw)==receipt[name+'_sha256'] and len(raw)==receipt[name+'_bytes']
        assert receipt['argv']==req['argv'] and receipt['metadata']==req['metadata']
        receipts+=1
    result={'scope':'Copied archive digest/closure/host receipt link verification only; no new executions or semantic attestations',
            'manifest_files_verified':len(manifest),'registered_sources_verified':len(registration['source_sha256']),
            'closures_verified':10,'host_receipts_linked':receipts,'new_model_or_test_calls':0,
            'original_physical_report_exit_code':0,'goal_achieved':False}
    print(json.dumps(result,sort_keys=True,indent=2))


if __name__=='__main__':main()
