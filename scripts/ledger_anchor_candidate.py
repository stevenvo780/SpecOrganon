"""Print one read-only ledger anchor entry candidate for independent review.

Stdout is one JSON object with ``schema: 1``, ``case_id``, ``entry``, and
``notice``. ``entry`` has the four fields expected for one case in a schema-1
external anchor file. This is deliberately not a complete anchor file: an
operator must independently review the candidate and maintain its custody.
Nothing here registers an anchor or approves evidence.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

sys.dont_write_bytecode = True

from specorganon import approval, ledger  # noqa: E402


def candidate(case: Path) -> dict[str, object]:
    """Validate the local chain and describe its current head without writes."""
    data = ledger.read_project(case, verify_external_anchor=False)
    case_id = data["project"].get("case_id")
    try:
        valid_case_id = isinstance(case_id, str) and str(uuid.UUID(case_id)) == case_id
    except (ValueError, AttributeError):
        valid_case_id = False
    if not valid_case_id:
        raise ledger.LedgerError("project case_id is missing or malformed; cannot propose an anchor")

    events = data["events"]
    return {
        "schema": 1,
        "case_id": case_id,
        "entry": {
            "path": approval.case_path(case),
            "project_sha256": approval.project_fingerprint(data["project"]),
            "seq": len(events),
            "head_hash": events[-1]["hash"] if events else ledger.ZERO_HASH,
        },
        "notice": "Candidate for independent custody and review; no anchor written and no evidence approved.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("case", type=Path, help="case directory containing organon.json")
    args = parser.parse_args(argv)
    try:
        result = candidate(args.case)
    except (ledger.LedgerError, OSError, RuntimeError, ValueError) as exc:
        print(f"Cannot propose ledger anchor candidate: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
