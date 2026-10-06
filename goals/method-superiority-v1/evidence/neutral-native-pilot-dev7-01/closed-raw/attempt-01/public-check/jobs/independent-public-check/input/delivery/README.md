# RangeAudit

RangeAudit normalizes integer half-open intervals from an NDJSON batch. It uses only the Python standard library, with no network access, external data files or environment changes. Intended environment: CPython 3.10 or newer with binary stdin/stdout/stderr available. No execution has been observed for this revision.

Run:

```sh
python3 -I -B /input/delivery/range_audit.py < requests.ndjson
```

Each input line must contain one JSON object with exactly the key `intervals`, whose value is a list of at most 2000 two-element arrays. Endpoints must be JSON integers, excluding booleans and floats, with absolute value at most 1000000000000 and start strictly less than end. Input is strict UTF-8 and the entire stdin is limited to 131072 bytes, including whitespace and line endings. Duplicate JSON keys, extra keys, malformed JSON and blank lines are invalid. An entirely empty stream is valid. LF and CRLF endings are accepted; the final request may omit its line ending. One final newline terminates the last request; another introduces an invalid blank line.

Each successful request produces one UTF-8 JSON line containing exactly `merged`, `covered`, `span` and `gaps`. Sorting and merging include overlaps, duplicates and adjacent intervals. Coverage is an exact integer; gaps exclude the exterior. An empty interval list produces empty arrays, coverage zero and a null span.

These examples are reproducible public expectations, not measured results:

```sh
printf '%s\n' '{"intervals":[[1,3],[3,7],[10,12]]}' | python3 -I -B /input/delivery/range_audit.py
```

Expected stdout:

```json
{"merged":[[1,7],[10,12]],"covered":8,"span":[1,12],"gaps":[[7,10]]}
```

```sh
printf '%s\n' '{"intervals":[[4,8],[1,2],[2,6],[4,8]]}' | python3 -I -B /input/delivery/range_audit.py
```

Expected stdout:

```json
{"merged":[[1,8]],"covered":7,"span":[1,8],"gaps":[]}
```

Both successful examples should exit 0 with empty stderr. Any invalid request makes the entire batch exit 2 with empty stdout and exactly `range-audit: invalid input\n` on stderr. Validation and output construction finish before stdout is written. This guarantees validation atomicity; it does not promise transactional writes if the output device fails. Empty stdin exits 0 with both output streams empty.

The separate test battery will be supplied after feedback on this program and README. Its fixed command is:

```sh
/opt/specorganon/venv/bin/python -I -B /input/delivery/test_range_audit.py
```

The battery must load this program by absolute path and use only standard-library dependencies. Planned coverage includes public examples, independent finite-domain coverage checks, boundaries, malformed inputs and whole-batch atomicity. There are currently no test execution receipts or independent acceptance findings. Finite tests cannot establish correctness for every input, field effects or superiority. Sorting costs O(n log n) per request for n intervals; batch input and output are buffered. Actual runtime, peak memory and environmental failure costs remain unmeasured.
