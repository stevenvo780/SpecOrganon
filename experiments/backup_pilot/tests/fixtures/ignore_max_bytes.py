#!/usr/bin/env python3
import json
import sys
import shutil

command = sys.argv[1]
if command == 'create':
    source_arg = sys.argv[sys.argv.index('--source') + 1]
    repo_arg = sys.argv[sys.argv.index('--repo') + 1]
    id_arg = sys.argv[sys.argv.index('--id') + 1]
    shutil.copytree(source_arg, repo_arg, dirs_exist_ok=True)
    print(json.dumps({"id": id_arg}))
else:
    id_arg = sys.argv[sys.argv.index('--id') + 1] if '--id' in sys.argv else 'test-id'
    if command == 'verify':
        print(json.dumps({"id": id_arg, "valid": True}))
    else:
        print(json.dumps({"id": id_arg}))
sys.exit(0)
