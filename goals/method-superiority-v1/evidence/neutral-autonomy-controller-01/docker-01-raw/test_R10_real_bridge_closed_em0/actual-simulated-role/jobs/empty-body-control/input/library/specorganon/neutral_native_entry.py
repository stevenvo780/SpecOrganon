"""Installed, trusted stdlib bootstrap for byte-bound public N/S pilots.

The interpreter, package initializer, this entry point and dependencies are the trusted boundary.
All remaining package modules compile the exact installed bytes pinned in the
plan; cached pyc and modules imported before launch cannot substitute for them.
No Docker invocation, account lookup or generation happens in this bootstrap.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.abc
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys


def read_regular(path, limit=2097152):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('bootstrap path traverses a symlink')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > limit:
            raise ValueError('bootstrap requires bounded singly linked regular bytes')
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    if len(raw) != before.st_size or (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise ValueError('bootstrap bytes changed during read')
    return raw


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def exact_json(raw):
    def pairs(items):
        value = {}
        for name, item in items:
            if name in value:
                raise ValueError('duplicate JSON field')
            value[name] = item
        return value
    def nonfinite(value):
        raise ValueError('nonfinite JSON')
    return json.loads(raw.decode(), object_pairs_hook=pairs, parse_constant=nonfinite)


class InstalledSources(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def __init__(self, package, source, bindings):
        self.modules = {}
        required = {name for name in bindings if Path(name).parent == Path('src/specorganon')}
        installed = {'src/specorganon/' + p.name for p in package.glob('*.py')}
        source_names = {'src/specorganon/' + p.name for p in (source / 'src/specorganon').glob('*.py')}
        if not required or required != installed or required != source_names:
            raise ValueError('installed/source/registered module inventories differ')
        for name in sorted(required):
            p = Path(name)
            if p.suffix != '.py' or re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', p.stem) is None:
                raise ValueError('invalid registered module name')
            path = package / p.name
            raw = read_regular(path)
            if sha(raw) != bindings[name] or raw != read_regular(source / p):
                raise ValueError('installed module differs from pinned source: ' + p.name)
            module = 'specorganon' if p.name == '__init__.py' else 'specorganon.' + p.stem
            self.modules[module] = (path, raw, bindings[name])

    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'specorganon' or fullname.startswith('specorganon.'):
            if fullname not in self.modules:
                raise ImportError('unregistered package module')
            return importlib.util.spec_from_loader(fullname, self, is_package=fullname == 'specorganon')
        return None

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        path, raw, pin = self.modules[module.__name__]
        module.__file__ = str(path)
        if module.__name__ == 'specorganon':
            module.__path__ = [str(path.parent)]
        exec(compile(raw, str(path), 'exec', dont_inherit=True), module.__dict__)
        module.__registered_source_sha256__ = pin


def launch(plan, expected, operation):
    allowed = {'specorganon', 'specorganon.neutral_native_entry'}
    if any(n.startswith('specorganon.') and n not in allowed for n in sys.modules):
        raise ValueError('fresh process required for installed pilot bootstrap')
    raw = read_regular(plan)
    if sha(raw) != expected:
        raise ValueError('plan digest differs before imports')
    record = exact_json(raw)
    if type(record) is not dict or type(record.get('schema')) is not int or record['schema'] != 2:
        raise ValueError('versioned neutral pilot plan required')
    source = Path(record['source_root']).absolute()
    bindings = record['source_sha256']
    if type(bindings) is not dict:
        raise ValueError('source bindings must be a map')
    for name, pin in bindings.items():
        rel = Path(name)
        if rel.is_absolute() or '..' in rel.parts or rel.as_posix() != name or sha(read_regular(source / rel)) != pin:
            raise ValueError('registered source differs or escapes root')
    package = Path(__file__).absolute().parent
    loader = InstalledSources(package, source, bindings)
    # This entry remains the trusted entry currently executing. Everything
    # subsequently imported is freshly compiled from the captured pinned bytes.
    sys.modules.pop('specorganon', None)
    sys.meta_path.insert(0, loader)
    try:
        from specorganon.neutral_pilot import execute
        return execute(plan, expected, operation, installed_root=package)
    finally:
        sys.meta_path.remove(loader)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['run', 'report'])
    parser.add_argument('plan', type=Path)
    parser.add_argument('--plan-sha256', required=True)
    args = parser.parse_args()
    try:
        result = launch(args.plan, args.plan_sha256, args.operation)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
        return 0 if result['status'] == 'closed' else 2
    except (ValueError, OSError, TypeError, KeyError) as exc:
        print(json.dumps({'status': 'rejected', 'error_type': type(exc).__name__,
                          'reason': str(exc), 'goal_achieved': False}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
