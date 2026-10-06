"""Compact machine-readable author grammar; never repairs native content."""
from __future__ import annotations
import re
import copy
from .engine import ITEM_ID
from .workflow import KIND_TO_PHASE, PHASE_BY_ID
from .runner import PUT_REQUIRED_FIELDS, PUT_OPTIONAL_FIELDS, MANIFEST_FIELDS


AUTHOR_FORMATS = frozenset({'manifest-v1', 'items-v1'})


def author_manifest_contract(phase, author_format='manifest-v1'):
    """Declare strict syntax; controller/engine remain authoritative."""
    if phase not in PHASE_BY_ID or author_format not in AUTHOR_FORMATS:
        raise ValueError("unknown author phase")
    contract = {
        "schema": 1, "advisory": True,
        "response_fields": ["schema", "manifest", "files", "reason"],
        "manifest_fields": sorted(MANIFEST_FIELDS),
        "steps_count": [1, 32], "op": "put",
        "put_required": sorted(PUT_REQUIRED_FIELDS),
        "put_optional": sorted(PUT_OPTIONAL_FIELDS),
        "id_pattern": ITEM_ID.pattern,
        "kinds": sorted(k for k, p in KIND_TO_PHASE.items()
                        if p == phase or (phase == "study" and k == "evidence")),
        "types": {"text": "nonblank str", "refs": "distinct IDs", "data": "object",
                  "expected_version": "int>=0", "expected_deps": "exact refs->int>=1"},
    }
    if author_format == 'items-v1':
        contract['response_fields'] = ['schema', 'items', 'files', 'reason']
        contract['items_required'] = sorted(PUT_REQUIRED_FIELDS - {'op'})
        contract['items_count'] = contract.pop('steps_count')
        for key in ('manifest_fields', 'put_required', 'put_optional', 'op'):
            contract.pop(key)
        contract['types'].pop('expected_version')
        contract['types'].pop('expected_deps')
        contract['assembly'] = 'Toolkit: op/schema/versions only.'
    return contract


def typed_author_manifest(response):
    """Assemble only declared mechanics; leave all native content unchanged."""
    if (type(response) is not dict or set(response) != {'schema', 'items', 'files', 'reason'}
            or type(response['schema']) is not int or response['schema'] != 1
            or type(response['items']) is not list or not 1 <= len(response['items']) <= 32
            or type(response['files']) is not dict
            or any(type(k) is not str or type(v) is not str for k, v in response['files'].items())
            or type(response['reason']) is not str or not response['reason'].strip()
            or any(type(item) is not dict or set(item) != PUT_REQUIRED_FIELDS - {'op'}
                   for item in response['items'])):
        raise ValueError('invalid typed author content contract')
    return {'schema': 1, 'steps': [{'op': 'put', **copy.deepcopy(item)} for item in response['items']]}


def manifest_error_detail(error):
    """Expose parser categories without echoing arbitrary authored values."""
    message = str(error)
    fixed = {
        "manifest needs schema 1 and a steps array", "unknown manifest fields",
        "manifest name must be a nonempty string", "manifest must contain finite JSON values",
    }
    if message in fixed:
        return message
    match = re.fullmatch(r"step ([0-9]+) (.*)", message, flags=re.DOTALL)
    if match:
        index, detail = match.groups()
        safe = {
            "must be an object", "has missing or unknown put fields", "has invalid item id",
            "needs valid kind and nonempty text", "needs distinct item ids in refs",
            "data must be an object", "expected_version must be a nonnegative integer",
            "expected_deps must map every ref to a positive version", "needs a known phase",
        }
        if detail in safe:
            return f"step {index}: {detail}"
        for prefix, category in [
            ("repeats item id ", "repeats item id"),
            ("repeats phase advance ", "repeats phase advance"),
            ("has unsupported op:", "requires op=put for author work"),
        ]:
            if detail.startswith(prefix):
                return f"step {index}: {category}"
    return "manifest violates declared grammar"
