# TopoPlan

TopoPlan plans directed acyclic graphs using Python 3.8+ and only the standard library. Run `python3 -I -B /absolute/path/to/topo_plan.py`. It reads UTF-8 NDJSON from stdin and writes one JSON object followed by a newline for each request. It does not access the network or read/write external data files.

Each request has exactly `nodes` and `edges`. Nodes are distinct ASCII names matching `[a-z][a-z0-9_]{0,15}`, with at most 120 nodes. Edges are at most 2000 two-element arrays naming existing nodes. Duplicate edges count once, but still count toward the 2000 input-entry limit. Self-loops and cycles are invalid. Total input, including whitespace and line endings, is limited to 131072 bytes. An entirely empty stream contains zero requests. A final newline is optional; blank request lines are invalid. CRLF works because the trailing carriage return is JSON whitespace.

`order` repeatedly selects the lexicographically smallest node among all currently available nodes. `layers` removes a whole sorted round at a time. `roots` is the initial round, or an empty list. The two calculations use separate copies of the original indegrees and share adjacency without modifying it.

These reproducible examples show expected outputs, not measured executions:

```sh
printf '%s\n' '{"nodes":["z","b","a"],"edges":[["a","b"]]}' | python3 -I -B /absolute/path/to/topo_plan.py
```

```json
{"order":["a","b","z"],"layers":[["a","z"],["b"]],"roots":["a","z"]}
```

```sh
printf '%s\n' '{"nodes":["c","a","b"],"edges":[["a","c"],["b","c"],["a","c"]]}' | python3 -I -B /absolute/path/to/topo_plan.py
```

```json
{"order":["a","b","c"],"layers":[["a","b"],["c"]],"roots":["a","b"]}
```

Valid batches exit 0 with empty stderr. Any invalid request makes the entire batch exit 2 with empty stdout and stderr exactly `topo-plan: invalid input\n`. Invalid UTF-8, malformed JSON, nonfinite constants, duplicate object keys, extra fields, bad names, repeated nodes, malformed edges, unknown endpoints, self-loops, cycles, blank lines and oversized batches are rejected. Every request is parsed and planned before any stdout write. This atomicity applies to input validation; operating-system I/O failures are outside that guarantee.

The size check reads at most 131073 bytes before rejecting an oversized stream. Planning uses O(V + E) graph storage and O((V + E) log V) time as a conservative bound per request, after duplicate elimination. Parsing and batch buffering also consume memory; output and parsed results are retained until validation finishes. Actual runtime, peak memory, interpreter-dependent parsing costs and resource-failure behavior have not been measured.

The fixed battery is supplied separately after this program and README are established. Its prescribed command is `/opt/specorganon/venv/bin/python -I -B /input/delivery/test_topo_plan.py`. The battery must load the program using an absolute runpy/importlib path, without depending on sys.path. At this submission no battery or execution receipt has been supplied. Planned coverage includes public examples, malformed input, byte and graph limits, atomic failure, and independent small-graph ordering/layer checks. Such tests would support only the cases actually checked; they cannot establish exhaustive correctness, independent acceptance or superiority.
