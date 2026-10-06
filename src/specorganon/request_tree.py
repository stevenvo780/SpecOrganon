"""Bounded pure lossless JSON Directed Acyclic Graph (DAG) deduplication codec.

Provides:
    - encode_tree(value) -> envelope
    - decode_tree(envelope, *, max_bytes=2097152, max_nodes=100000, max_depth=128) -> original
    - compact_tree(value) -> (representation, compressed_bool)

Envelope specification:
    {
        "schema": 1,
        "format": "specorganon-tree-refs-v1",
        "root": <node_index>,
        "nodes": [
            <post-order node>,
            ...
        ],
        "value_sha256": "<canonical sha256 of original value>"
    }

Node table specification (post-order, refs strictly backward integers 0 <= ref < own_index):
    - ['null']
    - ['bool', bool]
    - ['int', int]
    - ['float', float_finite]
    - ['str', str]
    - ['array', [child_id, ...]]
    - ['object', [[key_str_node_id, val_node_id], ...]]  (insertion order preserved)
"""

import copy
import json
import math
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from specorganon.request_content import (
    DEFAULT_MAX_BYTES,
    DEFAULT_MAX_DEPTH,
    DEFAULT_MAX_NODES,
    RequestContentError,
    RequestContentLimitError,
    RequestContentValidationError,
    _bounded_json_string_size,
    _check_and_count_nodes,
    _validate_json_types,
    canonical_json,
    sha256_hex,
)


class RequestTreeError(RequestContentError):
    """Base error for request tree codec errors."""
    pass


class RequestTreeValidationError(RequestTreeError, RequestContentValidationError):
    """Raised when JSON validation or tree envelope structure validation fails."""
    pass


class RequestTreeLimitError(RequestTreeError, RequestContentLimitError):
    """Raised when tree decoder limits (bytes, nodes, depth) are exceeded."""
    pass


FORMAT_IDENTIFIER = "specorganon-tree-refs-v1"
SCHEMA_VERSION = 1


def _validate_tree_input(value: Any) -> None:
    """Validate that input adheres to finite JSON types, no cycles, within default bounds."""
    try:
        _validate_json_types(value)
    except RequestContentLimitError as exc:
        raise RequestTreeLimitError(str(exc)) from exc
    except RequestContentValidationError as exc:
        raise RequestTreeValidationError(str(exc)) from exc
    except UnicodeError as exc:
        raise RequestTreeValidationError(f"Invalid Unicode in input: {exc}") from exc


def encode_tree(value: Any) -> Dict[str, Any]:
    """Encode value into a deduplicated JSON DAG envelope with readable node table.

    Does not mutate input value. Preserves finite JSON types, dict insertion order,
    negative zero, and full structure losslessly.
    """
    _validate_tree_input(value)
    canon_bytes = canonical_json(value)
    root_hash = sha256_hex(canon_bytes)

    nodes: List[List[Any]] = []
    memo: Dict[bytes, int] = {}

    def _encode_node(val: Any) -> int:
        if val is None:
            node = ["null"]
        elif type(val) is bool:
            node = ["bool", val]
        elif type(val) is int:
            node = ["int", val]
        elif type(val) is float:
            node = ["float", val]
        elif type(val) is str:
            node = ["str", val]
        elif type(val) is list:
            cids = [_encode_node(elem) for elem in val]
            node = ["array", cids]
        elif type(val) is dict:
            pairs = []
            for k, v in val.items():
                kid = _encode_node(k)
                vid = _encode_node(v)
                pairs.append([kid, vid])
            node = ["object", pairs]
        else:
            raise RequestTreeValidationError(f"Unsupported JSON type: {type(val).__name__}")

        key = canonical_json(node)
        if key in memo:
            return memo[key]
        nid = len(nodes)
        nodes.append(node)
        memo[key] = nid
        return nid

    root_id = _encode_node(value)

    return {
        "schema": SCHEMA_VERSION,
        "format": FORMAT_IDENTIFIER,
        "root": root_id,
        "nodes": nodes,
        "value_sha256": root_hash,
    }


