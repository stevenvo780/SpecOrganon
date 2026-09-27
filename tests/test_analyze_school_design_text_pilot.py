"""Synthetic, byte-bound checks for the blinded school-design pilot analyzer."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SCRIPT = SCRIPTS / "analyze_school_design_text_pilot.py"
sys.path.insert(0, str(SCRIPTS))
from analyze_school_design_text_pilot import (  # noqa: E402
    PilotAnalysisError, _format_observations, analyze,
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write(path: Path, content: bytes | str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = content.encode() if isinstance(content, str) else content
    path.write_bytes(data)
    return _sha(data)


def _dump(path: Path, value: Any) -> None:
    _write(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def _load(path: Path) -> Any:
    return json.loads(path.read_text())


def _rating(opaque_id: str, quote: str, q: int = 70,
            incidents: list[str] | None = None) -> dict[str, Any]:
    base, extra = divmod(q, 5)
    return {
        "id": opaque_id,
        "components": [
            {
                "score": base + (index < extra),
                "reason": "This quoted passage supports a bounded design judgment.",
                "evidence_quote": quote,
            }
            for index in range(5)
        ],
        "Q": q,
        "critical_incidents": [
            {"code": code, "evidence_quote": quote} for code in (incidents or [])
        ],
    }


@pytest.fixture
def pilot(tmp_path: Path) -> dict[str, Any]:
    root = tmp_path / "repo"
    base = root / "experiments/development/synthetic_school_pilot"
    prompts = {"N": "prompt_n.md", "S": "prompt_s.md", "A-M": "prompt_am.md"}
    source_hashes = {
        "cases/synthetic/source.md": _write(root / "cases/synthetic/source.md", "Synthetic source facts.\n")
    }
    protocol_hashes = {
        "README.md": _write(base / "README.md", "Synthetic pilot.\n"),
        "common_task.md": _write(base / "common_task.md", "A common synthetic task.\n"),
        "rubric.md": _write(base / "rubric.md", "Five scores, each 0 to 20.\n"),
    }
    prompt_hashes = {}
    for arm, filename in prompts.items():
        prompt_hashes[arm] = _write(base / filename, f"Common task + {arm} instruction.\n")
        protocol_hashes[filename] = prompt_hashes[arm]
    blocks = [
        {"block": index, "route": f"synthetic/model-{index}",
         "model_family": f"family-{index}", "effort_variant": "fixed",
         "arm_order": order}
        for index, order in enumerate((
            ["N", "S", "A-M"], ["S", "A-M", "N"], ["A-M", "N", "S"]
        ), start=1)
    ]
    cells = [
        {"id": f"v2_b{block['block']}_{arm.lower().replace('-', '')}",
         "block": block["block"], "arm": arm, "prompt": prompts[arm]}
        for block in blocks for arm in block["arm_order"]
    ]
    original_routes = {block: f"synthetic/short-route-{block}" for block in (1, 2, 3)}
    original_cells = [
        {"id": "g38l_n" if index == 0 else cell["id"].removeprefix("v2_"),
         "block": cell["block"], "arm": cell["arm"], "prompt": cell["prompt"]}
        for index, cell in enumerate(cells)
    ]
    _dump(base / "frozen_matrix.json", {
        "schema": 1, "source_files": source_hashes, "protocol_files": protocol_hashes,
        "runner": {"access": "text", "timeout_seconds_per_call": 120},
        "models": [
            {"block": block, "requested_route": route}
            for block, route in original_routes.items()
        ],
        "cells": original_cells,
    })
    _dump(base / "outputs/g38l_n.json", {
        "schema": 1, "cell_id": "g38l_n", "block": 1, "arm": "N",
        "requested_route": original_routes[1], "access": "text",
        "timeout_seconds": 120, "prompt_file": "prompt_n.md",
        "prompt_sha256": prompt_hashes["N"], "result": "route_rejected",
        "model_response": None,
        "raw_error": f"Delegación fallida: Modelo no permitido: '{original_routes[1]}'.",
        "usage_receipt": None, "cost_receipt": None,
    })
    _dump(base / "revision_v2.json", {
        "schema": 1, "revision": 2,
        "reason": f"The bridge rejected {original_routes[1]} before any provider call.",
        "source_frozen_matrix": "frozen_matrix.json",
        "source_prompt_hashes": prompt_hashes,
        "rubric_sha256": protocol_hashes["rubric.md"],
        "runner": {"access": "text", "timeout_seconds_per_call": 120,
                   "effort_argument": None, "output_word_limit_requested": 900,
                   "max_v2_calls": 9},
        "blocks": blocks, "cells": cells,
    })

    payloads = []
    mapping = {}
    ratings_a = []
    ratings_b = []
    ids = {}
    for index, cell in enumerate(cells):
        cid = cell["id"]
        opaque_id = f"r_{index:010x}"
        ids[cid] = opaque_id
        quote = f"Synthetic evidence passage {index}."
        blind = f"## Situación\n\n{quote}\n\n## Propuesta\n\nPlan.\n\n## Comprobación\n\nCheck.\n"
        raw = blind.rstrip("\n") + "\n\n[cloud-offload provider=synthetic]"
        output = {
            "schema": 1, "cell_id": cid, "block": cell["block"],
            "arm": cell["arm"], "requested_route": blocks[cell["block"] - 1]["route"],
            "effort_argument": None, "access": "text", "timeout_seconds": 120,
            "prompt_file": cell["prompt"], "prompt_sha256": prompt_hashes[cell["arm"]],
            "result": "provider_response", "response_raw_text": raw,
        }
        _dump(base / f"v2/outputs/{cid}.json", output)
        blind_hash = _write(base / f"v2/blind/{opaque_id}.md", blind)
        payloads.append({
            "id": opaque_id, "file": f"{opaque_id}.md", "sha256": blind_hash,
            "word_count_whitespace": len(blind.split()),
            "word_limit_requested": 900, "word_limit_exceeded": False,
        })
        mapping[opaque_id] = {
            "cell_id": cid,
            "source_path": f"experiments/development/synthetic_school_pilot/v2/outputs/{cid}.json",
            "response_raw_sha256": _sha(raw.encode()), "blind_sha256": blind_hash,
        }
        ratings_a.append(_rating(opaque_id, quote))
        ratings_b.append(_rating(opaque_id, quote, 74))
    _dump(base / "v2/blind/manifest.json", {
        "schema": 1, "source_revision": "revision_v2.json",
        "transform": "take response_raw_text before first newline-newline-[cloud-offload provider= marker; "
                     "strip trailing newlines and append one newline",
        "payloads": payloads,
    })
    mapping_path = tmp_path / "mapping.json"
    ratings_a_path = tmp_path / "a.json"
    ratings_b_path = tmp_path / "b.json"
    ratings_c_path = tmp_path / "c.json"
    _dump(mapping_path, mapping)
    _dump(ratings_a_path, {"schema": 1, "judge": "A", "ratings": ratings_a})
    _dump(ratings_b_path, {"schema": 1, "judge": "B", "ratings": ratings_b})
    return {
        "base": base, "mapping_path": mapping_path,
        "ratings_a_path": ratings_a_path, "ratings_b_path": ratings_b_path,
        "ratings_c_path": ratings_c_path, "ids": ids, "cells": cells,
    }


def _analyze(pilot: dict[str, Any], *, third: bool = False) -> dict[str, Any]:
    return analyze(
        pilot["base"], pilot["mapping_path"], pilot["ratings_a_path"],
        pilot["ratings_b_path"], pilot["ratings_c_path"] if third else None,
    )


def test_complete_positive_case_and_cli_stdout(pilot: dict[str, Any]) -> None:
    result = _analyze(pilot)
    assert result["coverage"]["response_count"] == 9
    assert result["coverage"]["aggregate_Q_count"] == 9
    assert result["coverage"]["completed_pair_count"] == 6
    assert {pair["Q_difference"] for pair in result["paired_differences"]} == {0.0}
    assert all(cell["aggregate_Q"] == 72 for cell in result["cells"])
    assert "prior_route_rejection" in result["evidence_sha256"]
    assert "not a conforming execution of v1" in result["protocol_deviations"][0]
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--base", str(pilot["base"]),
         "--mapping", str(pilot["mapping_path"]),
         "--ratings-a", str(pilot["ratings_a_path"]),
         "--ratings-b", str(pilot["ratings_b_path"])],
        check=True, capture_output=True, text=True,
    )
    assert json.loads(completed.stdout)["coverage"]["completed_pair_count"] == 6
    assert not completed.stderr


@pytest.mark.parametrize("change", ["missing", "wrong_result", "wrong_route"])
def test_prior_rejection_is_required_and_bound(pilot: dict[str, Any], change: str) -> None:
    path = pilot["base"] / "outputs/g38l_n.json"
    if change == "missing":
        path.unlink()
        expected = "cannot read"
    else:
        record = _load(path)
        record["result" if change == "wrong_result" else "requested_route"] = "provider_response"
        _dump(path, record)
        expected = "prior route rejection.*does not match frozen matrix"
    with pytest.raises(PilotAnalysisError, match=expected):
        _analyze(pilot)


@pytest.mark.parametrize("bad_link", ["duplicate", "wrong_source"])
def test_mapping_rejects_duplicate_or_wrongly_bound_cell(pilot: dict[str, Any], bad_link: str) -> None:
    mapping = _load(pilot["mapping_path"])
    first, second = list(mapping)[:2]
    if bad_link == "duplicate":
        mapping[second]["cell_id"] = mapping[first]["cell_id"]
    else:
        mapping[first]["source_path"] = mapping[second]["source_path"]
    _dump(pilot["mapping_path"], mapping)
    with pytest.raises(PilotAnalysisError, match="duplicated cell|source_path does not bind"):
        _analyze(pilot)


def test_changed_raw_hash_or_source_hash_is_rejected(pilot: dict[str, Any]) -> None:
    mapping = _load(pilot["mapping_path"])
    first = next(iter(mapping))
    mapping[first]["response_raw_sha256"] = "0" * 64
    _dump(pilot["mapping_path"], mapping)
    with pytest.raises(PilotAnalysisError, match="raw response hash mismatch"):
        _analyze(pilot)

    original = _load(pilot["mapping_path"])
    cid = original[first]["cell_id"]
    raw = _load(pilot["base"] / f"v2/outputs/{cid}.json")["response_raw_text"]
    original[first]["response_raw_sha256"] = _sha(raw.encode())
    _dump(pilot["mapping_path"], original)
    _write(pilot["base"].parents[2] / "cases/synthetic/source.md", "Changed source.\n")
    with pytest.raises(PilotAnalysisError, match="source_files.*hash mismatch"):
        _analyze(pilot)


def test_blind_text_must_derive_from_raw_even_if_rehashed(pilot: dict[str, Any]) -> None:
    manifest_path = pilot["base"] / "v2/blind/manifest.json"
    manifest = _load(manifest_path)
    row = manifest["payloads"][0]
    blind_path = pilot["base"] / "v2/blind" / row["file"]
    changed = blind_path.read_text().replace("Plan.", "A different plan.")
    row["sha256"] = _write(blind_path, changed)
    row["word_count_whitespace"] = len(changed.split())
    _dump(manifest_path, manifest)
    mapping = _load(pilot["mapping_path"])
    mapping[row["id"]]["blind_sha256"] = row["sha256"]
    _dump(pilot["mapping_path"], mapping)
    with pytest.raises(PilotAnalysisError, match="does not derive from output"):
        _analyze(pilot)


def test_wrong_q_sum_and_fabricated_quote_are_rejected(pilot: dict[str, Any]) -> None:
    judge = _load(pilot["ratings_a_path"])
    judge["ratings"][0]["Q"] += 1
    _dump(pilot["ratings_a_path"], judge)
    with pytest.raises(PilotAnalysisError, match="five-component sum"):
        _analyze(pilot)

    judge["ratings"][0]["Q"] -= 1
    judge["ratings"][0]["components"][0]["evidence_quote"] = "This text never appeared."
    _dump(pilot["ratings_a_path"], judge)
    with pytest.raises(PilotAnalysisError, match="not in blind payload"):
        _analyze(pilot)


def test_arbitration_pending_and_third_median(pilot: dict[str, Any]) -> None:
    judge_b = _load(pilot["ratings_b_path"])
    row = judge_b["ratings"][0]
    row.update(_rating(row["id"], row["components"][0]["evidence_quote"], 88))
    _dump(pilot["ratings_b_path"], judge_b)
    pending = _analyze(pilot)
    target = next(cell for cell in pending["cells"] if cell["opaque_id"] == row["id"])
    assert target["arbitration_required"] is True
    assert target["rating_state"] == "arbitration_pending"
    assert target["aggregate_Q"] is None
    assert pending["coverage"]["completed_pair_count"] < 6

    quote = row["components"][0]["evidence_quote"]
    _dump(pilot["ratings_c_path"], {
        "schema": 1, "judge": "C", "ratings": [_rating(row["id"], quote, 79)]
    })
    resolved = _analyze(pilot, third=True)
    target = next(cell for cell in resolved["cells"] if cell["opaque_id"] == row["id"])
    assert target["rating_state"] == "complete"
    assert target["aggregate_Q"] == 79
    assert target["aggregation_method"] == "median_three_after_arbitration"
    assert resolved["coverage"]["completed_pair_count"] == 6


def test_incident_disagreement_requires_arbitration(pilot: dict[str, Any]) -> None:
    judge_b = _load(pilot["ratings_b_path"])
    row = judge_b["ratings"][0]
    quote = row["components"][0]["evidence_quote"]
    row["critical_incidents"] = [{"code": "false_causal_effect", "evidence_quote": quote}]
    _dump(pilot["ratings_b_path"], judge_b)
    target = next(cell for cell in _analyze(pilot)["cells"] if cell["opaque_id"] == row["id"])
    assert target["arbitration_reasons"] == ["critical_incident_disagreement"]
    assert target["aggregate_Q"] is None


def test_judge_format_declarations_do_not_control_inclusion(pilot: dict[str, Any]) -> None:
    judge_a = _load(pilot["ratings_a_path"])
    judge_b = _load(pilot["ratings_b_path"])
    judge_a["ratings"][0]["format_deviations"] = ["Judge declared a possible format issue."]
    judge_b["ratings"][0]["format_deviations"] = [
        {"code": "over_900_words", "observed_words": 901, "count_method": "whitespace"}
    ]
    _dump(pilot["ratings_a_path"], judge_a)
    _dump(pilot["ratings_b_path"], judge_b)
    result = _analyze(pilot)
    target = next(cell for cell in result["cells"] if cell["opaque_id"] == judge_a["ratings"][0]["id"])
    assert target["format_deviations"] == []  # measured from the actual blind bytes
    assert target["aggregate_Q"] == 72
    assert target["ratings"]["A"]["format_deviations"] == ["Judge declared a possible format issue."]


def test_only_contextual_markdown_markers_are_excluded_from_word_count() -> None:
    payload = "## Situación\nx → + - € y\n- item\n## Propuesta\n## Comprobación\n"
    observations = _format_observations(payload, 900)
    assert observations["word_count_protocol"] == len(payload.split()) - 4


def test_over_limit_keeps_supplementary_notes_but_excludes_primary_pair(pilot: dict[str, Any]) -> None:
    cid = pilot["cells"][2]["id"]  # A-M in block 1
    opaque_id = pilot["ids"][cid]
    path = pilot["base"] / f"v2/outputs/{cid}.json"
    output = _load(path)
    blind = "### Situación\n\n### Propuesta\n\n" + "palabra " * 897 + "\n\n### Comprobación\n\n€\n"
    output["response_raw_text"] = blind.rstrip("\n") + "\n\n[cloud-offload provider=synthetic]"
    _dump(path, output)
    for judge_path in (pilot["ratings_a_path"], pilot["ratings_b_path"]):
        judge = _load(judge_path)
        rated = next(row for row in judge["ratings"] if row["id"] == opaque_id)
        for component in rated["components"]:
            component["evidence_quote"] = "palabra"
        _dump(judge_path, judge)
    manifest = _load(pilot["base"] / "v2/blind/manifest.json")
    manifest_row = next(row for row in manifest["payloads"] if row["id"] == opaque_id)
    manifest_row.update(
        sha256=_write(pilot["base"] / f"v2/blind/{opaque_id}.md", blind),
        word_count_whitespace=len(blind.split()), word_limit_exceeded=True,
    )
    _dump(pilot["base"] / "v2/blind/manifest.json", manifest)
    mapping = _load(pilot["mapping_path"])
    mapping[opaque_id]["response_raw_sha256"] = _sha(output["response_raw_text"].encode())
    mapping[opaque_id]["blind_sha256"] = manifest_row["sha256"]
    _dump(pilot["mapping_path"], mapping)

    result = _analyze(pilot)
    target = next(cell for cell in result["cells"] if cell["cell_id"] == cid)
    assert target["word_limit_exceeded"] is True
    assert target["word_count_whitespace"] == 904
    assert target["word_count_protocol"] == 901  # isolated € is not Markdown syntax
    assert target["rating_state"] == "excluded_format_deviation"
    assert target["ratings"]["A"]["Q"] == 70
    assert target["aggregate_Q"] is None
    assert result["coverage"]["completed_pair_count"] == 4
    assert result["coverage"]["supplementary_rated_cell_ids"] == [cid]
    assert result["protocol_deviations"]
