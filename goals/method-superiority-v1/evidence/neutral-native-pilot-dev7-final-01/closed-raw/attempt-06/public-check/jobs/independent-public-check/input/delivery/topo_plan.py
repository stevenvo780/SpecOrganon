#!/usr/bin/env python3
"""Strict NDJSON DAG planner using only the Python standard library."""

import heapq
import json
import math
import re
import sys

MAX_INPUT_BYTES = 131072
MAX_NODES = 120
MAX_EDGES = 2000
NAME_PATTERN = re.compile(r'[a-z][a-z0-9_]{0,15}', re.ASCII)
ERROR_MESSAGE = b'topo-plan: invalid input\n'


class InvalidInput(ValueError):
    """The input batch violates the public contract."""


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidInput('duplicate JSON key')
        result[key] = value
    return result


def _reject_constant(value):
    raise InvalidInput('non-finite JSON constant')


def _finite_float(value):
    result = float(value)
    if not math.isfinite(result):
        raise InvalidInput('non-finite JSON number')
    return result


def _parse_line(line):
    try:
        return json.loads(
            line,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
        )
    except (ValueError, RecursionError) as exc:
        # Includes JSON syntax, duplicate keys, numeric conversion limits,
        # non-finite values and excessive parser nesting.
        raise InvalidInput('invalid JSON') from exc


def _build_graph(request):
    if not isinstance(request, dict) or set(request) != {'nodes', 'edges'}:
        raise InvalidInput('expected exactly nodes and edges')

    nodes = request['nodes']
    edges = request['edges']
    if not isinstance(nodes, list) or len(nodes) > MAX_NODES:
        raise InvalidInput('invalid nodes list')
    if not isinstance(edges, list) or len(edges) > MAX_EDGES:
        raise InvalidInput('invalid edges list')

    known = set()
    for node in nodes:
        if not isinstance(node, str) or NAME_PATTERN.fullmatch(node) is None:
            raise InvalidInput('invalid node name')
        if node in known:
            raise InvalidInput('duplicate node')
        known.add(node)

    adjacency = {node: set() for node in nodes}
    indegrees = {node: 0 for node in nodes}
    for edge in edges:
        if not isinstance(edge, list) or len(edge) != 2:
            raise InvalidInput('invalid edge pair')
        source, target = edge
        if not isinstance(source, str) or not isinstance(target, str):
            raise InvalidInput('invalid endpoint type')
        if source not in known or target not in known or source == target:
            raise InvalidInput('unknown endpoint or self-loop')
        if target not in adjacency[source]:
            adjacency[source].add(target)
            indegrees[target] += 1

    # Freeze successor collections; both traversals copy the base degrees.
    return {node: frozenset(targets) for node, targets in adjacency.items()}, indegrees


def _topological_order(adjacency, base_indegrees):
    indegrees = base_indegrees.copy()
    available = [node for node, degree in indegrees.items() if degree == 0]
    heapq.heapify(available)
    order = []
    while available:
        node = heapq.heappop(available)
        order.append(node)
        for target in adjacency[node]:
            indegrees[target] -= 1
            if indegrees[target] == 0:
                heapq.heappush(available, target)
    if len(order) != len(base_indegrees):
        raise InvalidInput('cycle')
    return order


def _topological_layers(adjacency, base_indegrees):
    indegrees = base_indegrees.copy()
    frontier = sorted(node for node, degree in indegrees.items() if degree == 0)
    layers = []
    processed = 0
    while frontier:
        layers.append(frontier)
        processed += len(frontier)
        following = []
        for node in frontier:
            for target in adjacency[node]:
                indegrees[target] -= 1
                if indegrees[target] == 0:
                    following.append(target)
        frontier = sorted(following)
    if processed != len(base_indegrees):
        raise InvalidInput('cycle')
    return layers


def plan_request(request):
    """Validate a decoded request and return order, layers and roots.

    Raises InvalidInput on invalid structure or a cyclic graph.
    Does not mutate the supplied request.
    """
    adjacency, base_indegrees = _build_graph(request)
    order = _topological_order(adjacency, base_indegrees)
    layers = _topological_layers(adjacency, base_indegrees)
    return {'order': order, 'layers': layers, 'roots': layers[0][:] if layers else []}


def process_batch(data):
    """Convert input bytes to output bytes, with no stream side effects.

    Raises InvalidInput for any invalid request in the entire batch.
    """
    if len(data) > MAX_INPUT_BYTES:
        raise InvalidInput('input byte limit')
    if not data:
        return b''
    try:
        text = data.decode('utf-8', errors='strict')
    except UnicodeDecodeError as exc:
        raise InvalidInput('invalid UTF-8') from exc

    lines = text.split('\n')
    if lines[-1] == '':
        lines.pop()  # Remove only the terminator following the final request.

    serialized = []
    for line in lines:
        result = plan_request(_parse_line(line))
        serialized.append(json.dumps(result, ensure_ascii=True, allow_nan=False,
                                     separators=(',', ':')) + '\n')
    return ''.join(serialized).encode('ascii')


def _read_bounded(stream):
    # Handle short reads while never consuming more than limit + 1 bytes.
    chunks = []
    remaining = MAX_INPUT_BYTES + 1
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b''.join(chunks)


def main():
    try:
        output = process_batch(_read_bounded(sys.stdin.buffer))
    except InvalidInput:
        sys.stderr.buffer.write(ERROR_MESSAGE)
        sys.stderr.buffer.flush()
        return 2
    if output:
        sys.stdout.buffer.write(output)
        sys.stdout.buffer.flush()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
