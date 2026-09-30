from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import stat
import subprocess
import tarfile
import zipfile

REPO = Path('/workspace/SpecOrganon')
OUT = REPO / 'experiments/development/installed_complete_interface_2026-09-30'
D102 = REPO / 'experiments/development/lot_journal_prospectus_2026-09-30'


def pin(raw):
    return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}


def write(name, raw):
    p = OUT / name
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('xb') as f:
        f.write(raw)


def js(name, value):
    write(name, (json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n').encode())


def cp(source,name):
    raw = Path(source).read_bytes()
    write(name,raw)
    return pin(raw)


def bundle(source,name):
    source = Path(source)
    files, links = {}, {}
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer,mode='w') as tar:
        for path in sorted(source.rglob('*')):
            relative = str(path.relative_to(source))
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                links[relative] = str(path.readlink())
            elif stat.S_ISREG(mode):
                raw = path.read_bytes()
                assert b'-----BEGIN PRIVATE KEY-----' not in raw
                assert b'-----BEGIN OPENSSH PRIVATE KEY-----' not in raw
                files[relative] = pin(raw)
                info = tarfile.TarInfo(relative)
                info.size = len(raw)
                info.mode = 0o600
                tar.addfile(info,io.BytesIO(raw))
            elif not stat.S_ISDIR(mode) and not stat.S_ISFIFO(mode):
                raise ValueError('unexpected special file: '+relative)
    raw = buffer.getvalue()
    compressed = gzip.compress(raw,mtime=0)
    write(name,compressed)
    js(name+'.inventory.json',{'source':str(source),'files':files,'symlinks_metadata_only':links,
                             'decoded_tar':pin(raw),'compressed':pin(compressed),
                             'file_bytes_preserved':True,'file_times_permissions_not_attested':True,
                             'fifos_not_archived_as_files':True})
    with tarfile.open(fileobj=io.BytesIO(gzip.decompress(compressed))) as tar:
        for entry in tar:
            assert entry.isfile() and pin(tar.extractfile(entry).read()) == files[entry.name]
    return {'archive':name,'regular_files':len(files),'symlinks_metadata_only':len(links),
            'decoded_tar':pin(raw),'compressed':pin(compressed)}


archives=[]
for v in ('311','312'):
    for suffix in ('a','b'):
        source=Path('/tmp/specorganon-D103-transports-'+v+'-'+suffix)
        dest='transports/'+v+'/'+('initial_failed' if suffix=='a' else 'final')
        archives.append(bundle(source,dest+'/workspace.tar.gz'))
        for name in ('receipt.json','installed.json','pytest.stdout.txt','pytest.stderr.txt'):
            cp(source/name,dest+'/'+name)
        raw=(source/'transports.jsonl').read_bytes()
        write(dest+'/transports.jsonl.gz',gzip.compress(raw,mtime=0))
        assert gzip.decompress((OUT/dest/'transports.jsonl.gz').read_bytes())==raw
        for stream in ('stdout','stderr'):
            cp(str(source)+'.'+stream,dest+'/probe.'+stream)
    for group,label in (('signed','initial_summary_only'),('retained','final_retained')):
        prefix='/tmp/specorganon-D103-'+group+'-'+v+'-a' if group=='retained' else '/tmp/specorganon-D103-'+group+'-'+v
        for stream in ('stdout','stderr'):
            cp(prefix+'.'+stream,'signed/'+v+'/'+label+'/probe.'+stream)
        if group=='retained':
            archives.append(bundle(prefix,'signed/'+v+'/'+label+'/workspace.tar.gz'))
    final=json.loads((OUT/'transports'/v/'final/receipt.json').read_text())
    assert final['passed'] and len(final['test_reports'])==9
    assert all(r['outcome']=='passed' for r in final['test_reports'])

for stream in ('stdout','stderr'):
    cp('/tmp/specorganon-D103-smoke-312.'+stream,'smoke/312.'+stream)
cp('/tmp/specorganon-D103-pytest-install.json','environment/pytest-install.json')
cp('/tmp/specorganon-D103-pip-check.json','environment/pip-check.json')
archives.append(bundle('/tmp/specorganon-D103-native-o4sxm73a','native/workspace.tar.gz'))
for name in ('preparation.json','release.json','verification.json','verification-transports.json',
             'verification.stdout','verification.stderr'):
    cp(Path('/tmp/specorganon-D103-native-o4sxm73a')/name,'native/'+name)
cp('/tmp/verify_D103_native.py','native/verifier_executed.py')
for role in ('A','B'):
    for name in ('ready.json','receipt.json','calls.json','checks.json'):
        cp(Path('/tmp/specorganon-D103-native-o4sxm73a')/('writer-'+role)/name,'native/'+role+'/'+name)
    for stream in ('stdout','stderr'):
        cp('/tmp/specorganon-D103-native-o4sxm73a/writer-'+role+'.'+stream,'native/'+role+'/writer.'+stream)

freeze=json.loads((OUT/'source_freeze_amendment.json').read_text())
assert all(pin((REPO/name).read_bytes())==p for name,p in freeze['files'].items())
js('source_post_execution.json',{'recorded_at_utc':datetime.now(timezone.utc).isoformat(),
                               'all15_amended_pins_match':True,'files':freeze['files'],
                               'production_source_unchanged_since_D102':True})
wheel=(D102/'installed/specorganon-0.1.0-py3-none-any.whl').read_bytes()
assert pin(wheel)['sha256']=='e155d010a17a1235f071da6b0d89c1773b5dc92295a85251873f1880c448390b'
module_pins={}
with zipfile.ZipFile(io.BytesIO(wheel)) as archive:
    for name in archive.namelist():
        if name.startswith('specorganon/') and name.endswith('.py'):
            raw=archive.read(name)
            assert (REPO/'src'/name).read_bytes()==raw
            module_pins['src/'+name]=pin(raw)
assert len(module_pins)==24
js('environment/current_source_wheel_parity.json',{'all24_equal':True,'wheel':pin(wheel),'modules':module_pins})

smokes={
    '311':json.loads((D102/'validation/smoke-311.stdout').read_text()),
    '312':json.loads((OUT/'smoke/312.stdout').read_text()),
}
tools=smokes['312']['mcp_tools_discovered_names']
assert len(tools)==22 and tools==smokes['311']['mcp_tools_discovered_names']
coverage={'schema':1,'wheel':pin(wheel),'scope':'same installed D102 wheel, not union of historical wheel versions',
          'public_operations':[], 'each_python_positive_cli_and_mcp':22}
for op in tools:
    row={'operation':op,'python':{}}
    for v in ('311','312'):
        if op in smokes[v]['mcp_tools_seen']:
            evidence=str((D102/'validation/smoke-311.stdout').relative_to(REPO)) if v=='311' else str((OUT/'smoke/312.stdout').relative_to(REPO))
            row['python'][v]={'cli':True,'mcp':True,'parity':True,'effects_checked':True,
                             'source':'scripts/clean_smoke.py','evidence':evidence,
                             'capture_scope':'asserted summary with code hash, not per-call raw trace'}
        elif op=='audit_lot_journal':
            name='installed/'+v+'/transports.jsonl.gz'
            records=[json.loads(r) for r in gzip.decompress((D102/name).read_bytes()).splitlines()]
            assert records[0]['transport']=='cli' and records[0]['exit']==0
            response=records[4]['response']
            assert records[4]['tool']==op and not response['isError']
            mcp_value=response.get('structuredContent') or json.loads(response['content'][0]['text'])
            assert mcp_value==json.loads(records[0]['stdout']) and mcp_value['valid']
            row['python'][v]={'cli':True,'mcp':True,'parity':True,'effects_checked':True,
                             'source':'scripts/probe_bread_prospectus.py',
                             'evidence':str((D102/name).relative_to(REPO)),
                             'one_based_cli_line':1,'one_based_mcp_line':5,
                             'effects_scope':'pure declared audit output; no ledger effect'}
        else:
            dest=OUT/'transports'/v/'final'
            receipt=json.loads((dest/'receipt.json').read_text())
            records=[json.loads(r) for r in gzip.decompress((dest/'transports.jsonl.gz').read_bytes()).splitlines()]
            seqs={t:[r['seq'] for r in records if r['transport']==t and r.get('operation')==op and r['successful']] for t in ('cli','mcp')}
            assert all(seqs.values()) and all(receipt['positive_operations'][t][op]>0 for t in seqs)
            row['python'][v]={'cli':True,'mcp':True,'parity':True,'effects_checked':True,
                             'source':'scripts/probe_installed_signed_transports.py',
                             'evidence':str((dest/'transports.jsonl.gz').relative_to(REPO)),
                             'successful_seq':seqs,'effect_receipt':str((dest/'receipt.json').relative_to(REPO)),
                             'parity_scope':'same-head challenges and normalized distinct signed-record effects; statement signatures differ'}
    coverage['public_operations'].append(row)
js('coverage.json',coverage)
js('archives.json',archives)
preservation={}
receipt=json.loads((D102/'receipt.json').read_text())
for name,p in receipt['files'].items():
    actual=pin((REPO/name).read_bytes())
    assert actual==p,(name,actual,p)
    preservation[name]=p
js('preservation_before_documentation.json',{'d102_receipt_all97_match':len(preservation)==97,
                                         'files':preservation,'GOAL':pin((REPO/'GOAL.md').read_bytes()),
                                         'production24_unchanged':True,
                                         'documentation_updates_still_pending':True})
print(json.dumps({'archives':len(archives),'coverage_rows':len(coverage['public_operations']),
                  'production_modules':len(module_pins),'D102_pins':len(preservation)}))
