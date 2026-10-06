#!/usr/bin/env python3
"""Consolidate a bounded UTF-8 NDJSON batch using only standard streams."""

import json
import re
import sys


MAX_INPUT_BYTES = 131072
MAX_ENTRIES = 2000
MAX_DELTA = 1000000000000
ACCOUNT_PATTERN = re.compile(r'[a-z][a-z0-9_]{0,31}', re.ASCII)
ERROR_MESSAGE = b'ledger-fold: invalid input\n'


class InvalidInput(ValueError):
    """The input does not satisfy the LedgerFold contract."""


def unique_object(pairs):
    """Reject duplicate keys after JSON escape decoding, at every depth."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidInput('duplicate key')
        result[key] = value
    return result


def reject_constant(value):
    raise InvalidInput('non-finite constant')


def consolidate(request):
    if type(request) is not dict or set(request) != {'entries'}:
        raise InvalidInput('invalid request fields')
    entries = request['entries']
    if type(entries) is not list or len(entries) > MAX_ENTRIES:
        raise InvalidInput('invalid entries')

    balances = {}
    total = 0
    for entry in entries:
        if type(entry) is not dict or set(entry) != {'account', 'delta'}:
            raise InvalidInput('invalid entry fields')
        account = entry['account']
        delta = entry['delta']
        if type(account) is not str or ACCOUNT_PATTERN.fullmatch(account) is None:
            raise InvalidInput('invalid account')
        if type(delta) is not int or abs(delta) > MAX_DELTA:
            raise InvalidInput('invalid delta')
        balances[account] = balances.get(account, 0) + delta
        total += delta

    return {
        'balances': balances,
        'total': total,
        'count': len(entries),
        'zero_accounts': sorted(
            account for account, balance in balances.items() if balance == 0
        ),
    }


def fold_batch(data):
    """Return complete output bytes, or raise a validation/parser exception.

    This function performs no stream or file I/O. The caller must provide bytes.
    """
    if len(data) > MAX_INPUT_BYTES:
        raise InvalidInput('input too large')
    text = data.decode('utf-8', errors='strict')
    if not text:
        return b''

    lines = text.split('\n')
    if text.endswith('\n'):
        lines.pop()

    results = []
    for line in lines:
        # json.loads rejects empty/whitespace-only lines and trailing content.
        request = json.loads(
            line,
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
        results.append(consolidate(request))

    # All requests are valid before serialization or any stdout operation.
    output = ''.join(
        json.dumps(result, ensure_ascii=True, allow_nan=False, separators=(',', ':'))
        + '\n'
        for result in results
    )
    return output.encode('ascii')


def main():
    # Read at most one byte beyond the bound, including across short reads.
    chunks = []
    remaining = MAX_INPUT_BYTES + 1
    while remaining:
        chunk = sys.stdin.buffer.read(remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    data = b''.join(chunks)

    try:
        output = fold_batch(data)
    except (ValueError, UnicodeError, RecursionError):
        # ValueError includes JSONDecodeError, InvalidInput, and integer parser
        # limits. Excessive JSON nesting cannot satisfy this shallow schema.
        sys.stderr.buffer.write(ERROR_MESSAGE)
        sys.stderr.buffer.flush()
        return 2

    if output:
        sys.stdout.buffer.write(output)
        sys.stdout.buffer.flush()
    return 0


if __name__ == '__main__':
    sys.exit(main())
