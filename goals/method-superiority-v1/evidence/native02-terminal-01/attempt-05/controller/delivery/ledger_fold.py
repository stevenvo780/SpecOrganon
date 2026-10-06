#!/usr/bin/env python3
"""Consolidación exacta de lotes NDJSON con validación previa completa."""
import json
import re
import sys

LIMIT = 131072
ACCOUNT = re.compile(r'[a-z][a-z0-9_]{0,31}')


def invalid():
    raise ValueError('invalid input')


def unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            invalid()
        obj[key] = value
    return obj


def reject_constant(value):
    invalid()


def validate(raw):
    if len(raw) > LIMIT:
        invalid()
    text = raw.decode('utf-8', errors='strict')
    if not text:
        return []
    lines = text.split('\n')
    if lines[-1] == '':
        lines.pop()
    requests = []
    for line in lines:
        obj = json.loads(line, object_pairs_hook=unique_object,
                         parse_constant=reject_constant)
        if type(obj) is not dict or set(obj) != {'entries'}:
            invalid()
        entries = obj['entries']
        if type(entries) is not list or len(entries) > 2000:
            invalid()
        for entry in entries:
            if type(entry) is not dict or set(entry) != {'account', 'delta'}:
                invalid()
            account, delta = entry['account'], entry['delta']
            if type(account) is not str or ACCOUNT.fullmatch(account) is None:
                invalid()
            if type(delta) is not int or abs(delta) > 10**12:
                invalid()
        requests.append(entries)
    return requests


def consolidate(entries):
    balances = {}
    total = 0
    for entry in entries:
        account, delta = entry['account'], entry['delta']
        balances[account] = balances.get(account, 0) + delta
        total += delta
    return {'balances': balances, 'total': total, 'count': len(entries),
            'zero_accounts': sorted(a for a, b in balances.items() if b == 0)}


def main():
    try:
        requests = validate(sys.stdin.buffer.read(LIMIT + 1))
        output = ''.join(json.dumps(consolidate(entries), separators=(',', ':'))
                         + '\n' for entries in requests)
    except (ValueError, UnicodeError, RecursionError):
        sys.stderr.write('ledger-fold: invalid input\n')
        return 2
    sys.stdout.write(output)
    return 0


if __name__ == '__main__':
    sys.exit(main())
