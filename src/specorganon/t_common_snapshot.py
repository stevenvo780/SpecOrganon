"""Pure physical evidence snapshot exporter for candidate dev10 / method T.

Exports host-captured pre-audit evidence to an immutable, bounded, mode 0700
directory without promoting it to completion or asserting execution independence.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import stat
import uuid

from .common_evidence import read_snapshot, _exact, _sha, _name
from .ledger import strict_json_loads
from .role_jobs import _safe, _read, _parent, canonical, digest, JobError
from .software_controller import encoded_contribution

LIMIT_PHYSICAL_BYTES = 128000
LIMIT_DELIVERY_ENCODED = 20000
LIMIT_DOCUMENTS_ENCODED = 54000
LIMIT_STREAM_ENCODED = 4000
MAX_CAPTURES = 80
MAX_RECEIPTS = 80
MAX_STREAMS = 160
MAX_FILES_PER_GROUP = 256
MAX_LOCATORS = 512
ALLOWED_KINDS = frozenset({'criteria', 'planning', 'delivery', 'tests', 'execution', 'review'})


def _check_root(root_path: Path | str) -> Path:
    root = _safe(root_path)
    if not root.exists():
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = root.lstat()
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError('root must be a directory')
    if info.st_uid != os.geteuid() or (info.st_mode & 0o077):
        raise ValueError('private owned mode0700 root required')
    return root


def _ensure_dir(d: Path, root: Path) -> None:
    cur = root
    rel = d.relative_to(root)
    for part in rel.parts:
        cur = cur / part
        if not cur.exists():
            cur.mkdir(mode=0o700)
        info = cur.lstat()
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError(f'path is not a directory: {cur}')
        if info.st_uid != os.geteuid() or (info.st_mode & 0o077):
            raise ValueError(f'private owned mode0700 directory required: {cur}')


def _put(root: Path, rel_name: str, raw: bytes) -> dict:
    if len(raw) > LIMIT_PHYSICAL_BYTES:
        raise ValueError(f'file exceeds {LIMIT_PHYSICAL_BYTES} bytes: {rel_name}')
    _name(rel_name)
    path = _safe(root / rel_name)
    parent = path.parent
    _ensure_dir(parent, root)
    if path.exists():
        if _read(path, LIMIT_PHYSICAL_BYTES) != raw:
            raise ValueError(f'immutable snapshot bytes changed: {rel_name}')
    else:
        parent_fd, leaf = _parent(path)
        temp = '.' + leaf + '.' + uuid.uuid4().hex
        try:
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent_fd)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, leaf, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
            os.fsync(parent_fd)
        finally:
            try:
                os.unlink(temp, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
            os.close(parent_fd)
    return {'path': rel_name, 'sha256': digest(raw)}


def _validate_inputs(contract, policy, captures, receipts, streams):
    # contract
    if type(contract) is not str or not contract.strip():
        raise ValueError('empty common contract')
    contract_raw = contract.encode('utf-8')
    if len(contract_raw) > LIMIT_PHYSICAL_BYTES:
        raise ValueError('contract exceeds byte limit')
    _name('host/contract.txt')

    # policy
    if type(policy) is not dict or not policy:
        raise ValueError('empty common policy')
    if policy.get('method') not in (None, 'T'):
        raise ValueError('policy method must be T')
    policy_raw = canonical(policy)
    if len(policy_raw) > LIMIT_PHYSICAL_BYTES:
        raise ValueError('policy exceeds byte limit')
    _name('host/policy.json')

    # captures
    if type(captures) is not list or not (1 <= len(captures) <= MAX_CAPTURES):
        raise ValueError('captures list must be non-empty and <= 80')
    seen_cp_ids = set()
    unique_captures = {}
    checkpoints = []
    prev_sha = None

    for seq, cap in enumerate(captures, 1):
        _exact(cap, ('id', 'kind', 'job_id', 'request_sha256', 'delivery', 'documents'), 'capture')
        cp_id = _name(cap['id'])
        if cp_id in seen_cp_ids:
            raise ValueError('duplicate checkpoint id: ' + cp_id)
        seen_cp_ids.add(cp_id)

        if type(cap['kind']) is not str or cap['kind'] not in ALLOWED_KINDS:
            raise ValueError('invalid capture kind: ' + str(cap['kind']))
        job_id = _name(cap['job_id'])
        req_sha = _sha(cap['request_sha256'])

        # delivery
        deliv = cap['delivery']
        if type(deliv) is not dict or len(deliv) > MAX_FILES_PER_GROUP:
            raise ValueError('invalid delivery file map')
        for name, text in deliv.items():
            _name(name)
            _name('delivery/' + name)
            if type(text) is not str:
                raise ValueError('delivery content must be text')
            if len(text.encode('utf-8')) > LIMIT_PHYSICAL_BYTES:
                raise ValueError('delivery file exceeds byte limit: ' + name)
        if encoded_contribution(deliv) > LIMIT_DELIVERY_ENCODED:
            raise ValueError('delivery exceeds encoded contribution budget')

        # documents
        docs = cap['documents']
        if type(docs) is not dict or len(docs) > MAX_FILES_PER_GROUP:
            raise ValueError('invalid documents file map')
        for name, text in docs.items():
            _name(name)
            _name('documents/' + name)
            if type(text) is not str:
                raise ValueError('document content must be text')
            if len(text.encode('utf-8')) > LIMIT_PHYSICAL_BYTES:
                raise ValueError('document exceeds byte limit: ' + name)
        if encoded_contribution(docs) > LIMIT_DOCUMENTS_ENCODED:
            raise ValueError('documents exceed encoded contribution budget')

        # Historical capture payload
        hist_val = {'delivery': deliv, 'documents': docs}
        hist_raw = canonical(hist_val)
        if len(hist_raw) > LIMIT_PHYSICAL_BYTES:
            raise ValueError('historical capture exceeds byte limit')
        # All subsequent hashes and writes refer to this detached byte cut.
        hist_val = strict_json_loads(hist_raw.decode())
        deliv, docs = hist_val['delivery'], hist_val['documents']
        hist_sha = digest(hist_raw)
        _name('captures/' + hist_sha + '.json')
        unique_captures[hist_sha] = (hist_raw, hist_val)

        deliv_sha = digest(canonical(deliv))
        docs_sha = digest(canonical(docs))

        cp_event = {
            'schema': 1,
            'id': cp_id,
            'sequence': seq,
            'previous_sha256': prev_sha,
            'kind': cap['kind'],
            'job_id': job_id,
            'request_sha256': req_sha,
            'delivery_sha256': deliv_sha,
            'documents_sha256': docs_sha,
        }
        cp_raw = canonical(cp_event)
        if len(cp_raw) > LIMIT_PHYSICAL_BYTES:
            raise ValueError('checkpoint exceeds byte limit')
        _name('checkpoints/' + cp_id + '.json')
        cp_sha = digest(cp_raw)
        checkpoints.append((cp_id, cp_raw, cp_sha))
        prev_sha = cp_sha

    # Final delivery cannot be empty
    # Freeze the exact already validated historical bytes, not caller-owned
    # dictionaries which could change while this export waits for its lock.
    final_capture = strict_json_loads(hist_raw.decode())
    final_deliv = final_capture['delivery']
    if not final_deliv:
        raise ValueError('final delivery map cannot be empty')
    final_docs = final_capture['documents']

    if not (1 <= len(unique_captures) <= MAX_CAPTURES):
        raise ValueError('invalid bounded unique historical captures')

    # receipts
    if type(receipts) is not dict or len(receipts) > MAX_RECEIPTS:
        raise ValueError('invalid bounded receipt map')
    validated_receipts = {}
    test_jobs = set()
    for jid, r in receipts.items():
        _name(jid)
        _name('receipts/' + jid + '.json')
        _exact(r, ('kind', 'value'), 'receipt')
        if type(r['kind']) is not str or r['kind'] not in ('role', 'test'):
            raise ValueError('unknown receipt provenance kind')
        r_raw = canonical(r['value'])
        if len(r_raw) > LIMIT_PHYSICAL_BYTES:
            raise ValueError('receipt value exceeds byte limit: ' + jid)
        if r['kind'] == 'test':
            if type(r['value']) is not dict:
                raise ValueError('test receipt value must be an object')
            for stream in ('stdout', 'stderr'):
                _sha(r['value'].get(stream + '_sha256'))
                count = r['value'].get(stream + '_bytes')
                if type(count) is not int or not 0 <= count <= LIMIT_PHYSICAL_BYTES:
                    raise ValueError('test receipt stream count must be a bounded integer')
            test_jobs.add(jid)
        validated_receipts[jid] = (r['kind'], r_raw, strict_json_loads(r_raw.decode()))

    # streams
    if type(streams) is not dict or len(streams) > MAX_STREAMS:
        raise ValueError('invalid bounded measured stream map')
    expected_streams = {f'{jid}/{stream}' for jid in test_jobs for stream in ('stdout', 'stderr')}
    if set(streams.keys()) != expected_streams:
        raise ValueError('measured test streams missing or unbound')

    validated_streams = {}
    for sname, sraw in streams.items():
        _name(sname)
        _name('streams/' + sname + '.bin')
        if type(sraw) is not bytes:
            raise ValueError('stream data must be bytes')
        if len(sraw) > LIMIT_PHYSICAL_BYTES:
            raise ValueError('stream exceeds byte limit: ' + sname)
        try:
            stext = sraw.decode('utf-8')
        except UnicodeDecodeError as exc:
            raise ValueError('stream bytes must be valid utf-8: ' + sname) from exc
        jid, stream = sname.rsplit('/', 1)
        r_val = validated_receipts[jid][2]
        if digest(sraw) != r_val.get(stream + '_sha256'):
            raise ValueError('measured test stream sha differs from receipt: ' + sname)
        if len(sraw) != r_val.get(stream + '_bytes'):
            raise ValueError('measured test stream bytes differ from receipt: ' + sname)
        if encoded_contribution(stext) > LIMIT_STREAM_ENCODED:
            raise ValueError('measured test stream exceeds budget: ' + sname)
        validated_streams[sname] = sraw

    # Max locators guard
    total_locators = (
        1
        + 1
        + len(final_deliv)
        + len(final_docs)
        + len(checkpoints)
        + len(unique_captures)
        + len(validated_receipts)
        + len(validated_streams)
    )
    if total_locators > MAX_LOCATORS:
        raise ValueError(f'total locators ({total_locators}) exceed guard limit ({MAX_LOCATORS})')

    manifest = {
        'schema': 2,
        'method': 'T',
        'contract': {'path': 'host/contract.txt', 'sha256': digest(contract_raw)},
        'policy': {'path': 'host/policy.json', 'sha256': digest(policy_raw)},
        'delivery': {n: {'path': f'delivery/{n}', 'sha256': digest(final_deliv[n].encode('utf-8'))} for n in final_deliv},
        'documents': {n: {'path': f'documents/{n}', 'sha256': digest(final_docs[n].encode('utf-8'))} for n in final_docs},
        'checkpoints': [{'id': cid, 'path': f'checkpoints/{cid}.json', 'sha256': csha} for cid, _, csha in checkpoints],
        'captures': {sha: {'path': f'captures/{sha}.json', 'sha256': sha} for sha in unique_captures},
        'receipts': {jid: {'path': f'receipts/{jid}.json', 'sha256': digest(r_raw), 'kind': r_kind} for jid, (r_kind, r_raw, _) in validated_receipts.items()},
        'streams': {sname: {'path': f'streams/{sname}.bin', 'sha256': digest(sraw)} for sname, sraw in validated_streams.items()},
    }
    physical = [entry['path'] for key in ('delivery', 'documents', 'receipts', 'streams', 'captures')
                for entry in manifest[key].values()] + [entry['path'] for entry in manifest['checkpoints']]
    for name in physical:
        if any(parent.as_posix() in physical for parent in Path(name).parents):
            raise ValueError('snapshot file/directory namespace conflict')
    manifest_raw = canonical(manifest)
    if len(manifest_raw) > LIMIT_PHYSICAL_BYTES:
        raise ValueError('snapshot manifest exceeds byte limit')

    return (
        contract_raw,
        policy_raw,
        final_deliv,
        final_docs,
        checkpoints,
        unique_captures,
        validated_receipts,
        validated_streams,
        manifest_raw,
    )


@contextmanager
def _export_lock(root):
    path = root / '.snapshot.lock'
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise ValueError('invalid private snapshot lock')
        fcntl.flock(fd, fcntl.LOCK_EX)
        named = path.lstat()
        if (info.st_dev, info.st_ino) != (named.st_dev, named.st_ino):
            raise ValueError('snapshot lock changed during acquisition')
        yield
    finally:
        os.close(fd)


def export_snapshot(root, *, contract, policy, captures, receipts, streams) -> tuple[dict, dict]:
    """Export host-captured evidence as a pure physical schema 2 snapshot.

    Returns (snapshot, reference) where reference is {'path': str(root_abs), 'manifest_sha256': pin}.
    """
    (
        contract_raw,
        policy_raw,
        final_deliv,
        final_docs,
        checkpoints,
        unique_captures,
        validated_receipts,
        validated_streams,
        manifest_raw,
    ) = _validate_inputs(contract, policy, captures, receipts, streams)

    root = _check_root(root)

    with _export_lock(root):
        if (root / 'snapshot.json').exists() and _read(root / 'snapshot.json', LIMIT_PHYSICAL_BYTES) != manifest_raw:
            raise ValueError('immutable snapshot manifest changed')
        # 1. contract & policy
        _put(root, 'host/contract.txt', contract_raw)
        _put(root, 'host/policy.json', policy_raw)

        # 2. final delivery
        for name, text in final_deliv.items():
            _put(root, f'delivery/{name}', text.encode('utf-8'))

        # 3. final documents
        for name, text in final_docs.items():
            _put(root, f'documents/{name}', text.encode('utf-8'))

        # 4. checkpoints
        for cid, cp_raw, _ in checkpoints:
            _put(root, f'checkpoints/{cid}.json', cp_raw)

        # 5. historical captures
        for sha, (hist_raw, _) in unique_captures.items():
            _put(root, f'captures/{sha}.json', hist_raw)

        # 6. receipts
        for jid, (_, r_raw, _) in validated_receipts.items():
            _put(root, f'receipts/{jid}.json', r_raw)

        # 7. streams
        for sname, sraw in validated_streams.items():
            _put(root, f'streams/{sname}.bin', sraw)

        # 8. snapshot manifest (final commit marker)
        _put(root, 'snapshot.json', manifest_raw)

        pin = digest(manifest_raw)
        snapshot = read_snapshot(root, pin)
        reference = {'path': str(root), 'manifest_sha256': pin}
        return snapshot, reference


__all__ = ['export_snapshot']
