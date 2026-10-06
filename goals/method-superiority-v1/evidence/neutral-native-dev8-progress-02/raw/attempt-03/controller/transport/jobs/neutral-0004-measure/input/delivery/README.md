# LedgerFold

Python 3.8+ standard-library CLI for exact integer account aggregation. No installation or third-party dependencies are needed. Run `python3 -I -B /input/delivery/ledger_fold.py`, supplying UTF-8 NDJSON on stdin. Application code uses stdin/stdout/stderr and performs no external file or network operations.

Each request is an object with exactly `entries`, a list of at most 2000 objects with exactly `account` and `delta`. Accounts match ASCII `[a-z][a-z0-9_]{0,31}`. Deltas must be JSON integers, excluding booleans and floats, with absolute value at most 1000000000000. The entire stdin stream, including whitespace and line endings, must not exceed 131072 bytes. Empty stdin means zero requests. A final newline is optional; CRLF is accepted. Blank lines, invalid UTF-8, malformed JSON, non-finite constants, duplicate keys at any depth, and extra fields are rejected.

Each request produces one newline-terminated JSON object with exactly `balances`, `total`, `count`, and `zero_accounts`. All mentioned accounts remain in balances, including zero balances. Zero accounts are sorted lexicographically. Repeated, negative, and zero movements are permitted. Integer sums are exact and may exceed the per-movement bound. Object key order is immaterial.

## Reproducible examples

```sh
printf '%s\n' '{"entries":[{"account":"cash","delta":7},{"account":"cash","delta":-7},{"account":"bank","delta":3}]}' | python3 -I -B /input/delivery/ledger_fold.py
```

Expected stdout:

```json
{"balances":{"cash":0,"bank":3},"total":3,"count":3,"zero_accounts":["cash"]}
```

```sh
printf '%s\n' '{"entries":[]}' '{"entries":[{"account":"a","delta":1000000000000},{"account":"a","delta":1000000000000}]}' | python3 -I -B /input/delivery/ledger_fold.py
```

Expected stdout:

```json
{"balances":{},"total":0,"count":0,"zero_accounts":[]}
{"balances":{"a":2000000000000},"total":2000000000000,"count":2,"zero_accounts":[]}
```

Both examples expect exit 0 and empty stderr. These are public expectations, not execution receipts.

## Errors and atomicity

The program reads at most 131073 bytes, validates the whole batch, and serializes all results before writing stdout. Any invalid request produces empty stdout, exactly `ledger-fold: invalid input\n` on stderr, and exit 2, including when earlier requests are valid. Valid input exits 0 with empty stderr. Empty stdin produces no output. Atomicity covers validation failures; operating-system stream failures are outside the input contract.

## Tests and limitations

Run the separate fixed battery:

```sh
/opt/specorganon/venv/bin/python -I -B /input/delivery/test_ledger_fold.py
```

The script uses only the standard library. It launches isolated Python subprocesses that load the implementation by absolute path through runpy, with binary input and captured streams. All fixtures, deterministic generated cases, and oracle logic are embedded in the script; there are no additional test files or configuration dependencies. The implementation is the mutable subject under test.

Checks cover exact output schemas and integer types, aggregation, zero retention and sorting, input framing, account and delta boundaries, entry and byte limits, parsing failures, duplicate keys, invalid UTF-8, and batch atomicity. Generated valid cases use independently grouped sums as their oracle. Substantive criteria were recorded in documents/criteria.md before requesting measurement. The battery emits a compact JSON summary and exits 1 on a failed check or harness error, otherwise 0.

Supplied independent feedback accepted the earlier implementation and README by inspection and explicitly reported no test execution. This submission creates the battery and requests its first measurement; no execution result or final audit is claimed. Finite tests do not prove correctness for every input or establish superiority. Timing, peak memory, operating-system failures, and behavior across all supported interpreter versions remain unmeasured. The in-process input allocation is bounded by the byte cap; parsing and results require additional memory proportional to the bounded batch. Sorting zero accounts costs O(k log k) for k distinct accounts per request. Subprocess startup and test runtime costs are unknown until measured.
