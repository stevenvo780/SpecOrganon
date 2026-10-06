"""Tests for bounded pure lossless JSON string deduplication codec."""

import copy
import hashlib
import json
import pytest

from specorganon.request_content import (
    FORMAT_IDENTIFIER,
    SCHEMA_VERSION,
    RequestContentError,
    RequestContentLimitError,
    RequestContentValidationError,
    canonical_json,
    compact_content,
    decode_content,
    encode_content,
    sha256_hex,
)


def test_roundtrip_canonical_byte_identity_metadata_nested():
    """Verify exact canonical byte identity for metadata-like nested objects."""
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
    env = encode_content(metadata)
    assert env["schema"] == SCHEMA_VERSION
    assert env["format"] == FORMAT_IDENTIFIER
    assert len(env["string_references"]) > 0

    decoded = decode_content(env)
    decoded_bytes = canonical_json(decoded)

    assert decoded == metadata
    assert decoded_bytes == orig_bytes


def test_literal_reserved_looking_keys_dicts_nulls():
    """Verify handling of structures that resemble envelope fields or contain literal nulls."""
    data = {
        "schema": 1,
        "format": "specorganon-content-refs-v1",
        "value": None,
        "string_references": [
            {"path": ["some", "path"], "sha256": "abcdef"},
            None,
        ],
        "content_by_sha256": {
            "abc": "def",
        },
        "value_sha256": "0123456789abcdef",
        "null_field": None,
        "nested_nulls": [None, {"k": None}],
        "repeated_long": "L" * 300,
        "repeated_long_copy": "L" * 300,
    }

    orig_bytes = canonical_json(data)
    env = encode_content(data)
    decoded = decode_content(env)
    assert decoded == data
    assert canonical_json(decoded) == orig_bytes


def test_bool_vs_int_and_negative_zero_and_unicode():
    """Verify exact JSON types: bool is not coerced to int, -0.0 is preserved, and unicode is intact."""
    data = {
        "flag_true": True,
        "flag_false": False,
        "int_one": 1,
        "int_zero": 0,
        "float_neg_zero": -0.0,
        "float_val": 3.14159,
        "unicode_str": "Hola mundo! 🚀 日本語 ñoño" * 20,
        "unicode_dup": "Hola mundo! 🚀 日本語 ñoño" * 20,
    }

    orig_bytes = canonical_json(data)
    env = encode_content(data)
    decoded = decode_content(env)

    # Check types specifically
    assert decoded["flag_true"] is True
    assert type(decoded["flag_true"]) is bool
    assert decoded["flag_false"] is False
    assert type(decoded["flag_false"]) is bool
    assert decoded["int_one"] == 1
    assert type(decoded["int_one"]) is int
    assert decoded["int_zero"] == 0
    assert type(decoded["int_zero"]) is int

    assert canonical_json(decoded) == orig_bytes


def test_original_input_immutability():
    """Verify encoding does not mutate the original data structure."""
    long_str = "immutability_test_" * 30
    original = {
        "a": [long_str, long_str],
        "b": {"nested": long_str},
    }
    snapshot = copy.deepcopy(original)

    env = encode_content(original)
    assert original == snapshot
    # Ensure nested objects in env['value'] are modified, but original is intact
    assert original["a"][0] == long_str
    assert env["value"]["a"][0] is None

    # Mutate decoded, verify envelope not affected
    decoded = decode_content(env)
    decoded["a"].append("new")
    assert len(env["value"]["a"]) == 2


def test_repeated_long_strings_saving():
    """Verify bytes are saved when large repeated strings are deduplicated."""
    large_doc = "A" * 5000
    payload = {
        "current_files": {"file1": large_doc},
        "history_0": {"file1": large_doc},
        "history_1": {"file1": large_doc},
        "history_2": {"file1": large_doc},
    }
    raw_bytes = canonical_json(payload)
    env = encode_content(payload)
    env_bytes = canonical_json(env)

    assert len(env_bytes) < len(raw_bytes)
    assert len(env["content_by_sha256"]) == 1
    assert len(env["string_references"]) == 4

    compacted, compressed = compact_content(payload)
    assert compressed is True
    assert compacted["format"] == FORMAT_IDENTIFIER
    assert decode_content(compacted) == payload


def test_unique_or_small_fallback_compact_content():
    """Verify compact_content falls back to unencoded original when compression would increase size."""
    small_payload = {
        "status": "ok",
        "code": 200,
        "files": ["a", "b", "c"],
    }
    compacted, compressed = compact_content(small_payload)
    assert compressed is False
    assert compacted == small_payload
    assert "format" not in compacted

    # Test with string shorter than min_bytes repeated
    short_repeated = {
        "k1": "short",
        "k2": "short",
    }
    compacted2, compressed2 = compact_content(short_repeated)
    assert compressed2 is False
    assert compacted2 == short_repeated


