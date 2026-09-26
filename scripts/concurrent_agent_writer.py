"""Write a bounded, independently assigned branch into one shared case.

Used by native agents in a development concurrency trial. The controller holds
an exclusive flock on --barrier until both processes report READY. Each worker
then takes a shared flock, records its active interval and writes only its own
IDs. Revision conflicts are retried without replacing another writer's work.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from specorganon import engine
from specorganon.ledger import ConflictError


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--barrier", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--prefix", choices=("a", "b"), required=True)
    parser.add_argument("--count", type=int, default=40)
    args = parser.parse_args()
    if not 1 <= args.count <= 100:
        parser.error("--count must be 1..100")
    actor = f"agent:overlap_writer_{args.prefix}"
    args.result.parent.mkdir(parents=True, exist_ok=True)
    with args.barrier.open("a+") as barrier:
        ready_at = _now()
        print(json.dumps({"status": "READY", "prefix": args.prefix, "at": ready_at}), flush=True)
        fcntl.flock(barrier.fileno(), fcntl.LOCK_SH)
        start_ns = time.monotonic_ns()
        started_at = _now()
        conflicts = 0
        for number in range(1, args.count + 1):
            item_id = f"{args.prefix}_{number:03d}"
            for attempt in range(100):
                try:
                    engine.put_item(
                        args.case, item_id, "actor", f"Synthetic branch {args.prefix} item {number}",
                        ["p1"], {"origin": "synthetic_concurrency_trial"}, actor,
                    )
                    break
                except ConflictError:
                    conflicts += 1
                    if attempt == 99:
                        raise
                    time.sleep(min(0.002 * (1.4 ** attempt), 0.015))
            # Give the other live process a chance to take the next revision.
            time.sleep(0.003)
        end_ns = time.monotonic_ns()
        result = {
            "schema": 1,
            "prefix": args.prefix,
            "actor": actor,
            "count": args.count,
            "ids": [f"{args.prefix}_{number:03d}" for number in range(1, args.count + 1)],
            "ready_at_utc": ready_at,
            "started_at_utc": started_at,
            "ended_at_utc": _now(),
            "start_monotonic_ns": start_ns,
            "end_monotonic_ns": end_ns,
            "revision_conflicts_retried": conflicts,
        }
        args.result.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": "DONE", "prefix": args.prefix, "count": args.count,
                          "revision_conflicts_retried": conflicts}), flush=True)
        fcntl.flock(barrier.fileno(), fcntl.LOCK_UN)


if __name__ == "__main__":
    main()
