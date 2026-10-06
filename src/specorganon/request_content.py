"""Bounded pure lossless JSON string deduplication codec.

Provides:
    - encode_content(value, min_bytes=256) -> envelope
    - decode_content(envelope, max_bytes=2*1024*1024, max_nodes=100000, max_depth=128) -> original_value
    - compact_content(value, min_bytes=256) -> (representation, compressed_bool)

Envelope specification:
    {
        "schema": 1,
        "format": "specorganon-content-refs-v1",
        "value": <deep JSON clone with repeated strings >= min_bytes replaced by None>,
        "string_references": [
            {
                "path": [<key or array index>, ...],
                "sha256": "<64 hex chars>"
            },
            ...
        ],
        "content_by_sha256": {
            "<sha256>": "<original string>"
        },
        "value_sha256": "<canonical sha256 of original value>"
    }
"""

import copy
import hashlib
import json
from typing import Any, Dict, List, Optional, Set, Tuple, Union


class RequestContentError(ValueError):
    """Base error for request content codec errors."""
    pass


class RequestContentValidationError(RequestContentError):
    """Raised when JSON validation or envelope structure validation fails."""
    pass


class RequestContentLimitError(RequestContentError):
    """Raised when decoder limits (bytes, nodes, depth) are exceeded."""
    pass


FORMAT_IDENTIFIER = "specorganon-content-refs-v1"
SCHEMA_VERSION = 1
DEFAULT_MIN_BYTES = 256
DEFAULT_MAX_BYTES = 2 * 1024 * 1024  # 2 MB
DEFAULT_MAX_NODES = 100_000
DEFAULT_MAX_DEPTH = 128


def canonical_json(value: Any) -> bytes:
    """Serialize value to canonical JSON bytes.

    Rejects non-finite floats, non-string dict keys, and non-JSON types.
    """
    _validate_json_types(value)
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise RequestContentValidationError(f"Value cannot be canonically serialized: {exc}") from exc


def sha256_hex(data: bytes) -> str:
    """Compute hex SHA-256 digest of bytes."""
    return hashlib.sha256(data).hexdigest()


def _validate_json_types(value: Any, depth: int = 0, seen_ids: Optional[Set[int]] = None) -> None:
    """Check that value contains only exact finite JSON types and no cycles."""
    if seen_ids is None:
        # Check fixed input bounds before recursive validation/deepcopy/JSON.
        _check_and_count_nodes(value, 1, DEFAULT_MAX_DEPTH, DEFAULT_MAX_NODES,
                               [0], [0], DEFAULT_MAX_BYTES, set())
        seen_ids = set()

    obj_id = id(value)
    if type(value) in (dict, list):
        if obj_id in seen_ids:
            raise RequestContentValidationError("Cyclic reference detected in JSON structure")
        seen_ids.add(obj_id)

    try:
        if value is None:
            return
        elif type(value) is bool:
            # Must check bool before int because bool is a subclass of int in Python
            return
        elif type(value) is int:
            return
        elif type(value) is float:
            import math
            if not math.isfinite(value):
                raise RequestContentValidationError("Non-finite float value not allowed in JSON")
            return
        elif type(value) is str:
            return
        elif type(value) is list:
            for item in value:
                _validate_json_types(item, depth + 1, seen_ids)
        elif type(value) is dict:
            for k, v in value.items():
                if type(k) is not str:
                    raise RequestContentValidationError(f"Dict key must be str, got {type(k).__name__}")
                _validate_json_types(v, depth + 1, seen_ids)
        else:
            raise RequestContentValidationError(f"Unsupported JSON type: {type(value).__name__}")
    finally:
        if type(value) in (dict, list):
            seen_ids.remove(obj_id)


def _collect_string_occurrences(
    val: Any,
    current_path: Tuple[Union[str, int], ...],
    string_paths: Dict[str, List[Tuple[Union[str, int], ...]]],
    min_bytes: int,
) -> None:
    """Recursively collect occurrences of strings with UTF-8 byte length >= min_bytes in deterministic order."""
    if type(val) is str:
        raw = val.encode("utf-8")
        if len(raw) >= min_bytes:
            if val not in string_paths:
                string_paths[val] = []
            string_paths[val].append(current_path)
    elif type(val) is list:
        for idx, item in enumerate(val):
            _collect_string_occurrences(item, current_path + (idx,), string_paths, min_bytes)
    elif type(val) is dict:
        for k in sorted(val.keys()):
            _collect_string_occurrences(val[k], current_path + (k,), string_paths, min_bytes)


