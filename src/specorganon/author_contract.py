"""Compact machine-readable author grammar; never repairs native content."""
from __future__ import annotations
import re
from .engine import ITEM_ID
from .workflow import KIND_TO_PHASE, PHASE_BY_ID
from .runner import PUT_REQUIRED_FIELDS, PUT_OPTIONAL_FIELDS, MANIFEST_FIELDS


def author_manifest_contract(phase):
    """Declare strict syntax; controller/engine remain authoritative."""
    if phase not in PHASE_BY_ID:
        raise ValueError("unknown author phase")
    return {
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
