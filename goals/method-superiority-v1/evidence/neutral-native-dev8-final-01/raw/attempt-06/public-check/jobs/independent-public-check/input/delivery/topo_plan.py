#!/usr/bin/env python3
"""Plan DAG requests from bounded UTF-8 NDJSON input."""

import heapq
import json
import re
import sys


MAX_BYTES = 131072
MAX_NODES = 120
MAX_EDGES = 2000
NAME_PATTERN = re.compile(r'[a-z][a-z0-9_]{0,15}', re.ASCII)
ERROR = b'topo-plan: invalid input\n'


class InvalidInput(Exception):
    """The input violates the request contract."""


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidInput()
        result[key] = value
    return result


def reject_constant(value):
    raise InvalidInput()


def decode_request(line):
    try:
        return json.loads(
            line,
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except (ValueError, RecursionError) as exc:
        # Includes JSON syntax and interpreter numeric/depth limits.
        raise InvalidInput() from exc


def normalize_graph(request):
    if not isinstance(request, dict) or set(request) != {'nodes', 'edges'}:
        raise InvalidInput()
    nodes = request['nodes']
    edges = request['edges']
    if not isinstance(nodes, list) or len(nodes) > MAX_NODES:
        raise InvalidInput()
    if not isinstance(edges, list) or len(edges) > MAX_EDGES:
        raise InvalidInput()

    adjacency = {}
    indegree = {}
    for node in nodes:
        if not isinstance(node, str) or NAME_PATTERN.fullmatch(node) is None:
            raise InvalidInput()
        if node in adjacency:
            raise InvalidInput()
        adjacency[node] = set()
        indegree[node] = 0

    for edge in edges:
        if not isinstance(edge, list) or len(edge) != 2:
            raise InvalidInput()
        source, target = edge
        if not isinstance(source, str) or not isinstance(target, str):
            raise InvalidInput()
        if source not in adjacency or target not in adjacency:
            raise InvalidInput()
        if source == target:
            raise InvalidInput()
        if target not in adjacency[source]:
            adjacency[source].add(target)
            indegree[target] += 1
    return adjacency, indegree


def topological_order(adjacency, indegree):
    remaining = indegree.copy()
    available = [node for node in remaining if remaining[node] == 0]
    heapq.heapify(available)
    order = []
    while available:
        node = heapq.heappop(available)
        order.append(node)
        for target in adjacency[node]:
            remaining[target] -= 1
            if remaining[target] == 0:
                heapq.heappush(available, target)
    if len(order) != len(remaining):
        raise InvalidInput()
    return order


def topological_layers(adjacency, indegree):
    remaining = indegree.copy()
    frontier = sorted(node for node in remaining if remaining[node] == 0)
    layers = []
    processed = 0
    while frontier:
        layers.append(frontier)
        processed += len(frontier)
        next_frontier = []
        for node in frontier:
            for target in adjacency[node]:
                remaining[target] -= 1
                if remaining[target] == 0:
                    next_frontier.append(target)
        frontier = sorted(next_frontier)
    if processed != len(remaining):
        raise InvalidInput()
    return layers


def plan_request(request):
    adjacency, indegree = normalize_graph(request)
    order = topological_order(adjacency, indegree)
    layers = topological_layers(adjacency, indegree)
    roots = layers[0].copy() if layers else []
    return {'order': order, 'layers': layers, 'roots': roots}


def process_batch(data):
    """Return complete response bytes, or raise InvalidInput without output."""
    if len(data) > MAX_BYTES:
        raise InvalidInput()
    try:
        text = data.decode('utf-8', errors='strict')
    except UnicodeDecodeError as exc:
        raise InvalidInput() from exc
    if not text:
        return b''

    lines = text.split('\n')
    if lines[-1] == '':
        # Remove only the segment introduced by a final LF.
        lines.pop()
    responses = []
    for line in lines:
        response = plan_request(decode_request(line))
        responses.append(json.dumps(response, ensure_ascii=True, separators=(',', ':')))
    return ('\n'.join(responses) + '\n').encode('ascii')


def read_bounded(stream):
    """Read at most MAX_BYTES + 1 bytes, tolerating short reads."""
    chunks = []
    remaining = MAX_BYTES + 1
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    data = b''.join(chunks)
    if len(data) > MAX_BYTES:
        raise InvalidInput()
    return data


def main():
    try:
        data = read_bounded(sys.stdin.buffer)
        output = process_batch(data)
    except InvalidInput:
        sys.stderr.buffer.write(ERROR)
        sys.stderr.buffer.flush()
        return 2
    if output:
        sys.stdout.buffer.write(output)
        sys.stdout.buffer.flush()
    return 0


if __name__ == '__main__':
    sys.exit(main())
