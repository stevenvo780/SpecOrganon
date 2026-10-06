"""Installed-wheel probe; MCP case is synthetic, never native efficacy."""
import asyncio,hashlib,importlib,importlib.util,json,pkgutil,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path

BASE=Path(__file__).resolve().parent
SOURCE=BASE.parents[3]
import specorganon
installed=Path(specorganon.__file__).parent
expected={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (SOURCE/'src/specorganon').glob('*.py')}
observed={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in installed.glob('*.py')}
assert expected==observed
for module in pkgutil.iter_modules(specorganon.__path__):importlib.import_module('specorganon.'+module.name)
result=subprocess.run([str(Path(sys.executable).parent/'organon'),'--help'],capture_output=True,text=True,timeout=30)
assert result.returncode==0
spec=importlib.util.spec_from_file_location('installed_mcp_probe',SOURCE/'docker/codex/smoke.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.ROOT=BASE/'local-wheel/workspace';m.BIN=Path(sys.executable).parent
m.ROOT.mkdir(exist_ok=True)
for name in ('cases','results'):(m.ROOT/name).mkdir(exist_ok=True)
mcp=asyncio.run(asyncio.wait_for(m.exercise(),timeout=90))
assert mcp['passed'] is True and len(mcp['tools_discovered'])==24
wheel=BASE/'local-wheel/specorganon-0.2.0rc3.dev6-py3-none-any.whl'
receipt={'schema':1,'at':datetime.now(timezone.utc).isoformat(),'version':specorganon.__version__,
         'scope':'Local installed wheel module bytes/imports, CLI help, actual host MCP stdio; synthetic local case only, no native roles or Docker image dev6 claim',
         'wheel_sha256':hashlib.sha256(wheel.read_bytes()).hexdigest(),'installed_modules_byte_equal':len(observed),
         'installed_module_sha256':observed,'CLI_help_exit_code':result.returncode,'MCP':mcp,
         'new_provider_calls':0,'native_generation6':0,'reserved_subjects':0,'goal_achieved':False}
(BASE/'installed-receipt-05.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt,indent=2))
