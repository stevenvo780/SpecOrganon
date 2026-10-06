"""Offline installed-wheel checks; fixtures and native transcript reanalysis only."""
import asyncio
import hashlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import subprocess

import specorganon

root = Path('/checks')
installed = Path(specorganon.__file__).parent
assert '/site-packages/' in str(installed), installed
assert importlib.metadata.version('specorganon') == specorganon.__version__ == '0.2.0rc3.dev5'
hashes = {}
for original in sorted((root/'src/specorganon').glob('*.py')):
    actual = installed/original.name
    assert actual.read_bytes() == original.read_bytes(), original.name
    hashes[original.name] = hashlib.sha256(actual.read_bytes()).hexdigest()

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

bridge = load('final_bridge', root/'scripts/controller_native_role.py')
from specorganon.native_response_contract import validate_response_schema
e = root/'goals/method-superiority-v1/evidence/provider-json-schema-01'
registration = json.loads((root/'goals/method-superiority-v1/development/registration-provider-json-schema-03.json').read_text())
checks = []
for case in registration['cases']:
    raw = (e/'native-03'/case['id']/'stdout.bin').read_text()
    value, usage = bridge.parse_gemini_stream(raw)
    schema = bridge.response_contract_from_request(case['request'])
    validate_response_schema(value, schema)
    recorded = json.loads((e/(case['id']+'-outcome-03.json')).read_text())
    assert value == recorded['result']['result']
    checks.append({'id':case['id'], 'same_original_response':True, 'strict_validation':True})

cli = subprocess.run(['/opt/specorganon/venv/bin/organon', '--help'], capture_output=True)
assert cli.returncode == 0
smoke = load('installed_mcp_smoke', root/'docker/codex/smoke.py')
mcp = asyncio.run(asyncio.wait_for(smoke.exercise(), timeout=90))
assert mcp['passed'] and len(mcp['tools_discovered']) == 24
print(json.dumps({'installed_path':str(installed), 'version':specorganon.__version__,
    'module_sha256':hashes, 'CLI_exit_code':cli.returncode, 'MCP':mcp,
    'original_transcripts_revalidated_with_final_parser':checks,
    'network_enabled':False, 'new_model_calls':0, 'new_subjects':0,
    'scope':'Installed wheel CLI/MCP, rejection/recovery and offline transcript reanalysis; no new native projects'},indent=2))
