"""Literal report layout from synthetic labels, citations and review reasons.

The mechanical cases below are not real approvals, observations or identities.
No Markdown renderer is required: source-level fence/structure checks and CLI
roundtrips are complemented by separate renderer checks in the review evidence.
"""

from __future__ import annotations

import copy
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from specorganon import engine, report


TITLE = "Synthetic literature review\nCitation appendix\n================="
AUTHOR = "agent:synthetic\nReading group\n=============\tA"
NARRATIVE = (
    "Synthetic citation notes\n========================\n\n"
    "    Author (2026), p. 4 [draft].\n\n"
    "Two readings remain plausible.\n\n"
    "| Construct | Interpretation |\n| --- | --- |\n| agency | scope |"
)
REASON = (
    "Synthetic measurement rationale\n===============================\n\n"
    "    Baseline definition [draft]: retain the adverse observation.\n\n"
    "Quoted review label:\nRetirada: invalidada (invalidated).\n\n"
    "Review conclusion: pending independent evaluation."
)
LITERAL_BLOCK = re.compile(r"(?m)^(`{3,})(text|json)\n([\s\S]*?)\n\1(?=\n|$)")


def _text_blocks(markdown):
    return [match[3] for match in LITERAL_BLOCK.finditer(markdown) if match[2] == "text"]


def _outside_blocks(markdown):
    return LITERAL_BLOCK.sub("", markdown)


class ReportLayoutTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="specorganon-report-layout-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        environment = {key: value for key, value in os.environ.items() if not key.startswith("ORGANON_")}
        isolated = patch.dict(os.environ, environment, clear=True)
        isolated.start()
        self.addCleanup(isolated.stop)
        self.counter = 0

    def _case(self, *, title=TITLE, author=AUTHOR, narrative=NARRATIVE, reason=REASON):
        self.counter += 1
        case = self.root / f"case-{self.counter}"
        engine.create_case(case, title, "Synthetic mechanics only", "human:synthetic", approval_policy="local")
        engine.put_item(case, "p1", "problem", narrative, [], {}, author)
        nodes = [
            ("a1", "actor", ["p1"], {}), ("n1", "norm", ["p1", "a1"], {}),
            ("q1", "question", ["p1"], {}), ("h1", "hypothesis", ["q1"], {}),
            ("pr", "protocol", ["q1", "h1"], {
                "population": "synthetic", "method": "synthetic", "comparison": "synthetic",
                "uncertainty": "No observations",
            }),
            ("e1", "evidence", ["pr"], {
                "origin": "derived", "source": "synthetic", "date": "2026-10-03", "locator": "value",
                "metric_key": "count", "scope": "synthetic", "unit": "count", "value": 10,
            }),
            ("i1", "indicator", ["p1", "n1", "pr", "e1"], {"metric": "count", "unit": "count"}),
            ("i2", "indicator", ["p1", "n1", "pr", "e1"], {"metric": "count", "unit": "count"}),
        ]
        for key, kind, refs, data in nodes:
            engine.put_item(case, key, kind, "Synthetic " + key, refs, data, author)
        rejected = engine.review_item(case, "i1", "reject", "Synthetic negative judgment", "agent:independent")
        engine.retire_indicator(case, "i1", {"i2": 1}, reason, author,
                                expected_version=1, expected_review_seq=rejected["seq"])
        return case

    def _read(self, case):
        before = (case / "organon.json").read_bytes()
        state = engine.get_state(case)
        original = copy.deepcopy(state)
        with patch.object(report.engine, "get_state", return_value=state) as get_state:
            with patch.object(report, "describe_task", wraps=report.describe_task) as describe:
                result = report.case_report(case)
        get_state.assert_called_once_with(case)
        self.assertIs(describe.call_args.args[0], state)
        self.assertEqual(state, original)
        self.assertEqual((case / "organon.json").read_bytes(), before)
        self.assertEqual(result["next"], report.describe_task(state))
        self.assertEqual(result["title"], state["project"]["title"])
        self.assertEqual(result["revision"], state["revision"])
        self.assertEqual(result["accepted_phases"], 0)
        return result, state

    def test_multiline_title_and_author_stay_in_their_metadata_lines(self):
        result, _ = self._read(self._case())
        markdown = result["markdown"]
        self.assertEqual(markdown.splitlines()[0], "# " + report._text(json.dumps(TITLE, ensure_ascii=False)))
        author_line = "Autor: " + report._text(json.dumps(AUTHOR, ensure_ascii=False)) + "."
        self.assertEqual(markdown.splitlines().count(author_line), 9)
        self.assertIn("Autor de la retirada: " + report._text(json.dumps(AUTHOR, ensure_ascii=False)) + ".", markdown)
        outside = _outside_blocks(markdown)
        self.assertNotRegex(outside, r"(?m)^\s*=+\s*$")
        self.assertNotIn("\nReading group\n", outside)

    def test_narrative_and_reason_are_exact_literal_blocks(self):
        result, state = self._read(self._case())
        markdown = result["markdown"]
        self.assertEqual(_text_blocks(markdown), [NARRATIVE, REASON])
        self.assertEqual(state["items"]["p1"]["text"], NARRATIVE)
        self.assertEqual(state["items"]["i1"]["retirement_history"][0]["reason"], REASON)
        outside = _outside_blocks(markdown)
        self.assertNotIn("Synthetic citation notes", outside)
        self.assertNotIn("    Author", outside)
        self.assertNotIn("| Construct |", outside)
        self.assertNotIn("Retirada: invalidada", outside)
        self.assertIn("Retirada: efectiva (effective). Retirado actualmente: sí.", outside)
        self.assertIn("Aprobación vigente: pendiente.", outside)
        self.assertNotIn("Aprobación vigente: sí.", outside)
        self.assertEqual(len(re.findall(r"(?m)^# ", outside)), 1)
        self.assertEqual(len(re.findall(r"(?m)^## ", outside)), 4)
        self.assertEqual(len(re.findall(r"(?m)^### ", outside)), 9)
        self.assertEqual(len(re.findall(r"(?m)^\|", outside)), 11)

    def test_fence_lengths_preserve_backticks_tabs_paragraphs_and_unicode(self):
        narrative = "Literal citation 日本語\n\n\tAuthor *draft*\n\n```\n# Quoted heading\n``````\n| a | b |\n~~~\nLast paragraph"
        reason = "Revision á\n````````\n\n    retained citation [1]\n````\nClosing rationale"
        result, _ = self._read(self._case(narrative=narrative, reason=reason))
        self.assertEqual(_text_blocks(result["markdown"]), [narrative, reason])
        self.assertIn("```````text\n" + narrative + "\n```````", result["markdown"])
        self.assertIn("`````````text\n" + reason + "\n`````````", result["markdown"])
        self.assertNotIn("# Quoted heading", _outside_blocks(result["markdown"]))

    def test_line_endings_are_preserved_in_literal_content(self):
        for separator in ("\n", "\r\n", "\r"):
            with self.subTest(separator=repr(separator)):
                narrative = separator.join(("Citation", "===", "", "    Indented note"))
                reason = separator.join(("Synthetic rationale", "", "Tab\tand slash \\"))
                result, _ = self._read(self._case(title="Title" + separator + "Continuation",
                                                 narrative=narrative, reason=reason))
                self.assertEqual(_text_blocks(result["markdown"]), [narrative, reason])
                self.assertNotIn("\r", _outside_blocks(result["markdown"]))

    def test_multiline_blockers_and_item_issues_stay_in_single_list_items(self):
        case = self._case()
        state = engine.get_state(case)
        issue = "Synthetic issue\n\nInterpretation pending\n======================\n    citation [2]"
        state["items"]["i1"]["issues"].append(issue)
        state["items"]["i1"]["retirement_history"][0]["issues"].append(issue)
        task = report.describe_task(state)
        task["blockers"].append(issue)
        original = copy.deepcopy(state)
        with patch.object(report.engine, "get_state", return_value=state):
            with patch.object(report, "describe_task", return_value=task):
                result = report.case_report(case)
        expected = "- " + report._text(json.dumps(issue, ensure_ascii=False))
        self.assertEqual(result["markdown"].splitlines().count(expected), 3)
        self.assertNotIn("\nInterpretation pending\n", _outside_blocks(result["markdown"]))
        self.assertEqual(state, original)
        self.assertIn(issue, result["next"]["blockers"])

    def test_single_line_prose_and_json_fences_keep_existing_representation(self):
        result, _ = self._read(self._case(title="A *synthetic* title", author="agent:synthetic",
                                         narrative="Citation [draft] (2026).", reason="Synthetic reason [1]."))
        markdown = result["markdown"]
        self.assertTrue(markdown.startswith("# A \\*synthetic\\* title\n"))
        self.assertIn("\nCitation \\[draft\\] \\(2026\\)\\.\n", markdown)
        self.assertIn("\nAutor: agent:synthetic.\n", markdown)
        self.assertIn("\nMotivo: Synthetic reason \\[1\\]\\.\n", markdown)
        self.assertEqual(_text_blocks(markdown), [])
        blocks = [json.loads(match[3]) for match in LITERAL_BLOCK.finditer(markdown) if match[2] == "json"]
        self.assertEqual(len(blocks), 4)
        data = {"note": "````\nA [quoted] citation\n```"}
        block = report._json_block(data)
        self.assertTrue(block.startswith("`````json\n"))
        self.assertEqual(json.loads(next(LITERAL_BLOCK.finditer(block))[3]), data)

    def test_entity_notation_is_literal_in_prose_and_encoded_metadata(self):
        result, _ = self._read(self._case(title="Literal &copy;\nCitation appendix",
                                         author="agent:synthetic &amp;\nReading group",
                                         narrative="Literal &amp; notation.", reason="Synthetic reason."))
        markdown = result["markdown"]
        self.assertIn(r'Literal \&copy;\\nCitation appendix', markdown.splitlines()[0])
        self.assertIn("\nLiteral \\&amp; notation\\.\n", markdown)
        self.assertIn(r'agent:synthetic \&amp;\\nReading group', markdown)

    def test_fresh_cli_markdown_and_json_match_without_ledger_writes(self):
        case = self._case()
        result, _ = self._read(case)
        before = (case / "organon.json").read_bytes()
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(Path(engine.__file__).resolve().parents[1])
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        for format_name in ("markdown", "json"):
            with self.subTest(format=format_name):
                process = subprocess.run(
                    [sys.executable, "-B", "-c", "from specorganon.cli import main; main()",
                     "report", str(case), "--format", format_name],
                    env=environment, cwd=self.root, capture_output=True, text=True,
                    encoding="utf-8", check=False, timeout=20,
                )
                self.assertEqual(process.returncode, 0, process.stderr)
                self.assertEqual(process.stderr, "")
                self.assertEqual(process.stdout if format_name == "markdown" else json.loads(process.stdout),
                                 result["markdown"] if format_name == "markdown" else result)
                self.assertEqual((case / "organon.json").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
