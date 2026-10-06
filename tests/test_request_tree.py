"""Tests for bounded pure lossless JSON DAG deduplication codec."""

import copy
import hashlib
import json
import math
import tracemalloc
import pytest

import specorganon.request_tree as codec
from specorganon.request_tree import (
    DEFAULT_MAX_BYTES,
    DEFAULT_MAX_DEPTH,
    DEFAULT_MAX_NODES,
    FORMAT_IDENTIFIER,
    SCHEMA_VERSION,
    RequestTreeError,
    RequestTreeLimitError,
    RequestTreeValidationError,
    compact_tree,
    decode_tree,
    encode_tree,
)
from specorganon.request_content import (
    RequestContentError,
    RequestContentLimitError,
    RequestContentValidationError,
    canonical_json,
    sha256_hex,
)


def test_roundtrip_canonical_byte_identity_metadata_nested():
    """Verify exact canonical byte identity for complex nested metadata."""
    metadata = {
        "files": {
            "src/main.py": "def main():\n    print('hello world')\n" * 20,
            "src/helper.py": "def helper():\n    return 42\n",
        },
        "documents": {
            "mandate.txt": "Solve the problem cleanly without regressions." * 10,
            "policy.json": "{\"allowed\": true}" * 20,
        },
        "history": [
            {
                "reservation": {"id": 1, "active": True},
                "result": {"status": "ok", "output": "def main():\n    print('hello world')\n" * 20},
                "state": {
                    "files": {
                        "src/main.py": "def main():\n    print('hello world')\n" * 20,
                    },
                    "count": 100,
                    "ratio": 0.75,
                },
            },
            {
                "reservation": {"id": 2, "active": False},
                "result": {"status": "ok", "output": "def main():\n    print('hello world')\n" * 20},
                "state": {
                    "files": {
                        "src/main.py": "def main():\n    print('hello world')\n" * 20,
                    },
                    "count": 200,
                    "ratio": 1.5,
                },
            },
        ],
    }

    orig_bytes = canonical_json(metadata)
    env = encode_tree(metadata)

    assert set(env.keys()) == {"schema", "format", "root", "nodes", "value_sha256"}
    assert env["schema"] == SCHEMA_VERSION
    assert env["format"] == FORMAT_IDENTIFIER
    assert env["root"] == len(env["nodes"]) - 1
    assert env["value_sha256"] == sha256_hex(orig_bytes)

    decoded = decode_tree(env)
    decoded_bytes = canonical_json(decoded)

    assert decoded == metadata
    assert decoded_bytes == orig_bytes


def test_large_repeated_snapshots_history_cost_criteria_compression():
    """Verify genuinely smaller envelope for repetitive nested snapshots with dict keys and small scalars."""
    step_criteria = {"accuracy": 0.98, "latency_ms": 12.5, "passed": True, "notes": "verified"}
    cost_breakdown = {"compute_tokens": 1500, "storage_cents": 2, "currency": "USD"}
    history = []
    for i in range(100):
        history.append({
            "step": i,
            "phase": "execution",
            "active": True,
            "cost": cost_breakdown,
            "criteria": step_criteria,
            "tags": ["prod", "dev10", "stable"],
        })
    data = {
        "run_id": "run-2026-audit-dev10",
        "iterations": 100,
        "history": history,
        "final_criteria": step_criteria,
    }

    orig_bytes = canonical_json(data)
    env = encode_tree(data)
    env_bytes = canonical_json(env)

    # Must be genuinely smaller due to key and scalar deduplication
    assert len(env_bytes) < len(orig_bytes)
    assert len(env_bytes) < len(orig_bytes) * 0.4  # Greater than 60% reduction

    compacted, is_comp = compact_tree(data)
    assert is_comp is True
    assert compacted["format"] == FORMAT_IDENTIFIER

    decoded = decode_tree(compacted)
    assert decoded == data
    assert canonical_json(decoded) == orig_bytes


def test_preserved_order_dicts_and_lists():
    """Verify dictionary key insertion order and list order are strictly preserved."""
    data = {
        "z_last": 1,
        "a_first": 2,
        "m_middle": 3,
        "b_second": 4,
        "ordered_list": [40, 10, 30, 20],
        "nested_dict": {"k3": "v3", "k1": "v1", "k2": "v2"},
    }
    env = encode_tree(data)
    decoded = decode_tree(env)

    assert list(decoded.keys()) == ["z_last", "a_first", "m_middle", "b_second", "ordered_list", "nested_dict"]
    assert list(decoded["nested_dict"].keys()) == ["k3", "k1", "k2"]
    assert decoded["ordered_list"] == [40, 10, 30, 20]
    assert canonical_json(decoded) == canonical_json(data)


