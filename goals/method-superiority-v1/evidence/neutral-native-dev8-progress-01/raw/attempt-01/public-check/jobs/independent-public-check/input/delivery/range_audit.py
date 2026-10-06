#!/usr/bin/env python3
"""Normalize a bounded batch of integer intervals from UTF-8 NDJSON."""

import json
import sys

MAX_BYTES = 131072
MAX_INTERVALS = 2000
MAX_ENDPOINT = 10**12


def reject_constant(value):
    raise ValueError('nonstandard JSON constant')


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def normalize(request):
    if type(request) is not dict or set(request) != {'intervals'}:
        raise ValueError('expected exactly intervals')
    intervals = request['intervals']
    if type(intervals) is not list or len(intervals) > MAX_INTERVALS:
        raise ValueError('invalid interval list')
    for pair in intervals:
        if type(pair) is not list or len(pair) != 2:
            raise ValueError('invalid pair')
        start, end = pair
        if type(start) is not int or type(end) is not int:
            raise ValueError('endpoints must be integers')
        if abs(start) > MAX_ENDPOINT or abs(end) > MAX_ENDPOINT or start >= end:
            raise ValueError('invalid endpoints')

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
        'gaps': [[left[1], right[0]] for left, right in zip(merged, merged[1:])],
    }


def process_batch(raw):
    if len(raw) > MAX_BYTES:
        raise ValueError('batch too large')
    text = raw.decode('utf-8', errors='strict')
    if not text:
        return b''
    lines = text.split('\n')
    if lines[-1] == '':
        lines.pop()
    output = []
    for line in lines:
        if not line.strip():
            raise ValueError('empty line')
        request = json.loads(
            line, object_pairs_hook=unique_object, parse_constant=reject_constant
        )
        result = normalize(request)
        output.append(json.dumps(result, ensure_ascii=False, separators=(',', ':')) + '\n')
    return ''.join(output).encode('utf-8')


def main():
    try:
        raw = sys.stdin.buffer.read(MAX_BYTES + 1)
        output = process_batch(raw)
    except (ValueError, TypeError, RecursionError):
        sys.stderr.write('range-audit: invalid input\n')
        return 2
    sys.stdout.buffer.write(output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
