"""Read-only dev7 image byte/CLI/MCP probes; no credentials or provider calls."""
from pathlib import Path
import hashlib,json,subprocess
BASE=Path(__file__).resolve().parent
SOURCE=BASE.parents[3]
LOCAL=BASE/'local-install'
workspace=LOCAL/'docker-workspace';workspace.mkdir(exist_ok=True)
for name in ('cases','results'):(workspace/name).mkdir(exist_ok=True)
commands=[]
def call(name,argv,stdin=None):
 r=subprocess.run(argv,input=stdin,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120,cwd=SOURCE)
 (BASE/(name+'.stdout')).write_bytes(r.stdout);(BASE/(name+'.stderr')).write_bytes(r.stderr)
 commands.append({'argv':argv,'exit_code':r.returncode,'stdin_sha256':hashlib.sha256(stdin).hexdigest() if stdin else None})
 (BASE/'docker-installed-commands-01.json').write_text(json.dumps(commands,indent=2)+'\n')
 if r.returncode:raise RuntimeError(name+': '+r.stderr.decode()[:2000])
 return r.stdout
image=call('docker-image-inspect-01',['docker','image','inspect','specorganon-release:0.2.0rc3.dev7','--format','{{.Id}}']).decode().strip()
(BASE/'release-image-config-id.txt').write_text(image+'\n')
common=['docker','run','--rm','-i','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','--security-opt','seccomp='+str(SOURCE/'docker/codex/seccomp-codex.json'),'--security-opt','apparmor:unconfined','--pids-limit','256','--memory','1g','--tmpfs','/tmp:rw,nosuid,nodev']
expected={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (SOURCE/'src/specorganon').glob('*.py')}
code='import pathlib,hashlib,json,sys,specorganon; p=pathlib.Path(specorganon.__file__).parent; actual={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in p.glob("*.py")}; expected=json.load(sys.stdin); assert actual==expected; print(json.dumps({"version":specorganon.__version__,"module_count":len(actual),"modules_sha256":actual}))'
observed=json.loads(call('docker-installed-bytes-01',common+[image,'python','-I','-B','-c',code],json.dumps(expected).encode()))
assert observed['version']=='0.2.0rc3.dev7' and observed['module_count']==40
call('docker-installed-cli-01',common+[image,'organon','--help'])
raw=call('docker-installed-mcp-01',common+['--mount','type=bind,src='+str(workspace)+',dst=/workspace','--mount','type=bind,src='+str(SOURCE/'docker/codex/smoke.py')+',dst=/smoke.py,readonly',image,'python','-I','-B','/smoke.py'])
mcp=json.loads(raw);assert mcp['passed'] and mcp['tools_discovered']==24
result=workspace/'results'/Path(mcp['report']).name
(BASE/'docker-MCP-result-01.json').write_bytes(result.read_bytes())
receipt={'schema':1,'scope':'Actual installed dev7 release image, 40 source-byte equal modules, CLI help and offline MCP stdio synthetic case only; no native roles/qualification/superiority','image_id':image,'build_iid':(BASE/'release-image-id.txt').read_text().strip(),'observed':observed,'MCP':mcp,'provider_calls':0,'native_generations':0,'reserved_subjects':0,'goal_achieved':False}
(BASE/'docker-installed-receipt-01.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({'image_id':image,'installed_modules':40,'MCP_tools':24,'provider_calls':0}))
