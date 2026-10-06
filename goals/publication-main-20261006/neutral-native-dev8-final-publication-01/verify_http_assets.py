from pathlib import Path
import hashlib,json,urllib.request,re,datetime
b=Path(__file__).parent; w=Path('/datos/workspaces/personal/ViewSpecOrganon/web/dist'); origin='https://specorganon.stevenvallejo.com'
def get(path):
 with urllib.request.urlopen(urllib.request.Request(origin+path,headers={'User-Agent':'SpecOrganon-publication-verifier'}),timeout=30) as r:return r.status,r.read()
h=lambda raw:hashlib.sha256(raw).hexdigest()
status,html=get('/');assert status==200 and html==(w/'index.html').read_bytes(); assert b'href="https://github.com/stevenvo780/SpecOrganon"' not in html
assets=sorted(set(x for x in re.findall(r'(?:src|href)="([^\"]+)"',html.decode()) if x.startswith('/assets/') and x.endswith(('.js','.css'))))
checks=[]
for p in assets:
 status,raw=get(p);assert status==200 and raw==(w/p.lstrip('/')).read_bytes();checks.append({'path':p,'http':status,'sha256':h(raw)})
code=''.join((w/x.lstrip('/')).read_text() for x in assets if x.endswith('.js'))
assert all(v in code for v in ['avance-dev9','piloto-dev8','194','42','648','1180','BATTERY_ADDITION','review_ready','https://github.com/stevenvo780/SpecOrganon'])
r={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'canonical_url':origin,'http':200,'html_byte_equal_dist':True,'html_sha256':h(html),'assets_verified':checks,'dev9_and_terminal6cut_present_in_bundle':True,'rendered_UI_attributed_to':'public-web-checks.json and screenshots; HTTP does not execute SPA'}
(b/'canonical-http-assets.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'html':200,'assets_exact':len(checks),'dev9_and_terminal6cut_present':True}))