def test_bool_vs_int_and_negative_zero_and_unicode():
    """Verify exact JSON types: bool is not coerced to int, -0.0 is preserved, and unicode is intact."""
    data = {
        "flag_true": True,
        "flag_false": False,
        "int_one": 1,
        "int_zero": 0,
        "float_pos_zero": 0.0,
        "float_neg_zero": -0.0,
        "float_val": 3.14159,
        "unicode_str": "Hola mundo! 🚀 日本語 ñoño \0\n\t\\\"" * 5,
    }

    orig_bytes = canonical_json(data)
    env = encode_tree(data)
    decoded = decode_tree(env)

    assert decoded["flag_true"] is True
    assert type(decoded["flag_true"]) is bool
    assert decoded["flag_false"] is False
    assert type(decoded["flag_false"]) is bool
    assert decoded["int_one"] == 1
    assert type(decoded["int_one"]) is int
    assert decoded["int_zero"] == 0
    assert type(decoded["int_zero"]) is int

    assert decoded["float_pos_zero"] == 0.0
    assert math.copysign(1.0, decoded["float_pos_zero"]) == 1.0
    assert decoded["float_neg_zero"] == -0.0
    assert math.copysign(1.0, decoded["float_neg_zero"]) == -1.0

    assert canonical_json(decoded) == orig_bytes


def test_literal_reserved_looking_keys_dicts_nulls():
    """Verify handling of structures that resemble envelope fields or contain literal nulls."""
    data = {
        "schema": 1,
        "format": "specorganon-tree-refs-v1",
        "root": 42,
        "nodes": [["null"], ["int", 99]],
        "value_sha256": "abcdef0123456789" * 4,
        "null_field": None,
        "nested_nulls": [None, {"k": None, "sub": [None]}],
    }

    orig_bytes = canonical_json(data)
    env = encode_tree(data)
    decoded = decode_tree(env)

    assert decoded == data
    assert canonical_json(decoded) == orig_bytes


def test_original_input_immutability():
    """Verify encoding does not mutate the original data structure."""
    original = {
        "a": ["text", "text"],
        "b": {"nested": "value", "sub": [1, 2]},
    }
    snapshot = copy.deepcopy(original)

    env = encode_tree(original)
    assert original == snapshot

    # Mutate decoded object, verify envelope and original are not affected
    decoded = decode_tree(env)
    decoded["a"].append("new")
    decoded["b"]["nested"] = "changed"
    assert original == snapshot


def test_independent_decoded_aliases():
    """Verify decode constructs fresh mutable containers per occurrence, no aliases between repeated dict/lists."""
    shared_dict = {"count": 1, "items": [10, 20]}
    data = {
        "occ1": shared_dict,
        "occ2": shared_dict,
        "occ_list": [shared_dict, shared_dict],
    }

    env = encode_tree(data)
    decoded = decode_tree(env)

    # Mutate occ1, ensure occ2 and occ_list elements are unchanged
    decoded["occ1"]["count"] = 999
    assert decoded["occ2"]["count"] == 1
    assert decoded["occ_list"][0]["count"] == 1

    decoded["occ1"]["items"].append(30)
    assert decoded["occ2"]["items"] == [10, 20]
    assert decoded["occ_list"][0]["items"] == [10, 20]

    decoded["occ_list"][0]["items"].append(40)
    assert decoded["occ_list"][1]["items"] == [10, 20]


def test_fallback_small_payload_uncompressed():
    """Verify compact_tree falls back to unencoded copy when envelope would be larger."""
    small = {"ok": True, "n": 1}
    compacted, is_comp = compact_tree(small)
    assert is_comp is False
    assert compacted == small
    assert "format" not in compacted

    # Ensure uncompressed fallback does not alias original
    compacted["n"] = 2
    assert small["n"] == 1


def test_reject_cyclic_and_nonfinite_and_subclasses():
    """Verify rejection of cyclic structures, nonfinite floats, and Python subclasses."""
    cyclic_list = [1, 2]
    cyclic_list.append(cyclic_list)
    with pytest.raises(RequestTreeValidationError, match="Cyclic"):
        encode_tree(cyclic_list)

    cyclic_dict = {"a": 1}
    cyclic_dict["self"] = cyclic_dict
    with pytest.raises(RequestTreeValidationError, match="Cyclic"):
        encode_tree(cyclic_dict)

    for val in [float("nan"), float("inf"), float("-inf")]:
        with pytest.raises(RequestTreeValidationError, match="Non-finite float"):
            encode_tree({"val": val})

    for base in [dict, list, str, int, float]:
        class Derived(base):
            pass
        with pytest.raises(RequestTreeValidationError, match="Invalid JSON type|Unsupported JSON type"):
            encode_tree(Derived())

    # Non-string keys
    with pytest.raises(RequestTreeValidationError, match="Dictionary key must be string|Dict key must be str"):
        encode_tree({123: "val"})