def test_reject_tampered_root_digest():
    """Verify decode_content rejects envelopes with tampered value_sha256."""
    s = "Z" * 300
    data = [s, s]
    env = encode_content(data)
    env["value_sha256"] = "0" * 64
    with pytest.raises(RequestContentValidationError, match="Root digest mismatch"):
        decode_content(env)


def test_reject_tampered_content_hash():
    """Verify decode_content rejects content_by_sha256 entries whose hash doesn't match key."""
    s = "Z" * 300
    data = [s, s]
    env = encode_content(data)
    correct_sha = list(env["content_by_sha256"].keys())[0]
    env["content_by_sha256"][correct_sha] = "tampered content"
    with pytest.raises(RequestContentValidationError, match="Hash mismatch"):
        decode_content(env)


def test_reject_tampered_null_placeholder():
    """Verify decode_content rejects non-null value at reference path."""
    s = "Z" * 300
    data = [s, s]
    env = encode_content(data)
    env["value"][0] = "not null"
    with pytest.raises(RequestContentValidationError, match="Placeholder at path .* must be None/null"):
        decode_content(env)


def test_reject_bool_in_path_segment():
    """Verify decode_content rejects booleans in path segments (even though bool is int subclass)."""
    s = "Z" * 300
    data = [s, s]
    env = encode_content(data)
    env["string_references"][0]["path"] = [True]
    with pytest.raises(RequestContentValidationError, match="Path segment cannot be boolean"):
        decode_content(env)


def test_reject_missing_and_unused_ref_content():
    """Verify decode_content rejects missing refs or unused content."""
    s = "Z" * 300
    data = [s, s]
    env = encode_content(data)

    # Unused content
    dummy_text = "unused text"
    dummy_sha = sha256_hex(dummy_text.encode("utf-8"))
    env["content_by_sha256"][dummy_sha] = dummy_text
    with pytest.raises(RequestContentValidationError, match="Unused content"):
        decode_content(env)

    # Missing ref
    env2 = encode_content(data)
    del env2["content_by_sha256"][list(env2["content_by_sha256"].keys())[0]]
    with pytest.raises(RequestContentValidationError, match="missing in content_by_sha256"):
        decode_content(env2)


def test_reject_duplicate_and_overlapping_paths():
    """Verify decode_content rejects duplicate or overlapping paths."""
    s = "Z" * 300
    data = {"nested": [s, s]}
    env = encode_content(data)

    # Duplicate path
    ref0 = copy.deepcopy(env["string_references"][0])
    env["string_references"].insert(0, ref0)
    with pytest.raises(RequestContentValidationError, match="Duplicate reference path|not deterministically ordered"):
        decode_content(env)

    # Overlapping path
    env2 = encode_content(data)
    sha = env2["string_references"][0]["sha256"]
    # Path ['nested'] overlaps with ['nested', 0]
    env2["string_references"].append({"path": ["nested"], "sha256": sha})
    # Sort them using the codec's path sorting key so ordering check passes
    def sort_key(item):
        path = tuple(item["path"])
        return (tuple((0 if isinstance(p, int) else 1, p) for p in path), item["sha256"])

    env2["string_references"].sort(key=sort_key)
    with pytest.raises(RequestContentValidationError, match="Overlapping reference path"):
        decode_content(env2)


def test_reject_non_deterministic_reference_ordering():
    """Verify decode_content rejects envelopes with unsorted string_references."""
    s1 = "A" * 300
    s2 = "B" * 300
    data = {"z": s1, "a": s1, "y": s2, "b": s2}
    env = encode_content(data)
    assert len(env["string_references"]) >= 2
    # Reverse string_references
    env["string_references"].reverse()
    with pytest.raises(RequestContentValidationError, match="not deterministically ordered"):
        decode_content(env)


def test_reject_cyclic_and_nonfinite():
    """Verify rejection of cyclic structures and nonfinite floats."""
    cyclic_list = [1, 2]
    cyclic_list.append(cyclic_list)
    with pytest.raises(RequestContentValidationError, match="Cyclic reference"):
        encode_content(cyclic_list)

    nonfinite = {"val": float("nan")}
    with pytest.raises(RequestContentValidationError, match="Non-finite float"):
        encode_content(nonfinite)

    nonfinite_inf = {"val": float("inf")}
    with pytest.raises(RequestContentValidationError, match="Non-finite float"):
        encode_content(nonfinite_inf)


