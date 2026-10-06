"""Planificador DAG: NDJSON por stdin y validación atómica del lote."""
import heapq
import json
import re
import sys

LIMIT = 131072
NAME = re.compile(r'[a-z][a-z0-9_]{0,15}', re.ASCII)


def invalid():
    raise ValueError('invalid input')


def object_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            invalid()
        result[key] = value
    return result


def reject_constant(value):
    invalid()


def plan(request):
    if type(request) is not dict or set(request) != {'nodes', 'edges'}:
        invalid()
    nodes, edges = request['nodes'], request['edges']
    if type(nodes) is not list or len(nodes) > 120:
        invalid()
    if any(type(n) is not str or NAME.fullmatch(n) is None for n in nodes):
        invalid()
    if len(set(nodes)) != len(nodes):
        invalid()
    if type(edges) is not list or len(edges) > 2000:
        invalid()
    adjacency = {n: set() for n in nodes}
    degree = {n: 0 for n in nodes}
    for edge in edges:
        if type(edge) is not list or len(edge) != 2:
            invalid()
        source, target = edge
        if type(source) is not str or type(target) is not str:
            invalid()
        if source not in adjacency or target not in adjacency or source == target:
            invalid()
        if target not in adjacency[source]:
            adjacency[source].add(target)
            degree[target] += 1

    order_degree = degree.copy()
    available = [n for n in nodes if order_degree[n] == 0]
    heapq.heapify(available)
    order = []
    while available:
        node = heapq.heappop(available)
        order.append(node)
        for target in adjacency[node]:
            order_degree[target] -= 1
            if order_degree[target] == 0:
                heapq.heappush(available, target)
    if len(order) != len(nodes):
        invalid()

    layer_degree = degree.copy()
    current = sorted(n for n in nodes if layer_degree[n] == 0)
    layers = []
    while current:
        layers.append(current)
        following = []
        for node in current:
            for target in adjacency[node]:
                layer_degree[target] -= 1
                if layer_degree[target] == 0:
                    following.append(target)
        current = sorted(following)
    return {'order': order, 'layers': layers, 'roots': layers[0] if layers else []}


def batch(raw):
    if len(raw) > LIMIT:
        invalid()
    if not raw:
        return ''
    lines = raw.decode('utf-8').split('\n')
    if lines[-1] == '':
        lines.pop()
    responses = []
    for line in lines:
        if not line.strip():
            invalid()
        request = json.loads(line, object_pairs_hook=object_pairs,
                             parse_constant=reject_constant)
        responses.append(json.dumps(plan(request), separators=(',', ':')))
    return ''.join(response + '\n' for response in responses)


def main():
    try:
        output = batch(sys.stdin.buffer.read(LIMIT + 1))
    except (ValueError, TypeError, RecursionError):
        sys.stderr.write('topo-plan: invalid input\n')
        return 2
    sys.stdout.write(output)
    return 0


if __name__ == '__main__':
    sys.exit(main())
