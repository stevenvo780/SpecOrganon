#!/usr/bin/env python3
"""Normalize a bounded NDJSON batch of integer half-open intervals."""

import json
import sys

MAX_BYTES = 131072
MAX_INTERVALS = 2000
MAX_ENDPOINT = 10 ** 12
INVALID_MESSAGE = b"range-audit: invalid input\n"


class InvalidInput(ValueError):
    """The input batch violates the public interface."""


def read_bounded(stream):
    """Read through EOF or one byte beyond the permitted batch size."""
    chunks = []
    size = 0
    while size <= MAX_BYTES:
        chunk = stream.read(MAX_BYTES + 1 - size)
        if not chunk:
            break
        chunks.append(chunk)
        size += len(chunk)
    if size > MAX_BYTES:
        raise InvalidInput()
    return b"".join(chunks)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidInput()
        result[key] = value
    return result


def reject_constant(value):
    raise InvalidInput()


def validate_request(value):
    if type(value) is not dict or set(value) != {"intervals"}:
        raise InvalidInput()
    intervals = value["intervals"]
    if type(intervals) is not list or len(intervals) > MAX_INTERVALS:
        raise InvalidInput()
    validated = []
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
        validated.append((start, end))
    return validated


def parse_batch(data):
    text = data.decode("utf-8", errors="strict")
    if not text:
        return []
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    requests = []
    for line in lines:
        value = json.loads(
            line,
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
        requests.append(validate_request(value))
    return requests


def normalize(intervals):
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


def encode_batch(requests):
    lines = [
        json.dumps(normalize(intervals), ensure_ascii=False, separators=(",", ":"))
        for intervals in requests
    ]
    if not lines:
        return b""
    return ("\n".join(lines) + "\n").encode("utf-8")


def main():
    try:
        requests = parse_batch(read_bounded(sys.stdin.buffer))
    except (ValueError, RecursionError):
        # Includes UTF-8/JSON errors, explicit validation errors, and parser
        # integer-conversion or nesting limits. No output has been published.
        sys.stderr.buffer.write(INVALID_MESSAGE)
        sys.stderr.buffer.flush()
        return 2
    output = encode_batch(requests)
    if output:
        sys.stdout.buffer.write(output)
        sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
