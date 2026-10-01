"""Offline contract checks for the sealable A/B/C development method tool."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import development_method_tool as method_tool  # noqa: E402


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _nodes() -> list[dict]:
    return [
        {"id": "P", "kind": "problem", "phase": "philosophy", "status": "pending",
         "claim": "Public question", "depends_on": [],
         "risk": {"impact": 4, "uncertainty": 2, "effort": 2}},
        {"id": "A", "kind": "assumption", "phase": "science", "status": "pending",
         "claim": "Testable assumption", "depends_on": ["P"],
         "risk": {"impact": 3, "uncertainty": 5, "effort": 2}},
        {"id": "N", "kind": "normative", "phase": "validation", "status": "pending",
         "claim": "Human decision remains pending", "depends_on": ["P"],
         "risk": {"impact": 5, "uncertainty": 5, "effort": 3}},
        {"id": "R", "kind": "requirement", "phase": "engineering", "status": "pending",
         "claim": "Engineering proposal depends on human decision",
         "depends_on": ["A", "N"],
         "risk": {"impact": 4, "uncertainty": 4, "effort": 4}},
        {"id": "V", "kind": "test_result", "phase": "validation", "status": "pending",
         "claim": "No field test observed", "depends_on": ["R"],
         "risk": {"impact": 3, "uncertainty": 4, "effort": 5}},
    ]


def _stage(tmp_path: Path, alternative: str = "A", *,
           deliverables: list[str] | None = None) -> tuple[Path, Path, Path, Path]:
    stage = tmp_path / "stage"
    case, inputs, work = (stage / name for name in ("case", "inputs", "work"))
    for path in (case, inputs, work):
        path.mkdir(parents=True, mode=0o700)
    public = "Acentos: energía y pérdida.\n".encode("utf-8")
    (case / "task.md").write_bytes(public)
    manifest = {"schema": 1, "case_id": "D-E-PUBLIC", "files": [{
        "path": "task.md", "sha256": hashlib.sha256(public).hexdigest(),
        "bytes": len(public)}], "deliverables": deliverables or [
            "analysis.py", "metrics.json", "report.md", "sources.json"]}
    (case / "case.json").write_text(_canonical(manifest), encoding="utf-8")
    modes = {"A": "sequential", "B": "graph", "C": "risk"}
    (inputs / "arm_prompt").write_text(_canonical({
        "alternative": alternative, "mode": modes[alternative],
        "instructions": "Use the public case; leave human decisions pending."}), encoding="utf-8")
    tool = tmp_path / "development_tool"
    method_tool.build_tool(tool)
    return tool, case, inputs, work


def _call(tool: Path, case: Path, inputs: Path, work: Path,
          request: dict | str) -> tuple[int, dict | None, str]:
    inner = request if isinstance(request, str) else _canonical(request)
    outer = _canonical({"request": inner})
    result = subprocess.run([str(tool), str(case), str(inputs), str(work), outer],
                            capture_output=True, text=True, check=False, timeout=10)
    return result.returncode, json.loads(result.stdout) if result.stdout else None, result.stderr


def test_builder_embeds_unchanged_core_and_never_replaces(tmp_path: Path) -> None:
    tool, _, _, _ = _stage(tmp_path)
    script = tool.read_bytes()
    original = (ROOT / "prototypes" / "core.py").read_bytes()
    encoded = re.search(rb'CORE_BYTES = base64\.b64decode\("([A-Za-z0-9+/=]+)"', script)
    assert encoded is not None and base64.b64decode(encoded.group(1)) == original
    assert stat.S_IMODE(tool.stat().st_mode) == 0o500
    assert script.startswith(b"#!") and b"python" in script.splitlines()[0]
    with pytest.raises(FileExistsError):
        method_tool.build_tool(tool)
    assert script == tool.read_bytes()


@pytest.mark.parametrize("alternative", ["A", "B", "C"])
def test_real_prototype_operations_preserve_pending_norm(
    tmp_path: Path, alternative: str,
) -> None:
    tool, case, inputs, work = _stage(tmp_path, alternative)
    code, initial, err = _call(tool, case, inputs, work,
                                {"op": "init", "nodes": _nodes()})
    assert code == 0 and err == "" and initial is not None
    assert initial["ok"] and initial["method_exit_code"] == 0
    assert initial["mode"] == {"A": "sequential", "B": "graph", "C": "risk"}[alternative]
    assert initial["proposal_sha256"] == hashlib.sha256((work / "proposal.json").read_bytes()).hexdigest()
    assert initial["method_state_sha256"] == hashlib.sha256((work / "method_state.json").read_bytes()).hexdigest()
    assert (work / "method_state.json").is_file()
    for node in ("P", "A"):
        code, changed, _ = _call(tool, case, inputs, work,
                                 {"op": "revise", "id": node, "status": "supported",
                                  "reason": "Public fixture evidence only"})
        assert code == 0 and changed is not None and changed["ok"]
    if alternative != "A":
        assert _call(tool, case, inputs, work,
                     {"op": "review", "id": "A"})[1]["ok"]
    for phase in ("philosophy", "science"):
        code, advanced, _ = _call(tool, case, inputs, work,
                                  {"op": "advance", "phase": phase})
        assert code == 0 and advanced is not None and advanced["ok"]
    code, blocked, _ = _call(tool, case, inputs, work,
                             {"op": "advance", "phase": "engineering"})
    assert code == 0 and blocked is not None
    assert not blocked["ok"] and blocked["method_exit_code"] == 2
    status_code, status, _ = _call(tool, case, inputs, work, {"op": "status"})
    assert status_code == 0 and status is not None and status["ok"]
    assert status["details"]["method_result"]["pending_normative"] == ["N"]
    assert (work / "method_state.json").read_text().find('"approve"') == -1


@pytest.mark.parametrize("alternative", ["A", "B", "C"])
def test_revision_exposes_sequential_versus_dependency_invalidation(
    tmp_path: Path, alternative: str,
) -> None:
    tool, case, inputs, work = _stage(tmp_path, alternative)
    _call(tool, case, inputs, work, {"op": "init", "nodes": _nodes()})
    for node in ("P", "A"):
        assert _call(tool, case, inputs, work,
                     {"op": "revise", "id": node, "status": "supported",
                      "reason": "Fixture support"})[1]["ok"]
    if alternative != "A":
        assert _call(tool, case, inputs, work,
                     {"op": "review", "id": "A"})[1]["ok"]
    for phase in ("philosophy", "science"):
        assert _call(tool, case, inputs, work,
                     {"op": "advance", "phase": phase})[1]["ok"]
    assert _call(tool, case, inputs, work,
                 {"op": "revise", "id": "P", "status": "contradicted",
                  "reason": "New public contradiction"})[1]["ok"]
    report = _call(tool, case, inputs, work, {"op": "status"})[1]
    assert report is not None
    result = report["details"]["method_result"]
    if alternative == "A":
        assert result["phase_status"]["science"] == "accepted"
        assert "science" in result["unsafe_accepted_phases"]
    else:
        assert result["phase_status"]["science"] == "needs_review"
        assert "A" in result["stale_nodes"]
    assert result["pending_normative"] == ["N"]


def test_risk_plan_reports_priority_without_parallel_execution(tmp_path: Path) -> None:
    tool, case, inputs, work = _stage(tmp_path, "C")
    assert _call(tool, case, inputs, work, {"op": "init", "nodes": _nodes()})[1]["ok"]
    code, planned, _ = _call(tool, case, inputs, work, {"op": "plan", "budget": 2})
    assert code == 0 and planned is not None and planned["ok"]
    assert planned["parallel_work_executed"] is False
    result = planned["details"]["method_result"]
    assert result["selected"] and result["potential_waves"]
    assert result["budget"] == 2


def test_chunked_write_over_16k_and_exact_offset_cas(tmp_path: Path) -> None:
    tool, case, inputs, work = _stage(tmp_path)
    chunks = ["a" * 8000, "b" * 8000, "c" * 8000]
    offset = 0
    for chunk in chunks:
        code, response, _ = _call(tool, case, inputs, work,
                                  {"op": "write", "path": "sources.json",
                                   "offset": offset, "content": chunk})
        assert code == 0 and response is not None and response["ok"]
        offset += len(chunk.encode("utf-8"))
        assert response["details"]["bytes"] == offset
    assert offset > 16 * 1024
    assert (work / "sources.json").read_text() == "".join(chunks)
    old = (work / "sources.json").read_bytes()
    code, response, err = _call(tool, case, inputs, work,
                                {"op": "write", "path": "sources.json",
                                 "offset": 0, "content": "overwrite"})
    assert code == 2 and response is None and "offset" in err
    assert (work / "sources.json").read_bytes() == old


def test_public_read_and_security_rejections_have_no_side_effect(
    tmp_path: Path,
) -> None:
    tool, case, inputs, work = _stage(tmp_path)
    code, read, _ = _call(tool, case, inputs, work,
                          {"op": "read", "path": "task.md", "offset": 0, "length": 8192})
    assert code == 0 and read is not None and read["ok"]
    assert "energía" in read["details"]["content"] and read["details"]["eof"]
    initial_files = list(work.iterdir())
    for request in (
        {"op": "read", "path": "../task.md", "offset": 0, "length": 8},
        {"op": "read", "path": "case.json", "offset": 0, "length": 8},
        {"op": "write", "path": "method_state.json", "offset": 0, "content": "evil"},
        {"op": "write", "path": "../case/task.md", "offset": 0, "content": "evil"},
        {"op": "approve", "id": "N"},
        {"op": "analyze"},
    ):
        code, response, _ = _call(tool, case, inputs, work, request)
        assert code == 2 and response is None
    assert list(work.iterdir()) == initial_files
    assert (case / "task.md").read_text() == "Acentos: energía y pérdida.\n"


def test_symlinks_and_manifest_drift_are_rejected(tmp_path: Path) -> None:
    tool, case, inputs, work = _stage(tmp_path)
    outside = tmp_path / "outside"
    outside.write_text("untouched", encoding="utf-8")
    (work / "report.md").symlink_to(outside)
    code, _, _ = _call(tool, case, inputs, work,
                       {"op": "write", "path": "report.md", "offset": 0,
                        "content": "bad"})
    assert code == 2 and outside.read_text() == "untouched"
    (work / "report.md").unlink()
    (case / "task.md").write_text("changed", encoding="utf-8")
    code, _, err = _call(tool, case, inputs, work,
                         {"op": "read", "path": "task.md", "offset": 0, "length": 8})
    assert code == 2 and "differs" in err
    (case / "task.md").unlink()
    (case / "task.md").symlink_to(outside)
    assert _call(tool, case, inputs, work,
                 {"op": "read", "path": "task.md", "offset": 0, "length": 8})[0] == 2


def test_strict_nested_json_and_prompt_mode_binding(tmp_path: Path) -> None:
    tool, case, inputs, work = _stage(tmp_path, "B")
    for inner in ('{"op":"status","op":"approve"}', '{"op":"plan","budget":NaN}'):
        code, response, _ = _call(tool, case, inputs, work, inner)
        assert code == 2 and response is None
    assert not list(work.iterdir())
    prompt = json.loads((inputs / "arm_prompt").read_text())
    prompt["mode"] = "sequential"
    (inputs / "arm_prompt").write_text(_canonical(prompt), encoding="utf-8")
    code, response, err = _call(tool, case, inputs, work, {"op": "status"})
    assert code == 2 and response is None and "alternative" in err


def test_pending_normative_cannot_be_approved_through_tool(tmp_path: Path) -> None:
    tool, case, inputs, work = _stage(tmp_path, "B")
    assert _call(tool, case, inputs, work, {"op": "init", "nodes": _nodes()})[1]["ok"]
    before = (work / "method_state.json").read_bytes()
    for forbidden in ({"op": "approve", "id": "N"}, {"op": "analyze"}):
        code, response, _ = _call(tool, case, inputs, work, forbidden)
        assert code == 2 and response is None
    assert (work / "method_state.json").read_bytes() == before
    assert json.loads(before)["nodes"]["N"]["status"] == "pending"
