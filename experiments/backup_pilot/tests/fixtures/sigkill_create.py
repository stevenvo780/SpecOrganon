#!/usr/bin/env python3
import json
import sys
import time
import os

command = sys.argv[1]
if command == 'create':
    repo_arg = sys.argv[sys.argv.index('--repo') + 1]
    id_arg = sys.argv[sys.argv.index('--id') + 1]
    if id_arg == 'interrupted':
        # write a file to repo to simulate writing before kill
        with open(os.path.join(repo_arg, 'temp_write'), 'w') as f:
            f.write('writing...')
        time.sleep(10) # wait to be killed
        print(json.dumps({"id": id_arg}))
    else:
        print(json.dumps({"id": id_arg}))
else:
    id_arg = sys.argv[sys.argv.index('--id') + 1] if '--id' in sys.argv else 'test-id'
    if command == 'verify':
        print(json.dumps({"id": id_arg, "valid": True}))
    else:
        print(json.dumps({"id": id_arg}))
sys.exit(0)
