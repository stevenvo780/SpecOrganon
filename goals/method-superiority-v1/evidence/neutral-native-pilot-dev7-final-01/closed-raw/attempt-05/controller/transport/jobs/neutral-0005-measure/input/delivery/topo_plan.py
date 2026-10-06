#!/usr/bin/env python3
"""Validate an entire NDJSON batch, then emit deterministic DAG plans."""
import heapq
import json
import re
import sys

MAX_BYTES = 131072
NAME = re.compile(r"[a-z][a-z0-9_]{0,15}", re.ASCII)


def reject_constant(value):
    raise ValueError("nonfinite constant")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def plan(request):
    if not isinstance(request, dict) or set(request) != {"nodes", "edges"}:
        raise ValueError("invalid fields")
    nodes, edges = request["nodes"], request["edges"]
    if not isinstance(nodes, list) or len(nodes) > 120:
        raise ValueError("invalid nodes")
    if not isinstance(edges, list) or len(edges) > 2000:
        raise ValueError("invalid edges")
    known = set()
    for node in nodes:
        if not isinstance(node, str) or NAME.fullmatch(node) is None:
            raise ValueError("invalid name")
        if node in known:
            raise ValueError("duplicate node")
        known.add(node)
    successors = {node: set() for node in nodes}
    indegree = {node: 0 for node in nodes}
    for edge in edges:
        if not isinstance(edge, list) or len(edge) != 2:
            raise ValueError("invalid edge")
        source, target = edge
        if not isinstance(source, str) or not isinstance(target, str):
            raise ValueError("invalid endpoint type")
        if source not in known or target not in known or source == target:
            raise ValueError("invalid endpoint")
        if target not in successors[source]:
            successors[source].add(target)
            indegree[target] += 1

    # Every newly available node joins the same global priority queue.
    order_degree = indegree.copy()
    available = [node for node in nodes if order_degree[node] == 0]
    heapq.heapify(available)
    order = []
    while available:
        node = heapq.heappop(available)
        order.append(node)
        for target in successors[node]:
            order_degree[target] -= 1
            if order_degree[target] == 0:
                heapq.heappush(available, target)
    if len(order) != len(nodes):
        raise ValueError("cycle")

    # Start again from the original degrees; finish each whole round.
    layer_degree = indegree.copy()
    current = sorted(node for node in nodes if layer_degree[node] == 0)
    layers = []
    while current:
        layers.append(current)
        following = []
        for node in current:
            for target in successors[node]:
                layer_degree[target] -= 1
                if layer_degree[target] == 0:
                    following.append(target)
        current = sorted(following)
    return {"order": order, "layers": layers,
            "roots": layers[0][:] if layers else []}


def process(data):
    if len(data) > MAX_BYTES:
        raise ValueError("batch too large")
    text = data.decode("utf-8", errors="strict")
    if not text:
        return ""
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    results = []
    for line in lines:
        request = json.loads(line, object_pairs_hook=unique_object,
                             parse_constant=reject_constant)
        results.append(plan(request))
    return "".join(json.dumps(result, separators=(",", ":")) + "\n"
                   for result in results)


def main():
    try:
        data = sys.stdin.buffer.read(MAX_BYTES + 1)
        output = process(data)
    except (ValueError, UnicodeError, RecursionError):
        sys.stderr.write("topo-plan: invalid input\n")
        return 2
    sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
