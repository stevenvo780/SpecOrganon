# Criteria recorded before measurement

The original functional contract remains authoritative. These criteria specify intended checks, not observed passes.

1. Valid requests produce exactly the four required fields. Verify all balances, exact total, movement count and sorted zero-account list against explicit expected results or an independently accumulated oracle. Cover empty entries, duplicate movements, negative and zero values, cancellation, multiple accounts, and sums beyond the per-movement bound.
2. Accept exactly empty stdin as zero requests. Cover multiple requests, optional final newline, CRLF and ordinary JSON whitespace. Reject leading, internal and trailing blank request lines; one terminal newline is a separator, not an additional request.
3. Check account lengths 1 and 32, allowed digits and underscores after the first letter, and rejection of length 33, uppercase, leading digits, empty names, punctuation, whitespace and non-ASCII characters.
4. Check positive and negative delta bounds, one-step overflow, boolean, float, exponent-form number, string and null. Integer totals must remain exact.
5. Check 2000 entries accepted and 2001 rejected; check exactly 131072 input bytes accepted for an otherwise valid batch and 131073 rejected. Count raw bytes, not decoded characters.
6. Reject malformed JSON, all non-finite constants, invalid UTF-8, BOM, non-object requests, wrong entries types, missing/extra fields, non-object entries and duplicate keys at top level and inside entries. Duplicate-key rejection also applies inside malformed nested objects.
7. For invalid batches assert exit 2, stdout exactly empty and stderr exactly the required diagnostic, including cases with valid lines before and after the invalid request. For valid batches assert exit 0, empty stderr, one newline-terminated output per request and semantically exact JSON output.
8. Exercise the actual CLI main path with binary input and captured streams. Loading must use an absolute program path under Python -I -B; tests must not assume imports from the delivery directory. Test data and oracle code belong to the immutable battery, and the program remains the mutable implementation.

Passing the battery will establish only its observed cases under the measured environment. Semantic adequacy and package dependency declarations still require independent audit; host capture alone does not establish acceptance.