def compact_tree(value: Any) -> Tuple[Union[Dict[str, Any], Any], bool]:
    """Helper that encodes value if the canonical envelope size is strictly smaller than original.

    Returns (envelope, True) if compressed and smaller, else (copy.deepcopy(value), False).
    Always validates input bounds upfront without silent fallback bypass.
    """
    _validate_tree_input(value)
    orig_canon = canonical_json(value)
    envelope = encode_tree(value)
    # The encoded table may be larger than a valid original. Bound its own
    # metadata before dumping, then allow compact_tree to choose plain JSON.
    _check_and_count_nodes(envelope, 1, 16, 10 * DEFAULT_MAX_NODES + 32,
                           [0], [0], 4 * DEFAULT_MAX_BYTES + 512, set())
    env_canon = json.dumps(envelope, sort_keys=True, separators=(',', ':'),
                           ensure_ascii=False, allow_nan=False).encode('utf-8')

    if len(env_canon) < len(orig_canon):
        return envelope, True
    else:
        return copy.deepcopy(value), False


def _build_tree_node(node_id: int, nodes: List[List[Any]]) -> Any:
    """Instantiate fresh mutable containers per occurrence to guarantee no aliases."""
    node = nodes[node_id]
    tag = node[0]
    if tag == "null":
        return None
    elif tag == "bool":
        return node[1]
    elif tag == "int":
        return node[1]
    elif tag == "float":
        return node[1]
    elif tag == "str":
        return node[1]
    elif tag == "array":
        return [_build_tree_node(cid, nodes) for cid in node[1]]
    elif tag == "object":
        return {nodes[kid][1]: _build_tree_node(vid, nodes) for kid, vid in node[1]}
    else:
        raise RequestTreeValidationError(f"Invalid node tag: {tag}")


