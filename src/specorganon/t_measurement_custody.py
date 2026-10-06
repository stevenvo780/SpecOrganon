"""Private pre-measurement custody for T; no semantic audit or execution claim.

Called under the software controller's case lock BEFORE its executor. The first
seal never moves to a later ledger or easier test battery. It is a prerequisite
for the future common auditor, not evidence of D/G/H acceptance by itself.
"""
from __future__ import annotations

from pathlib import Path
import os
import time
import uuid

from . import engine
from .ledger import strict_json_loads
from .role_jobs import _read, _parent, _safe, canonical, digest


class CustodyError(ValueError):
    pass


def _put(path, raw):
    if path.exists():
        if _read(path, 64 * 1024 * 1024) != raw:
            raise CustodyError('immutable T custody bytes changed')
    else:
        parent_fd, name = _parent(path)
        temp = '.' + name + '.' + uuid.uuid4().hex
        try:
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=parent_fd)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(raw); stream.flush(); os.fsync(stream.fileno())
            os.replace(temp, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
            os.fsync(parent_fd)
        finally:
            try: os.unlink(temp, dir_fd=parent_fd)
            except FileNotFoundError: pass
            os.close(parent_fd)


def _root(controller):
    path = _safe(controller.root / 'measurement-custody')
    path.mkdir(exist_ok=True, mode=0o700)
    if path.stat().st_uid != os.geteuid() or path.stat().st_mode & 0o022:
        raise CustodyError('private owned T custody directory required')
    return path


def _load(controller):
    root = _root(controller)
    path = root / 'first.json'
    if not path.exists():
        return None
    seal = strict_json_loads(_read(path).decode())
    if (type(seal) is not dict or set(seal) != {
            'schema', 'scope', 'job_id', 'source_fingerprint', 'source_state',
            'files', 'criteria', 'ancestors', 'test_partition', 'argv', 'test_id',
            'ledger_sha256', 'policy_sha256', 'clock'} or seal['schema'] != 1):
        raise CustodyError('invalid T criteria custody seal')
    ledger = _read(root / 'ledger-before-first-measure.json', 64 * 1024 * 1024)
    if digest(ledger) != seal['ledger_sha256']:
        raise CustodyError('original T ledger capture changed')
    if digest(canonical(seal['source_state'])) != seal['source_fingerprint']:
        raise CustodyError('original T state capture changed')
    pin = _read(root / 'first.sha256').decode()
    if pin != digest(canonical(seal)):
        raise CustodyError('original T criteria capture changed')
    if digest(_read(controller.root / 'controller.json')) != seal['policy_sha256']:
        raise CustodyError('original T custody policy changed')
    current = strict_json_loads(_read(controller.case / 'organon.json', 64 * 1024 * 1024).decode())
    original = strict_json_loads(ledger.decode())
    if (current['project'] != original['project'] or current['schema'] != original['schema']
            or current['events'][:len(original['events'])] != original['events']):
        raise CustodyError('current ledger no longer extends the pre-measurement ledger')
    return seal


def verify_sealed_battery(controller, files, argv=None):
    """Permit repair of original mutable files, never of the sealed battery."""
    seal = _load(controller)
    if seal is None:
        raise CustodyError('missing original T pre-measurement criteria capture')
    partition = seal['test_partition']
    if set(files) != set(partition['test_files']) | set(partition['mutable_files']):
        raise CustodyError('T repair cannot add or remove sealed delivery files')
    if any(files.get(name) != seal['files'][name] for name in partition['test_files']):
        raise CustodyError('T repair cannot change the sealed own test battery')
    if argv is not None and argv != seal['argv']:
        raise CustodyError('T repair cannot change the sealed own test argv')
    return seal


def before_measure(controller, pending):
    """Persist full original criteria/ancestors/ledger before first dispatch.

An interrupted seal can complete its identical writes. An existing seal is
verified and reused; a second measurement cannot overwrite original criteria.
Actual test provenance must still be verified by the executor and common audit.
"""
    state = engine.get_state(controller.case)
    files = controller._files()
    if (canonical(state) != canonical(pending['source_state']) or files != pending['source_files']
            or digest(canonical(state)) != pending['source_fingerprint']):
        raise CustodyError('T pre-measurement source is no longer current')
    existing = _load(controller)
    if existing is not None:
        if pending['test_id'] != existing['test_id']:
            raise CustodyError('T measurement test identity changed')
        verify_sealed_battery(controller, files, state['items'][pending['test_id']]['data']['argv'])
        return existing
    if (not state['phases']['specify']['accepted'] or state['open_challenges']):
        raise CustodyError('T criteria must have current accepted specify before measurement')
    criteria = {key: item for key, item in state['items'].items() if item['kind'] == 'criterion'}
    if not criteria or any(v['stale'] or v['contested'] or v['issues'] for v in criteria.values()):
        raise CustodyError('T pre-measurement criteria absent or invalid')
    ancestors = {key: engine.trace(controller.case, key)['ancestors'] for key in criteria}
    program = controller._checkpoint('program')
    tests = controller._checkpoint('tests')
    if not program or not tests or tests['test_id'] != pending['test_id']:
        raise CustodyError('T pre-measurement custody needs both original build seals')
    test_files = sorted(set(files) - set(program['files']))
    if (not test_files or not set(program['files']) <= set(files)
            or tests['delivery_tree_sha256'] != digest(canonical(files))):
        raise CustodyError('T original test partition differs from sealed build stages')
    ledger = _read(controller.case / 'organon.json', 64 * 1024 * 1024)
    if engine.get_state(controller.case) != state:
        raise CustodyError('T criteria ledger changed during capture')
    root = _root(controller)
    draft = root / 'prepared.json'
    candidate = {'schema': 1,
        'scope': 'Host-captured before executor; no execution/semantic D/G/H claim',
        'job_id': pending['job_id'], 'source_fingerprint': pending['source_fingerprint'],
        'source_state': state, 'files': files, 'criteria': criteria, 'ancestors': ancestors,
        'test_partition': {'test_files': test_files, 'mutable_files': sorted(program['files'])},
        'argv': state['items'][pending['test_id']]['data']['argv'], 'test_id': pending['test_id'],
        'ledger_sha256': digest(ledger), 'policy_sha256': digest(_read(controller.root / 'controller.json')),
        'clock': {'boottime_ns': time.clock_gettime_ns(time.CLOCK_BOOTTIME),
                  'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip()}}
    # Preparation binds the clock once, even if the process dies between writes.
    if draft.exists():
        prepared = strict_json_loads(_read(draft).decode())
        candidate['clock'] = prepared['clock']
    _put(draft, canonical(candidate))
    _put(root / 'ledger-before-first-measure.json', ledger)
    _put(root / 'first.sha256', digest(canonical(candidate)).encode())
    # The manifest is the final commit marker, after every referenced byte.
    _put(root / 'first.json', canonical(candidate))
    return _load(controller)
