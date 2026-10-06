# Criteria recorded before measurement

1. For each valid request, balances equal the sum of all movements for each mentioned account; zero balances remain present, total equals the sum of deltas, count equals the entry count, and zero_accounts is exactly the sorted list of zero-balance accounts. Compare parsed outputs to independently computed expected objects, including duplicate accounts, cancellation, explicit zero, negative values, and sums beyond the per-movement bound.
2. Successful CLI runs have exit 0, empty stderr, exactly one newline-terminated JSON result per request, and no output for empty stdin. Exercise multiple requests and final-newline variants.
3. Every invalid batch has exit 2, stdout empty, and stderr exactly ledger-fold: invalid input followed by newline. Exercise invalid requests after a valid prefix to test batch atomicity.
4. Reject wrong root/entry types, missing or extra fields, duplicate keys at root and nested objects, malformed JSON, nonfinite constants, invalid UTF-8, blank lines, bool/float deltas, out-of-range deltas, and invalid account names. Include escaped spellings of duplicate keys.
5. Accept inclusive boundaries: 2000 entries, 32-character valid account, both delta endpoints, and exactly 131072 input bytes. Reject 2001 entries, 33-character accounts, deltas immediately outside either endpoint, and 131073 bytes. Generate byte-boundary inputs using legal JSON whitespace so byte size is isolated from other validity conditions.
6. The battery must use an absolute program path under Python -I -B, require no third-party packages, emit bounded diagnostic output, and preserve failures. All fixtures and test dependencies must belong to the immutable test partition; the implementation under test is mutable delivery code, not a test fixture.
7. Read the README against the actual interface and supplied receipts. Treat host execution success as evidence for these checks only; semantic acceptance and independent audit remain separate.

These are prospective acceptance criteria. No execution, feedback, or acceptance is claimed.
