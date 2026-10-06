#!/usr/bin/env python3
"""Collect source and role-review evidence after the whole campaign closes.

This is an inventory for manual review, not an automatic compliance verdict.
It never imports or executes a submitted implementation on the host.
"""
import ast
import hashlib
import json
from pathlib import Path

import run_pilot

BASE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect_source(path):
    text = path.read_text()
    try:
        tree = ast.parse(text)
    except (SyntaxError, UnicodeError) as error:
        return {'sha256': sha(path), 'parse_error': str(error)}
    imports = []
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend({'module': item.name, 'line': node.lineno} for item in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append({'module': node.module, 'level': node.level, 'line': node.lineno})
        elif isinstance(node, ast.Call):
            name = ast.unparse(node.func)
            if name in ('eval', 'exec', '__import__', 'compile') or name.startswith(
                ('subprocess.', 'os.system', 'os.popen', 'os.exec', 'os.spawn',
                 'importlib.', 'ctypes.', 'socket.', 'urllib.')
            ):
                calls.append({'function': name, 'line': node.lineno,
                              'expression': ast.get_source_segment(text, node)})
    return {'sha256': sha(path), 'bytes': path.stat().st_size,
            'imports': imports, 'calls_requiring_review': calls}


def main():
    marker = BASE / 'runs/complete.json'
    if not marker.is_file():
        raise SystemExit('Missing runs/complete.json; no early inspection')
    manifest = json.loads((BASE / 'frozen/manifest.json').read_text())
    run_pilot.check_freeze(manifest)
    if len(manifest['schedule']) != 18:
        raise SystemExit('Expected 18 scheduled runs')
    rows = []
    model_logs = []
    methods = []
    for row in manifest['schedule']:
        for stage in (1, 2):
            record = BASE / 'runs' / row['id'] / f'stage{stage}'
            if not (record / 'complete.json').is_file():
                raise SystemExit('Missing generation receipt')
            solution = record / 'artifact/solution'
            files = [p for p in sorted(solution.rglob('*')) if p.is_file() and not p.is_symlink()]
            rows.append({'id': row['id'], 'arm': row['arm'], 'stage': stage,
                         'readme_present': (solution / 'README.md').is_file(),
                         'files': [{'path': str(p.relative_to(solution)),
                                    'sha256': sha(p), 'bytes': p.stat().st_size} for p in files],
                         'python_sources': {str(p.relative_to(solution)): inspect_source(p)
                                            for p in files if p.suffix == '.py'}})
            for role in ('author', 'method', 'review'):
                log = record / f'{role}.jsonl'
                if not log.is_file():
                    continue
                events = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
                items = {}
                for event in events:
                    item = event.get('item')
                    if item and item.get('id'):
                        items[item['id']] = {**item, 'event_type': event.get('type')}
                stderr = record / f'{role}.stderr'
                model_logs.append({'id': row['id'], 'stage': stage, 'role': role,
                                   'jsonl_sha256': sha(log),
                                   'stderr_sha256': sha(stderr) if stderr.is_file() else None,
                                   'stderr_bytes': stderr.stat().st_size if stderr.is_file() else None,
                                   'item_messages': [item for item in items.values()
                                                     if item.get('type') == 'error']})
                if role == 'method':
                    commands = [{k: item.get(k) for k in
                                 ('id', 'command', 'status', 'exit_code', 'event_type')}
                                for item in items.values() if item.get('type') == 'command_execution']
                    changes = [item for item in items.values() if item.get('type') == 'file_change']
                    mcp = [{k: item.get(k) for k in
                            ('id', 'server', 'tool', 'status', 'error', 'event_type')}
                           for item in items.values() if item.get('type') == 'mcp_tool_call']
                    methods.append({'id': row['id'], 'stage': stage,
                                    'commands': commands, 'file_changes': changes, 'mcp': mcp})
    out = BASE / 'analysis/manual-review'
    out.mkdir(parents=True, exist_ok=True)
    report = {'kind': 'post-campaign evidence inventory, manual conclusions pending',
              'inspector_sha256': sha(Path(__file__)), 'sources': rows,
              'model_logs': model_logs, 'method_roles': methods,
              'limitations': ['AST inventory does not prove absence of vendored code or dynamic behavior.',
                              'Method workspace permits writes; event inspection is not a source snapshot before review.',
                              'A recorded shell command can have side effects through invoked programs.',
                              'Missing README is outside the frozen functional score and must be reported separately.']}
    (out / 'inventory.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'sources': len(rows), 'model_logs': len(model_logs),
                      'method_roles': len(methods), 'manual_verdict': 'pending'}))


if __name__ == '__main__':
    main()
