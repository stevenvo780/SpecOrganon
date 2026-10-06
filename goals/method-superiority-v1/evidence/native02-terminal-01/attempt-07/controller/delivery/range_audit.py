"""Normalize integer half-open intervals from an atomic NDJSON batch."""
import json
import sys

MAX_BYTES = 131072
MAX_INTERVALS = 2000
MAX_ENDPOINT = 10**12


def unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError('duplicate key')
        obj[key] = value
    return obj


def reject_constant(value):
    raise ValueError('non-JSON constant')


def validate_request(obj):
    if type(obj) is not dict or set(obj) != {'intervals'}:
        raise ValueError('invalid object')
    intervals = obj['intervals']
    if type(intervals) is not list or len(intervals) > MAX_INTERVALS:
        raise ValueError('invalid intervals')
    for pair in intervals:
        if type(pair) is not list or len(pair) != 2:
            raise ValueError('invalid pair')
        start, end = pair
        if type(start) is not int or type(end) is not int:
            raise ValueError('invalid endpoint type')
        if abs(start) > MAX_ENDPOINT or abs(end) > MAX_ENDPOINT:
            raise ValueError('endpoint outside limit')
        if start >= end:
            raise ValueError('invalid interval order')
    return intervals


def parse_batch(raw):
    if len(raw) > MAX_BYTES:
        raise ValueError('input too large')
    if not raw:
        return []
    text = raw.decode('utf-8', errors='strict')
    lines = text.split('\n')
    if lines[-1] == '':
        lines.pop()
    requests = []
    for line in lines:
        if not line.strip():
            raise ValueError('empty line')
        obj = json.loads(line, object_pairs_hook=unique_object,
                         parse_constant=reject_constant)
        requests.append(validate_request(obj))
    return requests


def normalize(intervals):
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    covered = sum(end - start for start, end in merged)
    span = [merged[0][0], merged[-1][1]] if merged else None
    gaps = [[left[1], right[0]]
            for left, right in zip(merged, merged[1:])]
    return {'merged': merged, 'covered': covered,
            'span': span, 'gaps': gaps}


def main():
    raw = sys.stdin.buffer.read(MAX_BYTES + 1)
    try:
        requests = parse_batch(raw)
    except (ValueError, RecursionError):
        sys.stderr.buffer.write(b'range-audit: invalid input\n')
        return 2
    output = ''.join(json.dumps(normalize(intervals),
                               separators=(',', ':'), allow_nan=False) + '\n'
                     for intervals in requests)
    sys.stdout.buffer.write(output.encode('utf-8'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
