#!/usr/bin/env python3
"""Normalize a bounded UTF-8 NDJSON batch of integer intervals."""

import json
import sys


MAX_INPUT_BYTES = 131072
MAX_INTERVALS = 2000
MAX_ENDPOINT = 10 ** 12
INVALID_MESSAGE = b"range-audit: invalid input\n"


class InvalidInput(ValueError):
    """The supplied batch violates the input contract."""


def read_limited(stream):
    """Read a binary stream through EOF, with one byte to detect excess."""
    chunks = []
    remaining = MAX_INPUT_BYTES + 1
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    data = b"".join(chunks)
    if len(data) > MAX_INPUT_BYTES:
        raise InvalidInput()
    return data


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidInput()
        result[key] = value
    return result


def _reject_number(token):
    # No floating-point or nonstandard constant can occur in a valid request.
    raise InvalidInput()


def _validate_request(value):
    if type(value) is not dict or set(value) != {"intervals"}:
        raise InvalidInput()
    intervals = value["intervals"]
    if type(intervals) is not list or len(intervals) > MAX_INTERVALS:
        raise InvalidInput()
    for pair in intervals:
        if type(pair) is not list or len(pair) != 2:
            raise InvalidInput()
        start, end = pair
        if type(start) is not int or type(end) is not int:
            raise InvalidInput()
        if abs(start) > MAX_ENDPOINT or abs(end) > MAX_ENDPOINT:
            raise InvalidInput()
        if start >= end:
            raise InvalidInput()
    return intervals


def parse_batch(data):
    """Validate bytes and return interval lists; raise InvalidInput on error."""
    if len(data) > MAX_INPUT_BYTES:
        raise InvalidInput()
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise InvalidInput() from exc
    if not text:
        return []
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()  # Only the artificial record after the terminal LF.
    requests = []
    for line in lines:
        try:
            value = json.loads(
                line,
                object_pairs_hook=_unique_object,
                parse_float=_reject_number,
                parse_constant=_reject_number,
            )
        except (ValueError, RecursionError) as exc:
            # Includes malformed JSON, duplicate keys, forbidden numbers,
            # excessive nesting and Python's integer-conversion limit.
            raise InvalidInput() from exc
        requests.append(_validate_request(value))
    return requests


def normalize(intervals):
    """Return the four result fields for an already validated interval list.

    The input is not modified. Sorting and scanning take O(n log n) time
    and O(n) additional memory.
    """
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            if end > merged[-1][1]:
                merged[-1][1] = end
        else:
            merged.append([start, end])
    covered = sum(end - start for start, end in merged)
    span = [merged[0][0], merged[-1][1]] if merged else None
    gaps = [
        [merged[index - 1][1], merged[index][0]]
        for index in range(1, len(merged))
    ]
    return {"merged": merged, "covered": covered, "span": span, "gaps": gaps}


def prepare_output(data):
    """Validate the entire batch and prepare all output before any emission."""
    requests = parse_batch(data)
    lines = [
        json.dumps(normalize(intervals), separators=(",", ":"), allow_nan=False)
        + "\n"
        for intervals in requests
    ]
    return "".join(lines).encode("utf-8")


def main():
    """Run the stdin/stdout CLI; return 0 on success or 2 on invalid input."""
    try:
        data = read_limited(sys.stdin.buffer)
        output = prepare_output(data)
    except InvalidInput:
        sys.stderr.buffer.write(INVALID_MESSAGE)
        sys.stderr.buffer.flush()
        return 2
    if output:
        sys.stdout.buffer.write(output)
        sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
