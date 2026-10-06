"""Consolidate a bounded UTF-8 NDJSON batch atomically."""
import json
import re
import sys

MAX_BYTES = 131072
MAX_ENTRIES = 2000
MAX_DELTA = 10**12
ACCOUNT = re.compile(r"[a-z][a-z0-9_]{0,31}", re.ASCII)


def reject_constant(value):
    raise ValueError("non-finite constant")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def fold(request):
    if type(request) is not dict or set(request) != {"entries"}:
        raise ValueError("request fields")
    entries = request["entries"]
    if type(entries) is not list or len(entries) > MAX_ENTRIES:
        raise ValueError("entries")
    balances = {}
    total = 0
    for entry in entries:
        if type(entry) is not dict or set(entry) != {"account", "delta"}:
            raise ValueError("entry fields")
        account, delta = entry["account"], entry["delta"]
        if type(account) is not str or ACCOUNT.fullmatch(account) is None:
            raise ValueError("account")
        if type(delta) is not int or abs(delta) > MAX_DELTA:
            raise ValueError("delta")
        balances[account] = balances.get(account, 0) + delta
        total += delta
    return {
        "balances": balances,
        "total": total,
        "count": len(entries),
        "zero_accounts": sorted(a for a, balance in balances.items() if balance == 0),
    }


def process(data):
    if len(data) > MAX_BYTES:
        raise ValueError("batch size")
    text = data.decode("utf-8", errors="strict")
    if not text:
        return ""
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    results = []
    for line in lines:
        request = json.loads(
            line, object_pairs_hook=unique_object, parse_constant=reject_constant
        )
        results.append(fold(request))
    return "".join(
        json.dumps(result, ensure_ascii=True, separators=(",", ":")) + "\n"
        for result in results
    )


def main():
    try:
        data = sys.stdin.buffer.read(MAX_BYTES + 1)
        output = process(data)
    except (ValueError, RecursionError):
        sys.stderr.write("ledger-fold: invalid input\n")
        return 2
    sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
