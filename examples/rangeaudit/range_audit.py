"""Normalize integer half-open intervals from an atomic NDJSON batch."""
import json
import sys

MAX_BYTES = 131072
MAX_INTERVALS = 2000
MAX_ENDPOINT = 10**12


def invalid_constant(value):
    raise ValueError('non-JSON constant')


def unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError('duplicate key')
        obj[key] = value
    return obj


def normalize(obj):
    if type(obj) is not dict or set(obj) != {'intervals'}:
        raise ValueError('object keys')
    intervals = obj['intervals']
    if type(intervals) is not list or len(intervals) > MAX_INTERVALS:
        raise ValueError('interval list')
    for pair in intervals:
        if type(pair) is not list or len(pair) != 2:
            raise ValueError('pair shape')
        start, end = pair
        if type(start) is not int or type(end) is not int:
            raise ValueError('endpoint type')
        if abs(start) > MAX_ENDPOINT or abs(end) > MAX_ENDPOINT or start >= end:
            raise ValueError('endpoint range')
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


def prepare(raw):
    if len(raw) > MAX_BYTES:
        raise ValueError('batch size')
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
        obj = json.loads(line, object_pairs_hook=unique_object,
                         parse_constant=invalid_constant)
        result = normalize(obj)
        output.append(json.dumps(result, ensure_ascii=True, separators=(',', ':')) + '\n')
    return ''.join(output).encode('utf-8')


def main():
    raw = sys.stdin.buffer.read(MAX_BYTES + 1)
    try:
        output = prepare(raw)
    except (ValueError, RecursionError):
        sys.stderr.buffer.write(b'range-audit: invalid input\n')
        return 2
    sys.stdout.buffer.write(output)
    return 0


if __name__ == '__main__':
    sys.exit(main())
