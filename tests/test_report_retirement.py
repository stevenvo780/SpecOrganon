"""Read-only retirement dossiers from explicitly synthetic mechanics cases.

All owner approvals and review judgments are invented test inputs, including
those using local policy. They are not real human or external-agent acceptance.
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

from specorganon import engine, report


ROOT = Path(__file__).resolve().parents[1]
AUTHOR = "agent:test-author"
REVIEWER = "agent:test-reviewer"
OWNER = "human:test-owner"


def _section(markdown, item_id):
    return markdown.split(f"### {item_id} · ", 1)[1].split("\n### ", 1)[0].split("\n## ", 1)[0]


class ReportRetirementTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="specorganon-retirement-report-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        environment = {key: value for key, value in os.environ.items() if not key.startswith("ORGANON_")}
        isolated = patch.dict(os.environ, environment, clear=True)
        isolated.start()
        self.addCleanup(isolated.stop)

    def _case(self, policy="local"):
        if policy == "fixture":
            os.environ["ORGANON_ALLOW_FIXTURES"] = "1"
        case = self.root / policy
        owner = "human:fixture" if policy == "fixture" else OWNER
        engine.create_case(case, "Synthetic retirement report", "test data", owner,
                           approval_policy=policy)
        manifest = json.loads((ROOT / "workflows/synthetic_full.json").read_text(encoding="utf-8"))
        for step in manifest["steps"]:
            if step.get("phase") == "study":
                break
            if step["op"] != "put":
                continue
            data = copy.deepcopy(step["data"])
            if step["id"] == "e0":
                data.update(metric_key="count", scope="synthetic test data", unit="count", value=10)
            engine.put_item(case, step["id"], step["kind"], step["text"], step["refs"], data, AUTHOR)
        engine.approve(case, "n1", "Invented owner approval for mechanics only", owner)
        item = engine.get_state(case)["items"]["i1"]
        engine.put_item(case, "i2", "indicator", "Synthetic replacement indicator",
                        list(item["deps"]), item["data"], AUTHOR)
        return case

    def _retire(self, case, reason="Synthetic retirement only", actor=AUTHOR, replacements=None):
        rejected = engine.review_item(case, "i1", "reject", "Invented negative review only", REVIEWER)
        event = engine.retire_indicator(case, "i1", replacements or {"i2": 1}, reason, actor,
                                        expected_version=1, expected_review_seq=rejected["seq"])
        return event, rejected

    def _revise(self, case, item_id):
        item = engine.get_state(case)["items"][item_id]
        return engine.put_item(case, item_id, item["kind"], item["text"] + " Revised test data.",
                               list(item["deps"]), item["data"], AUTHOR,
                               expected_version=item["version"], expected_deps=item["deps"])

    def _read(self, case):
        ledger = case / "organon.json"
        before = ledger.read_bytes()
        state = engine.get_state(case)
        result = report.case_report(case)
        self.assertEqual(ledger.read_bytes(), before)
        self.assertEqual(engine.get_state(case), state)
        self.assertEqual(result["revision"], state["revision"])
        self.assertEqual(result["artifact_count"], len(state["items"]))
        self.assertEqual(result["next"], report.describe_task(state))
        return result, state

    def test_effective_retirement_keeps_rejection_and_exact_declaration(self):
        for policy in ("local", "fixture"):
            with self.subTest(policy=policy):
                case = self._case(policy)
                event, rejected = self._retire(case)
                result, state = self._read(case)
                self.assertTrue(state["items"]["i1"]["retired"])
                section = _section(result["markdown"], "i1")
                self.assertIn("Retirada: efectiva (effective). Retirado actualmente: sí.", section)
                self.assertIn(f"Declaración de retirada #{event['seq']}: i1 v1; vigente: sí.", section)
                self.assertIn(f"Revisión negativa vinculada: #{rejected['seq']}.", section)
                self.assertIn("Reemplazos declarados: i2 v1.", section)
                self.assertIn("Autor de la retirada: agent:test\\-author.", section)
                self.assertIn("Motivo: Synthetic retirement only", section)
                self.assertIn("latest item review rejected this version", section)
                self.assertIn("no acredita aprobación ni validez empírica", section)
                self.assertNotIn("Aprobación vigente: sí", section)
                self.assertIn("### i2 · indicator · v1", result["markdown"])

    def test_changed_replacement_invalidates_without_rewriting_recorded_version(self):
        case = self._case()
        event, _ = self._retire(case)
        self._revise(case, "i2")
        result, state = self._read(case)
        self.assertFalse(state["items"]["i1"]["retired"])
        self.assertEqual(state["items"]["i1"]["retirement_status"], "invalidated")
        section = _section(result["markdown"], "i1")
        self.assertIn("Retirada: invalidada (invalidated). Retirado actualmente: no.", section)
        self.assertIn(f"Declaración de retirada #{event['seq']}: i1 v1; vigente: no.", section)
        self.assertIn("Reemplazos declarados: i2 v1.", section)
        self.assertNotIn("Reemplazos declarados: i2 v2.", section)
        self.assertIn("replacement i2 is not an indicator at its declared current version", section)
        self.assertIn("latest item review rejected this version", section)
        self.assertIn("### i2 · indicator · v2", result["markdown"])

    def test_changed_source_supersedes_retirement_of_previous_version(self):
        case = self._case()
        event, _ = self._retire(case)
        self._revise(case, "i1")
        result, state = self._read(case)
        self.assertEqual(state["items"]["i1"]["retirement_status"], "superseded")
        section = _section(result["markdown"], "i1")
        self.assertTrue(section.startswith("indicator · v2"))
        self.assertIn("Retirada: superada (superseded). Retirado actualmente: no.", section)
        self.assertIn(f"Declaración de retirada #{event['seq']}: i1 v1; vigente: no.", section)
        self.assertIn("source indicator version changed", section)
        self.assertNotIn("latest item review rejected this version", section)

    def test_later_declaration_preserves_superseded_and_effective_history(self):
        case = self._case()
        first, _ = self._retire(case, "First synthetic retirement")
        self._revise(case, "i2")
        second, _ = self._retire(case, "Second synthetic retirement", replacements={"i2": 2})
        result, state = self._read(case)
        history = state["items"]["i1"]["retirement_history"]
        self.assertEqual([record["effective"] for record in history], [False, True])
        section = _section(result["markdown"], "i1")
        self.assertIn(f"Declaración de retirada #{first['seq']}: i1 v1; vigente: no.", section)
        self.assertIn(f"Declaración de retirada #{second['seq']}: i1 v1; vigente: sí.", section)
        self.assertLess(section.index("First synthetic retirement"), section.index("Second synthetic retirement"))
        self.assertIn("superseded by a later retirement declaration", section)
        self.assertIn("Reemplazos declarados: i2 v1.", section)
        self.assertIn("Reemplazos declarados: i2 v2.", section)
        self.assertIn("latest item review rejected this version", section)

    def test_changed_review_invalidates_retirement_and_keeps_linked_review(self):
        case = self._case()
        _, rejected = self._retire(case)
        engine.review_item(case, "i1", "accept", "Invented changed review only", REVIEWER)
        result, state = self._read(case)
        self.assertEqual(state["items"]["i1"]["retirement_status"], "invalidated")
        section = _section(result["markdown"], "i1")
        self.assertIn("Retirada: invalidada (invalidated). Retirado actualmente: no.", section)
        self.assertIn(f"Revisión negativa vinculada: #{rejected['seq']}.", section)
        self.assertIn("source needs its current independent negative review at the expected sequence", section)
        self.assertNotIn("- latest item review rejected this version", section)

    def test_changed_ancestor_displays_all_current_retirement_issues(self):
        case = self._case()
        self._retire(case)
        self._revise(case, "n1")
        result, state = self._read(case)
        item = state["items"]["i1"]
        self.assertEqual(item["retirement_status"], "invalidated")
        self.assertGreater(len(item["retirement_issues"]), 1)
        section = _section(result["markdown"], "i1")
        for issue in item["retirement_issues"]:
            self.assertIn(report._text(issue), section)
        self.assertIn("Sus dependencias cambiaron; requiere revisión.", section)

    def test_retirement_metadata_is_markdown_escaped_and_replacements_sorted(self):
        case = self._case()
        item = engine.get_state(case)["items"]["i2"]
        for item_id in ("i_3", "i-4"):
            engine.put_item(case, item_id, "indicator", "Synthetic extra replacement",
                            list(item["deps"]), item["data"], AUTHOR)
        reason = "Synthetic [link](https://example.invalid) <tag> `code` *only*\n# Heading"
        actor = "agent:[test]<actor>"
        self._retire(case, reason, actor, {"i_3": 1, "i-4": 1})
        result, _ = self._read(case)
        section = _section(result["markdown"], "i1")
        self.assertIn("Motivo: Synthetic \\[link\\]\\(https://example\\.invalid\\) \\<tag\\> \\`code\\` \\*only\\*\n\\# Heading", section)
        self.assertIn("Autor de la retirada: agent:\\[test\\]\\<actor\\>.", section)
        self.assertIn("Reemplazos declarados: i\\-4 v1, i\\_3 v1.", section)
        self.assertNotIn("[link](https://example.invalid)", section)
        self.assertNotIn("\n# Heading", section)

    def test_active_indicator_section_stays_unchanged(self):
        case = self._case()
        result, state = self._read(case)
        self.assertEqual(state["items"]["i1"]["retirement_status"], "none")
        self.assertEqual(_section(result["markdown"], "i1"),
                         "indicator · v1\n\nCount fixture units\\.\n\n"
                         "Autor: agent:test\\-author.\n\n"
                         "Depende de: e0 v1, n1 v1, p1 v1.\n\n"
                         '```json\n{\n  "metric": "count",\n  "unit": "count"\n}\n```\n')
        self.assertNotIn("Retirada:", result["markdown"])

    def test_report_uses_one_snapshot_without_mutating_it(self):
        case = self._case()
        self._retire(case)
        state = engine.get_state(case)
        original = copy.deepcopy(state)
        ledger = (case / "organon.json").read_bytes()
        with patch.object(report.engine, "get_state", return_value=state) as get_state:
            with patch.object(report, "describe_task", wraps=report.describe_task) as describe_task:
                result = report.case_report(case)
        get_state.assert_called_once_with(case)
        describe_task.assert_called_once()
        self.assertIs(describe_task.call_args.args[0], state)
        self.assertEqual(state, original)
        self.assertEqual((case / "organon.json").read_bytes(), ledger)
        self.assertEqual(result["revision"], state["revision"])

    def test_fresh_cli_reports_replay_each_lifecycle_without_ledger_writes(self):
        case = self._case()
        self._retire(case)
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(Path(engine.__file__).resolve().parents[1])
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        for status, changed_item in (("effective", None), ("invalidated", "i2"), ("superseded", "i1")):
            with self.subTest(status=status):
                if changed_item:
                    self._revise(case, changed_item)
                result, state = self._read(case)
                self.assertEqual(state["items"]["i1"]["retirement_status"], status)
                before = (case / "organon.json").read_bytes()
                for _ in range(2):
                    process = subprocess.run(
                        [sys.executable, "-B", "-c", "from specorganon.cli import main; main()",
                         "report", str(case), "--format", "markdown"],
                        env=environment, cwd=self.root, capture_output=True, text=True,
                        encoding="utf-8", check=False, timeout=20,
                    )
                    self.assertEqual(process.returncode, 0, process.stderr)
                    self.assertEqual(process.stderr, "")
                    self.assertEqual(process.stdout, result["markdown"])
                    self.assertIn(f"({status})", _section(process.stdout, "i1"))
                    self.assertEqual((case / "organon.json").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
