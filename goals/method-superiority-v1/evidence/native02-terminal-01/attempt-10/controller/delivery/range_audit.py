"""Normaliza lotes NDJSON de intervalos enteros semiabiertos."""
import json
import sys

MAX_BYTES = 131072
MAX_INTERVALS = 2000
MAX_ENDPOINT = 10**12


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate key')
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError('non-JSON constant')


def parse_batch(raw):
    if len(raw) > MAX_BYTES:
        raise ValueError('batch too large')
    text = raw.decode('utf-8', errors='strict')
    if not text:
        return []
    lines = text.split('\n')
    if lines[-1] == '':
        lines.pop()
    requests = []
    for line in lines:
        if not line.strip():
            raise ValueError('blank line')
        obj = json.loads(line, object_pairs_hook=unique_object,
                         parse_constant=reject_constant)
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
                raise ValueError('endpoint outside limits')
            if start >= end:
                raise ValueError('empty or reversed interval')
        requests.append(intervals)
    return requests


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
        requests = parse_batch(sys.stdin.buffer.read(MAX_BYTES + 1))
    except (ValueError, RecursionError):
        sys.stderr.buffer.write(b'range-audit: invalid input\n')
        return 2
    output = ''.join(json.dumps(normalize(intervals), separators=(',', ':'))
                     + '\n' for intervals in requests)
    sys.stdout.buffer.write(output.encode('utf-8'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
