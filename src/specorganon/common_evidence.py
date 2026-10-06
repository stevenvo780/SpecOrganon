"""Read host-captured common-audit evidence without promoting it to completion.

The manifest digest must come from the controller's private checkpoint, outside
the role response. This verifies bytes and checkpoint order, not the honesty of
a host controlling the entire journal, semantic truth, or method completion.
Receipt files alone are insufficient: a trusted transport verifier is mandatory
for every declared receipt locator. Neither authors nor reviewers supply that
callable. The eventual controller must separately enforce stage chronology and
resource accounting; this module never returns a common_complete flag.
"""
from __future__ import annotations

import copy
from pathlib import Path
import re

from .common_review import declaration, summarize_assertions
from .ledger import strict_json_loads
from .neutral_author import PATH_PATTERN
from .role_jobs import _read, _safe, canonical, digest


def _exact(value, keys, label):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError('invalid ' + label)
    return value


def _sha(value):
    if type(value) is not str or re.fullmatch(r'[0-9a-f]{64}', value) is None:
        raise ValueError('invalid evidence digest')
    return value


def _name(value):
    if type(value) is not str or len(value) > 200 or re.fullmatch(PATH_PATTERN, value) is None:
        raise ValueError('unsafe evidence name')
    return value


def _json(raw):
    return strict_json_loads(raw.decode('utf-8'))


