"""Installed stdlib bootstrap for prospective public T native development.

The interpreter, package initializer, this entry and external dependencies are
the trusted boundary. Launch with ``python -I -B`` for interpreter isolation and
to suppress bytecode writes; console scripts need not have those flags. Neither
flag replaces the installed-wheel and captured-source checks here. Remaining
package imports compile captured, pinned source bytes without pyc or fallback.
This bootstrap performs no provider, credential, network or Docker lookup.
"""
from __future__ import annotations

import argparse
import base64
import csv
from email.parser import BytesParser
import hashlib
import importlib.abc
import importlib.metadata
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import re
import site
import stat
import sys
import sysconfig


def _absolute(path):
    path = Path(path)
    if '..' in path.parts:
        raise ValueError('bootstrap path traverses a parent')
    return path.absolute()


def _directories(path):
    """Open every component relative to a held directory, never a symlink."""
    descriptors = []
    try:
        descriptors.append(os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW))
        for part in path.parts[1:]:
            descriptors.append(os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                       dir_fd=descriptors[-1]))
        return descriptors
    except BaseException:
        for fd in reversed(descriptors):
            os.close(fd)
        raise


def _same_file(a, b):
    return (a.st_dev, a.st_ino, a.st_mode, a.st_nlink, a.st_size,
            a.st_mtime_ns, a.st_ctime_ns) == (b.st_dev, b.st_ino, b.st_mode,
            b.st_nlink, b.st_size, b.st_mtime_ns, b.st_ctime_ns)


def _check_directories(path, descriptors):
    for index, part in enumerate(path.parts[1:], 1):
        named = os.stat(part, dir_fd=descriptors[index - 1], follow_symlinks=False)
        held = os.fstat(descriptors[index])
        if not stat.S_ISDIR(named.st_mode) or (named.st_dev, named.st_ino) != (held.st_dev, held.st_ino):
            raise ValueError('bootstrap directory changed during read')


def read_regular(path, limit=2097152):
    """Read bounded, singly linked bytes through an openat directory chain."""
    if type(limit) is not int or limit < 0:
        raise ValueError('nonnegative integer byte limit required')
    path = _absolute(path)
    descriptors = _directories(path.parent)
    fd = None
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=descriptors[-1])
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > limit:
            raise ValueError('bootstrap requires bounded singly linked regular bytes')
        chunks = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(fd, min(remaining, 65536))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b''.join(chunks)
        after = os.fstat(fd)
        named = os.stat(path.name, dir_fd=descriptors[-1], follow_symlinks=False)
        _check_directories(path.parent, descriptors)
        if len(raw) != before.st_size or not _same_file(before, after) or not _same_file(after, named):
            raise ValueError('bootstrap bytes changed during read')
        return raw
    finally:
        if fd is not None:
            os.close(fd)
        for directory in reversed(descriptors):
            os.close(directory)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _digest(value):
    if type(value) is not str or re.fullmatch(r'[a-f0-9]{64}', value) is None:
        raise ValueError('exact lowercase SHA256 required')
    return value


def exact_json(raw):
    def pairs(items):
        result = {}
        for name, value in items:
            if name in result:
                raise ValueError('duplicate JSON field')
            result[name] = value
        return result

    def nonfinite(value):
        raise ValueError('nonfinite JSON')

    def finite_float(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError('nonfinite JSON')
        return parsed

    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                      parse_constant=nonfinite, parse_float=finite_float)


def _relative(name):
    if type(name) is not str or not name:
        raise ValueError('registered relative path required')
    path = Path(name)
    if path.is_absolute() or '..' in path.parts or path.as_posix() != name or name == '.':
        raise ValueError('registered path escapes source or is not canonical')
    return path


def _inventory(root):
    """Inventory Python sources without following directory or file symlinks."""
    root = _absolute(root)
    descriptors = _directories(root)
    names = set()

    def walk(fd, prefix):
        for name in os.listdir(fd):
            if name == '__pycache__':
                continue
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            relative = prefix / name
            if stat.S_ISLNK(info.st_mode):
                raise ValueError('module inventory contains a symlink')
            if stat.S_ISDIR(info.st_mode):
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                try:
                    held = os.fstat(child)
                    if (held.st_dev, held.st_ino) != (info.st_dev, info.st_ino):
                        raise ValueError('module inventory directory changed')
                    walk(child, relative)
                    named = os.stat(name, dir_fd=fd, follow_symlinks=False)
                    if (named.st_dev, named.st_ino) != (held.st_dev, held.st_ino):
                        raise ValueError('module inventory directory changed')
                finally:
                    os.close(child)
            elif relative.suffix == '.py':
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise ValueError('module inventory requires singly linked regular files')
                names.add(relative.as_posix())

    try:
        walk(descriptors[-1], Path())
        _check_directories(root, descriptors)
        return names
    finally:
        for fd in reversed(descriptors):
            os.close(fd)


