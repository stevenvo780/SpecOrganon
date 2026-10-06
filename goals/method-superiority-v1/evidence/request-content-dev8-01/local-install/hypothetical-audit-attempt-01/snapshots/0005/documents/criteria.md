# Criteria recorded before measurement

These are proposed acceptance criteria, not execution findings.

1. For valid requests, parse every output line as JSON and require exactly merged, covered, span and gaps. Require integer endpoints and coverage without booleans or floats. Output interval order must increase, each interval must have positive length, and consecutive merged intervals must be strictly separated.
2. Check the four supplied examples, empty stdin, multiple valid requests, LF/CRLF and a final line without newline. Require exit 0 and empty stderr; every nonempty successful output must end in newline.
3. Compare generated small-domain requests against an independent integer-cell oracle: expand input coverage into a set of unit cells, reconstruct maximal consecutive runs, count cells, derive span and internal gaps. Include unsorted, duplicate, nested, overlapping, adjacent and negative intervals. This tests semantic coverage without copying the implementation's sorting-and-merging algorithm.
4. Exercise endpoint values at and beyond +/-10^12, exactly 2000 and 2001 pairs, and batches of exactly 131072 and 131073 bytes. Inclusive valid limits must succeed; exceeded limits must fail.
5. Reject incorrect roots, missing/extra/duplicate keys, escaped-equivalent duplicate keys, invalid lists/pairs, booleans, floats, strings, null, zero/reversed ranges, malformed JSON, nonstandard numeric constants, invalid UTF-8, blank lines and whitespace-only input. Include deeply nested malformed requests to check controlled parser failure.
6. For every rejection require exit 2, exactly empty stdout and stderr bytes equal to b'range-audit: invalid input\n'. Place invalid requests before and after valid requests to check batch atomicity.
7. The test harness must execute the real CLI with binary streams under Python -I -B, loading via an absolute runpy path; no sys.path assumptions, external fixtures, network or environment mutation. Keep reported streams short and complete. Failures must remain visible.

Strategy: bounded binary read, strict UTF-8 decode, LF framing, duplicate-aware JSON parsing, exact-type validation, sorted interval sweep, and deferred output. The 131073-byte read distinguishes the inclusive batch limit without reading an unbounded stream.

Trace: initial program and README supplied here; separate battery intentionally not supplied yet. Request independent feedback before preparing the battery against this version. No execution, host seal, reviewer finding or semantic acceptance has been observed. The first measurement will explicitly declare all delivery files and freeze the battery and partition.
