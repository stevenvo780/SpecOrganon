#!/usr/bin/env python3
"""Plan directed acyclic graphs from a bounded UTF-8 NDJSON batch."""
import heapq
import json
import math
import re
import sys

MAX_BYTES = 131072
NAME = re.compile(r'[a-z][a-z0-9_]{0,15}', re.ASCII)


def invalid():
    raise ValueError('invalid input')


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            invalid()
        result[key] = value
    return result


def finite_float(token):
    value = float(token)
    if not math.isfinite(value):
        invalid()
    return value


def reject_constant(token):
    invalid()


def graph(request):
    if not isinstance(request, dict) or set(request) != {'nodes', 'edges'}:
        invalid()
    nodes, edges = request['nodes'], request['edges']
    if not isinstance(nodes, list) or len(nodes) > 120:
        invalid()
    if not isinstance(edges, list) or len(edges) > 2000:
        invalid()
    names = set()
    for node in nodes:
        if not isinstance(node, str) or NAME.fullmatch(node) is None:
            invalid()
        if node in names:
            invalid()
        names.add(node)
    successors = {node: set() for node in names}
    indegrees = {node: 0 for node in names}
    for edge in edges:
        if not isinstance(edge, list) or len(edge) != 2:
            invalid()
        source, target = edge
        if not isinstance(source, str) or not isinstance(target, str):
            invalid()
        if source not in names or target not in names or source == target:
            invalid()
        if target not in successors[source]:
            successors[source].add(target)
            indegrees[target] += 1
    return successors, indegrees


def plan(request):
    successors, original_degrees = graph(request)
    degrees = original_degrees.copy()
    available = [node for node in degrees if degrees[node] == 0]
    heapq.heapify(available)
    order = []
    while available:
        node = heapq.heappop(available)
        order.append(node)
        for target in successors[node]:
            degrees[target] -= 1
            if degrees[target] == 0:
                heapq.heappush(available, target)
    if len(order) != len(original_degrees):
        invalid()

    degrees = original_degrees.copy()
    current = sorted(node for node in degrees if degrees[node] == 0)
    layers = []
    while current:
        layers.append(current)
        following = []
        for node in current:
            for target in successors[node]:
                degrees[target] -= 1
                if degrees[target] == 0:
                    following.append(target)
        current = sorted(following)
    return {'order': order, 'layers': layers,
            'roots': layers[0] if layers else []}


def process(raw):
    if len(raw) > MAX_BYTES:
        invalid()
    text = raw.decode('utf-8', errors='strict')
    if not text:
        return ''
    lines = text.split('\n')
    if lines[-1] == '':
        lines.pop()
    output = []
    for line in lines:
        if not line.strip():
            invalid()
        request = json.loads(line, object_pairs_hook=unique_object,
                             parse_constant=reject_constant,
                             parse_float=finite_float)
        output.append(json.dumps(plan(request), separators=(',', ':')) + '\n')
    return ''.join(output)


def main():
    try:
        raw = sys.stdin.buffer.read(MAX_BYTES + 1)
        output = process(raw)
    except (ValueError, UnicodeError, RecursionError):
        sys.stderr.write('topo-plan: invalid input\n')
        return 2
    sys.stdout.write(output)
    return 0


if __name__ == '__main__':
    sys.exit(main())
