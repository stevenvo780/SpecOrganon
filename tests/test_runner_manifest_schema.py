"""Manifest schema boundary checks with explicitly synthetic ledger content.

The documented schema is JSON numeric version 1. Keep equivalent numeric JSON
spellings compatible while rejecting Booleans, which Python compares to ints.
These tests use real temporary cases and CLI processes, without approvals,
signing keys, installs, test execution receipts, or an MCP server.
"""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from specorganon import engine, runner


SOURCE_ROOT = Path(runner.__file__).resolve().parents[1]
OWNER = "human:schema-test-owner"
AUTHOR = "agent:schema-test-author"
SCHEMA_ERROR = "manifest needs schema 1 and a steps array"
PUT = {"op": "put", "id": "p1", "kind": "problem",
       "text": "Synthetic manifest schema test data", "refs": [], "data": {}}


class RunnerManifestSchemaTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="specorganon-manifest-schema-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.case_number = 0
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith("ORGANON_")}
        clean_environment = patch.dict(os.environ, environment, clear=True)
        clean_environment.start()
        self.addCleanup(clean_environment.stop)

    def _case(self, policy="local"):
        self.case_number += 1
        case = self.root / f"case-{self.case_number}"
        engine.create_case(case, "Synthetic schema boundary test", "test data", OWNER,
                           approval_policy=policy)
        engine.put_item(case, "p0", "problem", "Synthetic existing checkpoint",
                        [], {}, AUTHOR)
        return case

    def _manifest(self, schema):
        return {"schema": schema, "steps": [copy.deepcopy(PUT)]}

    def _snapshot(self, case):
        return (case / "organon.json").read_bytes(), engine.get_state(case)

    def _assert_unchanged(self, case, before):
        ledger, state = self._snapshot(case)
        self.assertEqual(ledger, before[0])
        self.assertEqual(state, before[1])
        self.assertEqual(set(state["items"]), {"p0"})
        self.assertTrue(all(not phase["accepted"] for phase in state["phases"].values()))

    def _cli(self, case, manifest_json):
        manifest_file = self.root / "manifest.json"
        manifest_file.write_text(manifest_json, encoding="utf-8")
        env = {**os.environ, "PYTHONPATH": str(SOURCE_ROOT), "PYTHONDONTWRITEBYTECODE": "1"}
        return subprocess.run(
            [sys.executable, "-B", "-W", "error::ResourceWarning", "-m", "specorganon.cli",
             "run", str(case), "--manifest", str(manifest_file), "--actor", AUTHOR],
            cwd=self.root, env=env, capture_output=True, text=True, timeout=15, check=False)

    def _json_with_schema(self, token):
        return '{"schema": ' + token + ', "steps": ' + json.dumps([PUT]) + '}'

    def test_true_is_rejected_before_any_write_for_both_policies(self):
        for policy in ("local", "signed"):
            with self.subTest(policy=policy):
                case = self._case(policy)
                before = self._snapshot(case)
                with self.assertRaisesRegex(runner.ManifestError, SCHEMA_ERROR):
                    runner.run_manifest(case, self._manifest(True), AUTHOR)
                self._assert_unchanged(case, before)
                self.assertFalse((case / ".organon.runner.lock").exists())

    def test_cli_true_is_rejected_before_any_write_for_both_policies(self):
        for policy in ("local", "signed"):
            with self.subTest(policy=policy):
                case = self._case(policy)
                before = self._snapshot(case)
                result = self._cli(case, self._json_with_schema("true"))
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr, f"organon: {SCHEMA_ERROR}\n")
                self._assert_unchanged(case, before)
                self.assertFalse((case / ".organon.runner.lock").exists())

    def test_other_invalid_schema_values_and_shapes_preserve_ledger(self):
        values = [False, None, "1", "1.0", [], {}, 0, -1, 2, 1.5,
                  float("nan"), float("inf"), float("-inf")]
        manifests = [self._manifest(value) for value in values]
        manifests += [{"steps": [PUT]}, {"schema": 1}, {"schema": 1, "steps": {}},
                      None, [], 1, True]
        for manifest in manifests:
            with self.subTest(manifest=manifest):
                case = self._case()
                before = self._snapshot(case)
                with self.assertRaisesRegex(runner.ManifestError, SCHEMA_ERROR):
                    runner.run_manifest(case, manifest, AUTHOR)
                self._assert_unchanged(case, before)
                self.assertFalse((case / ".organon.runner.lock").exists())

    def test_cli_other_invalid_schema_values_preserve_ledger(self):
        for token in ("false", "null", '"1"', '"1.0"', "[]", "{}", "0", "-1", "2", "1.5"):
            with self.subTest(token=token):
                case = self._case()
                before = self._snapshot(case)
                result = self._cli(case, self._json_with_schema(token))
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr, f"organon: {SCHEMA_ERROR}\n")
                self._assert_unchanged(case, before)

    def test_numeric_version_one_applies_and_replays_without_mutation(self):
        for policy in ("local", "signed"):
            for schema in (1, 1.0):
                with self.subTest(policy=policy, schema=schema, type=type(schema).__name__):
                    case = self._case(policy)
                    manifest = self._manifest(schema)
                    original_manifest = copy.deepcopy(manifest)
                    before = self._snapshot(case)
                    result = runner.run_manifest(case, manifest, AUTHOR)
                    self.assertEqual(result["applied"], 1)
                    self.assertEqual(result["skipped"], 0)
                    after = self._snapshot(case)
                    self.assertEqual(after[1]["revision"], before[1]["revision"] + 1)
                    self.assertEqual(set(after[1]["items"]), {"p0", "p1"})
                    self.assertEqual(after[1]["items"]["p1"]["version"], 1)
                    self.assertEqual(after[1]["project"]["approval_policy"], policy)
                    self.assertEqual(manifest, original_manifest)
                    for compatible_schema in (1, 1.0):
                        replay = runner.run_manifest(case, self._manifest(compatible_schema), AUTHOR)
                        self.assertEqual(replay["applied"], 0)
                        self.assertEqual(replay["skipped"], 1)
                        self.assertEqual(self._snapshot(case), after)
                    self.assertTrue(all(not phase["accepted"]
                                        for phase in after[1]["phases"].values()))

    def test_cli_numeric_version_spellings_apply_and_replay(self):
        for policy in ("local", "signed"):
            for token in ("1", "1.0", "1e0", "10e-1"):
                with self.subTest(policy=policy, token=token):
                    case = self._case(policy)
                    before = self._snapshot(case)
                    first = self._cli(case, self._json_with_schema(token))
                    self.assertEqual(first.returncode, 0, first.stderr)
                    self.assertEqual(first.stderr, "")
                    self.assertEqual(json.loads(first.stdout)["applied"], 1)
                    after = self._snapshot(case)
                    self.assertEqual(after[1]["revision"], before[1]["revision"] + 1)
                    self.assertEqual(set(after[1]["items"]), {"p0", "p1"})
                    replay = self._cli(case, self._json_with_schema("1"))
                    self.assertEqual(replay.returncode, 0, replay.stderr)
                    self.assertEqual(replay.stderr, "")
                    self.assertEqual(json.loads(replay.stdout)["applied"], 0)
                    self.assertEqual(json.loads(replay.stdout)["skipped"], 1)
                    self.assertEqual(self._snapshot(case), after)


if __name__ == "__main__":
    unittest.main()