def _set_path_to_none(root: Any, path: Tuple[Union[str, int], ...]) -> None:
    """Traverse to parent and set the target location to None."""
    curr = root
    for step in path[:-1]:
        curr = curr[step]
    last = path[-1]
    curr[last] = None


def encode_content(value: Any, min_bytes: int = DEFAULT_MIN_BYTES) -> Dict[str, Any]:
    """Encode value into a deduplicated JSON envelope.

    Always returns the dictionary envelope with deep JSON clone.
    Does not mutate the input value.
    """
    if type(min_bytes) is not int or not 1 <= min_bytes <= DEFAULT_MAX_BYTES:
        raise RequestContentValidationError("min_bytes must be a positive bounded integer")
    _validate_json_types(value)
    canon_bytes = canonical_json(value)
    root_hash = sha256_hex(canon_bytes)

    # Clone value
    cloned_value = copy.deepcopy(value)

    # Collect string occurrences
    string_paths: Dict[str, List[Tuple[Union[str, int], ...]]] = {}
    _collect_string_occurrences(value, (), string_paths, min_bytes)

    # Select strings repeated >= 2 times
    repeated_strings = {s: paths for s, paths in string_paths.items() if len(paths) >= 2}

    content_by_sha256: Dict[str, str] = {}
    raw_refs: List[Tuple[Tuple[Union[str, int], ...], str]] = []

    for s, paths in repeated_strings.items():
        s_sha = sha256_hex(s.encode("utf-8"))
        content_by_sha256[s_sha] = s
        for path in paths:
            raw_refs.append((path, s_sha))
            _set_path_to_none(cloned_value, path)

    # Deterministic sort for string_references:
    # Sort by path representation
    def path_sort_key(item: Tuple[Tuple[Union[str, int], ...], str]):
        # Represent path elements consistently for sorting:
        # (type_tag, value) where int -> 0, str -> 1
        path, sha = item
        return (tuple((0 if type(p) is int else 1, p) for p in path), sha)

    raw_refs.sort(key=path_sort_key)

    string_references = [{"path": list(p), "sha256": s_sha} for p, s_sha in raw_refs]

    return {
        "schema": SCHEMA_VERSION,
        "format": FORMAT_IDENTIFIER,
        "value": cloned_value,
        "string_references": string_references,
        "content_by_sha256": content_by_sha256,
        "value_sha256": root_hash,
    }


def compact_content(
    value: Any,
    min_bytes: int = DEFAULT_MIN_BYTES,
) -> Tuple[Union[Dict[str, Any], Any], bool]:
    """Helper that encodes content if the canonical envelope size is strictly smaller than original.

    Returns (envelope, True) if compressed and smaller, else (deepcopy(value), False).
    """
    orig_canon = canonical_json(value)
    envelope = encode_content(value, min_bytes=min_bytes)
    env_canon = canonical_json(envelope)

    if len(env_canon) < len(orig_canon):
        return envelope, True
    else:
        return copy.deepcopy(value), False


def _check_and_count_nodes(
    val: Any,
    current_depth: int,
    max_depth: int,
    max_nodes: int,
    node_count: List[int],
    byte_count: List[int],
    max_bytes: int,
    seen_ids: Set[int],
) -> None:
    """Count nodes and depth in value clone, checking against decoder bounds."""
    if current_depth > max_depth:
        raise RequestContentLimitError(f"Maximum depth exceeded: {current_depth} > {max_depth}")

    node_count[0] += 1
    if node_count[0] > max_nodes:
        raise RequestContentLimitError(f"Maximum nodes exceeded: {node_count[0]} > {max_nodes}")

    obj_id = id(val)
    if type(val) in (dict, list):
        if obj_id in seen_ids:
            raise RequestContentValidationError("Cyclic reference detected")
        seen_ids.add(obj_id)

    try:
        if val is None:
            byte_count[0] += 4
        elif type(val) is bool:
            byte_count[0] += 4 if val else 5
        elif type(val) is int:
            byte_count[0] += len(str(val))
        elif type(val) is float:
            import math
            if not math.isfinite(val):
                raise RequestContentValidationError("Non-finite float in decoded value")
            byte_count[0] += len(str(val))
        elif type(val) is str:
            byte_count[0] += len(val.encode("utf-8"))
        elif type(val) is list:
            for item in val:
                _check_and_count_nodes(item, current_depth + 1, max_depth, max_nodes, node_count, byte_count, max_bytes, seen_ids)
        elif type(val) is dict:
            for k, v in val.items():
                if type(k) is not str:
                    raise RequestContentValidationError("Dictionary key must be string")
                byte_count[0] += len(k.encode("utf-8"))
                _check_and_count_nodes(v, current_depth + 1, max_depth, max_nodes, node_count, byte_count, max_bytes, seen_ids)
        else:
            raise RequestContentValidationError(f"Invalid JSON type: {type(val).__name__}")
    finally:
        if type(val) in (dict, list):
            seen_ids.remove(obj_id)

    if byte_count[0] > max_bytes:
        raise RequestContentLimitError(f"Maximum expanded bytes estimate exceeded: {byte_count[0]} > {max_bytes}")


