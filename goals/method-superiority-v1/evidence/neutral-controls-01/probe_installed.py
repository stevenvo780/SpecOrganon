"""Local wheel import/custody probe; no model calls or efficacy claims."""
import hashlib
import importlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys

import specorganon

SOURCE=Path('/home/stev/.codex/worktrees/strong-controls-v1/SpecOrganon')
installed=Path(specorganon.__file__).parent
assert importlib.metadata.version('specorganon')=='0.2.0rc3.dev6'
assert installed!=SOURCE/'src/specorganon'
hashes={}
for path in sorted((SOURCE/'src/specorganon').glob('*.py')):
    expected=path.read_bytes();actual=(installed/path.name).read_bytes()
    assert expected==actual, path.name
    importlib.import_module('specorganon'+('.'+path.stem if path.stem!='__init__' else ''))
    hashes[path.name]=hashlib.sha256(actual).hexdigest()
from specorganon.native_response_contract import response_schema,validate_response_schema
from specorganon.neutral_author import neutral_author_content
from specorganon.author_contract import AUTHOR_FORMATS
value={'schema':1,'files':{'program.py':'print(1)\n'},'documents':{},'reason':'Packaging fixture only'}
validate_response_schema(value,response_schema('author',author_format='files-v1'))
assert neutral_author_content(value)==value and 'files-v1' not in AUTHOR_FORMATS
help_result=subprocess.run([sys.executable,'-I','-m','specorganon.cli','--help'],capture_output=True,timeout=15)
assert help_result.returncode==0 and b'usage:' in help_result.stdout
print(json.dumps({'scope':'Installed wheel imports, CLI help and source byte equality only',
                  'version':importlib.metadata.version('specorganon'),'installed':str(installed),
                  'module_sha256':hashes,'cli_help_exit_code':help_result.returncode,
                  'new_model_calls':0,'native_efficacy_measured':False},sort_keys=True,indent=2))
