"""Policy-specific runner handoffs using labeled mechanics test cases.

The local declarations and deterministic signing keys below are invented test
inputs. They do not represent owner consent, independent agent review or real
key custody. Test subprocess outcomes are measured; no model or server runs.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from specorganon import approval, engine, runner


ROOT = Path(__file__).resolve().parents[1]
OWNER = "human:test-owner"
AUTHOR = "agent:test-author"
REVIEWER = "agent:test-reviewer"
EXECUTOR = "executor:test-executor"
ADVANCE = {"schema": 1, "steps": [{"op": "advance", "phase": "build"}]}
EXHAUSTED = {"schema": 1, "steps": []}


def _signed(private_key, challenge):
    return base64.b64encode(private_key.sign(base64.b64decode(challenge["message_base64"]))).decode()


class RunnerHandoffTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="specorganon-handoff-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        environment = {key: value for key, value in os.environ.items() if not key.startswith("ORGANON_")}
        self.environment = patch.dict(os.environ, environment, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def _execution(self, exit_code):
        argv = [sys.executable, "-c", f"print('measured handoff test'); raise SystemExit({exit_code})"]
        process = subprocess.run(argv, capture_output=True, check=False, timeout=10)
        self.assertEqual(process.returncode, exit_code)
        data = {
            "passed": process.returncode == 0,
            "argv": argv,
            "command": shlex.join(argv),
            "receipt": {
                "argv": argv, "exit_code": process.returncode, "timed_out": False,
                "stdout_sha256": hashlib.sha256(process.stdout).hexdigest(),
                "stderr_sha256": hashlib.sha256(process.stderr).hexdigest(),
            },
        }
        data["receipt"]["result_sha256"] = engine.local_test_result_sha256(data)
        return data

    def _signed_registry(self, case):
        # Deliberately public deterministic test keys, confined to this process.
        keys = {actor: Ed25519PrivateKey.from_private_bytes(bytes([index]) * 32)
                for index, actor in enumerate((OWNER, REVIEWER, EXECUTOR), 1)}
        encoded = {
            actor: base64.b64encode(key.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
            for actor, key in keys.items()
        }
        project = engine.get_state(case)["project"]
        registry = self.root / "synthetic-public-registry.json"
        registry.write_text(json.dumps({"schema": 2, "cases": {project["case_id"]: {
            "path": str(case.resolve()), "project_sha256": approval.project_fingerprint(project),
            "approvers": {OWNER: encoded[OWNER]},
            "phase_reviewers": {REVIEWER: encoded[REVIEWER]},
            "test_executors": {EXECUTOR: encoded[EXECUTOR]},
        }}}), encoding="utf-8")
        os.environ["ORGANON_APPROVERS_FILE"] = str(registry)
        return keys

    def _build_case(self, policy, *, missing_receipt=False, signed_report=False):
        case = self.root / "case"
        engine.create_case(case, "Synthetic handoff test data", "test data", OWNER,
                           approval_policy=policy)
        keys = self._signed_registry(case) if policy == "signed" else {}
        manifest = json.loads((ROOT / "workflows/synthetic_full.json").read_text(encoding="utf-8"))
        measured = self._execution(3)
        for step in manifest["steps"]:
            if step["op"] == "advance":
                phase = step["phase"]
                if phase == "build":
                    break
                if phase in {"critique", "specify"}:
                    target = "n1" if phase == "critique" else "d1"
                    reason = "Invented owner decision for mechanics tests only"
                    signature = (_signed(keys[OWNER], engine.approval_challenge(case, target, reason, OWNER))
                                 if keys else None)
                    engine.approve(case, target, reason, OWNER, signature)
                reason = "Invented review for mechanics tests only"
                signature = (_signed(keys[REVIEWER], engine.phase_review_challenge(
                    case, phase, "accept", reason, REVIEWER)) if keys else None)
                engine.review_phase(case, phase, "accept", reason, REVIEWER, signature)
                engine.advance(case, phase, AUTHOR)
                continue
            data = copy.deepcopy(step["data"])
            if step["id"] == "e0":
                data.update(metric_key="count", scope="test data", unit="count", value=10)
            elif step["kind"] == "criterion":
                data["threshold"] = {"operator": ">=", "statistic": "estimate", "value": 0}
            elif step["kind"] == "test":
                data = copy.deepcopy(measured)
                if missing_receipt or policy == "signed":
                    data.pop("receipt")
            engine.put_item(case, step["id"], step["kind"], step["text"], step["refs"], data, AUTHOR)
        if signed_report:
            receipt = measured["receipt"]
            report = {"schema": 1, "artifacts": [],
                      **{key: value for key, value in receipt.items() if key != "result_sha256"}}
            challenge = engine.test_execution_challenge(case, "t1", report, EXECUTOR)
            engine.record_test_execution(case, "t1", report, EXECUTOR, _signed(keys[EXECUTOR], challenge))
        return case

    def _assert_wait(self, case, manifest, expected_reason):
        before = (case / "organon.json").read_bytes()
        response = runner.run_manifest(case, manifest, AUTHOR)
        self.assertEqual((case / "organon.json").read_bytes(), before)
        self.assertEqual(response["status"], "waiting")
        self.assertEqual(response["next"]["action"], "execute_test")
        self.assertEqual(response["reason"], expected_reason)
        self.assertEqual(response["applied"], 0)
        self.assertEqual(response["skipped"], 0)
        self.assertFalse(engine.gate(case, "build")["accepted"])
        return response

    def test_local_failed_execution_uses_local_reason_at_advance(self):
        case = self._build_case("local")
        result = self._assert_wait(case, ADVANCE, "local_test_execution_required")
        self.assertEqual(result["next"]["test_execution_trust"], "local_declared")
        self.assertIn("local_declared", result["next"]["task"])
        self.assertEqual(result["next"]["test_execution_targets"][0]["id"], "t1")
        self.assertEqual(engine.get_state(case)["items"]["t1"]["data"]["receipt"]["exit_code"], 3)

    def test_local_missing_receipt_uses_local_reason_when_manifest_exhausted(self):
        case = self._build_case("local", missing_receipt=True)
        result = self._assert_wait(case, EXHAUSTED, "local_test_execution_required")
        self.assertEqual(result["cursor"], 0)
        self.assertEqual(result["total_steps"], 0)

    def test_cli_local_waiting_and_fresh_process_replay_preserve_ledger(self):
        case = self._build_case("local")
        manifest = self.root / "advance.json"
        manifest.write_text(json.dumps(ADVANCE), encoding="utf-8")
        before = (case / "organon.json").read_bytes()
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
        responses = []
        for _ in range(2):
            process = subprocess.run(
                [sys.executable, "-B", "-m", "specorganon.cli", "run", str(case),
                 "--manifest", str(manifest), "--actor", AUTHOR],
                cwd=self.root, env=env, capture_output=True, text=True, timeout=15, check=False)
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(process.stderr, "")
            responses.append(json.loads(process.stdout))
        self.assertEqual((case / "organon.json").read_bytes(), before)
        self.assertEqual(responses[0], responses[1])
        self.assertEqual(responses[0]["reason"], "local_test_execution_required")

    def test_signed_missing_execution_retains_signed_reason_at_advance(self):
        case = self._build_case("signed")
        self._assert_wait(case, ADVANCE, "signed_test_execution_required")

    def test_signed_failed_execution_retains_signed_reason_when_exhausted(self):
        case = self._build_case("signed", signed_report=True)
        self._assert_wait(case, EXHAUSTED, "signed_test_execution_required")
        self.assertEqual(engine.get_state(case)["items"]["t1"]["test_execution_status"], "signed_failed")

    def test_local_repair_still_requires_separate_phase_review(self):
        case = self._build_case("local")
        failed = engine.get_state(case)["items"]["t1"]
        engine.put_item(case, "t1", "test", failed["text"], list(failed["deps"]),
                        self._execution(0), AUTHOR, expected_version=1, expected_deps=failed["deps"])
        before = (case / "organon.json").read_bytes()
        result = runner.run_manifest(case, ADVANCE, AUTHOR)
        self.assertEqual(result["reason"], "independent_review_required")
        self.assertEqual(result["next"]["action"], "review_phase")
        self.assertEqual(result["applied"], 0)
        self.assertEqual((case / "organon.json").read_bytes(), before)
        self.assertFalse(engine.gate(case, "build")["accepted"])


if __name__ == "__main__":
    unittest.main()