def decode_content(
    envelope: Any,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_nodes: int = DEFAULT_MAX_NODES,
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> Any:
    """Decode an envelope back into the exact original value.

    Enforces finite JSON type validation, bound limits, deterministic structure,
    and cryptographic root digest verification.
    """
    for name, limit in (("max_bytes", max_bytes), ("max_nodes", max_nodes), ("max_depth", max_depth)):
        if type(limit) is not int or limit < 1:
            raise RequestContentValidationError(name + " must be a positive integer")
    # Bound the encoded structure before cloning or hashing any payload.
    _check_and_count_nodes(envelope, 1, DEFAULT_MAX_DEPTH + 8, DEFAULT_MAX_NODES * 4,
                           [0], [0], DEFAULT_MAX_BYTES * 4, set())
    if type(envelope) is not dict:
        raise RequestContentValidationError("Envelope must be a dict")

    # Validate required envelope keys
    required_keys = {"schema", "format", "value", "string_references", "content_by_sha256", "value_sha256"}
    if set(envelope.keys()) != required_keys:
        raise RequestContentValidationError(f"Envelope keys mismatch: expected {sorted(required_keys)}, got {sorted(envelope.keys())}")

    if type(envelope["schema"]) is not int or envelope["schema"] != SCHEMA_VERSION:
        raise RequestContentValidationError(f"Unsupported schema version: {envelope['schema']}")

    if type(envelope["format"]) is not str or envelope["format"] != FORMAT_IDENTIFIER:
        raise RequestContentValidationError(f"Unsupported format: {envelope['format']}")

    value_sha256 = envelope["value_sha256"]
    if type(value_sha256) is not str or len(value_sha256) != 64 or not all(c in "0123456789abcdef" for c in value_sha256):
        raise RequestContentValidationError("value_sha256 must be a 64-char lowercase hex string")

    content_by_sha256 = envelope["content_by_sha256"]
    if type(content_by_sha256) is not dict:
        raise RequestContentValidationError("content_by_sha256 must be a dict")

    # Validate content_by_sha256 types and hashes
    for sha, text in content_by_sha256.items():
        if type(sha) is not str or len(sha) != 64 or not all(c in "0123456789abcdef" for c in sha):
            raise RequestContentValidationError(f"Invalid sha256 key in content_by_sha256: {sha}")
        if type(text) is not str:
            raise RequestContentValidationError(f"Content for sha256 {sha} must be a str, got {type(text).__name__}")
        actual_sha = sha256_hex(text.encode("utf-8"))
        if actual_sha != sha:
            raise RequestContentValidationError(f"Hash mismatch for content_by_sha256 key {sha}: calculated {actual_sha}")

    string_references = envelope["string_references"]
    if type(string_references) is not list:
        raise RequestContentValidationError("string_references must be a list")

    # Deep copy value to avoid mutating the envelope
    _validate_json_types(envelope["value"])
    decoded = copy.deepcopy(envelope["value"])

    # Track used hashes and paths to reject duplicate, overlapping, or unused content
    used_hashes: Set[str] = set()
    seen_paths: Set[Tuple[Union[str, int], ...]] = set()

    # Verify deterministic ordering of string_references
    def path_sort_key(item: Tuple[Tuple[Union[str, int], ...], str]):
        path, sha = item
        return (tuple((0 if type(p) is int else 1, p) for p in path), sha)

    prev_key = None
    previous_path = None

    # Pass 1: Validate deterministic ordering, duplicate paths, overlapping paths, and missing references
    for ref in string_references:
        if type(ref) is not dict:
            raise RequestContentValidationError("string_reference item must be a dict")
        if set(ref.keys()) != {"path", "sha256"}:
            raise RequestContentValidationError(f"Invalid keys in string_reference: {ref.keys()}")

        ref_path = ref["path"]
        ref_sha = ref["sha256"]

        if type(ref_path) is not list:
            raise RequestContentValidationError("Reference path must be a list")
        if len(ref_path) > max_depth:
            raise RequestContentLimitError("Reference path exceeds max_depth")
        if len(ref_path) == 0:
            raise RequestContentValidationError("Reference path cannot be empty")

        for segment in ref_path:
            # Check bool first because bool is subclass of int!
            if type(segment) is bool:
                raise RequestContentValidationError(f"Path segment cannot be boolean: {segment}")
            if type(segment) not in (str, int):
                raise RequestContentValidationError(f"Path segment must be str or int, got {type(segment).__name__}")
            if type(segment) is int and segment < 0:
                raise RequestContentValidationError(f"Negative list index not allowed in path: {segment}")

        tuple_path = tuple(ref_path)

        if type(ref_sha) is not str or len(ref_sha) != 64 or not all(c in "0123456789abcdef" for c in ref_sha):
            raise RequestContentValidationError(f"Invalid reference sha256: {ref_sha}")

        # Deterministic order check
        curr_key = path_sort_key((tuple_path, ref_sha))
        if prev_key is not None and curr_key < prev_key:
            raise RequestContentValidationError("string_references is not deterministically ordered")
        prev_key = curr_key

        if tuple_path in seen_paths:
            raise RequestContentValidationError(f"Duplicate reference path: {ref_path}")

        # Check overlapping path (prefix check)
        if previous_path is not None and tuple_path[:len(previous_path)] == previous_path:
            raise RequestContentValidationError("Overlapping reference path")
        previous_path = tuple_path

        seen_paths.add(tuple_path)

        if ref_sha not in content_by_sha256:
            raise RequestContentValidationError(f"Reference sha256 {ref_sha} missing in content_by_sha256")
        used_hashes.add(ref_sha)

    # Pass 2: Traverse and replace NULL placeholders
    for ref in string_references:
        ref_path = ref["path"]
        ref_sha = ref["sha256"]
        curr = decoded
        for idx, segment in enumerate(ref_path[:-1]):
            if type(curr) is dict:
                if type(segment) is not str or segment not in curr:
                    raise RequestContentValidationError(f"Path segment {segment} not found in dict")
                curr = curr[segment]
            elif type(curr) is list:
                if type(segment) is not int or segment >= len(curr):
                    raise RequestContentValidationError(f"Path index {segment} out of bounds")
                curr = curr[segment]
            else:
                raise RequestContentValidationError(f"Cannot traverse non-container at segment {segment}")

        last_seg = ref_path[-1]
        if type(curr) is dict:
            if type(last_seg) is not str or last_seg not in curr:
                raise RequestContentValidationError(f"Final path segment {last_seg} not found in dict")
            placeholder = curr[last_seg]
            if placeholder is not None:
                raise RequestContentValidationError(f"Placeholder at path {ref_path} must be None/null, got {type(placeholder).__name__}")
            curr[last_seg] = content_by_sha256[ref_sha]
        elif type(curr) is list:
            if type(last_seg) is not int or last_seg >= len(curr):
                raise RequestContentValidationError(f"Final path index {last_seg} out of bounds")
            placeholder = curr[last_seg]
            if placeholder is not None:
                raise RequestContentValidationError(f"Placeholder at path {ref_path} must be None/null, got {type(placeholder).__name__}")
            curr[last_seg] = content_by_sha256[ref_sha]
        else:
            raise RequestContentValidationError(f"Final target container at {ref_path[:-1]} is not dict or list")

    # Reject unused content in content_by_sha256
    unused = set(content_by_sha256.keys()) - used_hashes
    if unused:
        raise RequestContentValidationError(f"Unused content entries in content_by_sha256: {unused}")

    # Enforce decoder limits on the restored object
    node_count = [0]
    byte_count = [0]
    seen_ids: Set[int] = set()
    _check_and_count_nodes(
        decoded,
        current_depth=1,
        max_depth=max_depth,
        max_nodes=max_nodes,
        node_count=node_count,
        byte_count=byte_count,
        max_bytes=max_bytes,
        seen_ids=seen_ids,
    )

    # Verify canonical root digest
    decoded_canon = canonical_json(decoded)
    if len(decoded_canon) > max_bytes:
        raise RequestContentLimitError(f"Canonical decoded size {len(decoded_canon)} exceeds max_bytes {max_bytes}")

    actual_root_sha = sha256_hex(decoded_canon)
    if actual_root_sha != value_sha256:
        raise RequestContentValidationError(
            f"Root digest mismatch: expected {value_sha256}, got {actual_root_sha}"
        )

    return decoded