class InstalledSources(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Snapshot all registered package sources before executing any of them."""
    def __init__(self, package, source, bindings):
        self.modules = {}
        self.package = _absolute(package)
        self.source = _absolute(source)
        prefix = 'src/specorganon/'
        required = {name[len(prefix):] for name in bindings if name.startswith(prefix)}
        if (not required or '__init__.py' not in required
                or required != _inventory(self.package)
                or required != _inventory(self.source / 'src/specorganon')):
            raise ValueError('installed/source/registered module inventories differ')
        for name in sorted(required):
            relative = _relative(name)
            if relative.suffix != '.py' or any(re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', part) is None
                                               for part in (*relative.parts[:-1], relative.stem)):
                raise ValueError('invalid registered module name')
            path = self.package / relative
            raw = read_regular(path)
            pin = _digest(bindings[prefix + name])
            if sha(raw) != pin or raw != read_regular(self.source / prefix / relative):
                raise ValueError('installed module differs from pinned source: ' + name)
            parts = relative.parts[:-1] if relative.name == '__init__.py' else (*relative.parts[:-1], relative.stem)
            module = '.'.join(('specorganon', *parts))
            self.modules[module] = (path, raw, pin)
        self.check_inventory()

    def check_inventory(self):
        names = {path.relative_to(self.package).as_posix() for path, _, _ in self.modules.values()}
        if names != _inventory(self.package) or names != _inventory(self.source / 'src/specorganon'):
            raise ValueError('captured module inventory changed')

    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'specorganon' or fullname.startswith('specorganon.'):
            if fullname not in self.modules:
                raise ImportError('unregistered package module; no filesystem fallback')
            is_package = self.modules[fullname][0].name == '__init__.py'
            return importlib.util.spec_from_loader(fullname, self, is_package=is_package)
        return None

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        path, raw, pin = self.modules[module.__name__]
        module.__file__ = str(path)
        if path.name == '__init__.py':
            module.__path__ = [str(path.parent)]
        exec(compile(raw, str(path), 'exec', dont_inherit=True), module.__dict__)
        module.__registered_source_sha256__ = pin


def _installed_distribution(package, source, version):
    roots = {Path(p).absolute() for p in (sysconfig.get_path('purelib'), sysconfig.get_path('platlib'),
                                        *site.getsitepackages(), site.getusersitepackages()) if p}
    dist = importlib.metadata.distribution('specorganon')
    root = _absolute(dist.locate_file(''))
    if (root not in roots or package != root / 'specorganon'
            or package.is_relative_to(source) or source.is_relative_to(package)
            or dist.version != version):
        raise ValueError('matching installed specorganon wheel outside source checkout required')
    files = dist.files
    if not files:
        raise ValueError('installed wheel RECORD inventory required')
    records = {}
    for item in files:
        name = str(item)
        # Wheel RECORD may also contain console scripts outside site-packages.
        if name.startswith('specorganon/') or '.dist-info/' in name:
            relative = _relative(name)
            if name in records or _absolute(dist.locate_file(item)) != root / relative:
                raise ValueError('wheel RECORD location or duplicate differs')
            records[name] = item
    metadata_dirs = {Path(n).parts[0] for n in records if n.endswith('.dist-info/WHEEL')}
    if len(metadata_dirs) != 1:
        raise ValueError('installed wheel WHEEL metadata required')
    metadata_dir = metadata_dirs.pop()
    for name in ('WHEEL', 'METADATA', 'RECORD'):
        if metadata_dir + '/' + name not in records:
            raise ValueError('installed wheel metadata records required')
    record_bytes = read_regular(root / metadata_dir / 'RECORD')
    recorded_modules = set()
    recorded_names = set()
    for row in csv.reader(io.StringIO(record_bytes.decode('utf-8')), strict=True):
        if len(row) != 3 or row[0] in recorded_names:
            raise ValueError('invalid or duplicate wheel RECORD row')
        recorded_names.add(row[0])
        if row[0].startswith('specorganon/') and row[0].endswith('.py'):
            _relative(row[0])
            recorded_modules.add(row[0][len('specorganon/'):])
    wheel = BytesParser().parsebytes(read_regular(root / metadata_dir / 'WHEEL'))
    metadata = BytesParser().parsebytes(read_regular(root / metadata_dir / 'METADATA'))
    if (wheel.get_all('Wheel-Version') != ['1.0'] or metadata.get_all('Name') != ['specorganon']
            or metadata.get_all('Version') != [version]):
        raise ValueError('installed wheel metadata identity differs')
    direct = root / metadata_dir / 'direct_url.json'
    if direct.exists() or direct.is_symlink():
        if metadata_dir + '/direct_url.json' not in records:
            raise ValueError('unrecorded direct_url metadata')
        url = exact_json(read_regular(direct))
        if type(url) is not dict:
            raise ValueError('direct_url metadata must be an object')
        if 'dir_info' in url:
            info = url['dir_info']
            if type(info) is not dict or info.get('editable') is not False:
                raise ValueError('editable or ambiguous directory installation rejected')
    module_records = {n[len('specorganon/'):] for n in records
                      if n.startswith('specorganon/') and n.endswith('.py')}
    if module_records != recorded_modules or module_records != _inventory(package):
        raise ValueError('wheel RECORD/package module inventories differ')
    return records


def launch(plan, expected, operation):
    _digest(expected)
    if type(operation) is not str or operation not in ('run', 'report'):
        raise ValueError('run or report operation required')
    allowed = {'specorganon', 'specorganon.t_native_entry'}
    if any(n.startswith('specorganon.') and n not in allowed for n in sys.modules):
        raise ValueError('fresh process required for installed T pilot bootstrap')
    raw = read_regular(plan)
    if sha(raw) != expected:
        raise ValueError('plan digest differs before imports')
    record = exact_json(raw)
    if (type(record) is not dict or type(record.get('schema')) is not int or record['schema'] != 1
            or type(record.get('protocol')) is not str or record['protocol'] != 'T-native-development-v1'
            or type(record.get('classification')) is not str
            or record['classification'] != 'prospective public T native development'
            or type(record.get('candidate_version')) is not str or not record['candidate_version']):
        raise ValueError('versioned prospective public T native plan required')
    source_name = record.get('source_root')
    if type(source_name) is not str or not source_name:
        raise ValueError('absolute source root required')
    source = _absolute(source_name)
    if str(source) != source_name:
        raise ValueError('canonical absolute source root required')
    bindings = record.get('source_sha256')
    if type(bindings) is not dict or not bindings or len(bindings) > 512:
        raise ValueError('bounded source bindings must be a map')
    for name, pin in bindings.items():
        relative = _relative(name)
        _digest(pin)
        if sha(read_regular(source / relative)) != pin:
            raise ValueError('registered source differs: ' + name)
    package = _absolute(__file__).parent
    initializer = sys.modules.get('specorganon')
    if (initializer is not None and
            (getattr(initializer, '__file__', None) != str(package / '__init__.py')
             or list(getattr(initializer, '__path__', [])) != [str(package)])):
        raise ValueError('package initializer must belong to the installed entry package')
    records = _installed_distribution(package, source, record['candidate_version'])
    loader = InstalledSources(package, source, bindings)
    for path, captured, pin in loader.modules.values():
        item = records['specorganon/' + path.relative_to(package).as_posix()]
        record_hash = item.hash
        encoded = base64.urlsafe_b64encode(bytes.fromhex(pin)).rstrip(b'=').decode('ascii')
        if (record_hash is None or record_hash.mode != 'sha256' or record_hash.value != encoded
                or type(item.size) is not int or item.size != len(captured)):
            raise ValueError('wheel RECORD module hash or size differs')
    loader.check_inventory()
    # Entry/init have already executed within the declared trusted boundary.
    # All subsequent package imports, including the initializer, use the snapshot.
    sys.modules.pop('specorganon', None)
    sys.meta_path.insert(0, loader)
    try:
        from specorganon.t_native_pilot import execute
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
        if (type(result) is not dict or type(result.get('status')) is not str
                or result['status'] not in ('closed', 'incomplete', 'rejected')):
            raise ValueError('pilot result must contain a closed, incomplete or rejected status')
        if result['status'] != 'closed':
            result = {**result, 'goal_achieved': False}
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
        return 0 if result['status'] == 'closed' else 2
    except (ValueError, OSError, TypeError, KeyError, ImportError, SyntaxError, csv.Error) as exc:
        print(json.dumps({'status': 'rejected', 'error_type': type(exc).__name__,
                          'reason': str(exc), 'goal_achieved': False}, allow_nan=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
