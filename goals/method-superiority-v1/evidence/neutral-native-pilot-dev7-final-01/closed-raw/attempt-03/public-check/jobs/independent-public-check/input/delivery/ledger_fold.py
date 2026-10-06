#!/usr/bin/env python3
"""Validate a complete NDJSON batch before emitting account balances."""
import json
import re
import sys

MAX_BYTES = 131072
MAX_ENTRIES = 2000
MAX_DELTA = 10**12
ACCOUNT = re.compile(r"[a-z][a-z0-9_]{0,31}", re.ASCII)


class InvalidInput(ValueError):
    pass


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidInput("duplicate key")
        result[key] = value
    return result


def reject_constant(value):
    raise InvalidInput("nonfinite constant")


def fold_request(request):
    if type(request) is not dict or set(request) != {"entries"}:
        raise InvalidInput("request shape")
    entries = request["entries"]
    if type(entries) is not list or len(entries) > MAX_ENTRIES:
        raise InvalidInput("entries shape or size")
    balances = {}
    total = 0
    for entry in entries:
        if type(entry) is not dict or set(entry) != {"account", "delta"}:
            raise InvalidInput("entry shape")
        account = entry["account"]
        delta = entry["delta"]
        if type(account) is not str or ACCOUNT.fullmatch(account) is None:
            raise InvalidInput("account")
        if type(delta) is not int or abs(delta) > MAX_DELTA:
            raise InvalidInput("delta")
        balances[account] = balances.get(account, 0) + delta
        total += delta
    return {
        "balances": balances,
        "total": total,
        "count": len(entries),
        "zero_accounts": sorted(a for a, balance in balances.items() if balance == 0),
    }


def fold_batch(data):
    """Return serialized output for bytes; raise ValueError for invalid input."""
    if len(data) > MAX_BYTES:
        raise InvalidInput("byte limit")
    text = data.decode("utf-8", errors="strict")
    if not text:
        return ""
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    output = []
    for line in lines:
        request = json.loads(
            line, object_pairs_hook=unique_object, parse_constant=reject_constant
        )
        result = fold_request(request)
        output.append(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
    return "\n".join(output) + "\n"


def main():
    try:
        data = sys.stdin.buffer.read(MAX_BYTES + 1)
        output = fold_batch(data)
    except (ValueError, RecursionError):
        sys.stderr.write("ledger-fold: invalid input\n")
        return 2
    sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