def read_snapshot(root, expected_manifest_sha256):
    """Capture and verify one bounded immutable manifest's referenced bytes.

    Returns host data plus physical locator bytes. Reading a receipt verifies its
    bytes only. The caller must additionally use validate_bound_audit with the
    trusted journal/transport verifier, and independently enforce actual stages.
    """
    root = _safe(root)
    manifest_raw = _read(root / 'snapshot.json', 128000)
    if digest(manifest_raw) != _sha(expected_manifest_sha256):
        raise ValueError('snapshot manifest differs from private checkpoint')
    m = _exact(_json(manifest_raw),
               ('schema','method','contract','policy','delivery','documents','checkpoints','receipts'),
               'snapshot manifest')
    if type(m['schema']) is not int or m['schema'] != 1:
        raise ValueError('unsupported snapshot schema')
    from .common_review import checklist
    checklist(m['method'])
    locators = {}
    physical_paths = set()

    def capture(ref, limit):
        _exact(ref, ('path','sha256'), 'physical reference')
        name = _name(ref['path'])
        if name in physical_paths or name == 'snapshot.json':
            raise ValueError('evidence namespaces must use distinct physical files')
        physical_paths.add(name)
        raw = _read(root / name, limit)
        if digest(raw) != _sha(ref['sha256']):
            raise ValueError('evidence bytes differ: ' + name)
        return raw

    contract_raw = capture(m['contract'], 128000)
    policy_raw = capture(m['policy'], 128000)
    if not contract_raw.decode('utf-8').strip():
        raise ValueError('empty common contract')
    policy = _json(policy_raw)
    if type(policy) is not dict or not policy:
        raise ValueError('empty common policy')
    locators['contract:public'] = contract_raw
    locators['policy:captured'] = policy_raw
    maps = {}
    for group in ('delivery','documents'):
        refs = m[group]
        if type(refs) is not dict or len(refs) > 256:
            raise ValueError('invalid bounded evidence file map')
        texts = {}
        for name, ref in refs.items():
            _name(name)
            raw = capture(ref, 128000)
            texts[name] = raw.decode('utf-8')
            locators[('document' if group == 'documents' else group) + ':' + name] = raw
        maps[group] = texts
    if not maps['delivery']:
        raise ValueError('snapshot has no delivery')
    history = m['checkpoints']
    if type(history) is not list or not 1 <= len(history) <= 80:
        raise ValueError('invalid bounded checkpoint history')
    previous = None
    captured_history = []
    seen = set()
    for sequence, ref in enumerate(history, 1):
        _exact(ref, ('id','path','sha256'), 'checkpoint reference')
        name = _name(ref['id'])
        if name in seen:
            raise ValueError('duplicate checkpoint id')
        seen.add(name)
        raw = capture({'path':ref['path'],'sha256':ref['sha256']}, 128000)
        event = _exact(_json(raw), ('schema','id','sequence','previous_sha256','kind',
                        'job_id','request_sha256','delivery_sha256','documents_sha256'), 'checkpoint')
        if (type(event['schema']) is not int or event['schema'] != 1 or event['id'] != name
                or type(event['sequence']) is not int or event['sequence'] != sequence
                or event['previous_sha256'] != previous
                or event['kind'] not in ('criteria','planning','delivery','tests','execution','review')):
            raise ValueError('checkpoint chain or sequence diverged')
        _name(event['job_id'])
        for key in ('request_sha256','delivery_sha256','documents_sha256'):
            _sha(event[key])
        previous = ref['sha256']
        captured_history.append(event)
        locators['checkpoint:' + name] = raw
    latest = captured_history[-1]
    if (latest['delivery_sha256'] != digest(canonical(maps['delivery']))
            or latest['documents_sha256'] != digest(canonical(maps['documents']))):
        raise ValueError('current files differ from final checkpoint')
    receipt_refs = m['receipts']
    if type(receipt_refs) is not dict or len(receipt_refs) > 80:
        raise ValueError('invalid bounded receipt map')
    receipts = {}
    for name, ref in receipt_refs.items():
        _name(name)
        _exact(ref, ('path','sha256','kind'), 'receipt reference')
        if ref['kind'] not in ('role','test'):
            raise ValueError('unknown receipt provenance kind')
        raw = capture({'path':ref['path'],'sha256':ref['sha256']}, 128000)
        receipts[name] = {'kind':ref['kind'],'value':_json(raw),'raw_sha256':ref['sha256']}
        locators['receipt:' + name] = raw
    binding = {'contract_sha256':m['contract']['sha256'],
               'policy_sha256':m['policy']['sha256'],
               'delivery_sha256':digest(canonical(maps['delivery'])),
               'documents_sha256':digest(canonical(maps['documents'])),
               'history_sha256':digest(canonical(captured_history))}
    # Re-read the manifest to detect a concurrent replacement while capturing.
    if _read(root / 'snapshot.json', 128000) != manifest_raw:
        raise ValueError('manifest changed during capture')
    return {'method':m['method'],'binding':binding,'locators':locators,
            'delivery':maps['delivery'],'documents':maps['documents'],
            'history':captured_history,'receipts':receipts,'policy':policy,
            'manifest_sha256':expected_manifest_sha256}


def validate_bound_audit(snapshot, declared, review, *, verify_receipt=None):
    """Check bound bytes/locators, preserving assertions and refusing fake receipts.

    verify_receipt(name, kind, captured_value, snapshot) must be a trusted host
    transport/journal verifier, returning exactly True or raising. This helper
    cannot infer role independence, test success, stage chronology or F from it.
    """
    declared = declaration(declared)
    assertions = summarize_assertions(review, declared)
    if declared['method'] != snapshot['method'] or declared['binding'] != snapshot['binding']:
        raise ValueError('common audit differs from captured snapshot')
    for locator in declared['locators']:
        if locator not in snapshot['locators']:
            raise ValueError('unresolved physical locator: ' + locator)
        if locator.startswith('receipt:'):
            name = locator.removeprefix('receipt:')
            receipt = snapshot['receipts'][name]
            if not callable(verify_receipt) or verify_receipt(
                    name, receipt['kind'], copy.deepcopy(receipt['value']), copy.deepcopy(snapshot)) is not True:
                raise ValueError('receipt requires actual private journal verification')
    return {'scope':'Verified captured bytes and supplied transport receipt checks; semantic and stage proof pending',
            'assertions':assertions,'physical_locators_verified':list(declared['locators']),
            'review':copy.deepcopy(review)}
