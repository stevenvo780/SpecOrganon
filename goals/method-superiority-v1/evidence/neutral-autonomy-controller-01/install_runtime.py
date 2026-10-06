"""Build/install isolated wheel without profiles or model calls."""
import json, subprocess
from pathlib import Path
BASE = Path(__file__).resolve().parent
SOURCE = BASE.parents[3]
LOCAL = BASE / 'local-install'
LOCAL.mkdir(exist_ok=True)
steps = [
 ('wheel-build-01', ['uv','build','--wheel','--out-dir',str(LOCAL/'dist')]),
 ('wheel-export-01', ['uv','export','--frozen','--extra','dev','--no-emit-project','--format','requirements-txt','-o',str(LOCAL/'requirements.txt')]),
 ('wheel-venv-01', ['uv','venv',str(LOCAL/'venv')]),
 ('wheel-deps-01', ['uv','pip','install','--python',str(LOCAL/'venv/bin/python'),'--require-hashes','-r',str(LOCAL/'requirements.txt')]),
 ('wheel-install-01', ['uv','pip','install','--python',str(LOCAL/'venv/bin/python'),'--no-deps',str(LOCAL/'dist/specorganon-0.2.0rc3.dev7-py3-none-any.whl')]),
 ('wheel-check-01', ['uv','pip','check','--python',str(LOCAL/'venv/bin/python')]),
]
commands=[]
for name,argv in steps:
 result=subprocess.run(argv,cwd=SOURCE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 (BASE/(name+'.stdout')).write_bytes(result.stdout);(BASE/(name+'.stderr')).write_bytes(result.stderr)
 commands.append({'argv':argv,'cwd':str(SOURCE),'exit_code':result.returncode})
 (BASE/'wheel-commands-01.json').write_text(json.dumps(commands,indent=2)+'\n')
 if result.returncode: raise SystemExit(result.returncode)
print('Fresh wheel installed with locked dependency hashes and pip check.')