def test_reject_surrogates_in_strings():
    """Verify rejection of surrogate code points in strings."""
    with pytest.raises(RequestTreeValidationError, match="Invalid Unicode|Surrogates"):
        encode_tree({"bad": "\ud800"})

    env = encode_tree({"good": "val"})
    env["nodes"][0][1] = "\ud800"
    with pytest.raises(RequestTreeValidationError, match="Invalid Unicode|surrogates"):
        decode_tree(env)


def test_reject_tampered_root_digest():
    """Verify decode_tree rejects envelopes with tampered value_sha256."""
    env = encode_tree({"a": 1, "b": 2})
    env["value_sha256"] = "0" * 64
    with pytest.raises(RequestTreeValidationError, match="Root digest mismatch"):
        decode_tree(env)


def test_reject_tampered_envelope_structure():
    """Verify decode_tree rejects invalid envelope headers, schemas, formats, and keys."""
    env = encode_tree({"a": 1})

    # Envelope not a dict
    with pytest.raises(RequestTreeValidationError, match="Envelope must be a dict"):
        decode_tree(["not", "a", "dict"])

    # Extra key
    env_extra = copy.deepcopy(env)
    env_extra["extra"] = 123
    with pytest.raises(RequestTreeValidationError, match="Envelope keys mismatch"):
        decode_tree(env_extra)

    # Missing key
    env_missing = copy.deepcopy(env)
    del env_missing["value_sha256"]
    with pytest.raises(RequestTreeValidationError, match="Envelope keys mismatch"):
        decode_tree(env_missing)

    # Schema invalid
    for bad_schema in [2, True, 1.0, "1", None]:
        env_bad_schema = copy.deepcopy(env)
        env_bad_schema["schema"] = bad_schema
        with pytest.raises(RequestTreeValidationError, match="schema"):
            decode_tree(env_bad_schema)

    # Format invalid
    env_bad_fmt = copy.deepcopy(env)
    env_bad_fmt["format"] = "other-format"
    with pytest.raises(RequestTreeValidationError, match="Unsupported format"):
        decode_tree(env_bad_fmt)

    # Root invalid
    for bad_root in [True, 0.0, "0", None]:
        env_bad_root = copy.deepcopy(env)
        env_bad_root["root"] = bad_root
        with pytest.raises(RequestTreeValidationError, match="root"):
            decode_tree(env_bad_root)

    # Root not last index
    env_root_offset = copy.deepcopy(env)
    env_root_offset["root"] = 0
    with pytest.raises(RequestTreeValidationError, match="Root index must be"):
        decode_tree(env_root_offset)

    # Empty nodes
    env_empty = copy.deepcopy(env)
    env_empty["nodes"] = []
    env_empty["root"] = 0
    with pytest.raises(RequestTreeValidationError, match="cannot be empty"):
        decode_tree(env_empty)


def test_reject_malformed_node_shapes_and_tags():
    """Verify decode_tree rejects invalid node representations."""
    # Not a list
    env = {"schema": 1, "format": FORMAT_IDENTIFIER, "root": 0, "nodes": ["not_a_list"], "value_sha256": "a" * 64}
    with pytest.raises(RequestTreeValidationError, match="must be a list"):
        decode_tree(env)

    # Unknown tag
    env = {"schema": 1, "format": FORMAT_IDENTIFIER, "root": 0, "nodes": [["custom", 123]], "value_sha256": "a" * 64}
    with pytest.raises(RequestTreeValidationError, match="Invalid node tag"):
        decode_tree(env)

    # Shape mismatches
    bad_shapes = [
        [["null", 1]],
        [["bool"]],
        [["bool", 1]],
        [["int", True]],
        [["float", 1]],
        [["float", float("nan")]],
        [["str", 123]],
        [["array", "not_a_list"]],
        [["object", "not_a_list"]],
        [["object", [["not_a_pair"]]]],
    ]
    for nodes in bad_shapes:
        env = {"schema": 1, "format": FORMAT_IDENTIFIER, "root": 0, "nodes": nodes, "value_sha256": "a" * 64}
        with pytest.raises(RequestTreeValidationError):
            decode_tree(env)


