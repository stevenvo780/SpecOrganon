#!/usr/bin/env python3
"""Normalize integer half-open intervals from an atomic NDJSON batch."""
import json
import sys

MAX_BYTES = 131072
MAX_ENDPOINT = 10 ** 12


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate key')
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError('nonstandard JSON constant')


def validate(line):
    if not line.strip():
        raise ValueError('empty line')
    obj = json.loads(line, object_pairs_hook=unique_object,
                     parse_constant=reject_constant)
    if type(obj) is not dict or set(obj) != {'intervals'}:
        raise ValueError('invalid object')
    intervals = obj['intervals']
    if type(intervals) is not list or len(intervals) > 2000:
        raise ValueError('invalid intervals')
    for pair in intervals:
        if type(pair) is not list or len(pair) != 2:
            raise ValueError('invalid pair')
        start, end = pair
        if type(start) is not int or type(end) is not int:
            raise ValueError('invalid endpoint type')
        if abs(start) > MAX_ENDPOINT or abs(end) > MAX_ENDPOINT:
            raise ValueError('endpoint limit')
        if start >= end:
            raise ValueError('invalid interval')
    return intervals


def normalize(intervals):
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return {
        'merged': merged,
        'covered': sum(end - start for start, end in merged),
        'span': [merged[0][0], merged[-1][1]] if merged else None,
        'gaps': [[left[1], right[0]]
                 for left, right in zip(merged, merged[1:])],
    }


def main():
    try:
        raw = sys.stdin.buffer.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError('input limit')
        text = raw.decode('utf-8', errors='strict')
        lines = text.split('\n') if raw else []
        if lines and lines[-1] == '':
            lines.pop()
        requests = [validate(line) for line in lines]
        output = ''.join(json.dumps(normalize(intervals),
                                    separators=(',', ':'), allow_nan=False)
                         + '\n' for intervals in requests).encode('utf-8')
    except (ValueError, RecursionError):
        sys.stderr.buffer.write(b'range-audit: invalid input\n')
        return 2
    sys.stdout.buffer.write(output)
    return 0


if __name__ == '__main__':
    sys.exit(main())
