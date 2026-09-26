"""Load an explicit case seed into a new Organon ledger; no approvals are inferred."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from specorganon import engine


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("seed", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    seed = json.loads(args.seed.read_text(encoding="utf-8"))
    engine.create_case(args.output, seed["title"], seed["domain"], seed["actor"])
    for item in seed["items"]:
        engine.put_item(
            args.output,
            item["id"],
            item["kind"],
            item["text"],
            item.get("refs", []),
            item.get("data", {}),
            seed["actor"],
        )
    state = engine.get_state(args.output)
    print(json.dumps({"revision": state["revision"], "items": len(state["items"]), "ready_phases": [phase for phase, result in state["phases"].items() if result["ready"]]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
