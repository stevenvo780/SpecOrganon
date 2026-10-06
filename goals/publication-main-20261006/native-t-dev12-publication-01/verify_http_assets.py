"""Verify anonymous canonical HTML/assets/dev12 payload bytes against the final built site."""
from pathlib import Path
import hashlib,json,urllib.request,concurrent.futures,datetime
WEB=Path('/datos/workspaces/personal/ViewSpecOrganon/web');P=Path(__file__).resolve().parent;DIST=WEB/'dist';base='https://specorganon.stevenvallejo.com/'
files=[DIST/'index.html',*sorted((DIST/'assets').glob('*')),*sorted((DIST/'resultados/software/avance-dev12').glob('*'))]
def one(f):
 rel=str(f.relative_to(DIST));r=urllib.request.urlopen(base+rel,timeout=40);b=r.read();exp=f.read_bytes();assert r.status==200 and b==exp,rel
 return {'path':rel,'http':r.status,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'byte_exact':True}
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:checks=list(pool.map(one,files))
html=(DIST/'index.html').read_text();assert 'https://github.com/stevenvo780/SpecOrganon/tree/main' in html
bundle=''.join(f.read_text() for f in (DIST/'assets').glob('*.js'))
for value in ['avance-dev12','593','48','CT-01','TEX-01','common_complete','complete_source_acceptance']:assert value in bundle,value
d={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'base':base,'checks':checks,'files_exact':len(checks),'HTML_plus_assets_exact':sum('/avance-dev12/' not in c['path'] for c in checks),'dev12_payloads_plus_manifest_exact':sum('/avance-dev12/' in c['path'] for c in checks),'no_authorization_headers':True,'noscript_main_link':True,'dev12_partial_scope_bundle_present':True,'browser_rendering_scope':'Separate publisher check_web.cjs two-viewport receipt'}
(P/'canonical-http-assets.json').write_text(json.dumps(d,indent=2)+'\n');print(json.dumps({'anonymous_files_HTTP200_SHA_exact':len(checks),'dev12_scope':True,'noscript_main':True}))
