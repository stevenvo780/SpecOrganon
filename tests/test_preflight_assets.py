"""Offline asset preflight verifies real bytes and isolates one run release."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SCRIPT = SCRIPTS / "preflight_assets.py"
sys.path.insert(0, str(SCRIPTS))
import preflight_assets  # noqa: E402
from plan_confirmatory import compile_schedule  # noqa: E402


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _case_bytes(case_id: str, role: str) -> bytes:
    return f"{role.upper()}-CONTENT-{case_id}\n".encode()


def _input_bytes(role: str) -> bytes:
    return f"INPUT-CONTENT-{role}\n".encode()


def _fixture(tmp_path: Path) -> tuple[dict[str, Any], dict[str, Any], Path, Path]:
    assets_dir = tmp_path / "source"
    assets_dir.mkdir()
    cases: dict[str, Any] = {}
    case_manifest = []
    for case_id in ("R-F", "R-M", "R-S"):
        cases[case_id] = {}
        for role in ("package", "reference"):
            path = assets_dir / f"{case_id}_{role}.bin"
            path.write_bytes(_case_bytes(case_id, role))
            cases[case_id][role] = str(path)
        case_manifest.append({
            "case_id": case_id,
            "package_sha256": _hash(_case_bytes(case_id, "package")),
            "reference_sha256": _hash(_case_bytes(case_id, "reference")),
        })

    inputs: dict[str, Any] = {}
    manifest_inputs: dict[str, Any] = {}
    for role in ("task_contract", "common_prompt", "rubric", "tool_policy", "sdd_guide", "toolkit"):
        path = assets_dir / role
        path.write_bytes(_input_bytes(role))
        inputs[role] = str(path)
        manifest_inputs[role] = {"ref": f"synthetic/{role}", "sha256": _hash(_input_bytes(role))}
    inputs["arm_prompts"] = {}
    manifest_inputs["arm_prompts"] = {}
    for arm in ("N", "S", "T"):
        path = assets_dir / f"prompt_{arm}"
        role = f"prompt_{arm}"
        path.write_bytes(_input_bytes(role))
        inputs["arm_prompts"][arm] = str(path)
        manifest_inputs["arm_prompts"][arm] = {
            "ref": f"synthetic/{role}", "sha256": _hash(_input_bytes(role)),
        }

    models = []
    for family in ("family-a", "family-b"):
        for tier in ("lower", "higher"):
            controlled = tier == "higher"
            models.append({
                "family": family, "tier": tier, "model_id": f"{family}/{tier}",
                "version": "synthetic-v1", "effort_control": controlled,
                "efforts": ([
                    {"label": "low", "provider_value": "low"},
                    {"label": "high", "provider_value": "high"},
                ] if controlled else [{"label": "default"}]),
            })
    manifest = {
        "schema": 1, "seed": 29,
        "protocol_sha256": _hash(b"synthetic protocol"),
        "tool_call_cap": 23, "models": models,
        "cases": case_manifest, "inputs": manifest_inputs,
    }
    schedule = compile_schedule(manifest)
    asset_map = {
        "schema": 1,
        "schedule_sha256": schedule["schedule_sha256"],
        "input_sha256": schedule["input_sha256"],
        "cases": cases,
        "inputs": inputs,
    }
    schedule_path = tmp_path / "schedule.json"
    asset_map_path = tmp_path / "assets.json"
    schedule_path.write_text(json.dumps(schedule), encoding="utf-8")
    asset_map_path.write_text(json.dumps(asset_map), encoding="utf-8")
    return schedule, asset_map, schedule_path, asset_map_path


def _cli(schedule: Path, assets: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(schedule), str(assets), *args],
        capture_output=True, text=True, check=False,
    )


def test_check_cli_verifies_every_asset_without_writing_or_disclosing_paths(tmp_path: Path) -> None:
    schedule, asset_map, schedule_path, asset_map_path = _fixture(tmp_path)
    before = set(tmp_path.rglob("*"))

    process = _cli(schedule_path, asset_map_path, "--check")

    assert process.returncode == 0, process.stderr
    result = json.loads(process.stdout)
    assert result == {
        "schema": 1,
        "classification": "development_asset_preflight_unsealed",
        "notice": "Independent human content review and external custody are required before case reservation.",
        "schedule_sha256": schedule["schedule_sha256"],
        "input_sha256": schedule["input_sha256"],
        "scheduled_runs": 324,
        "verified_assets": 15,
        "verified_case_packages": 3,
        "verified_hidden_references": 3,
        "asset_digest_binding_sha256": result["asset_digest_binding_sha256"],
    }
    assert len(result["asset_digest_binding_sha256"]) == 64
    assert set(tmp_path.rglob("*")) == before
    combined = process.stdout + process.stderr
    assert str(tmp_path) not in combined
    assert "REFERENCE-CONTENT" not in combined
    assert "R-F_reference" not in combined
    assert asset_map["inputs"]["rubric"] not in combined


@pytest.mark.parametrize("arm,expected", [
    ("N", {"case_package", "task_contract", "common_prompt", "arm_prompt", "tool_policy"}),
    ("S", {"case_package", "task_contract", "common_prompt", "arm_prompt", "tool_policy", "sdd_guide"}),
    ("T", {"case_package", "task_contract", "common_prompt", "arm_prompt", "tool_policy", "toolkit"}),
])
def test_release_cli_copies_only_one_arms_visible_bytes(
    tmp_path: Path, arm: str, expected: set[str]
) -> None:
    schedule, asset_map, schedule_path, asset_map_path = _fixture(tmp_path)
    run = next(item for item in schedule["runs"] if item["arm"] == arm and item["case_id"] == "R-M")
    output = tmp_path / f"release-{arm}"

    process = _cli(schedule_path, asset_map_path, "--run-id", run["run_id"], "--output-dir", str(output))

    assert process.returncode == 0, process.stderr
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert json.loads(process.stdout) == manifest
    assert manifest["classification"] == "development_release_unsealed"
    assert manifest["run_id"] == run["run_id"]
    assert manifest["run_sha256"] == run["run_sha256"]
    assert manifest["schedule_sha256"] == schedule["schedule_sha256"]
    assert manifest["coordinates"]["arm"] == arm
    assert manifest["coordinates"]["case_id"] == "R-M"
    assert manifest["limits"] == schedule["per_run_limits"]
    assert set(manifest["files"]) == expected
    assert {path.name for path in output.iterdir()} == expected | {"manifest.json"}
    assert (output / "case_package").read_bytes() == Path(asset_map["cases"]["R-M"]["package"]).read_bytes()
    assert (output / "arm_prompt").read_bytes() == Path(asset_map["inputs"]["arm_prompts"][arm]).read_bytes()
    for name, details in manifest["files"].items():
        assert set(details) == {"file", "sha256", "bytes"}
        assert details["file"] == name
        assert details["sha256"] == _hash((output / name).read_bytes())
        assert details["bytes"] == (output / name).stat().st_size
        assert (output / name).stat().st_mode & 0o777 == 0o600
    assert (output / "manifest.json").stat().st_mode & 0o777 == 0o600
    assert output.stat().st_mode & 0o777 == 0o700

    rendered = (output / "manifest.json").read_text(encoding="utf-8")
    all_bytes = b"".join(path.read_bytes() for path in output.iterdir())
    for case_id in ("R-F", "R-M", "R-S"):
        assert _case_bytes(case_id, "reference") not in all_bytes
        assert _hash(_case_bytes(case_id, "reference")) not in rendered
    assert _input_bytes("rubric") not in all_bytes
    assert _hash(_input_bytes("rubric")) not in rendered
    for other in set(("N", "S", "T")) - {arm}:
        assert _input_bytes(f"prompt_{other}") not in all_bytes
        assert _hash(_input_bytes(f"prompt_{other}")) not in rendered
    assert str(tmp_path) not in rendered
    assert all(other["run_id"] not in rendered for other in schedule["runs"] if other is not run)


def test_altered_source_bytes_fail_before_destination_creation(tmp_path: Path) -> None:
    schedule, asset_map, schedule_path, asset_map_path = _fixture(tmp_path)
    Path(asset_map["inputs"]["common_prompt"]).write_bytes(b"changed after planning")
    output = tmp_path / "must-not-exist"
    process = _cli(schedule_path, asset_map_path, "--run-id", schedule["runs"][0]["run_id"], "--output-dir", str(output))
    assert process.returncode == 2
    assert "byte digest differs" in process.stderr
    assert not output.exists()
    assert str(tmp_path) not in process.stderr


def test_forged_asset_map_digest_binding_rejected_before_writing(tmp_path: Path) -> None:
    schedule, asset_map, schedule_path, asset_map_path = _fixture(tmp_path)
    asset_map["schedule_sha256"] = "0" * 64
    asset_map_path.write_text(json.dumps(asset_map), encoding="utf-8")
    output = tmp_path / "must-not-exist"
    process = _cli(schedule_path, asset_map_path, "--run-id", schedule["runs"][0]["run_id"], "--output-dir", str(output))
    assert process.returncode == 2
    assert "digest binding" in process.stderr
    assert not output.exists()


def test_missing_hidden_reference_rejected_before_writing(tmp_path: Path) -> None:
    schedule, asset_map, schedule_path, asset_map_path = _fixture(tmp_path)
    Path(asset_map["cases"]["R-S"]["reference"]).unlink()
    output = tmp_path / "must-not-exist"
    process = _cli(schedule_path, asset_map_path, "--run-id", schedule["runs"][0]["run_id"], "--output-dir", str(output))
    assert process.returncode == 2
    assert "case:R-S:reference cannot be read" in process.stderr
    assert not output.exists()


def test_invalid_schedule_rejected_before_writing(tmp_path: Path) -> None:
    schedule, _, schedule_path, asset_map_path = _fixture(tmp_path)
    schedule["runs"][0]["order_position"] = 99
    schedule_path.write_text(json.dumps(schedule), encoding="utf-8")
    output = tmp_path / "must-not-exist"
    process = _cli(schedule_path, asset_map_path, "--run-id", schedule["runs"][0]["run_id"], "--output-dir", str(output))
    assert process.returncode == 2
    assert "invalid candidate schedule" in process.stderr
    assert not output.exists()


def test_existing_destination_is_never_deleted_or_overwritten(tmp_path: Path) -> None:
    schedule, _, schedule_path, asset_map_path = _fixture(tmp_path)
    output = tmp_path / "existing"
    output.mkdir()
    marker = output / "marker"
    marker.write_bytes(b"keep this")
    process = _cli(schedule_path, asset_map_path, "--run-id", schedule["runs"][0]["run_id"], "--output-dir", str(output))
    assert process.returncode == 2
    assert "already exists" in process.stderr
    assert marker.read_bytes() == b"keep this"
    assert {item.name for item in output.iterdir()} == {"marker"}


@pytest.mark.parametrize("change", ["relative_path", "extra_key", "missing_arm", "wrong_type", "unknown_run"])
def test_invalid_asset_map_or_run_rejected_without_writing(tmp_path: Path, change: str) -> None:
    schedule, asset_map, schedule_path, asset_map_path = _fixture(tmp_path)
    run_id = schedule["runs"][0]["run_id"]
    if change == "relative_path":
        asset_map["inputs"]["rubric"] = "relative/rubric"
    elif change == "extra_key":
        asset_map["inputs"]["unused"] = str(tmp_path / "unused")
    elif change == "missing_arm":
        del asset_map["inputs"]["arm_prompts"]["T"]
    elif change == "wrong_type":
        asset_map["cases"]["R-F"]["reference"] = None
    else:
        run_id = "conf-unknown"
    asset_map_path.write_text(json.dumps(asset_map), encoding="utf-8")
    output = tmp_path / "must-not-exist"
    process = _cli(schedule_path, asset_map_path, "--run-id", run_id, "--output-dir", str(output))
    assert process.returncode == 2
    assert not output.exists()
    assert str(tmp_path) not in process.stderr


def test_hidden_bytes_equal_to_visible_asset_cannot_be_released(tmp_path: Path) -> None:
    schedule, asset_map, _, _ = _fixture(tmp_path)
    source = Path(asset_map["inputs"]["rubric"])
    source.write_bytes(_input_bytes("common_prompt"))
    manifest = {
        "schema": 1, "seed": schedule["seed"], "protocol_sha256": schedule["protocol_sha256"],
        "tool_call_cap": schedule["per_run_limits"]["tool_calls"],
        "models": schedule["models"], "cases": schedule["cases"], "inputs": schedule["inputs"],
    }
    manifest["inputs"]["rubric"]["sha256"] = _hash(_input_bytes("common_prompt"))
    schedule = compile_schedule(manifest)
    asset_map["schedule_sha256"] = schedule["schedule_sha256"]
    asset_map["input_sha256"] = schedule["input_sha256"]
    output = tmp_path / "must-not-exist"
    with pytest.raises(preflight_assets.PreflightError, match="identical bytes"):
        preflight_assets.preflight(schedule, asset_map, run_id=schedule["runs"][0]["run_id"], output_dir=output)
    assert not output.exists()


def test_change_after_preflight_leaves_no_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    schedule, asset_map, _, _ = _fixture(tmp_path)
    original = preflight_assets._open_verified_assets

    def mutate_after_open(paths: Any, digests: Any, stack: Any) -> Any:
        opened = original(paths, digests, stack)
        Path(asset_map["inputs"]["common_prompt"]).write_bytes(b"late change")
        return opened

    monkeypatch.setattr(preflight_assets, "_open_verified_assets", mutate_after_open)
    output = tmp_path / "partial-untrusted"
    with pytest.raises(preflight_assets.PreflightError, match="untrusted"):
        preflight_assets.preflight(schedule, asset_map, run_id=schedule["runs"][0]["run_id"], output_dir=output)
    assert output.exists()
    assert not (output / "manifest.json").exists()


def test_replaced_output_directory_cannot_redirect_release(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    schedule, asset_map, _, _ = _fixture(tmp_path)
    output = tmp_path / "release"
    moved = tmp_path / "moved-original"
    original_open = preflight_assets.os.open

    def replace_at_reopen(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        if path == output.name and flags & os.O_DIRECTORY and kwargs.get("dir_fd") is not None:
            output.rename(moved)
            output.mkdir()
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(preflight_assets.os, "open", replace_at_reopen)
    with pytest.raises(preflight_assets.PreflightError, match="untrusted"):
        preflight_assets.preflight(schedule, asset_map, run_id=schedule["runs"][0]["run_id"], output_dir=output)
    assert output.is_dir() and not list(output.iterdir())
    assert moved.is_dir() and not list(moved.iterdir())


def test_replacement_during_copy_cannot_write_valid_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    schedule, asset_map, _, _ = _fixture(tmp_path)
    output = tmp_path / "release"
    moved = tmp_path / "moved-original"
    original_copy = preflight_assets._copy_verified_asset
    swapped = False

    def swap_after_copy(source_fd: int, directory_fd: int, name: str, expected: str) -> dict[str, Any]:
        nonlocal swapped
        result = original_copy(source_fd, directory_fd, name, expected)
        if not swapped:
            output.rename(moved)
            output.mkdir()
            swapped = True
        return result

    monkeypatch.setattr(preflight_assets, "_copy_verified_asset", swap_after_copy)
    with pytest.raises(preflight_assets.PreflightError, match="untrusted"):
        preflight_assets.preflight(schedule, asset_map, run_id=schedule["runs"][0]["run_id"], output_dir=output)
    assert output.is_dir() and not list(output.iterdir())
    assert moved.is_dir()
    assert not (moved / "manifest.json").exists()


def test_hidden_reference_mutation_after_first_hash_blocks_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    schedule, asset_map, _, _ = _fixture(tmp_path)
    output = tmp_path / "release"
    hidden = Path(asset_map["cases"]["R-F"]["reference"])
    original_copy = preflight_assets._copy_verified_asset
    changed = False

    def mutate_hidden(source_fd: int, directory_fd: int, name: str, expected: str) -> dict[str, Any]:
        nonlocal changed
        result = original_copy(source_fd, directory_fd, name, expected)
        if not changed:
            hidden.write_bytes(b"new hidden answer")
            changed = True
        return result

    monkeypatch.setattr(preflight_assets, "_copy_verified_asset", mutate_hidden)
    with pytest.raises(preflight_assets.PreflightError, match="untrusted"):
        preflight_assets.preflight(schedule, asset_map, run_id=schedule["runs"][0]["run_id"], output_dir=output)
    assert output.is_dir()
    assert not (output / "manifest.json").exists()


@pytest.mark.parametrize("unsafe", ["writable_parent", "symlink_parent"])
def test_uncontrolled_parent_rejected_before_destination_creation(tmp_path: Path, unsafe: str) -> None:
    schedule, _, schedule_path, asset_map_path = _fixture(tmp_path)
    parent = tmp_path / "parent"
    if unsafe == "writable_parent":
        parent.mkdir()
        parent.chmod(0o777)
    else:
        actual = tmp_path / "actual"
        actual.mkdir()
        parent.symlink_to(actual, target_is_directory=True)
    output = parent / "release"
    process = _cli(schedule_path, asset_map_path, "--run-id", schedule["runs"][0]["run_id"], "--output-dir", str(output))
    assert process.returncode == 2
    assert "parent" in process.stderr
    assert not output.exists()


def test_symlink_source_and_duplicate_json_key_rejected(tmp_path: Path) -> None:
    schedule, asset_map, schedule_path, asset_map_path = _fixture(tmp_path)
    real = Path(asset_map["inputs"]["task_contract"])
    link = tmp_path / "link"
    link.symlink_to(real)
    asset_map["inputs"]["task_contract"] = str(link)
    asset_map_path.write_text(json.dumps(asset_map), encoding="utf-8")
    process = _cli(schedule_path, asset_map_path, "--check")
    assert process.returncode == 2
    assert "cannot be read" in process.stderr
    assert str(tmp_path) not in process.stderr

    asset_map_path.write_text('{"schema":1,"schema":1}', encoding="utf-8")
    process = _cli(schedule_path, asset_map_path, "--check")
    assert process.returncode == 2
    assert "duplicate JSON object key" in process.stderr


def test_cli_rejects_relative_output_directory(tmp_path: Path) -> None:
    schedule, _, schedule_path, asset_map_path = _fixture(tmp_path)
    process = _cli(schedule_path, asset_map_path, "--run-id", schedule["runs"][0]["run_id"], "--output-dir", "relative")
    assert process.returncode == 2
    assert "absolute" in process.stderr
    assert not (tmp_path / "relative").exists()


def test_check_does_not_modify_source_modes(tmp_path: Path) -> None:
    _, asset_map, schedule_path, asset_map_path = _fixture(tmp_path)
    source = Path(asset_map["inputs"]["common_prompt"])
    os.chmod(source, 0o640)
    assert _cli(schedule_path, asset_map_path, "--check").returncode == 0
    assert source.stat().st_mode & 0o777 == 0o640
