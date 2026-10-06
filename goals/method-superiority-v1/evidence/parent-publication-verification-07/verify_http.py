"""Anonymous HTTP byte checks independent of the publication worker."""
import concurrent.futures
import datetime
import hashlib
from html.parser import HTMLParser
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
    assert any(p.parent.name == 'controles-dev6' for p in paths)
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
    old = json.loads((PUBLISHED/'goals/method-superiority-v1/evidence/parent-publication-verification-06/public-http-verification.json').read_text())
    assert len(old['files']) == 86
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
    engineering=json.loads((SOURCE/'goals/method-superiority-v1/evidence/staged-controls-01/engineering-receipt.json').read_text())
    names=[*engineering['source_sha256'], 'pyproject.toml','src/specorganon/__init__.py','src/specorganon/engine.py',
           'goals/method-superiority-v1/evidence/staged-controls-01/engineering-receipt.json',
           'goals/method-superiority-v1/evidence/staged-controls-01/code-review-06.json',
           'goals/method-superiority-v1/evidence/staged-controls-01/installed-receipt-05.json',
           'goals/method-superiority-v1/evidence/native02-terminal-01/summary.json',
           'goals/method-superiority-v1/evidence/native02-terminal-01/archive-verification.json','GOAL.md']
    for name in names:
        status, raw = read('https://raw.githubusercontent.com/stevenvo780/SpecOrganon/'+commit+'/'+name)
        assert status == 200 and raw == (SOURCE/name).read_bytes() == (PUBLISHED/name).read_bytes(), name
        checks[name] = hashlib.sha256(raw).hexdigest()
    status,html=read(URL+'/')
    assert status==200 and html==(Path('/datos/workspaces/personal/ViewSpecOrganon/web/dist/index.html')).read_bytes()
    class Assets(HTMLParser):
        def __init__(self):super().__init__();self.paths=[]
        def handle_starttag(self,tag,attributes):
            attrs=dict(attributes)
            if tag=='script' and attrs.get('type')=='module':self.paths.append(attrs['src'])
            elif tag=='link' and attrs.get('rel') in ('modulepreload','stylesheet'):self.paths.append(attrs['href'])
    parser=Assets();parser.feed(html.decode());assert parser.paths
    assets=[];module_text=''
    for path in parser.paths:
        assert path.startswith('/assets/') and '..' not in Path(path).parts
        status,data=read(URL+path);local=Path('/datos/workspaces/personal/ViewSpecOrganon/web/dist')/path.lstrip('/')
        assert status==200 and data==local.read_bytes(), path
        assets.append({'path':path,'http_status':status,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)})
        if path.endswith('.js'):module_text+=data.decode()
    assert 'controles-dev6' in module_text and '627' in module_text
    _,raw=read('https://api.github.com/repos/stevenvo780/SpecOrganon/commits/main')
    assert json.loads(raw)['sha']==commit, 'main moved during byte verification; rerun on final publication'
    receipt = {'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
               'canonical_url':URL,'main_commit':commit,'public_repository':True,'default_branch':'main',
               'manifests':manifests,'verified_downloads':len(files),'previous_86_sha_preserved':True,
               'anonymous_http':True,'canonical_page_HTTP200':True,'canonical_SPA_assets_byte_equal':True,'compiled_staged_texts_present':True,'rendered_UI_checked_by_parent':False,'assets':assets,'files':files,'source_sha256':checks,'new_model_calls':0,
               'goal_achieved':False,'scope':'Independent parent HTTP/source verification; UI verification belongs to worker receipt'}
    (BASE/'public-http-verification.json').write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n')
    print(json.dumps({k:v for k,v in receipt.items() if k not in {'files','source_sha256'}},ensure_ascii=False))


if __name__ == '__main__': main()