def test_bounded_decoder_limits():
    """Verify decoder limits (max_depth, max_nodes, max_bytes)."""
    # Test max_depth
    deep = {}
    curr = deep
    for i in range(100):
        curr["child"] = {}
        curr = curr["child"]

    env = encode_content(deep)
    with pytest.raises(RequestContentLimitError, match="Maximum depth exceeded"):
        decode_content(env, max_depth=50)

    # Test max_nodes
    many_nodes = {"items": list(range(200))}
    env_nodes = encode_content(many_nodes)
    with pytest.raises(RequestContentLimitError, match="Maximum nodes exceeded"):
        decode_content(env_nodes, max_nodes=50)

    # Test max_bytes
    big_s = "W" * 500
    data = {"a": big_s, "b": big_s}
    env_bytes = encode_content(data)
    with pytest.raises(RequestContentLimitError, match="Maximum expanded bytes estimate exceeded|exceeds max_bytes"):
        decode_content(env_bytes, max_bytes=300)


def test_compact_content_tuple_flag_explicit():
    """Test API fallback ambiguity explicitly via (representation, compressed_bool) tuple flag."""
    big_s = "M" * 1000
    compressible = {"files": [big_s, big_s, big_s]}
    res_comp, is_comp = compact_content(compressible)
    assert is_comp is True
    assert isinstance(res_comp, dict)
    assert res_comp["format"] == FORMAT_IDENTIFIER
    assert decode_content(res_comp) == compressible

    uncompressible = {"num": 1, "text": "short text"}
    res_uncomp, is_uncomp = compact_content(uncompressible)
    assert is_uncomp is False
    assert res_uncomp == uncompressible
    assert "format" not in res_uncomp


@pytest.mark.parametrize('schema', [True, 1.0, '1'])
def test_reject_non_integer_schema(schema):
    env = encode_content({'status': 'real'})
    env['schema'] = schema
    with pytest.raises(RequestContentValidationError):
        decode_content(env)


@pytest.mark.parametrize('base', [dict, list, str, int, float])
def test_reject_python_subclasses_before_copy(base):
    class Derived(base):
        pass
    with pytest.raises(RequestContentValidationError):
        encode_content(Derived())


def test_deep_encoded_input_rejected_before_recursive_copy():
    data = None
    for _ in range(1000):
        data = [data]
    with pytest.raises(RequestContentLimitError, match='depth'):
        encode_content(data)
    env = encode_content(None); env['value'] = data
    with pytest.raises(RequestContentLimitError, match='depth'):
        decode_content(env)


@pytest.mark.parametrize('option', ['max_bytes', 'max_nodes', 'max_depth'])
@pytest.mark.parametrize('invalid', [True, 0, -1, 1.5, None])
def test_decoder_limit_types_are_strict(option, invalid):
    with pytest.raises(RequestContentValidationError):
        decode_content(encode_content(None), **{option: invalid})


def test_roundtrip_at_expanded_depth_boundary_with_envelope_overhead():
    data = ["x" * 300, "x" * 300]
    for _ in range(126):
        data = [data]
    envelope = encode_content(data)
    assert canonical_json(decode_content(envelope)) == canonical_json(data)


@pytest.mark.parametrize('as_key', [False, True])
def test_excessive_strings_rejected_without_full_utf8_buffer(as_key):
    import tracemalloc
    text = 'A' * (4 * 1024 * 1024)
    value = {text: 0} if as_key else {'x': text}
    tracemalloc.start()
    try:
        with pytest.raises(RequestContentLimitError):
            encode_content(value)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 512000  # Input already exists; rejection must not copy 4 MiB.


@pytest.mark.parametrize('limits', [{'max_nodes': 5}, {'max_depth': 1}, {'max_bytes': 20}])
def test_caller_bounds_checked_before_any_deepcopy(monkeypatch, limits):
    import specorganon.request_content as codec
    envelope = encode_content({'items': [0] * 100})
    monkeypatch.setattr(codec.copy, 'deepcopy', lambda *_: pytest.fail('copied before caller limits'))
    with pytest.raises(RequestContentLimitError):
        decode_content(envelope, **limits)


def test_reference_expansion_checked_before_copy(monkeypatch):
    import specorganon.request_content as codec
    envelope = encode_content({'a': 'large string' * 100, 'b': 'large string' * 100})
    monkeypatch.setattr(codec.copy, 'deepcopy', lambda *_: pytest.fail('copied before expanded size bound'))
    with pytest.raises(RequestContentLimitError):
        decode_content(envelope, max_bytes=1500)


def test_exact_canonical_byte_boundary_including_json_escaping():
    value = {'ñ\\"\n': ['\0' * 100, True, False, -0.0]}
    envelope = encode_content(value)
    size = len(canonical_json(value))
    assert canonical_json(decode_content(envelope, max_bytes=size)) == canonical_json(value)
    with pytest.raises(RequestContentLimitError):
        decode_content(envelope, max_bytes=size-1)
