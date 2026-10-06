# Criteria recorded before measurement

No execution, feedback or measurement receipt is present in the supplied context. The following are intended acceptance criteria, not observed results.

1. Valid requests produce exactly order, layers and roots, with each node appearing once in order and once across layers. Empty graph and empty stream have the specified distinct outputs.
2. At every order step the selected node is the lexicographically least among all nodes whose predecessors have already been removed. The public a->b plus isolated z example must distinguish this order from concatenated layers.
3. Layers are independently calculated from original graph indegrees: each sorted round contains every node available before removing that round. Roots equals the first round, or []. Duplicate edges have the same result as one edge.
4. Reject all contract-invalid input classes, including invalid UTF-8, empty lines, malformed JSON, duplicate keys even within nested objects, literal nonfinite constants, extra/missing fields, wrong container and endpoint types, invalid names, duplicate nodes, unknown endpoints, self-loops and cycles, including cycles beside an acyclic component.
5. Test inclusive bounds: 120 versus 121 nodes; 2000 versus 2001 edge entries, including duplicates; 131072 versus 131073 total input bytes. Exact-limit valid input must succeed. Read no more than limit+1 bytes to decide an oversized input.
6. For any invalid batch, including a valid prefix followed by invalid input, require exit 2, zero stdout bytes and stderr exactly b'topo-plan: invalid input\n'. Valid batches require exit 0 and zero stderr bytes. Every successful response ends in one newline.
7. Verify LF, CRLF and an unterminated final request; reject an extra blank request. JSON whitespace is allowed within a request, but a whitespace-only line is invalid.
8. The separate fixed battery must execute under the prescribed isolated Python argv, load the program by absolute path and use only stdlib. Its checks must exercise the CLI with byte streams and compare statuses and complete outputs, as well as use an independent reference for small graphs. No test depends on README or criteria content.
9. All delivered test bytes and the full test/mutable partition become immutable at first measurement. Any subsequent implementation/document changes require a fresh measurement before final audit. Host capture alone is not semantic acceptance.

Strategy: strict byte-limited batch parsing, validation before graph use, duplicate-edge sets, heap-based Kahn order, and a separate round-based Kahn pass. Request independent static feedback before constructing the separate battery. Then declare its actual dependencies and request measurement. No reserved-task functionality, independent F, performance result or superiority is claimed.
