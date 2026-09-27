"""Six-cell local audit controls; all constructed runs use synthetic evidence."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).parent))
import audit_development_triplet as audit  # noqa: E402
import run_development_arm as runner  # noqa: E402
from test_run_development_arm import (  # noqa: E402
    FAKE_CLI, _write_pilot_triplet_plan, activation_dossier_fixture,
    fake_t_setup,
)


PLAN_SHA = "1" * 64
DOSSIER_SHA = "2" * 64


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _synthetic_observation(family: str, arm: str) -> dict[str, Any]:
    return {
        "schema": 1,
        "classification": "development_observation_unsealed",
        "run_json_sha256": _hash(f"run-{family}-{arm}"),
        "execution_status": "artifacts_ready_for_inspection",
        "observation_state": "recorded_materials_verified_prelaunch_unproven",
        "arm": arm,
        "pilot_mode": "explicit_triplet",
        "provider_cli": "codex" if family == "A" else "agy",
        "requested_model": "synthetic-a" if family == "A" else "synthetic-b",
        "requested_effort": "medium" if family == "A" else "high",
        "tool_policy": "default",
        "pilot_triplet_binding": {
            "plan_sha256": PLAN_SHA,
            "activation_dossier_sha256": DOSSIER_SHA,
            "plan_schema": 2,
            "active_budget_seconds": 37,
            "cell": {"family_slot": family, "arm": arm},
        },
        "run_time_budget": {"active_budget_seconds": 37},
        "cli_usage": {
            "complete": True, "terminal_success": True,
            "final_usage": {"input_tokens": 10, "output_tokens": 2},
        },
        "verified_inputs": {
            "work/task.md": {"sha256": _hash("same task")},
            "work/source_manifest.json": {"sha256": _hash("same manifest")},
            "work/sample_first_complete_week.csv": {"sha256": _hash("same case data")},
            "work/common.md": {"sha256": _hash("same common prompt")},
            "work/arm.md": {"sha256": _hash(f"assigned arm {arm}")},
            "prompt.txt": {"sha256": _hash(f"assembled prompt {arm}")},
        },
    }


def _write_observation(run_dir: Path, observation: dict[str, Any]) -> None:
    (run_dir / "observation.json").write_text(
        json.dumps(observation, sort_keys=True), encoding="utf-8",
    )


@pytest.fixture
def synthetic_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> dict[tuple[str, str], Path]:
    """Use folders as stubbed observer results for cross-run logic only."""
    def read_observation(path: Path) -> dict[str, Any]:
        return json.loads((path / "observation.json").read_text(encoding="utf-8"))

    monkeypatch.setattr(audit, "observe_run_dir", read_observation)
    dirs: dict[tuple[str, str], Path] = {}
    for family, arm in audit.CELLS:
        run_dir = tmp_path / f"{family}-{arm}"
        run_dir.mkdir()
        _write_observation(run_dir, _synthetic_observation(family, arm))
        dirs[(family, arm)] = run_dir
    return dirs


def _ordered_dirs(dirs: dict[tuple[str, str], Path]) -> list[Path]:
    return [dirs[cell] for cell in audit.CELLS]


def _edit_observation(path: Path, edit: Any) -> None:
    data = json.loads((path / "observation.json").read_text(encoding="utf-8"))
    edit(data)
    _write_observation(path, data)


def _check(report: dict[str, Any], scope: str, field: str) -> dict[str, Any]:
    return next(item for item in report["comparability_checks"]
                if item["scope"] == scope and item["field"] == field)


def test_zero_directories_report_json_and_exit_incomplete() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "audit_development_triplet.py"),
         "--expected-plan-sha256", PLAN_SHA],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 1, result.stderr
    report = json.loads(result.stdout)
    assert report["provided_run_count"] == 0
    assert report["missing_cells"] == ["A/N", "A/S", "A/T", "B/N", "B/S", "B/T"]
    assert all(cell["local_usage"] is None for cell in report["cells"])
    assert report["six_unique_cells_present"] is False
    assert report["six_cell_recorded_local_completion"] is False
    assert report["signed_toolkit_workflow_verified"] is False
    assert report["effective_tool_parity_proven"] is False
    assert report["authenticated_tokens"] is None
    assert report["authenticated_cost_usd"] is None
    assert report["controlled_comparison_eligible"] is False
    assert report["criterion_4"] == "not_assessed"


def test_six_synthetic_cells_are_only_a_local_completion(
    synthetic_runs: dict[tuple[str, str], Path],
) -> None:
    report = audit.audit_development_triplet(_ordered_dirs(synthetic_runs), PLAN_SHA)
    assert report["six_unique_cells_present"] is True
    assert report["six_cell_recorded_local_completion"] is True
    assert report["six_cell_recorded_local_completion_scope"] == (
        "recorded artifacts and complete local usage ready for inspection only"
    )
    assert report["signed_toolkit_workflow_verified"] is False
    assert report["activation_dossier_sha256"] == DOSSIER_SHA
    assert report["missing_cells"] == report["duplicate_cells"] == []
    assert all(item["status"] == "match" for item in report["comparability_checks"])
    assert [cell["local_usage"]["input_tokens"] for cell in report["cells"]] == [10] * 6
    assert report["effective_tool_parity_proven"] is False
    assert report["controlled_comparison_eligible"] is False
    assert report["criterion_4"] == "not_assessed"


def test_missing_and_copied_run_do_not_fill_a_different_cell(
    synthetic_runs: dict[tuple[str, str], Path], tmp_path: Path,
) -> None:
    missing = _ordered_dirs(synthetic_runs)[:-1]
    report = audit.audit_development_triplet(missing, PLAN_SHA)
    assert report["missing_cells"] == ["B/T"]
    assert report["cells"][-1]["execution_status"] is None
    assert report["cells"][-1]["local_usage"] is None

    copy_path = tmp_path / "copied-A-N"
    shutil.copytree(synthetic_runs[("A", "N")], copy_path)
    report = audit.audit_development_triplet([*missing, copy_path], PLAN_SHA)
    assert report["missing_cells"] == ["B/T"]
    assert report["duplicate_cells"] == ["A/N"]
    assert report["duplicate_run_record_indexes"] == [[0, 5]]
    assert report["six_unique_cells_present"] is False


@pytest.mark.parametrize("change, expected", [
    ("other_plan", "plan_sha256_differs_from_expected"),
    ("generic", "generic_run_without_explicit_triplet_binding"),
    ("v1", "pilot_plan_is_not_schema_2"),
])
def test_other_plan_generic_and_v1_do_not_fill_cells(
    synthetic_runs: dict[tuple[str, str], Path], change: str, expected: str,
) -> None:
    def change_one(data: dict[str, Any]) -> None:
        if change == "other_plan":
            data["pilot_triplet_binding"]["plan_sha256"] = "3" * 64
        elif change == "generic":
            data["pilot_mode"] = "generic_exploratory"
            data["pilot_triplet_binding"] = None
        else:
            data["pilot_triplet_binding"]["plan_schema"] = 1

    _edit_observation(synthetic_runs[("A", "N")], change_one)
    report = audit.audit_development_triplet(_ordered_dirs(synthetic_runs), PLAN_SHA)
    assert report["runs"][0]["invalid_reasons"] == [expected]
    assert report["invalid_run_indexes"] == [0]
    assert report["invalid_cells"] == [{
        "run_index": 0, "cell": None if change == "generic" else "A/N",
        "reasons": [expected],
    }]
    assert report["missing_cells"] == ["A/N"]
    assert report["six_unique_cells_present"] is False


def test_other_dossier_prevents_one_six_cell_set(
    synthetic_runs: dict[tuple[str, str], Path],
) -> None:
    _edit_observation(
        synthetic_runs[("B", "T")],
        lambda data: data["pilot_triplet_binding"].update(
            activation_dossier_sha256="4" * 64,
        ),
    )
    report = audit.audit_development_triplet(_ordered_dirs(synthetic_runs), PLAN_SHA)
    assert report["activation_dossier_sha256"] is None
    assert report["activation_dossier_sha256s"] == [DOSSIER_SHA, "4" * 64]
    assert _check(report, "all_cells", "activation_dossier_sha256")["status"] == "mismatch"
    assert report["six_unique_cells_present"] is False


@pytest.mark.parametrize("scope,field,cell,new_value", [
    ("all_cells", "work/task.md", ("B", "S"), "other task"),
    ("all_cells", "work/source_manifest.json", ("B", "S"), "other manifest"),
    ("all_cells", "work/common.md", ("B", "S"), "other common prompt"),
    ("arm_N", "prompt.txt", ("B", "N"), "other assembled prompt"),
    ("family_A", "requested_model", ("A", "T"), "other-model"),
    ("family_B", "requested_effort", ("B", "S"), "low"),
    ("family_A", "requested_provider_cli", ("A", "S"), "agy"),
    ("all_cells", "requested_local_budget_seconds", ("B", "T"), 40),
])
def test_cross_run_mismatch_is_reported_where_observer_data_permits(
    synthetic_runs: dict[tuple[str, str], Path], scope: str, field: str,
    cell: tuple[str, str], new_value: str | int,
) -> None:
    def alter(data: dict[str, Any]) -> None:
        if field.startswith("work/") or field == "prompt.txt":
            data["verified_inputs"][field]["sha256"] = _hash(str(new_value))
        elif field == "requested_local_budget_seconds":
            data["run_time_budget"]["active_budget_seconds"] = new_value
            data["pilot_triplet_binding"]["active_budget_seconds"] = new_value
        else:
            key = "provider_cli" if field == "requested_provider_cli" else field
            data[key] = new_value

    _edit_observation(synthetic_runs[cell], alter)
    report = audit.audit_development_triplet(_ordered_dirs(synthetic_runs), PLAN_SHA)
    assert _check(report, scope, field)["status"] == "mismatch"
    assert report["six_cell_recorded_local_completion"] is False
    assert report["controlled_comparison_eligible"] is False


@pytest.mark.parametrize("status", ["preparing", "cli_failure", "required_artifact_missing"])
def test_partial_or_failed_run_keeps_its_cell_and_null_usage(
    synthetic_runs: dict[tuple[str, str], Path], status: str,
) -> None:
    def alter(data: dict[str, Any]) -> None:
        data["execution_status"] = status
        if status == "preparing":
            data["observation_state"] = "partial"
            data["cli_usage"] = None
            data["verified_inputs"].pop("work/arm.md")

    _edit_observation(synthetic_runs[("A", "S")], alter)
    report = audit.audit_development_triplet(_ordered_dirs(synthetic_runs), PLAN_SHA)
    assert report["six_unique_cells_present"] is True
    assert report["cells"][1]["execution_status"] == status
    assert report["cells"][1]["local_usage"] is None
    assert report["runs"][1]["local_usage"] is None
    assert report["six_cell_recorded_local_completion"] is False


def test_success_without_complete_local_usage_cannot_claim_local_completion(
    synthetic_runs: dict[tuple[str, str], Path],
) -> None:
    _edit_observation(
        synthetic_runs[("B", "N")],
        lambda data: data["cli_usage"].update(complete=False),
    )
    report = audit.audit_development_triplet(_ordered_dirs(synthetic_runs), PLAN_SHA)
    assert report["six_unique_cells_present"] is True
    assert report["cells"][3]["execution_status"] == "artifacts_ready_for_inspection"
    assert report["cells"][3]["local_usage"] is None
    assert report["six_cell_recorded_local_completion"] is False


def test_real_observer_rejects_tampered_copied_plan_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, dossier_path, _ = activation_dossier_fixture.__wrapped__(tmp_path, monkeypatch)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    executable = fake_bin / "codex"
    executable.write_text(FAKE_CLI, encoding="utf-8")
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", str(fake_bin) + os.pathsep + os.environ["PATH"])
    dossier_sha = runner._sha256(dossier_path)
    plan_path = tmp_path / "plan.json"
    plan_sha = _write_pilot_triplet_plan(plan_path, dossier_sha)
    run_dir, _ = runner.run_development_arm(
        arm="N", provider="codex", model="test-model", effort="medium",
        output_root=tmp_path / "runs", timeout_seconds=10,
        pilot_triplet_plan=plan_path, pilot_triplet_plan_sha256=plan_sha,
        activation_dossier=dossier_path, activation_dossier_sha256=dossier_sha,
        family_slot="A",
    )
    clean = audit.audit_development_triplet([run_dir], plan_sha)
    assert clean["invalid_run_indexes"] == []
    assert clean["cells"][0]["execution_status"] == "artifacts_ready_for_inspection"
    copied_plan = run_dir / "pilot_triplet_plan.json"
    copied_plan.write_bytes(copied_plan.read_bytes() + b"\n")
    tampered = audit.audit_development_triplet([run_dir], plan_sha)
    assert tampered["invalid_run_indexes"] == [0]
    assert tampered["invalid_cells"][0]["cell"] is None
    assert "pilot triplet plan differs from its recorded bytes" in (
        tampered["runs"][0]["invalid_reasons"][0]
    )
    assert tampered["cells"][0]["execution_status"] is None
    assert tampered["six_unique_cells_present"] is False


def test_six_fake_cli_runs_are_observed_as_one_local_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, dossier_path, _ = activation_dossier_fixture.__wrapped__(tmp_path, monkeypatch)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "base_fake_cli.py").write_text(FAKE_CLI, encoding="utf-8")
    wrapper = '''#!/usr/bin/env python3
import subprocess
from pathlib import Path

tool = Path.cwd() / ".venv/bin/organon"
if tool.is_file():
    for _ in range(2):
        subprocess.run([str(tool), "publish"], check=True,
                       stdout=subprocess.DEVNULL)
source = Path(__file__).with_name("base_fake_cli.py")
exec(compile(source.read_text(encoding="utf-8"), str(source), "exec"))
'''
    for name in ("codex", "agy"):
        executable = fake_bin / name
        executable.write_text(wrapper, encoding="utf-8")
        executable.chmod(0o755)
    monkeypatch.setenv("PATH", str(fake_bin) + os.pathsep + os.environ["PATH"])

    def policy_only_t_setup(
        work: Path, run_dir: Path, wheel: Path | None, timeout_seconds: int,
        env: dict[str, str], *, expected_wheel_sha256: str | None = None,
        active_deadline: float | None = None,
    ) -> dict[str, Any]:
        result = fake_t_setup(
            work, run_dir, wheel, timeout_seconds, env,
            expected_wheel_sha256=expected_wheel_sha256,
            active_deadline=active_deadline,
        )
        tool = work / ".venv/bin/organon"
        python_executable = work / ".venv/bin/python"
        python_executable.symlink_to(sys.executable)
        tool_source = '''#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

if sys.argv[1] == "status":
    print(json.dumps({"project": {"approval_policy": "signed"}}))
elif sys.argv[1] == "publish":
    case = Path.cwd() / "case"
    case.mkdir(exist_ok=True)
    temporary = case / ".organon-synthetic-publish"
    temporary.write_text(json.dumps({
        "project": {"approval_policy": "signed"},
        "events": [{"type": "synthetic"}],
    }), encoding="utf-8")
    os.replace(temporary, case / "organon.json")
else:
    sys.exit(2)
'''
        tool.write_text(
            tool_source.replace("#!/usr/bin/env python3", f"#!{python_executable}", 1),
            encoding="utf-8",
        )
        tool.chmod(0o755)
        result["toolkit_files_fingerprint_sha256"] = runner._toolkit_fingerprint(work)
        return result

    monkeypatch.setattr(runner, "_setup_toolkit", policy_only_t_setup)
    dossier_sha = runner._sha256(dossier_path)
    plan_path = tmp_path / "plan.json"
    plan_sha = _write_pilot_triplet_plan(plan_path, dossier_sha, active_budget_seconds=37)
    dirs = []
    for family, arm in audit.CELLS:
        provider, model, effort = (
            ("codex", "test-model", "medium") if family == "A"
            else ("agy", "test-model-b", "high")
        )
        run_dir, summary = runner.run_development_arm(
            arm=arm, provider=provider, model=model, effort=effort,
            output_root=tmp_path / "runs", timeout_seconds=10,
            active_budget_seconds=37,
            toolkit_wheel=(root / "dist/specorganon-0.1.0-py3-none-any.whl"
                           if arm == "T" else None),
            pilot_triplet_plan=plan_path, pilot_triplet_plan_sha256=plan_sha,
            activation_dossier=dossier_path, activation_dossier_sha256=dossier_sha,
            family_slot=family,
        )
        if arm == "T":
            # The fixture records a signed policy value; it verifies no signatures.
            assert summary["t_ledger"]["signed_policy"] is True
            assert summary["t_ledger"]["event_count"] == 1
            assert summary["t_process_trace"]["tool_ledger_publish_count"] == 2
            assert summary["t_process_trace"]["other_ledger_write_count"] == 0
        dirs.append(run_dir)
    report = audit.audit_development_triplet(dirs, plan_sha)
    assert report["invalid_run_indexes"] == []
    assert report["missing_cells"] == report["duplicate_cells"] == []
    assert report["six_unique_cells_present"] is True
    assert [item["execution_status"] for item in report["cells"]] == [
        "artifacts_ready_for_inspection"
    ] * 6
    assert report["six_cell_recorded_local_completion"] is True
    assert report["signed_toolkit_workflow_verified"] is False
    assert any("Ed25519 signatures" in item for item in report["limitations"])
    assert all(item["local_usage"] is not None for item in report["cells"])
    assert all(item["status"] == "match" for item in report["comparability_checks"])
    assert report["activation_dossier_sha256"] == dossier_sha
    assert report["controlled_comparison_eligible"] is False
    assert report["criterion_4"] == "not_assessed"
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "audit_development_triplet.py"),
         "--expected-plan-sha256", plan_sha, *(str(path) for path in dirs)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    cli_report = json.loads(result.stdout)
    assert cli_report["six_cell_recorded_local_completion"] is True
    assert cli_report["controlled_comparison_eligible"] is False


def test_invalid_digest_and_seventh_run_are_rejected() -> None:
    with pytest.raises(ValueError, match="expected plan SHA-256"):
        audit.audit_development_triplet([], "not-a-digest")
    with pytest.raises(ValueError, match="at most six"):
        audit.audit_development_triplet(["/missing"] * 7, PLAN_SHA)
    for args in (
        ["--expected-plan-sha256", "not-a-digest"],
        ["--expected-plan-sha256", PLAN_SHA, *(["/missing"] * 7)],
    ):
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "audit_development_triplet.py"), *args],
            capture_output=True, text=True, check=False,
        )
        assert result.returncode == 2
        assert result.stdout == ""
