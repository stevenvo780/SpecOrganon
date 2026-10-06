"""Unauthenticated new temporary profile; installed CLI/MCP only."""
import subprocess,json,asyncio,importlib.util,hashlib
from pathlib import Path
import specorganon
assert specorganon.__version__=='0.2.0rc3.dev4'
config=Path('/home/codex/.codex/config.toml').read_text()
assert 'approval_policy = "on-request"' in config and 'sandbox_mode = "workspace-write"' in config
assert not Path('/home/codex/.codex/auth.json').exists()
version=subprocess.run(['codex','--version'],capture_output=True,text=True,check=True).stdout.strip()
assert version=='codex-cli 0.160.0',version
p='/opt/codex-lab/smoke.py';s=importlib.util.spec_from_file_location('smoke',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
r=asyncio.run(asyncio.wait_for(m.exercise(),timeout=90));assert r['passed']
print(json.dumps({'codex_version':version,'specorganon_version':specorganon.__version__,'auth_present':False,'temporary_profile':True,'policy':'on-request/workspace-write','MCP':r,'network_enabled':False,'new_model_calls':0},indent=2))