def test_reject_malformed_references():
    """Verify forward, self, negative, and invalid type references are rejected."""
    # Self reference
    env = {
        "schema": 1, "format": FORMAT_IDENTIFIER, "root": 0,
        "nodes": [["array", [0]]], "value_sha256": "a" * 64,
    }
    with pytest.raises(RequestTreeValidationError, match="0 <= ref < 0"):
        decode_tree(env)

    # Forward reference
    env = {
        "schema": 1, "format": FORMAT_IDENTIFIER, "root": 1,
        "nodes": [["array", [1]], ["int", 42]], "value_sha256": "a" * 64,
    }
    with pytest.raises(RequestTreeValidationError, match="0 <= ref < 0"):
        decode_tree(env)

    # Negative reference
    env = {
        "schema": 1, "format": FORMAT_IDENTIFIER, "root": 1,
        "nodes": [["int", 42], ["array", [-1]]], "value_sha256": "a" * 64,
    }
    with pytest.raises(RequestTreeValidationError, match="0 <= ref < 1"):
        decode_tree(env)

    # Boolean reference (subclass of int)
    env = {
        "schema": 1, "format": FORMAT_IDENTIFIER, "root": 1,
        "nodes": [["int", 42], ["array", [False]]], "value_sha256": "a" * 64,
    }
    with pytest.raises(RequestTreeValidationError, match="child reference must be int"):
        decode_tree(env)

    # Object key ref not pointing to string node
    env = {
        "schema": 1, "format": FORMAT_IDENTIFIER, "root": 2,
        "nodes": [["int", 100], ["int", 200], ["object", [[0, 1]]]], "value_sha256": "a" * 64,
    }
    with pytest.raises(RequestTreeValidationError, match="must reference a str node"):
        decode_tree(env)


def test_reject_duplicate_keys_in_object_node():
    """Verify decode_tree rejects duplicate keys in object nodes."""
    # Same key ref duplicated
    env = {
        "schema": 1, "format": FORMAT_IDENTIFIER, "root": 3,
        "nodes": [
            ["str", "k"],
            ["int", 1],
            ["int", 2],
            ["object", [[0, 1], [0, 2]]],
        ],
        "value_sha256": "a" * 64,
    }
    with pytest.raises(RequestTreeValidationError, match="Duplicate key in object: k"):
        decode_tree(env)

    # Distinct key nodes with identical string value
    env = {
        "schema": 1, "format": FORMAT_IDENTIFIER, "root": 4,
        "nodes": [
            ["str", "dup"],
            ["str", "dup"],
            ["int", 1],
            ["int", 2],
            ["object", [[0, 2], [1, 3]]],
        ],
        "value_sha256": "a" * 64,
    }
    with pytest.raises(RequestTreeValidationError, match="Duplicate key in object: dup"):
        decode_tree(env)


def test_reject_unused_nodes():
    """Verify decode_tree rejects tables with unreferenced/unused nodes."""
    env = {
        "schema": 1, "format": FORMAT_IDENTIFIER, "root": 1,
        "nodes": [
            ["str", "unused_node"],
            ["null"],
        ],
        "value_sha256": "a" * 64,
    }
    with pytest.raises(RequestTreeValidationError, match="Unused nodes detected"):
        decode_tree(env)


def test_caller_bounds_checked_before_builder(monkeypatch):
    """Verify limits are strictly enforced bottom-up BEFORE invoking the container builder."""
    payload = {"items": [0] * 100}
    env = encode_tree(payload)

    # Monkeypatch builder to fail if invoked
    monkeypatch.setattr(codec, "_build_tree_node", lambda *_: pytest.fail("builder was invoked before limit check"))

    with pytest.raises(RequestTreeLimitError, match="Maximum nodes exceeded"):
        decode_tree(env, max_nodes=50)

    with pytest.raises(RequestTreeLimitError, match="Maximum depth exceeded"):
        decode_tree(env, max_depth=1)

    with pytest.raises(RequestTreeLimitError, match="Maximum expanded bytes estimate exceeded"):
        decode_tree(env, max_bytes=20)


def test_2_to_n_dag_expansion_checked_before_building(monkeypatch):
    """Verify exponential billion-laughs DAG expansion is rejected by limits before building."""
    # 26 levels of array duplication = 2^26 value nodes
    nodes = [["str", "leaf"]]
    for i in range(1, 26):
        nodes.append(["array", [i - 1, i - 1]])

    env = {
        "schema": 1,
        "format": FORMAT_IDENTIFIER,
        "root": 25,
        "nodes": nodes,
        "value_sha256": "0" * 64,
    }

    monkeypatch.setattr(codec, "_build_tree_node", lambda *_: pytest.fail("builder called on exponential DAG"))

    # Must fail immediately in microseconds without allocating 2^26 nodes
    with pytest.raises(RequestTreeLimitError, match="Maximum nodes exceeded|Maximum expanded bytes estimate exceeded"):
        decode_tree(env)


