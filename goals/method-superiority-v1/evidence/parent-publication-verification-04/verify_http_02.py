"""Anonymous production/source verification; no account credentials."""
from pathlib import Path
import concurrent.futures,datetime,hashlib,json,urllib.request,urllib.parse
base=Path(__file__).parent
published=Path('/home/stev/.codex/worktrees/publish-main/SpecOrganon')
canonical='https://specorganon.stevenvallejo.com'
def read(url):
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'SpecOrganon-public-verifier'}),timeout=30) as r:
        return r.status,r.read()
status,raw=read(canonical+'/resultados/software/descargas-manifest.json')
manifest=json.loads(raw)
assert status==200 and manifest==json.loads((published/'website/public/resultados/software/descargas-manifest.json').read_text())
def check(row):
    name,expected=row
    url=canonical+'/resultados/software/'+urllib.parse.quote(name,safe='/')
    status,raw=read(url);actual=hashlib.sha256(raw).hexdigest()
    assert status==200 and actual==expected,(name,status,actual)
    return {'path':name,'http_status':status,'sha256':actual,'bytes':len(raw)}
entries=list(manifest['files'].items())
for prefix in ['cohorte-nativa-01','cohorte-nativa-02','avance-dev3','avance-dev4']:
    status,nested_raw=read(canonical+'/resultados/software/'+prefix+'/descargas-sha256.json')
    nested=json.loads(nested_raw)
    assert status==200 and nested==json.loads((published/('website/public/resultados/software/'+prefix+'/descargas-sha256.json')).read_text())
    entries.extend((prefix+'/'+name,expected) for name,expected in nested['files'].items())
assert len(entries)==61 and len({n for n,_ in entries})==61
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    files=list(pool.map(check,entries))
status,raw=read('https://api.github.com/repos/stevenvo780/SpecOrganon');repo=json.loads(raw)
assert status==200 and repo['default_branch']=='main' and repo['private'] is False
status,raw=read('https://api.github.com/repos/stevenvo780/SpecOrganon/commits/main');commit=json.loads(raw)['sha']
source_checks={}
for rel in ['pyproject.toml','src/specorganon/__init__.py','src/specorganon/docker_roles.py','src/specorganon/native_response_contract.py','scripts/controller_native_role.py','scripts/run_registered_native.py']:
    status,raw=read('https://raw.githubusercontent.com/stevenvo780/SpecOrganon/main/'+rel)
    assert status==200 and raw==(published/rel).read_bytes(),rel
    source_checks[rel]=hashlib.sha256(raw).hexdigest()
tags={}
for tag,expected in [('dev4-source-20261006','f322362f9c3e31a92b72faa4a92a6e26ee7c94f4'),('dev4-native-cohort02-registration-20261006','197066dd18ad421b537ba98e1fbe620bd93eaa33')]:
    status,raw=read('https://api.github.com/repos/stevenvo780/SpecOrganon/git/ref/tags/'+tag)
    ref=json.loads(raw)['object'];actual=ref['sha']
    if ref['type']=='tag':
        _,raw=read(ref['url']);actual=json.loads(raw)['object']['sha']
    assert actual==expected,(tag,actual)
    tags[tag]=actual
receipt={'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'canonical_url':canonical,
         'public_repository':True,'default_branch':'main','main_commit':commit,'verified_downloads':len(files),
         'anonymous_http':True,'manifest_matches_published_source':True,'files':files,'source_sha256':source_checks,
         'provenance_tags':tags,'new_model_calls':0,'goal_achieved':False,
         'scope':'Parent independent anonymous HTTP/source verification; UI checks in publication worker receipt'}
(base/'public-http-verification-02.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({'main_commit':commit,'verified_downloads':len(files),'source_files':len(source_checks),'provenance_tags':len(tags),'http_success':True}))
