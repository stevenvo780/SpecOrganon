"""Recheck the documentary bread frame through the installed CLI and MCP client.

This verifies local bytes and interface behavior. It does not authenticate
published measurements, a human approver, or a field intervention.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

from mcp.client import Client
from mcp.client.stdio import StdioServerParameters


ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "cases" / "bread_norway"
CLI = Path(sys.executable).parent / "organon"
MCP = Path(sys.executable).parent / "organon-mcp"
SOURCE_PDFS = {
    "source_lca.pdf": (2_212_666, "9d64c0538b76ebaa19af86fb7ec231243cb5e1272316105ad979cfb9b6de3a32"),
    "source_survey.pdf": (526_604, "61b3b63cc7b5748138335fa2eaebde2f4ab0e454750e4592582fb80a5043dcee"),
}
SOURCE_DOI = {
    "source_lca.pdf": "https://doi.org/10.3390/su11010043",
    "source_survey.pdf": "https://doi.org/10.3390/su10072251",
}
# Identity and meaning are fixed independently of the manifest/ledger. The PDF
# passage used for extraction is reported separately: two historic locator
# labels additionally mention Table 1, which does not itself contain the number.
SOURCE_CLAIMS = {
    "e_product_mass": ("source_lca.pdf", "secciones 3.2.1 y 4.2; tabla 1", "piece_mass", "g/pieza", "section 4.2 paragraph"),
    "e_wheat_origin": ("source_lca.pdf", "sección 4.3 y tabla 1", "norway_wheat_share", "%", "section 4.3 paragraph"),
    "e_mill_energy": ("source_lca.pdf", "tabla 2", "mill_electricity", "kWh/t_harina", "Table 2 mill energy row"),
    "e_mill_bran": ("source_lca.pdf", "tabla 3, balance másico de productos del trigo", "wheat_bran_output", "%", "Table 3 wheat flour row"),
    "e_mill_transport": ("source_lca.pdf", "tabla 5", "mill_to_baker_distance", "km", "Table 5 transport row"),
    "e_baker_energy": ("source_lca.pdf", "tabla 5", "bakery_electricity", "kWh/pieza", "Table 5 baker energy row"),
    "e_retail_waste": ("source_lca.pdf", "tabla 7, retail waste", "retail_bread_waste", "%_pan_entrante_sistema", "Table 7 retail waste row"),
    "e_household_est": ("source_lca.pdf", "tabla 7, consumer waste y nota de fuente", "consumer_bread_waste_estimate", "%_pan_entrante_sistema", "Table 7 consumer waste row and source note"),
    "e_survey_size": ("source_survey.pdf", "resumen y sección 3", "survey_respondents", "personas", "abstract and Table 1 total row"),
}


class SourceCheckError(ValueError):
    """A bread evidence claim is unsupported by its pinned PDF passage."""


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _section(text: str, start: str, end: str) -> str:
    if text.count(start) != 1:
        raise SourceCheckError(f"PDF locator not unique: {start}")
    tail = text.split(start, 1)[1]
    if end not in tail:
        raise SourceCheckError(f"PDF locator missing: {end}")
    return tail.split(end, 1)[0]


def _number(text: str, pattern: str) -> Decimal:
    matches = re.findall(pattern, text, flags=re.MULTILINE)
    if len(matches) != 1:
        raise SourceCheckError(f"PDF numeric locator yielded {len(matches)} matches: {pattern}")
    return Decimal(matches[0])


def published_evidence_values(case: Path) -> dict[str, Decimal]:
    """Extract the nine claimed numbers from anchored passages in the fixed PDFs.

    Poppler's ``pdftotext`` is required. These are published aggregates and
    estimates, not a reconstruction of the underlying company or survey data.
    """
    texts = {}
    for archive, (size, expected_sha256) in SOURCE_PDFS.items():
        path = case / archive
        if path.stat().st_size != size:
            raise SourceCheckError(f"archived PDF size changed: {archive}")
        if digest(path) != expected_sha256:
            raise SourceCheckError(f"archived PDF SHA-256 changed: {archive}")
        try:
            result = subprocess.run(
                ["pdftotext", "-layout", str(path), "-"],
                text=True,
                capture_output=True,
                check=True,
                timeout=20,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("Poppler pdftotext is required for the bread PDF content check") from exc
        if len(result.stdout) >= 2_000_000:
            raise SourceCheckError(f"extracted PDF text too large: {archive}")
        texts[archive] = result.stdout

    lca = texts["source_lca.pdf"]
    survey = texts["source_survey.pdf"]
    composition = _section(lca, "4.2. Composition of Bread", "4.3. Cultivation")
    cultivation = _section(lca, "4.3. Cultivation and Transport", "4.4. Processing")
    mill = _section(lca, "Table 2. Processing data.", "Table 3. Data for allocation")
    flour = _section(lca, "Table 3. Data for allocation", "4.5. Packaging")
    bakery = _section(lca, "Table 5. Data on bread production", "4.7. Retail")
    waste = _section(lca, "Table 7. Data on bread waste", "4.10. Waste Management")
    abstract = _section(survey, "Abstract:", "Keywords:")
    survey_table = _section(survey, "Table 1. Frequency distribution", "The data was analyzed")

    values = {
        "e_product_mass": _number(composition, r"total mass of the bread itself was\s+(\d+)\s+grams"),
        "e_wheat_origin": _number(cultivation, r"average of\s+(\d+)% of the wheat has been coming from Norway"),
        "e_mill_energy": _number(mill, r"Mill energy consumption\s+(\d+) kWh electricity per ton of flour"),
        "e_mill_bran": _number(flour, r"Wheat flour products \(% w/w\).*?\b(\d+\.\d+)% bran\."),
        "e_mill_transport": _number(bakery, r"Transport from mill to baker\s+(\d+) km on >32 tonne truck"),
        "e_baker_energy": _number(bakery, r"Baker energy consumption\s+(\d+\.\d+) kWh electricity and"),
        "e_retail_waste": _number(waste, r"^\s*Retail waste\s+(\d+\.\d+)\s+"),
        "e_household_est": _number(waste, r"^\s*Consumer waste\s+(\d+\.\d+)\s*$"),
        "e_survey_size": _number(abstract, r"web-based questionnaire has been employed, with\s+(\d+) respondents"),
    }
    if values["e_survey_size"] != _number(survey_table, r"^\s*Total\s+(\d+)\s+100\.0\s*$"):
        raise SourceCheckError("survey abstract and Table 1 respondent totals differ")
    if "Calculated from consumption data in Reference" not in waste:
        raise SourceCheckError("consumer waste source note missing")
    return values


def verify_source_transcription(manifest: dict, ledger: dict, case: Path) -> dict[str, Decimal]:
    """Reject a false numeric transcription even if manifest and ledger agree."""
    published = published_evidence_values(case)
    manifest_items = {
        step["id"]: step for step in manifest["steps"]
        if step["op"] == "put" and step["kind"] == "evidence"
    }
    ledger_items = {
        event["payload"]["id"]: event["payload"] for event in ledger["events"]
        if event["kind"] == "item_put" and event["payload"]["kind"] == "evidence"
    }
    if len(manifest_items) != len(ledger_items) or manifest_items.keys() != ledger_items.keys():
        raise SourceCheckError("manifest/ledger evidence sets differ")
    if manifest_items.keys() != published.keys() or published.keys() != SOURCE_CLAIMS.keys():
        raise SourceCheckError("evidence ID set differs from pinned PDF claims")
    for evidence_id, value in published.items():
        manifest_data = manifest_items[evidence_id]["data"]
        ledger_data = ledger_items[evidence_id]["data"]
        if manifest_data != ledger_data:
            raise SourceCheckError(f"manifest/ledger evidence differs: {evidence_id}")
        archive, locator, metric_key, unit, _ = SOURCE_CLAIMS[evidence_id]
        if (
            manifest_data["archive"], manifest_data["locator"],
            manifest_data["metric_key"], manifest_data["unit"],
        ) != (archive, locator, metric_key, unit):
            raise SourceCheckError(f"PDF claim identity differs: {evidence_id}")
        if manifest_data["source"] != SOURCE_DOI[archive]:
            raise SourceCheckError(f"PDF DOI differs: {evidence_id}")
        if manifest_data["source_sha256"] != SOURCE_PDFS[archive][1]:
            raise SourceCheckError(f"PDF digest differs: {evidence_id}")
        if type(manifest_data["value"]) not in (int, float) or Decimal(str(manifest_data["value"])) != value:
            raise SourceCheckError(f"published PDF value differs from manifest/ledger: {evidence_id}")
    return published


def cli(*args: str) -> dict:
    result = subprocess.run([str(CLI), *args], text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


def tool_data(result) -> dict:
    assert not result.is_error, result.content
    if result.structured_content is not None:
        return result.structured_content
    assert len(result.content) == 1
    return json.loads(result.content[0].text)


async def check_mcp(manifest: dict, cli_views: dict, original_hash: str) -> dict:
    environment = os.environ.copy()
    environment["ORGANON_ROOT"] = str(CASE.parent)
    params = StdioServerParameters(command=str(MCP), cwd=str(ROOT), env=environment)
    checked: list[str] = []
    async with Client(params, mode="legacy") as client:
        discovered = {tool.name for tool in (await client.list_tools()).tools}
        assert {"status", "gate", "trace", "next_task", "run"} <= discovered
        for name, arguments in (
            ("status", {"path": CASE.name}),
            ("gate_frame", {"path": CASE.name, "phase": "frame"}),
            ("gate_critique", {"path": CASE.name, "phase": "critique"}),
            ("trace", {"path": CASE.name, "id": "n_bread_harm"}),
            ("next_task", {"path": CASE.name}),
        ):
            tool = "gate" if name.startswith("gate_") else name
            assert tool_data(await client.call_tool(tool, arguments)) == cli_views[name]
            checked.append(name)
        replay = tool_data(await client.call_tool(
            "run", {"path": CASE.name, "manifest": manifest, "actor": "agent:analyst"}
        ))
        assert replay["applied"] == 0 and replay["skipped"] == 20
        assert replay["reason"] == "human_approval_required"
        assert digest(CASE / "organon.json") == original_hash
        checked.append("idempotent_run")

        invalid = await client.call_tool(
            "run", {"path": CASE.name, "manifest": {"schema": 1, "steps": [
                {"op": "approve", "id": "n_bread_harm"}
            ]}, "actor": "agent:analyst"}
        )
        assert invalid.is_error
        assert digest(CASE / "organon.json") == original_hash
        checked.append("invalid_run_no_mutation")
    return {"discovered_tools": len(discovered), "parity_checks": checked}


def main() -> None:
    manifest_path = CASE / "frame_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    put_steps = [step for step in manifest["steps"] if step["op"] == "put"]
    evidence = [step for step in put_steps if step["kind"] == "evidence"]
    assert len(manifest["steps"]) == 20 and len(put_steps) == 19 and len(evidence) == 9
    source_hashes: dict[str, str] = {}
    for step in evidence:
        archive = step["data"]["archive"]
        observed = digest(CASE / archive)
        assert observed == step["data"]["source_sha256"]
        source_hashes[archive] = observed

    ledger_path = CASE / "organon.json"
    original_hash = digest(ledger_path)
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    published = verify_source_transcription(manifest, ledger, CASE)
    events = Counter(event["kind"] for event in ledger["events"])
    assert events == {"item_put": 19, "phase_review": 1, "phase_advance": 1}
    review = next(event for event in ledger["events"] if event["kind"] == "phase_review")
    assert review["actor"] == "agent:independent_reviewer"
    assert review["payload"]["phase"] == "frame"
    assert review["payload"]["verdict"] == "accept" and review["payload"]["independent"]

    path = str(CASE)
    cli_views = {
        "status": cli("status", path),
        "gate_frame": cli("gate", path, "frame"),
        "gate_critique": cli("gate", path, "critique"),
        "trace": cli("trace", path, "n_bread_harm"),
        "next_task": cli("next-task", path),
    }
    status = cli_views["status"]
    assert status["revision"] == 21 and status["project"]["approval_policy"] == "signed"
    assert status["phases"]["frame"]["accepted"]
    assert status["phases"]["frame"]["independent_review"]
    assert not status["phases"]["critique"]["ready"]
    assert "n_bread_harm requires a verified human approval" in status["phases"]["critique"]["blockers"]
    assert cli_views["next_task"]["action"] == "human_approval"
    assert cli_views["next_task"]["approval_targets"] == [{"id": "n_bread_harm", "version": 1}]
    mcp = asyncio.run(check_mcp(manifest, cli_views, original_hash))
    replay = cli("run", path, "--manifest", str(manifest_path), "--actor", "agent:analyst")
    assert replay["applied"] == 0 and replay["skipped"] == 20
    assert replay["reason"] == "human_approval_required" and digest(ledger_path) == original_hash

    report = {
        "schema": 1,
        "case": "cases/bread_norway",
        "scope": "documentary_development_frame_only",
        "source_sha256": dict(sorted(source_hashes.items())),
        "source_content_check": {
            "method": "pdftotext -layout, fixed PDF SHA-256, anchored passage or table row",
            "values": {key: str(value) for key, value in sorted(published.items())},
            "verified_pdf_locations": {key: claim[4] for key, claim in sorted(SOURCE_CLAIMS.items())},
            "scope": "nine published numbers only; no raw records or field impact verified",
            "dependency": "Poppler pdftotext; text layout may vary by version and ambiguous extraction fails",
        },
        "manifest_sha256": digest(manifest_path),
        "ledger_sha256": original_hash,
        "ledger_revision": status["revision"],
        "events": dict(sorted(events.items())),
        "frame_accepted": status["phases"]["frame"]["accepted"],
        "independent_review_recorded": status["phases"]["frame"]["independent_review"],
        "review_actor_is_unverified_label": review["actor"],
        "critique_blockers": status["phases"]["critique"]["blockers"],
        "approval_trust": status["approval_trust"],
        "next_action": cli_views["next_task"]["action"],
        "cli_replay_skipped": replay["skipped"],
        "mcp": mcp,
        "criterion_3": "not_assessed",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
