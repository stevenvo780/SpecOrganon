#!/usr/bin/env python3
import json
import sys
import os

command = sys.argv[1]
if command == 'create':
    source_arg = sys.argv[sys.argv.index('--source') + 1]
    id_arg = sys.argv[sys.argv.index('--id') + 1]
    # Silently modify the source to simulate source mutation
    for root, dirs, files in os.walk(source_arg):
        for f in files:
            with open(os.path.join(root, f), 'a') as f_obj:
                f_obj.write("corrupted!")
    print(json.dumps({"id": id_arg}))
elif command == 'restore':
    dest_arg = sys.argv[sys.argv.index('--dest') + 1]
    id_arg = sys.argv[sys.argv.index('--id') + 1]
    # create dest to simulate restore but not accurate
    os.makedirs(dest_arg, exist_ok=True)
    with open(os.path.join(dest_arg, 'dummy'), 'w') as f_obj:
        f_obj.write('dummy content')
    print(json.dumps({"id": id_arg}))
elif command == 'verify':
    id_arg = sys.argv[sys.argv.index('--id') + 1]
    print(json.dumps({"id": id_arg, "valid": True}))
else:
    print(json.dumps({"snapshots": []}))
sys.exit(0)
