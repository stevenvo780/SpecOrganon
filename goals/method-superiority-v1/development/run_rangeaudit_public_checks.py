"""Measure a completed native delivery with the public independent checker."""
import datetime
import hashlib
import json
from pathlib import Path
from specorganon.docker_roles import DockerRoles
from specorganon.role_jobs import _write


def main():
    base=Path(__file__).resolve().parent
    r=json.loads((base/'registration-rangeaudit-01.json').read_text())
    assert all(hashlib.sha256((Path(r['source_root'])/p).read_bytes()).hexdigest()==h for p,h in r['source_sha256'].items())
    run=Path(r['run_root'])
    actions=[json.loads(p.read_text()) for p in sorted(run.glob('action-*.json'))]
    assert actions[-1]['result'].get('package_allowed') is True,'Requires terminal nine-phase native package'
    files={str(p.relative_to(run/'controller/delivery')):p.read_text()
           for p in (run/'controller/delivery').rglob('*') if p.is_file()}
    checker=(base/'check_rangeaudit_public.py').read_text()
    checker_sha=hashlib.sha256(checker.encode()).hexdigest()
    root=run/'independent-public-checks'
    assert not (root/'registration.json').exists(),'No repeat of development evaluation'
    root.mkdir(mode=0o700,exist_ok=True)
    _write(root/'registration.json',{'schema':1,'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'classification':'post-generation independent public development checks; not reserved or blinded',
        'checker_sha256':checker_sha,'delivery_source_sha256':{n:hashlib.sha256(s.encode()).hexdigest() for n,s in files.items()},
        'case_sources_unchanged':True,'automatic_retry':False})
    files['check_rangeaudit_public.py']=checker
    transport=DockerRoles(root/'transport',native_image=r['native_image'],test_image=r['test_image'],
        source_root=Path(r['source_root']),public_catalog=Path(r['source_root'])/'experiments/software_comparison_v3/public-models.json',
        reviewer_model='Gemini 3.8 Flash (Medium)',codex_reasoning_effort='medium',
        seccomp=Path(r['source_root'])/'docker/codex/seccomp-codex.json')
    receipt=transport.measure('rangeaudit-public-contract-checks-01',
        ['/opt/specorganon/venv/bin/python','/input/delivery/check_rangeaudit_public.py'],files)
    _write(root/'result.json',receipt)
    print(json.dumps(receipt))


if __name__=='__main__':main()
