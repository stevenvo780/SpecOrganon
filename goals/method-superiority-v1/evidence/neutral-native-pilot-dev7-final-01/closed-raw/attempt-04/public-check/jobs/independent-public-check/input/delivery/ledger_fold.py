#!/usr/bin/env python3
"""Consolidate a bounded UTF-8 NDJSON batch using only standard streams."""

import json
import re
import sys


MAX_BYTES = 131072
MAX_ENTRIES = 2000
MAX_DELTA = 1000000000000
ACCOUNT_PATTERN = re.compile(r'[a-z][a-z0-9_]{0,31}', re.ASCII)
INVALID_MESSAGE = b'ledger-fold: invalid input\n'


class InvalidInput(ValueError):
    """The input batch violates the public contract."""


def read_batch(stream):
    """Read until EOF or the first byte beyond the permitted size."""
    data = bytearray()
    while len(data) <= MAX_BYTES:
        chunk = stream.read(MAX_BYTES + 1 - len(data))
        if not chunk:
            break
        data.extend(chunk)
    if len(data) > MAX_BYTES:
        raise InvalidInput()
    return bytes(data)


def unique_object(pairs):
    """Reject duplicate decoded names in every JSON object."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidInput()
        result[key] = value
    return result


def bounded_integer(token):
    """Convert only small integer tokens, without global interpreter changes."""
    negative = token.startswith('-')
    digits = token[1:] if negative else token
    # JSON's parser already enforces integer grammar: no leading zeros.
    limit = str(MAX_DELTA)
    if len(digits) > len(limit):
        raise InvalidInput()
    if len(digits) == len(limit) and digits > limit:
        raise InvalidInput()
    value = int(digits)
    return -value if negative else value


def reject_number(token):
    """No floating-point token or non-finite constant can occur in valid input."""
    raise InvalidInput()


def consolidate(request):
    if type(request) is not dict or set(request) != {'entries'}:
        raise InvalidInput()
    entries = request['entries']
    if type(entries) is not list or len(entries) > MAX_ENTRIES:
        raise InvalidInput()

    balances = {}
    total = 0
    for entry in entries:
        if type(entry) is not dict or set(entry) != {'account', 'delta'}:
            raise InvalidInput()
        account = entry['account']
        delta = entry['delta']
        if type(account) is not str or ACCOUNT_PATTERN.fullmatch(account) is None:
            raise InvalidInput()
        if type(delta) is not int or abs(delta) > MAX_DELTA:
            raise InvalidInput()
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
    """Validate and serialize the whole batch; perform no stream writes."""
    if len(data) > MAX_BYTES:
        raise InvalidInput()
    if not data:
        return b''

    try:
        text = data.decode('utf-8', errors='strict')
    except UnicodeDecodeError as error:
        raise InvalidInput() from error

    lines = text.split('\n')
    if lines[-1] == '':
        lines.pop()

    output = []
    for line in lines:
        try:
            request = json.loads(
                line,
                object_pairs_hook=unique_object,
                parse_int=bounded_integer,
                parse_float=reject_number,
                parse_constant=reject_number,
            )
        except (json.JSONDecodeError, RecursionError) as error:
            raise InvalidInput() from error
        result = consolidate(request)
        output.append(json.dumps(result, ensure_ascii=True, separators=(',', ':')))

    return ('\n'.join(output) + '\n').encode('ascii')


def main(stdin=None, stdout=None, stderr=None):
    """Use blocking binary streams; return the CLI status code."""
    if stdin is None:
        stdin = sys.stdin.buffer
    if stdout is None:
        stdout = sys.stdout.buffer
    if stderr is None:
        stderr = sys.stderr.buffer

    try:
        output = fold_batch(read_batch(stdin))
    except InvalidInput:
        stderr.write(INVALID_MESSAGE)
        stderr.flush()
        return 2

    if output:
        stdout.write(output)
        stdout.flush()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
