"""Reserved behavioral evaluator draft. Never mount this file in native roles.

Expected values and suite definitions stay in the trusted host process. Subject
containers receive only opaque delivery bytes and the current filesystem input.
This is neither a software delivery nor a nine-phase case. Freeze/audit required
before study generation; no candidate generation or provider calls happen here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import stat


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def exact_json(raw):
    """Strict finite JSON, including duplicate-key rejection at every depth."""
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def constant(_):
        raise ValueError("nonfinite JSON")

    def floating(text):
        value = float(text)
        if not math.isfinite(value):
            raise ValueError("nonfinite JSON")
        return value

    return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                      parse_constant=constant, parse_float=floating)


def same_typed(actual, expected):
    # JSON bool is distinct from int, and float is distinct from int. Python's
    # equality alone would wrongly accept true == 1 or 1.0 == 1.
    if type(actual) is not type(expected):
        return False
    if type(expected) is dict:
        return actual.keys() == expected.keys() and all(
            same_typed(actual[k], expected[k]) for k in expected)
    if type(expected) is list:
        return len(actual) == len(expected) and all(
            same_typed(a, b) for a, b in zip(actual, expected))
    return actual == expected


def judge(case, result):
    """Evaluate closed streams only; infrastructure uncertainty is not a score."""
    if result.get("infrastructure_error"):
        return {"status": "inconclusive", "reason": result["infrastructure_error"]}
    if result.get("timed_out") or result.get("truncated_streams"):
        return {"status": "fail", "reason": "invocation limit"}
    success = case["expected"] is not None
    if result["exit_code"] != (0 if success else 2):
        return {"status": "fail", "reason": "exit code"}
    output = result["stdout"] if success else result["stderr"]
    blank = result["stderr"] if success else result["stdout"]
    if blank or not output.endswith(b"\n"):
        return {"status": "fail", "reason": "stream framing"}
    try:
        actual = exact_json(output)
    except (ValueError, UnicodeError, RecursionError):
        return {"status": "fail", "reason": "output JSON"}
    expected = case["expected"] if success else {"error": "invalid_input"}
    return {"status": "pass" if same_typed(actual, expected) else "fail",
            "reason": "typed contract comparison"}


def path_oracle(nodes, edges, source, target):
    """Enumerate simple paths, not Dijkstra; small private graphs only.

    Larger boundary cases are sparse chains/stars with at most a handful of
    simple paths. This trusted oracle never executes generated solution code.
    """
    outgoing = {node: [] for node in nodes}
    for edge in edges:
        outgoing[edge["source"]].append((edge["target"], edge["cost"]))
    best = None
    visits = 0

    def visit(current, path, cost):
        nonlocal best, visits
        visits += 1
        if visits > 100_000:
            raise ValueError("oracle fixture too dense; refuse to freeze")
        if current == target:
            candidate = (cost, path)
            if best is None or candidate < best:
                best = candidate
            return
        for other, weight in outgoing[current]:
            if other not in path:
                visit(other, path + [other], cost + weight)

    visit(source, [source], 0)
    return ({"reachable": False, "cost": None, "path": []} if best is None
            else {"reachable": True, "cost": best[0], "path": best[1]})


def route_suite():
    cases = []

    def valid(label, nodes, edges, source, target, *, group="routing", raw=None):
        value = {"nodes": nodes,
                 "edges": [{"source": a, "target": b, "cost": c} for a, b, c in edges],
                 "query": {"source": source, "target": target}}
        expected = path_oracle(nodes, value["edges"], source, target)
        cases.append({"id": label, "task": "routeplan", "group": group,
                      "argv": [], "stdin_hex": (encoded(value) if raw is None else raw).hex(),
                      "expected": expected})

    valid("self", ["A"], [("A", "A", 1000)], "A", "A")
    valid("unreachable", ["Left", "Right"], [], "Left", "Right")
    valid("directed", ["A", "B"], [("B", "A", 1)], "A", "B")
    valid("cost-before-hops", ["A", "B", "C"],
          [("A", "C", 10), ("A", "B", 1), ("B", "C", 1)], "A", "C")
    valid("full-list-tie", ["S", "a", "b", "c", "z"],
          [("S", "b", 1), ("b", "z", 2), ("S", "a", 1),
           ("a", "c", 1), ("c", "z", 1), ("S", "z", 3)], "S", "z", group="ties")
    valid("deep-tie", ["S", "B", "C", "D", "End"],
          [("S", "B", 1), ("B", "D", 2), ("D", "End", 1),
           ("B", "C", 1), ("C", "End", 2)], "S", "End", group="ties")
    valid("case-sensitive-tie", ["S", "A_0", "a_0", "End"],
          [("S", "a_0", 1), ("a_0", "End", 1),
           ("S", "A_0", 1), ("A_0", "End", 1)], "S", "End", group="ties")
    valid("positive-cycle", ["A", "B", "C"],
          [("A", "B", 1), ("B", "A", 1), ("B", "C", 2), ("C", "C", 1)], "A", "C")
    valid("id-length-cap", ["A" * 16], [], "A" * 16, "A" * 16, group="bounds")
    rng = random.Random(0x51EC2026)
    for index in range(12):
        nodes = ["A", "B", "C", "D", "E", "F"]
        edges = [(a, b, rng.randrange(1, 8)) for a in nodes for b in nodes
                 if a != b and rng.random() < .30]
        rng.shuffle(nodes); rng.shuffle(edges)
        valid(f"fixed-graph-{index:02d}", nodes, edges, "A", "F")
    nodes = [f"N{x:02d}" for x in range(32)]
    valid("node-cap-chain", nodes,
          [(a, b, 1000) for a, b in zip(nodes, nodes[1:])], nodes[0], nodes[-1], group="bounds")
    # 128 edges exactly, but all extra positive self/back arcs cannot improve
    # the unique simple forward chain. Dense DFS is intentionally avoided.
    edges = [(nodes[i], nodes[i + 1], 1) for i in range(31)]
    edges += [(n, n, 1) for n in nodes]
    edges += [(nodes[i], nodes[j], 999) for i in range(1, 32) for j in range(i)][:65]
    # Use query==source to check legal edge cap without exponential oracle paths.
    valid("edge-cap", nodes, edges, nodes[0], nodes[0], group="bounds")
    # Known expected independent of exhaustive enumeration: positive integer
    # costs imply cost>=1, and this complete graph has exactly one direct arc
    # of cost1 from A to K. Any multi-arc path costs>=2. Tests density without
    # making the trusted DFS oracle enumerate millions of irrelevant paths.
    dense_nodes = list("ABCDEFGHIJK")
    dense = {"nodes": dense_nodes,
             "edges": [{"source": a, "target": b, "cost": 1}
                       for a in dense_nodes for b in dense_nodes if a != b],
             "query": {"source": "A", "target": "K"}}
    cases.append({"id": "dense-direct-bound", "task": "routeplan", "group": "bounds",
                  "argv": [], "stdin_hex": encoded(dense).hex(),
                  "expected": {"reachable": True, "cost": 1, "path": ["A", "K"]}})
    base = {"nodes": ["A", "B"], "edges": [{"source": "A", "target": "B", "cost": 1}],
            "query": {"source": "A", "target": "B"}}
    valid("byte-cap", ["A", "B"], [("A", "B", 1)], "A", "B", group="bounds",
          raw=encoded(base) + b" " * (65536 - len(encoded(base))))

    def invalid(label, raw, args=None, group="validation"):
        cases.append({"id": label, "task": "routeplan", "group": group,
                      "argv": args or [], "stdin_hex": raw.hex(), "expected": None})

    for label, raw in [("empty", b""), ("utf8", b"\xff"), ("bom", b"\xef\xbb\xbf" + encoded(base)),
                       ("trailing", encoded(base) + b" {}"), ("top-array", b"[]"),
                       ("duplicate-top", b'{"nodes":[],"nodes":["A"],"edges":[],"query":{"source":"A","target":"A"}}'),
                       ("duplicate-inner", b'{"nodes":["A"],"edges":[],"query":{"source":"A","source":"A","target":"A"}}'),
                       ("byte-over-cap", encoded(base) + b" " * (65537 - len(encoded(base))))]:
        invalid(label, raw)
    invalid("extra-argument", encoded(base), ["--help"])
    variants = {
        "empty-nodes": {"nodes": []}, "duplicate-nodes": {"nodes": ["A", "B", "B"]},
        "node-over-cap": {"nodes": ["A", "B", *[f"N{x}" for x in range(31)]]},
        "bad-id": {"nodes": ["A", "B", "bad-id"]}, "unicode-id": {"nodes": ["A", "B", "é"]},
        "long-id": {"nodes": ["A", "B", "B" * 17]}, "bool-node": {"nodes": ["A", "B", True]},
        "unknown-query": {"query": {"source": "A", "target": "Missing"}},
        "query-extra": {"query": {"source": "A", "target": "B", "x": 1}},
        "edge-extra": {"edges": [{**base["edges"][0], "extra": 1}]},
        "unknown-edge": {"edges": [{"source": "A", "target": "Missing", "cost": 1}]},
        "duplicate-edge": {"edges": base["edges"] * 2},
        "edges-not-array": {"edges": {}},
        "extra-field": {"extra": 1},
    }
    for cost in [True, False, 0, -1, 1001, 1.0, "1", None]:
        variants[f"bad-cost-{str(cost)}-{type(cost).__name__}"] = {
            "edges": [{"source": "A", "target": "B", "cost": cost}]}
    for label, patch in variants.items():
        invalid(label, encoded({**base, **patch}))
    cap_nodes = ["A", "B", *[f"N{x}" for x in range(14)]]
    cap_edges = [{"source": a, "target": b, "cost": 1}
                 for a in cap_nodes for b in cap_nodes][:129]
    invalid("edge-over-cap", encoded({**base, "nodes": cap_nodes, "edges": cap_edges}))
    invalid("nan", encoded(base).replace(b'"cost":1', b'"cost":NaN'))
    invalid("infinity", encoded(base).replace(b'"cost":1', b'"cost":Infinity'))
    invalid("missing-field", encoded({k: v for k, v in base.items() if k != "query"}))
    invalid("huge-integer", encoded(base).replace(b'"cost":1', b'"cost":' + b"1" * 4500))
    return cases


def tree_expected(entries, depth=4, suffix=None):
    """Derive inventory from declarative fixture, independently of OS walking."""
    visited = [e for e in entries if len(e["path"].split("/")) <= depth]
    if len(visited) > 256 or any(len(e["path"].encode("utf-8")) > 512 for e in visited):
        return None
    files = [{"path": e["path"], "bytes": e["size"]} for e in visited
             if e["kind"] == "file" and (suffix is None or e["path"].split("/")[-1].endswith(suffix))]
    files.sort(key=lambda item: item["path"])
    return {"files": files, "total_bytes": sum(e["bytes"] for e in files),
            "symlinks": sorted(e["path"] for e in visited if e["kind"] == "link")}


def tree_suite():
    cases = []

    def add(label, entries, *, depth=4, suffix=None, args=None, expected="derive", group="inventory"):
        if args is None:
            args = ["--root", "/fixture/root", "--max-depth", str(depth)]
            if suffix is not None:
                args += ["--suffix", suffix]
        cases.append({"id": label, "task": "treemap", "group": group,
                      "argv": args, "stdin_hex": "", "entries": entries,
                      "expected": tree_expected(entries, depth, suffix) if expected == "derive" else expected})

    sample = [{"kind": "file", "path": "a.txt", "size": 2},
              {"kind": "file", "path": "z.bin", "size": 1},
              {"kind": "dir", "path": "sub"},
              {"kind": "file", "path": "sub/b.txt", "size": 3},
              {"kind": "link", "path": "shortcut", "target": "sub"}]
    add("empty", [])
    add("depth-one", sample, depth=1, suffix=".txt", group="depth-filter")
    add("depth-two", sample, depth=2, suffix=".txt", group="depth-filter")
    add("default-depth", sample, args=["--root", "/fixture/root"])
    add("option-order", sample, suffix=".txt",
        args=["--suffix", ".txt", "--max-depth", "4", "--root", "/fixture/root"], group="arguments")
    add("lexical-root", sample, args=["--root", "/fixture//root/./"])
    add("relative-root", sample, args=["--root", "../../fixture/root"], expected=None, group="arguments")
    # Relative valid path from /input/delivery is supplied using a separate
    # controlled cwd in runtime; this case is attached to /fixture itself.
    add("relative-valid", sample, args=["--root", "root"])
    cases[-1]["cwd"] = "/fixture"
    mixed = [{"kind": "file", "path": name, "size": size} for name, size in
             [(".hidden", 0), ("é space.txt", 7), ("a\nline.txt", 2), ("Z.TXT", 3), ("A.txt", 1), ("a.bin", 4)]]
    mixed += [{"kind": "dir", "path": "directory.txt"},
              {"kind": "file", "path": "directory.txt/child.bin", "size": 12},
              {"kind": "link", "path": "file-link", "target": "A.txt"},
              {"kind": "link", "path": "dangling", "target": "missing"},
              {"kind": "link", "path": "outside", "target": "/etc/passwd"},
              {"kind": "link", "path": "loop", "target": "."},
              {"kind": "fifo", "path": "pipe"},
              {"kind": "file", "path": "unreadable", "size": 8, "mode": 0}]
    add("mixed-types", mixed)
    add("basename-suffix-case", mixed, suffix=".txt", group="depth-filter")
    add("no-selected-files", mixed, suffix=".xyz", group="depth-filter")
    add("sparse-size", [{"kind": "file", "path": "large", "size": 8_000_003}])
    chain = [{"kind": "dir", "path": "/".join(["d"] * i)} for i in range(1, 9)]
    chain += [{"kind": "file", "path": "/".join(["d"] * i + ["f.txt"]), "size": i} for i in range(1, 9)]
    for depth in [1, 4, 8]:
        add(f"depth-{depth}-chain", chain, depth=depth, group="depth-filter")
    add("entry-cap", [{"kind": "file", "path": f"f{x:03d}", "size": x} for x in range(256)], group="bounds")
    add("entry-over-cap-filtered", [{"kind": "file", "path": f"f{x:03d}", "size": 0} for x in range(257)],
        suffix=".txt", group="bounds")
    a, b = "a" * 250, "b" * 250
    for leaf in ["c" * 10, "c" * 11]:
        entries = [{"kind": "dir", "path": a}, {"kind": "dir", "path": a + "/" + b},
                   {"kind": "file", "path": a + "/" + b + "/" + leaf, "size": 1}]
        add(f"path-bytes-{len(entries[-1]['path'])}", entries, group="bounds")
    add("unreadable-directory", [{"kind": "dir", "path": "denied", "mode": 0}], expected=None, group="errors")
    for leaf in ["cc", "ccc"]:
        a, b = "é" * 127, "ñ" * 127
        entries = [{"kind": "dir", "path": a}, {"kind": "dir", "path": a + "/" + b},
                   {"kind": "file", "path": a + "/" + b + "/" + leaf, "size": 1}]
        add(f"unicode-path-bytes-{len(entries[-1]['path'].encode('utf-8'))}", entries, group="bounds")
    counted = [{"kind": "dir", "path": f"d{x:03d}"} for x in range(252)]
    counted += [{"kind": "link", "path": f"link{x}", "target": "missing"} for x in range(3)]
    counted += [{"kind": "fifo", "path": "pipe"}, {"kind": "file", "path": "file", "size": 0}]
    add("entry-over-cap-nonregular", counted, group="bounds")
    add("denied-at-depth-boundary", [{"kind": "dir", "path": "denied", "mode": 0}], depth=1, group="depth-filter")
    add("invalid-filename-utf8", [{"kind": "file", "path_bytes_hex": "626164ff", "size": 0}], expected=None, group="errors")
    for label, args in [
        ("missing-root", []), ("empty-root", ["--root", ""]),
        ("missing-root-value", ["--root"]), ("equals-option", ["--root=/fixture/root"]),
        ("missing-depth-value", ["--root", "/fixture/root", "--max-depth"]),
        ("missing-suffix-value", ["--root", "/fixture/root", "--suffix"]),
        ("extra-positional", ["--root", "/fixture/root", "x"]),
        ("unknown-option", ["--root", "/fixture/root", "--x", "1"]),
        ("duplicate-root", ["--root", "/fixture/root", "--root", "/fixture/root"]),
        ("duplicate-depth", ["--root", "/fixture/root", "--max-depth", "1", "--max-depth", "2"]),
        ("duplicate-suffix", ["--root", "/fixture/root", "--suffix", ".txt", "--suffix", ".txt"]),
        ("dotdot", ["--root", "/fixture/root/../root"]),
        ("nonexistent", ["--root", "/fixture/absent"]),
        ("file-root", ["--root", "/fixture/root/a.txt"]),
        ("symlink-root", ["--root", "/fixture/root/shortcut"]),
        ("symlink-root-slash", ["--root", "/fixture/root/shortcut/"]),
        ("symlink-root-dot", ["--root", "/fixture/root/shortcut/."]),
    ]:
        add(label, sample, args=args, expected=None, group="arguments")
    for value in ["0", "9", "01", "-1", "١", "1.0"]:
        add("invalid-depth-" + value, [], args=["--root", "/fixture/root", "--max-depth", value],
            expected=None, group="arguments")
    for value in ["txt", ".", ".a-b", "." + "a" * 13]:
        add("invalid-suffix-" + value, [], args=["--root", "/fixture/root", "--suffix", value],
            expected=None, group="arguments")
    return cases


def materialize(root, entries):
    """Create owned fixtures only; never discover expected values from delivery."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    deferred = []
    for entry in entries:
        if "path_bytes_hex" in entry:
            path = os.fsencode(root) + b"/" + bytes.fromhex(entry["path_bytes_hex"])
        else:
            name = entry["path"]
            if name.startswith("/") or any(p in {".", "..", ""} for p in name.split("/")):
                raise ValueError("invalid fixture path")
            path = root / name
        kind = entry["kind"]
        if kind == "dir":
            os.mkdir(path, 0o755)
        elif kind == "file":
            with open(path, "xb") as stream:
                stream.truncate(entry["size"])
        elif kind == "link":
            os.symlink(entry["target"], path)
        elif kind == "fifo":
            os.mkfifo(path)
        else:
            raise ValueError("unknown fixture kind")
        if "mode" in entry:
            deferred.append((path, entry["mode"]))
    # Apply denied-directory modes only after all declarative children exist.
    for path, mode in deferred:
        os.chmod(path, mode)


def suite():
    cases = route_suite() + tree_suite()
    ids = [(c["task"], c["id"]) for c in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate reserved fixture ID")
    return {"schema": 1, "status": "draft_not_preregistered",
            "seed": "fixed-private-v1-before-generation", "cases": cases}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-draft", type=Path, required=True)
    args = parser.parse_args()
    raw = encoded(suite()) + b"\n"
    args.write_draft.parent.mkdir(parents=True, exist_ok=True)
    with args.write_draft.open("xb") as out:
        out.write(raw)
    print(json.dumps({"status": "draft", "sha256": sha(raw), "bytes": len(raw),
                      "cases": len(suite()["cases"]), "software_deliveries": 0}))


if __name__ == "__main__":
    main()
