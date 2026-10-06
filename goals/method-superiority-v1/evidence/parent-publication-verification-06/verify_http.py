"""Anonymous HTTP byte checks independent of the publication worker."""
import concurrent.futures
import datetime
import hashlib
import json
from pathlib import Path
import urllib.parse
import urllib.request

BASE = Path(__file__).parent
PUBLISHED = Path('/home/stev/.codex/worktrees/publish-main/SpecOrganon')
SOURCE = Path('/home/stev/.codex/worktrees/strong-controls-v1/SpecOrganon')
URL = 'https://specorganon.stevenvallejo.com'


def read(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'SpecOrganon-independent-public-verifier'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.status, response.read()


def main():
    root = PUBLISHED/'website/public/resultados/software'
    paths = [root/'descargas-manifest.json', *sorted(root.glob('*/descargas-sha256.json'))]
    assert any(p.parent.name == 'avance-dev6' for p in paths)
    entries = {}; manifests = []
    for p in paths:
        relative = str(p.relative_to(root))
        status, raw = read(URL+'/resultados/software/'+relative)
        local = p.read_bytes()
        assert status == 200 and json.loads(raw) == json.loads(local), relative
        data = json.loads(local)
        prefix = str(p.parent.relative_to(root))
        if prefix == '.': prefix = ''
        for name, expected in data['files'].items():
            key = (prefix+'/' if prefix else '')+name
            assert key not in entries
            entries[key] = expected
        manifests.append(relative)
    assert any(p.parent.name == 'cohorte-dev4-terminal' for p in paths)
    old = json.loads((PUBLISHED/'goals/method-superiority-v1/evidence/parent-publication-verification-05/public-http-verification.json').read_text())
    assert len(old['files']) == 73
    assert all(entries.get(row['path']) == row['sha256'] for row in old['files'])
    def check(pair):
        name, expected = pair
        status, raw = read(URL+'/resultados/software/'+urllib.parse.quote(name,safe='/'))
        actual = hashlib.sha256(raw).hexdigest()
        assert status == 200 and actual == expected, name
        return {'path': name, 'http_status': status, 'sha256': actual, 'bytes': len(raw)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        files = list(pool.map(check, sorted(entries.items())))
    status, raw = read('https://api.github.com/repos/stevenvo780/SpecOrganon')
    repo = json.loads(raw)
    assert status == 200 and repo['private'] is False and repo['default_branch'] == 'main'
    _, raw = read('https://api.github.com/repos/stevenvo780/SpecOrganon/commits/main')
    commit = json.loads(raw)['sha']
    checks = {}
    names = ['pyproject.toml','src/specorganon/__init__.py','src/specorganon/docker_roles.py',
             'src/specorganon/native_response_contract.py','scripts/controller_native_role.py',
             'scripts/run_registered_native.py','examples/topoplan/topo_plan.py',
             'src/specorganon/neutral_author.py','src/specorganon/common_review.py',
             'src/specorganon/common_evidence.py',
             'goals/method-superiority-v1/evidence/native02-terminal-01/summary.json',
             'goals/method-superiority-v1/evidence/native02-terminal-01/archive-verification.json']
    for name in names:
        status, raw = read('https://raw.githubusercontent.com/stevenvo780/SpecOrganon/main/'+name)
        assert status == 200 and raw == (SOURCE/name).read_bytes() == (PUBLISHED/name).read_bytes(), name
        checks[name] = hashlib.sha256(raw).hexdigest()
    receipt = {'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
               'canonical_url':URL,'main_commit':commit,'public_repository':True,'default_branch':'main',
               'manifests':manifests,'verified_downloads':len(files),'previous_73_sha_preserved':True,
               'anonymous_http':True,'files':files,'source_sha256':checks,'new_model_calls':0,
               'goal_achieved':False,'scope':'Independent parent HTTP/source verification; UI verification belongs to worker receipt'}
    (BASE/'public-http-verification.json').write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n')
    print(json.dumps({k:v for k,v in receipt.items() if k not in {'files','source_sha256'}},ensure_ascii=False))


if __name__ == '__main__': main()
