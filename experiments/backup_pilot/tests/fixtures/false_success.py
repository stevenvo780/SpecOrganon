#!/usr/bin/env python3
import json
import sys

# Always returns success without actually doing the backup correctly.
command = sys.argv[1]
if command == 'create':
    id_arg = sys.argv[sys.argv.index('--id') + 1] if '--id' in sys.argv else 'test-id'
    print(json.dumps({"id": id_arg}))
elif command == 'verify':
    id_arg = sys.argv[sys.argv.index('--id') + 1] if '--id' in sys.argv else 'test-id'
    print(json.dumps({"id": id_arg, "valid": True}))
elif command == 'restore':
    id_arg = sys.argv[sys.argv.index('--id') + 1] if '--id' in sys.argv else 'test-id'
    print(json.dumps({"id": id_arg}))
elif command == 'list':
    print(json.dumps({"snapshots": ["test-id"]}))
sys.exit(0)