def test_deep_input_rejected_before_copy():
    """Verify deeply nested input is rejected at encode time."""
    deep = None
    for _ in range(150):
        deep = [deep]
    with pytest.raises(RequestTreeLimitError, match="depth"):
        encode_tree(deep)


def test_excessive_strings_rejected_without_full_utf8_buffer():
    """Verify strings exceeding byte bounds are rejected without memory bloat."""
    text = "A" * (4 * 1024 * 1024)
    tracemalloc.start()
    try:
        with pytest.raises(RequestTreeLimitError):
            encode_tree({"data": text})
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 512000


def test_escaped_huge_input_rejected_before_dumps():
    """Verify strings with heavy escaping that exceed limits fail before big json dumps."""
    # 1.5MB of quotes expands to 3MB of JSON escaped characters (\")
    text = '"' * (1500 * 1024)
    with pytest.raises(RequestTreeLimitError):
        encode_tree({"data": text})


@pytest.mark.parametrize("option", ["max_bytes", "max_nodes", "max_depth"])
@pytest.mark.parametrize("invalid", [True, 0, -1, 1.5, None, "100"])
def test_decoder_limit_types_are_strict(option, invalid):
    """Verify decoder limit arguments reject non-positive or non-integer types."""
    env = encode_tree(None)
    with pytest.raises(RequestTreeValidationError):
        decode_tree(env, **{option: invalid})


def test_exact_canonical_byte_boundary_including_json_escaping():
    """Verify exact canonical byte boundary enforcement down to single byte precision."""
    value = {'ñ\\"\n': ['\0' * 100, True, False, -0.0]}
    env = encode_tree(value)
    size = len(canonical_json(value))

    assert canonical_json(decode_tree(env, max_bytes=size)) == canonical_json(value)
    with pytest.raises(RequestTreeLimitError):
        decode_tree(env, max_bytes=size - 1)


def test_node_table_length_exceeding_bound_rejected():
    """Verify node table length > 2 * max_nodes + 1 is rejected immediately."""
    env = encode_tree([0, 1, 2, 3, 4])
    # Set max_nodes very small so len(nodes) > 2 * max_nodes + 1
    with pytest.raises(RequestTreeLimitError, match="Nodes table length"):
        decode_tree(env, max_nodes=1)


def test_exception_inheritance_compatibility():
    """Verify RequestTreeError exceptions inherit from both RequestContentError and RequestTreeError."""
    val_err = RequestTreeValidationError("test validation")
    lim_err = RequestTreeLimitError("test limit")

    assert isinstance(val_err, RequestTreeError)
    assert isinstance(val_err, RequestContentValidationError)
    assert isinstance(val_err, RequestContentError)
    assert isinstance(val_err, ValueError)

    assert isinstance(lim_err, RequestTreeError)
    assert isinstance(lim_err, RequestContentLimitError)
    assert isinstance(lim_err, RequestContentError)
    assert isinstance(lim_err, ValueError)


def test_noncompressible_table_over_original_node_cap_keeps_plain_fallback():
    # A valid original can have an encoded metadata table with >100000 nodes.
    # compact_tree must compare sizes and return plain JSON, not reject the
    # original using the original-tree limit on its larger encoded table.
    value = {f'unique-key-{i:05d}': i for i in range(12000)}
    compacted, compressed = compact_tree(value)
    assert compressed is False
    assert compacted == value and compacted is not value
    assert decode_tree(encode_tree(value)) == value


def test_small_caller_limit_bounds_envelope_before_scalar_allocation(monkeypatch):
    import tracemalloc
    from specorganon import request_tree as tree
    env = {'schema': 1, 'format': FORMAT_IDENTIFIER, 'root': 0,
           'nodes': [['str', 'x' * 1000000]], 'value_sha256': '0' * 64}
    monkeypatch.setattr(tree, '_build_tree_node', lambda *a: pytest.fail('must reject before builder'))
    tracemalloc.start()
    try:
        with pytest.raises(RequestTreeLimitError): decode_tree(env, max_bytes=16)
        _, peak = tracemalloc.get_traced_memory()
        assert peak < 512000
    finally:
        tracemalloc.stop()
