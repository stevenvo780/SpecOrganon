"""Pure mocked precheck probe; no native runtime, transport or tool is invoked."""
from __future__ import annotations

import contextlib
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "scripts"))
import observed_coordinated_runtime as observer  # noqa: E402


def main():
    rows = []
    paths = ["scripts/observed_coordinated_runtime.py", "scripts/coordinated_observation_journal.py",
             "tests/test_observed_coordinated_runtime.py", "tests/test_coordinated_observation_journal.py"]
    pins = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in paths}
    for kind in ("activation", "merge", "delivery", "metrics", "valid"):
        touched = []
        state = {"state": "paused" if kind in ("activation", "merge") else "completed",
                 "delegations": [{"activation": {}}] if kind == "activation" else [],
                 "merges": [{"receipt": {}}] if kind == "merge" else [],
                 "delivery": {"current_metrics": {"value": 1}}}
        status = {"state": state["state"], "checkpoint_sha256": "a" * 64}
        broker = SimpleNamespace(current_metrics=lambda _role: {"value": 2 if kind == "metrics" else 1})
        def receipt(_value, label):
            touched.append(label)
            if kind in ("activation", "merge", "delivery"):
                raise observer.ObservationError("synthetic receipt mismatch")
        def visitor(*_args):
            touched.append("visitor")
            return "accepted"
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(observer, "_run_lock", lambda _path: contextlib.nullcontext()))
            stack.enter_context(patch.object(observer, "_private_dir", lambda _path: None))
            stack.enter_context(patch.object(observer, "_private_file", lambda _path: None))
            stack.enter_context(patch.object(observer.engine, "_load", lambda _path: ({}, state, None, None, broker)))
            stack.enter_context(patch.object(observer.runtime, "guard_coordinated_runtime", lambda *_args: None))
            stack.enter_context(patch.object(observer.engine, "_audit", lambda *_args: None))
            stack.enter_context(patch.object(observer.engine, "_bound_receipt", receipt))
            stack.enter_context(patch.object(observer.engine, "_view", lambda *_args: status))
            stack.enter_context(patch.object(observer, "_expected", lambda *_args: []))
            try:
                result = observer._native_snapshot(Path("/synthetic/mocked/run"), visitor=visitor)
                rows.append({"case": kind, "accepted": result == "accepted", "touched": touched})
            except observer.ObservationError as error:
                rows.append({"case": kind, "accepted": False, "error": str(error), "touched": touched})
        assert ("visitor" in touched) is (kind == "valid")
        assert rows[-1]["accepted"] is (kind == "valid")
    assert pins == {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in paths}
    print(json.dumps({"scope": "PURE_mocked_snapshot_only_no_native_effects_no_CLI_bypass_claim",
                      "sources_sha256": pins, "sources_unchanged": True, "cases": rows}, sort_keys=True))


if __name__ == "__main__":
    main()