def decode_tree(
    envelope: Any,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_nodes: int = DEFAULT_MAX_NODES,
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> Any:
    """Decode a DAG envelope back into the exact original value.

    Validates envelope shape, backward-only refs, string key references,
    duplicate keys, full reachability (no unused nodes), and computes saturated
    expanded limits bottom-up before any container allocation.
    """
    for name, limit in (("max_bytes", max_bytes), ("max_nodes", max_nodes), ("max_depth", max_depth)):
        if type(limit) is not int or limit < 1:
            raise RequestTreeValidationError(f"{name} must be a positive integer")

    if type(envelope) is not dict:
        raise RequestTreeValidationError("Envelope must be a dict")

    required_keys = {"schema", "format", "root", "nodes", "value_sha256"}
    if set(envelope.keys()) != required_keys:
        raise RequestTreeValidationError(
            f"Envelope keys mismatch: expected {sorted(required_keys)}, got {sorted(envelope.keys())}"
        )

    if type(envelope["schema"]) is not int or envelope["schema"] != SCHEMA_VERSION:
        raise RequestTreeValidationError(f"Unsupported schema version: {envelope['schema']}")

    if type(envelope["format"]) is not str or envelope["format"] != FORMAT_IDENTIFIER:
        raise RequestTreeValidationError(f"Unsupported format: {envelope['format']}")

    value_sha256 = envelope["value_sha256"]
    if type(value_sha256) is not str or len(value_sha256) != 64 or not all(c in "0123456789abcdef" for c in value_sha256):
        raise RequestTreeValidationError("value_sha256 must be a 64-char lowercase hex string")

    nodes = envelope["nodes"]
    if type(nodes) is not list:
        raise RequestTreeValidationError("Envelope nodes must be a list")

    if len(nodes) == 0:
        raise RequestTreeValidationError("Nodes table cannot be empty")

    root = envelope["root"]
    if type(root) is not int:
        raise RequestTreeValidationError("Envelope root must be an integer")

    if root != len(nodes) - 1:
        raise RequestTreeValidationError(f"Root index must be {len(nodes) - 1}, got {root}")

    if len(nodes) > 2 * max_nodes + 1:
        raise RequestTreeLimitError(
            f"Nodes table length {len(nodes)} exceeds maximum allowed {2 * max_nodes + 1}"
        )

    # Bound envelope overhead before deep structural processing
    env_max_bytes = max(512, 4 * max_bytes + 8)
    env_max_nodes = 10 * max_nodes + 32
    env_max_depth = 16
    try:
        _check_and_count_nodes(
            envelope, 1, env_max_depth, env_max_nodes, [0], [0], env_max_bytes, set()
        )
    except RequestContentLimitError as exc:
        raise RequestTreeLimitError(str(exc)) from exc
    except RequestContentValidationError as exc:
        raise RequestTreeValidationError(str(exc)) from exc
    except UnicodeError as exc:
        raise RequestTreeValidationError(f"Invalid Unicode in envelope: {exc}") from exc

    n_count = len(nodes)

    # Validate node shapes and strictly backward references
    for i in range(n_count):
        node = nodes[i]
        if type(node) is not list:
            raise RequestTreeValidationError(f"Node {i} must be a list")
        if len(node) == 0:
            raise RequestTreeValidationError(f"Node {i} must not be empty")
        tag = node[0]
        if type(tag) is not str:
            raise RequestTreeValidationError(f"Node {i} tag must be a str")

        if tag == "null":
            if len(node) != 1:
                raise RequestTreeValidationError(f"null node {i} must have shape ['null']")
        elif tag == "bool":
            if len(node) != 2 or type(node[1]) is not bool:
                raise RequestTreeValidationError(f"bool node {i} must have shape ['bool', bool]")
        elif tag == "int":
            if len(node) != 2 or type(node[1]) is not int:
                raise RequestTreeValidationError(f"int node {i} must have shape ['int', int]")
        elif tag == "float":
            if len(node) != 2 or type(node[1]) is not float or not math.isfinite(node[1]):
                raise RequestTreeValidationError(f"float node {i} must have shape ['float', float_finite]")
        elif tag == "str":
            if len(node) != 2 or type(node[1]) is not str:
                raise RequestTreeValidationError(f"str node {i} must have shape ['str', str]")
            try:
                _bounded_json_string_size(node[1], max_bytes)
            except RequestContentLimitError as exc:
                raise RequestTreeLimitError(str(exc)) from exc
            except UnicodeError as exc:
                raise RequestTreeValidationError(f"str node {i} contains invalid Unicode: {exc}") from exc
        elif tag == "array":
            if len(node) != 2 or type(node[1]) is not list:
                raise RequestTreeValidationError(f"array node {i} must have shape ['array', [childids]]")
            for cid in node[1]:
                if type(cid) is not int or cid < 0 or cid >= i:
                    raise RequestTreeValidationError(
                        f"array node {i} child reference must be int with 0 <= ref < {i}, got {cid}"
                    )
        elif tag == "object":
            if len(node) != 2 or type(node[1]) is not list:
                raise RequestTreeValidationError(
                    f"object node {i} must have shape ['object', [[k_ref, v_ref], ...]]"
                )
            seen_keys: Set[str] = set()
            for pair in node[1]:
                if type(pair) is not list or len(pair) != 2:
                    raise RequestTreeValidationError(
                        f"object node {i} entry must be [k_ref, v_ref]"
                    )
                kid, vid = pair
                if type(kid) is not int or kid < 0 or kid >= i:
                    raise RequestTreeValidationError(
                        f"object node {i} key reference must be int with 0 <= ref < {i}, got {kid}"
                    )
                if type(vid) is not int or vid < 0 or vid >= i:
                    raise RequestTreeValidationError(
                        f"object node {i} value reference must be int with 0 <= ref < {i}, got {vid}"
                    )
                if nodes[kid][0] != "str":
                    raise RequestTreeValidationError(
                        f"object node {i} key ref {kid} must reference a str node, got {nodes[kid][0]}"
                    )
                key_str = nodes[kid][1]
                if key_str in seen_keys:
                    raise RequestTreeValidationError(f"Duplicate key in object: {key_str}")
                seen_keys.add(key_str)
        else:
            raise RequestTreeValidationError(f"Invalid node tag: {tag}")

    # Reachability check: all nodes must be reachable from root
    reachable = [False] * n_count
    reachable[root] = True
    stack = [root]
    count_reachable = 1
    while stack:
        curr = stack.pop()
        node = nodes[curr]
        tag = node[0]
        if tag == "array":
            for cid in node[1]:
                if not reachable[cid]:
                    reachable[cid] = True
                    count_reachable += 1
                    stack.append(cid)
        elif tag == "object":
            for kid, vid in node[1]:
                if not reachable[kid]:
                    reachable[kid] = True
                    count_reachable += 1
                    stack.append(kid)
                if not reachable[vid]:
                    reachable[vid] = True
                    count_reachable += 1
                    stack.append(vid)

    if count_reachable < n_count:
        raise RequestTreeValidationError(
            f"Unused nodes detected: {n_count - count_reachable} unreferenced nodes"
        )

    # Bottom-up saturated computation of expanded height, value nodes, and canonical bytes.
    # Enforces limits BEFORE building any container.
    height = [0] * n_count
    value_nodes = [0] * n_count
    expanded_bytes = [0] * n_count

    for i in range(n_count):
        node = nodes[i]
        tag = node[0]
        if tag == "null":
            height[i] = 1
            value_nodes[i] = 1
            expanded_bytes[i] = 4
        elif tag == "bool":
            height[i] = 1
            value_nodes[i] = 1
            expanded_bytes[i] = 4 if node[1] else 5
        elif tag == "int":
            height[i] = 1
            value_nodes[i] = 1
            expanded_bytes[i] = len(str(node[1]))
        elif tag == "float":
            height[i] = 1
            value_nodes[i] = 1
            expanded_bytes[i] = len(canonical_json(node[1]))
        elif tag == "str":
            height[i] = 1
            value_nodes[i] = 1
            try:
                expanded_bytes[i] = _bounded_json_string_size(node[1], max_bytes)
            except RequestContentLimitError as exc:
                raise RequestTreeLimitError(str(exc)) from exc
        elif tag == "array":
            cids = node[1]
            h = 1
            vn = 1
            eb = 2 + max(0, len(cids) - 1)
            if eb > max_bytes:
                raise RequestTreeLimitError(f"Maximum expanded bytes estimate exceeded: {eb} > {max_bytes}")
            for cid in cids:
                if height[cid] + 1 > h:
                    h = height[cid] + 1
                vn += value_nodes[cid]
                if vn > max_nodes:
                    raise RequestTreeLimitError(f"Maximum nodes exceeded: {vn} > {max_nodes}")
                eb += expanded_bytes[cid]
                if eb > max_bytes:
                    raise RequestTreeLimitError(f"Maximum expanded bytes estimate exceeded: {eb} > {max_bytes}")
            height[i] = h
            value_nodes[i] = vn
            expanded_bytes[i] = eb
        elif tag == "object":
            pairs = node[1]
            h = 1
            vn = 1
            eb = 2 + len(pairs) + max(0, len(pairs) - 1)
            if eb > max_bytes:
                raise RequestTreeLimitError(f"Maximum expanded bytes estimate exceeded: {eb} > {max_bytes}")
            for kid, vid in pairs:
                if height[vid] + 1 > h:
                    h = height[vid] + 1
                vn += value_nodes[vid]
                if vn > max_nodes:
                    raise RequestTreeLimitError(f"Maximum nodes exceeded: {vn} > {max_nodes}")
                eb += expanded_bytes[kid] + expanded_bytes[vid]
                if eb > max_bytes:
                    raise RequestTreeLimitError(f"Maximum expanded bytes estimate exceeded: {eb} > {max_bytes}")
            height[i] = h
            value_nodes[i] = vn
            expanded_bytes[i] = eb

        if height[i] > max_depth:
            raise RequestTreeLimitError(f"Maximum depth exceeded: {height[i]} > {max_depth}")
        if value_nodes[i] > max_nodes:
            raise RequestTreeLimitError(f"Maximum nodes exceeded: {value_nodes[i]} > {max_nodes}")
        if expanded_bytes[i] > max_bytes:
            raise RequestTreeLimitError(f"Maximum expanded bytes estimate exceeded: {expanded_bytes[i]} > {max_bytes}")

    # Build fresh mutable containers per occurrence
    decoded = _build_tree_node(root, nodes)

    decoded_canon = canonical_json(decoded)
    if len(decoded_canon) > max_bytes:
        raise RequestTreeLimitError(f"Canonical decoded size {len(decoded_canon)} exceeds max_bytes {max_bytes}")

    actual_root_sha = sha256_hex(decoded_canon)
    if actual_root_sha != value_sha256:
        raise RequestTreeValidationError(
            f"Root digest mismatch: expected {value_sha256}, got {actual_root_sha}"
        )

    return decoded
