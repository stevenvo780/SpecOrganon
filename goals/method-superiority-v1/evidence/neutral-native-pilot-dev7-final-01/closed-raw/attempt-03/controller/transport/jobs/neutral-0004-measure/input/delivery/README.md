# LedgerFold

LedgerFold consolidates integer movements by account using Python 3.9 or newer and only the standard library. The CLI reads UTF-8 NDJSON from standard input and writes one compact JSON object per request to standard output. Run `python3 -I -B ledger_fold.py`. It requires no network, external dependencies, or application data files.

Each input object has exactly `entries`, a list of at most 2000 objects having exactly `account` and `delta`. Accounts match the ASCII pattern `[a-z][a-z0-9_]{0,31}`. Deltas must be JSON integers, excluding booleans and floats, with absolute value at most 1000000000000. Repeated accounts, negative movements, and zero movements are allowed. Integer balances and totals are exact; the movement limit does not cap their sums.

The entire input is limited to 131072 bytes, including whitespace and line endings. Empty stdin means zero requests. A final newline is optional; CRLF line endings work because the trailing carriage return is JSON whitespace. Empty lines, whitespace-only lines, malformed JSON, nonfinite constants, duplicate object keys at any depth, extra fields, and invalid UTF-8 are rejected. A UTF-8 BOM is rejected by the JSON parser.

Each output object has exactly `balances`, `total`, `count`, and `zero_accounts`. All mentioned accounts remain in balances, including accounts whose balance is zero. `count` counts movements. `zero_accounts` is sorted lexicographically. Each output object ends with a newline; object-key ordering is not an interface guarantee.

## Reproducible examples

These outputs are public expectations, not measured execution results. Run from the directory containing the program.

```sh
printf '%s\n' '{"entries":[{"account":"cash","delta":7},{"account":"cash","delta":-7},{"account":"bank","delta":3}]}' | python3 -I -B ledger_fold.py
```

Expected stdout:

```json
{"balances":{"cash":0,"bank":3},"total":3,"count":3,"zero_accounts":["cash"]}
```

```sh
printf '%s\n' '{"entries":[]}' '{"entries":[{"account":"a","delta":1000000000000},{"account":"a","delta":1000000000000}]}' | python3 -I -B ledger_fold.py
```

Expected stdout:

```json
{"balances":{},"total":0,"count":0,"zero_accounts":[]}
{"balances":{"a":2000000000000},"total":2000000000000,"count":2,"zero_accounts":[]}
```

Both valid examples have exit status 0 and empty stderr.

## Errors and atomicity

Any invalid request invalidates the entire batch: exit status 2, empty stdout, and stderr exactly `ledger-fold: invalid input\n`. The program reads at most 131073 bytes to detect overflow, validates every request, and prepares the complete output before writing stdout. Consequently a valid prefix followed by an invalid request produces no partial results. Empty stdin exits 0 with both streams empty.

Atomicity concerns input validation. Operating-system failures such as a broken output pipe or exhausted memory are outside this invalid-input guarantee. No runtime performance or resource benchmark has been supplied.

## Verification

The separate battery will be delivered as `test_ledger_fold.py` after review of this program and README. Its fixed host command is:

```sh
/opt/specorganon/venv/bin/python -I -B /input/delivery/test_ledger_fold.py
```

The battery must load the program using an absolute runpy/importlib path and use only the standard library. Planned checks cover exact CLI streams and status, batch atomicity, strict parsing, account and delta boundaries, byte and entry limits, and aggregation against independently calculated expectations. The first measurement will freeze its bytes and declare all test dependencies explicitly.

No tests have been executed in this text-only author invocation. No independent feedback or measurement receipt has yet been supplied. Planned tests cannot establish exhaustive correctness, independent acceptance, comparative superiority, or unknown execution costs.
