"""A real killed runner process must leave a replayable atomic ledger."""

from __future__ import annotations

import json
import signal
import subprocess
import sys
import time

from specorganon import engine
from specorganon.runner import run_manifest


def test_sigkill_during_manifest_replays_without_duplicates(tmp_path):
    case = tmp_path / "case"
    engine.create_case(case, "Interrupted fixture", "fixture", "human:fixture")
    steps = [{"op": "put", "id": "p1", "kind": "problem", "text": "Fixture problem", "refs": [], "data": {}}]
    steps.extend(
        {"op": "put", "id": f"a{i}", "kind": "actor", "text": f"Fixture actor {i}", "refs": ["p1"], "data": {}}
        for i in range(100)
    )
    manifest = {"schema": 1, "steps": steps}
    manifest_file = tmp_path / "manifest.json"
    manifest_file.write_text(json.dumps(manifest), encoding="utf-8")
    code = (
        "import json,sys; from specorganon.runner import run_manifest; "
        "run_manifest(sys.argv[1],json.load(open(sys.argv[2])), 'agent:runner')"
    )
    process = subprocess.Popen([sys.executable, "-c", code, str(case), str(manifest_file)])
    ledger_file = case / "organon.json"
    deadline = time.monotonic() + 10
    revision = 0
    while time.monotonic() < deadline:
        revision = len(json.loads(ledger_file.read_text(encoding="utf-8"))["events"])
        if revision >= 3:
            break
        assert process.poll() is None, "runner exited before interruption"
        time.sleep(0.002)
    else:
        process.kill()
        process.wait()
        raise AssertionError("runner did not persist an initial checkpoint")
    process.send_signal(signal.SIGKILL)
    process.wait(timeout=5)
    assert process.returncode == -signal.SIGKILL
    revision = engine.get_state(case)["revision"]
    assert 3 <= revision < len(steps)
    replay = run_manifest(case, manifest, "agent:runner")
    assert replay["applied"] == len(steps) - revision
    assert replay["skipped"] == revision
    assert engine.get_state(case)["revision"] == len(steps)
    assert len(engine.get_state(case)["items"]) == len(steps)
    assert run_manifest(case, manifest, "agent:runner")["applied"] == 0
