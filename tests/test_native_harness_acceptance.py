"""Stdlib regressions for the reference check; no agent-review claim."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "native_harness_reference", ROOT / "scripts/check_native_harness_acceptance.py")
reference = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reference)


class NativeHarnessAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="specorganon-reference-test-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.output = Path(cls.temporary.name) / "reference"
        cls.summary = reference.run_reference(cls.output)

    def read(self, path):
        return json.loads((self.output / path).read_bytes())

    def test_real_execution_is_bound_to_preserved_source_and_streams(self):
        for variant, expected in (("working", 0), ("regression", 1)):
            with self.subTest(variant=variant):
                data = self.read(f"{variant}/local-test.json")
                process = self.read(f"{variant}/execution/process.json")
                self.assertEqual(process["exit_code"], expected)
                self.assertFalse(process["timed_out"])
                self.assertEqual(data["passed"], expected == 0)
                self.assertEqual(data["receipt"]["result_sha256"], reference.local_test_result_sha256(data))
                for name, digest in data["source_identity"]["sha256"].items():
                    self.assertEqual(digest, hashlib.sha256((self.output / variant / name).read_bytes()).hexdigest())
                for stream in ("stdout", "stderr"):
                    digest = hashlib.sha256((self.output / variant / "execution" / f"{stream}.bin").read_bytes()).hexdigest()
                    self.assertEqual(process[f"{stream}_sha256"], digest)
                    self.assertEqual(data["receipt"][f"{stream}_sha256"], digest)

    def test_failed_local_receipt_is_rejected_and_all_revisions_survive(self):
        failed = self.read("local-failed-test.json")
        self.assertIn("local test execution failed or timed out", failed["items"]["t1"]["issues"])
        self.assertFalse(failed["phases"]["build"]["ready"])
        ledger = self.read("local-review-case/organon.json")
        tests = [e["payload"] for e in ledger["events"]
                 if e["kind"] == "item_put" and e["payload"]["id"] == "t1"]
        self.assertEqual([t["data"]["receipt"]["exit_code"] for t in tests], [0, 1, 0])
        self.assertEqual([t["deps"]["impl1"] for t in tests], [1, 2, 3])
        final = self.read("local-final.json")
        self.assertEqual(final["items"]["impl1"]["data"]["source_identity"],
                         final["items"]["t1"]["data"]["source_identity"])

    def test_only_synthetic_fixture_receives_synthetic_decisions(self):
        local = self.read("local-review-case/organon.json")
        self.assertFalse(any(e["kind"] in {"approval", "phase_review", "phase_advance"}
                             for e in local["events"]))
        final = self.read("local-final.json")
        self.assertFalse(any(p["accepted"] for p in final["phases"].values()))
        self.assertEqual(self.summary["native_agent_and_human_review"]["status"], "not_run")
        fixture = self.read("mechanics-case/organon.json")
        self.assertEqual(fixture["project"]["approval_policy"], "fixture")
        self.assertEqual({e["actor"] for e in fixture["events"] if e["kind"] == "approval"}, {"human:fixture"})

    def test_changed_premise_invalidates_previous_synthetic_acceptance(self):
        completed = self.read("mechanics-completed.json")
        revised = self.read("mechanics-invalidated.json")
        self.assertEqual(sum(p["accepted"] for p in completed["phases"].values()), 9)
        self.assertFalse(revised["phases"]["validate"]["accepted"])
        self.assertTrue(revised["items"]["req1"]["stale"])
        self.assertTrue(revised["items"]["t1"]["stale"])
        self.assertTrue(revised["phases"]["study"]["accepted"])
        self.assertEqual(revised["items"]["e1"]["version"], 2)

    def test_restart_summary_never_converts_missing_mcp_into_success(self):
        self.assertTrue(self.summary["cli"]["restart_replay_unchanged"])
        expected = "passed" if self.summary["mcp"]["status"] == "passed" else "blocked"
        self.assertEqual(self.summary["status"], expected)
        self.assertEqual(self.summary["scope"], "deterministic reference mechanics only")
        self.assertEqual(self.summary["next"]["action"], "review_phase")

    def test_preserved_inventory_matches_every_file(self):
        inventory = self.read("sha256.json")
        observed = {str(path.relative_to(self.output)): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in self.output.rglob("*") if path.is_file() and path.name != "sha256.json"}
        self.assertEqual(inventory, observed)

    def test_existing_output_is_never_replaced(self):
        before = (self.output / "summary.json").read_bytes()
        with self.assertRaises(FileExistsError):
            reference.run_reference(self.output)
        self.assertEqual((self.output / "summary.json").read_bytes(), before)

    def test_timeout_preserves_actual_partial_output(self):
        directory = Path(self.temporary.name) / "timeout"
        receipt = reference._execute(
            [sys.executable, "-c", "import time; print('started', flush=True); time.sleep(30)"],
            directory, cwd=ROOT, env=reference._environment(), timeout=1)
        self.assertTrue(receipt["timed_out"])
        self.assertIsNone(receipt["exit_code"])
        self.assertEqual((directory / "stdout.bin").read_bytes(), b"started\n")
        self.assertEqual(receipt["stdout_sha256"], hashlib.sha256(b"started\n").hexdigest())


if __name__ == "__main__":
    unittest.main()
