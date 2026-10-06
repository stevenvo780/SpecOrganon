#!/usr/bin/env python3
"""Plan an entire NDJSON batch before emitting any output."""
import heapq
import json
import re
import sys

MAX_BYTES = 131072
NAME = re.compile(r'[a-z][a-z0-9_]{0,15}', re.ASCII)


class InvalidInput(ValueError):
    pass


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidInput('duplicate key')
        result[key] = value
    return result


def reject_constant(value):
    raise InvalidInput('nonfinite constant')


def plan(request):
    if type(request) is not dict or set(request) != {'nodes', 'edges'}:
        raise InvalidInput('fields')
    nodes, edges = request['nodes'], request['edges']
    if type(nodes) is not list or len(nodes) > 120:
        raise InvalidInput('nodes')
    if type(edges) is not list or len(edges) > 2000:
        raise InvalidInput('edges')
    known = set()
    for node in nodes:
        if type(node) is not str or NAME.fullmatch(node) is None:
            raise InvalidInput('name')
        if node in known:
            raise InvalidInput('duplicate node')
        known.add(node)
    adjacency = {node: set() for node in nodes}
    indegree = {node: 0 for node in nodes}
    for edge in edges:
        if type(edge) is not list or len(edge) != 2:
            raise InvalidInput('pair')
        source, target = edge
        if type(source) is not str or type(target) is not str:
            raise InvalidInput('endpoint type')
        if source not in known or target not in known or source == target:
            raise InvalidInput('endpoint')
        if target not in adjacency[source]:
            adjacency[source].add(target)
            indegree[target] += 1

    # The heap always contains every currently available node.
    order_degrees = indegree.copy()
    available = [node for node in nodes if order_degrees[node] == 0]
    heapq.heapify(available)
    order = []
    while available:
        node = heapq.heappop(available)
        order.append(node)
        for target in adjacency[node]:
            order_degrees[target] -= 1
            if order_degrees[target] == 0:
                heapq.heappush(available, target)
    if len(order) != len(nodes):
        raise InvalidInput('cycle')

    # Start again from the original indegrees; remove whole rounds.
    layer_degrees = indegree.copy()
    current = sorted(node for node in nodes if layer_degrees[node] == 0)
    layers = []
    while current:
        layers.append(current)
        following = []
        for node in current:
            for target in adjacency[node]:
                layer_degrees[target] -= 1
                if layer_degrees[target] == 0:
                    following.append(target)
        current = sorted(following)
    return {'order': order, 'layers': layers,
            'roots': layers[0].copy() if layers else []}


def process_batch(raw):
    if len(raw) > MAX_BYTES:
        raise InvalidInput('byte limit')
    text = raw.decode('utf-8', errors='strict')
    if not text:
        return ''
    lines = text.split('\n')
    if lines[-1] == '':
        lines.pop()
    results = []
    for line in lines:
        if not line.strip():
            raise InvalidInput('blank line')
        request = json.loads(line, object_pairs_hook=unique_object,
                             parse_constant=reject_constant)
        results.append(plan(request))
    return ''.join(json.dumps(result, ensure_ascii=True,
                              separators=(',', ':')) + '\n'
                   for result in results)


def main():
    try:
        raw = sys.stdin.buffer.read(MAX_BYTES + 1)
        output = process_batch(raw)
    except (ValueError, UnicodeError, RecursionError):
        sys.stderr.write('topo-plan: invalid input\n')
        return 2
    sys.stdout.write(output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
