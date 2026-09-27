"""Offline asset preflight verifies real bytes and isolates one run release."""

from __future__ import annotations

import copy
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
from local_block_release_gate import BlockReleaseError, verify_claim  # noqa: E402
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


def test_release_requires_explicit_mode_before_destination_creation(tmp_path: Path) -> None:
    schedule, assets, schedule_path, asset_map_path = _fixture(tmp_path)
    run_id = schedule["runs"][0]["run_id"]
    output = tmp_path / "unreleased"

    process = _cli(
        schedule_path, asset_map_path,
        "--run-id", run_id, "--output-dir", str(output),
    )

    assert process.returncode == 2
    assert "requires --gate-dir or --development-unsequenced" in process.stderr
    assert not output.exists()

    both = _cli(
        schedule_path, asset_map_path,
        "--run-id", run_id, "--output-dir", str(output),
        "--gate-dir", str(tmp_path / "gate"), "--development-unsequenced",
    )
    assert both.returncode == 2
    assert "not allowed with argument" in both.stderr
    assert not output.exists()

    with pytest.raises(preflight_assets.PreflightError, match="exactly one"):
        preflight_assets.preflight(assets_raw=assets, schedule_raw=schedule,
                                   run_id=run_id, output_dir=output)
    with pytest.raises(preflight_assets.PreflightError, match="exactly one"):
        preflight_assets.preflight(
            schedule, assets, run_id=run_id, output_dir=output,
            gate_root=tmp_path / "gate", development_unsequenced=True,
        )
    assert not output.exists()


def test_check_rejects_release_mode_without_writing(tmp_path: Path) -> None:
    _, _, schedule_path, asset_map_path = _fixture(tmp_path)
    gate = tmp_path / "gate"

    process = _cli(
        schedule_path, asset_map_path, "--check", "--gate-dir", str(gate)
    )

    assert process.returncode == 2
    assert "release mode requires --run-id" in process.stderr
    assert not gate.exists()


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

    process = _cli(schedule_path, asset_map_path, "--run-id", run["run_id"], "--output-dir", str(output), "--development-unsequenced")

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


def test_gated_release_claims_first_run_and_denies_second_before_output(tmp_path: Path) -> None:
    schedule, _, schedule_path, asset_map_path = _fixture(tmp_path)
    first, second = schedule["runs"][:2]
    assert (first["release_block_order"], first["order_position"]) == (1, 1)
    assert (second["release_block_order"], second["order_position"]) == (1, 2)
    gate = tmp_path / "gate"
    first_output = tmp_path / "release-first"
    second_output = tmp_path / "release-second"

    released = _cli(
        schedule_path, asset_map_path,
        "--run-id", first["run_id"], "--output-dir", str(first_output),
        "--gate-dir", str(gate),
    )
    assert released.returncode == 0, released.stderr
    assert (first_output / "manifest.json").is_file()
    claim = verify_claim(schedule, first["run_id"], gate, first_output)
    assert claim["run_id"] == first["run_id"]
    assert claim["release_dir"] == str(first_output)

    denied = _cli(
        schedule_path, asset_map_path,
        "--run-id", second["run_id"], "--output-dir", str(second_output),
        "--gate-dir", str(gate),
    )
    assert denied.returncode == 2
    assert "release gate rejected claim" in denied.stderr
    assert not second_output.exists()
    assert str(tmp_path) not in denied.stderr


def test_mutating_caller_schedule_after_claim_cannot_change_published_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    schedule, assets, _, _ = _fixture(tmp_path)
    snapshot = copy.deepcopy(schedule)
    first = schedule["runs"][0]
    gate = tmp_path / "gate"
    output = tmp_path / "release"
    original_claim = preflight_assets.claim_release

    def mutate_after_claim(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = original_claim(*args, **kwargs)
        schedule["per_run_limits"]["tool_calls"] = 24
        return result

    monkeypatch.setattr(preflight_assets, "claim_release", mutate_after_claim)
    manifest = preflight_assets.preflight(
        schedule, assets, run_id=first["run_id"], output_dir=output,
        gate_root=gate,
    )

    assert schedule["per_run_limits"]["tool_calls"] == 24
    assert manifest["limits"]["tool_calls"] == 23
    assert json.loads((output / "manifest.json").read_text(encoding="utf-8"))["limits"]["tool_calls"] == 23
    assert verify_claim(snapshot, first["run_id"], gate, output)["run_id"] == first["run_id"]


def test_gated_asset_error_occurs_before_claim(tmp_path: Path) -> None:
    schedule, assets, schedule_path, asset_map_path = _fixture(tmp_path)
    Path(assets["inputs"]["common_prompt"]).write_bytes(b"changed")
    gate = tmp_path / "gate"
    output = tmp_path / "release"

    process = _cli(
        schedule_path, asset_map_path,
        "--run-id", schedule["runs"][0]["run_id"],
        "--output-dir", str(output), "--gate-dir", str(gate),
    )

    assert process.returncode == 2
    assert "byte digest differs" in process.stderr
    assert not gate.exists()
    assert not output.exists()


def test_gated_existing_output_is_rejected_before_claim(tmp_path: Path) -> None:
    schedule, _, schedule_path, asset_map_path = _fixture(tmp_path)
    gate = tmp_path / "gate"
    output = tmp_path / "existing"
    output.mkdir()
    marker = output / "marker"
    marker.write_bytes(b"preserved")

    process = _cli(
        schedule_path, asset_map_path,
        "--run-id", schedule["runs"][0]["run_id"],
        "--output-dir", str(output), "--gate-dir", str(gate),
    )

    assert process.returncode == 2
    assert "already exists" in process.stderr
    assert not gate.exists()
    assert marker.read_bytes() == b"preserved"


def test_gated_copy_failure_leaves_active_claim_and_untrusted_partial_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    schedule, assets, _, _ = _fixture(tmp_path)
    first = schedule["runs"][0]
    gate = tmp_path / "gate"
    output = tmp_path / "release"

    def fail_copy(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise preflight_assets.PreflightError("synthetic copy failure")

    monkeypatch.setattr(preflight_assets, "_copy_verified_asset", fail_copy)
    with pytest.raises(preflight_assets.PreflightError, match="untrusted"):
        preflight_assets.preflight(
            schedule, assets, run_id=first["run_id"], output_dir=output,
            gate_root=gate,
        )

    assert output.is_dir()
    assert not (output / "manifest.json").exists()
    with pytest.raises(BlockReleaseError):
        verify_claim(schedule, first["run_id"], gate, output)


def test_gated_post_manifest_identity_failure_removes_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    schedule, assets, _, _ = _fixture(tmp_path)
    first = schedule["runs"][0]
    gate = tmp_path / "gate"
    output = tmp_path / "release"
    original = preflight_assets._directory_matches_name
    checked = 0

    def fail_after_manifest(directory_fd: int, parent_fd: int, name: str) -> bool:
        nonlocal checked
        checked += 1
        return checked == 1 and original(directory_fd, parent_fd, name)

    monkeypatch.setattr(preflight_assets, "_directory_matches_name", fail_after_manifest)
    with pytest.raises(preflight_assets.PreflightError, match="untrusted"):
        preflight_assets.preflight(
            schedule, assets, run_id=first["run_id"], output_dir=output,
            gate_root=gate,
        )

    assert checked == 2
    assert output.is_dir()
    assert not (output / "manifest.json").exists()
    with pytest.raises(BlockReleaseError):
        verify_claim(schedule, first["run_id"], gate, output)


def test_failed_manifest_cleanup_cannot_publish_pending_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    schedule, assets, _, _ = _fixture(tmp_path)
    first = schedule["runs"][0]
    gate = tmp_path / "gate"
    output = tmp_path / "release"
    original_unlink = os.unlink
    checked = 0
    published: list[bool] = []

    def fail_after_manifest(directory_fd: int, parent_fd: int, name: str) -> bool:
        nonlocal checked
        checked += 1
        return checked == 1

    def deny_unlink(path: str, *args: Any, **kwargs: Any) -> None:
        if path == "manifest.json" and kwargs.get("dir_fd") is not None:
            raise OSError("synthetic unlink failure")
        original_unlink(path, *args, **kwargs)

    def marker_must_not_run(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        published.append(True)
        raise AssertionError("publication marker reached after failed identity check")

    monkeypatch.setattr(preflight_assets, "_directory_matches_name", fail_after_manifest)
    monkeypatch.setattr(preflight_assets.os, "unlink", deny_unlink)
    monkeypatch.setattr(preflight_assets, "mark_published", marker_must_not_run)
    with pytest.raises(preflight_assets.PreflightError, match="untrusted"):
        preflight_assets.preflight(
            schedule, assets, run_id=first["run_id"], output_dir=output,
            gate_root=gate,
        )

    assert checked == 2
    assert not published
    assert (output / "manifest.json").is_file()
    with pytest.raises(BlockReleaseError):
        verify_claim(schedule, first["run_id"], gate, output)


def test_failed_publication_marker_leaves_pending_claim(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    schedule, assets, _, _ = _fixture(tmp_path)
    first = schedule["runs"][0]
    gate = tmp_path / "gate"
    output = tmp_path / "release"

    def deny_marker(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise BlockReleaseError("synthetic marker failure")

    monkeypatch.setattr(preflight_assets, "mark_published", deny_marker)
    with pytest.raises(preflight_assets.PreflightError, match="untrusted"):
        preflight_assets.preflight(
            schedule, assets, run_id=first["run_id"], output_dir=output,
            gate_root=gate,
        )

    assert output.is_dir()
    assert not (output / "manifest.json").exists()
    with pytest.raises(BlockReleaseError):
        verify_claim(schedule, first["run_id"], gate, output)


def test_gated_manifest_sync_failure_removes_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    schedule, assets, _, _ = _fixture(tmp_path)
    first = schedule["runs"][0]
    gate = tmp_path / "gate"
    output = tmp_path / "release"
    original_fsync = os.fsync
    failed = False

    def fail_release_directory_sync(fd: int) -> None:
        nonlocal failed
        if output.is_dir() and (output / "manifest.json").exists():
            opened = os.fstat(fd)
            named = output.stat()
            if (opened.st_dev, opened.st_ino) == (named.st_dev, named.st_ino) and not failed:
                failed = True
                raise OSError("synthetic manifest directory sync failure")
        original_fsync(fd)

    monkeypatch.setattr(preflight_assets.os, "fsync", fail_release_directory_sync)
    with pytest.raises(preflight_assets.PreflightError, match="untrusted"):
        preflight_assets.preflight(
            schedule, assets, run_id=first["run_id"], output_dir=output,
            gate_root=gate,
        )

    assert failed
    assert output.is_dir()
    assert not (output / "manifest.json").exists()
    with pytest.raises(BlockReleaseError):
        verify_claim(schedule, first["run_id"], gate, output)


def test_altered_source_bytes_fail_before_destination_creation(tmp_path: Path) -> None:
    schedule, asset_map, schedule_path, asset_map_path = _fixture(tmp_path)
    Path(asset_map["inputs"]["common_prompt"]).write_bytes(b"changed after planning")
    output = tmp_path / "must-not-exist"
    process = _cli(schedule_path, asset_map_path, "--run-id", schedule["runs"][0]["run_id"], "--output-dir", str(output), "--development-unsequenced")
    assert process.returncode == 2
    assert "byte digest differs" in process.stderr
    assert not output.exists()
    assert str(tmp_path) not in process.stderr


def test_forged_asset_map_digest_binding_rejected_before_writing(tmp_path: Path) -> None:
    schedule, asset_map, schedule_path, asset_map_path = _fixture(tmp_path)
    asset_map["schedule_sha256"] = "0" * 64
    asset_map_path.write_text(json.dumps(asset_map), encoding="utf-8")
    output = tmp_path / "must-not-exist"
    process = _cli(schedule_path, asset_map_path, "--run-id", schedule["runs"][0]["run_id"], "--output-dir", str(output), "--development-unsequenced")
    assert process.returncode == 2
    assert "digest binding" in process.stderr
    assert not output.exists()


def test_missing_hidden_reference_rejected_before_writing(tmp_path: Path) -> None:
    schedule, asset_map, schedule_path, asset_map_path = _fixture(tmp_path)
    Path(asset_map["cases"]["R-S"]["reference"]).unlink()
    output = tmp_path / "must-not-exist"
    process = _cli(schedule_path, asset_map_path, "--run-id", schedule["runs"][0]["run_id"], "--output-dir", str(output), "--development-unsequenced")
    assert process.returncode == 2
    assert "case:R-S:reference cannot be read" in process.stderr
    assert not output.exists()


def test_invalid_schedule_rejected_before_writing(tmp_path: Path) -> None:
    schedule, _, schedule_path, asset_map_path = _fixture(tmp_path)
    schedule["runs"][0]["order_position"] = 99
    schedule_path.write_text(json.dumps(schedule), encoding="utf-8")
    output = tmp_path / "must-not-exist"
    process = _cli(schedule_path, asset_map_path, "--run-id", schedule["runs"][0]["run_id"], "--output-dir", str(output), "--development-unsequenced")
    assert process.returncode == 2
    assert "invalid candidate schedule" in process.stderr
    assert not output.exists()


def test_existing_destination_is_never_deleted_or_overwritten(tmp_path: Path) -> None:
    schedule, _, schedule_path, asset_map_path = _fixture(tmp_path)
    output = tmp_path / "existing"
    output.mkdir()
    marker = output / "marker"
    marker.write_bytes(b"keep this")
    process = _cli(schedule_path, asset_map_path, "--run-id", schedule["runs"][0]["run_id"], "--output-dir", str(output), "--development-unsequenced")
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
    process = _cli(schedule_path, asset_map_path, "--run-id", run_id, "--output-dir", str(output), "--development-unsequenced")
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
        preflight_assets.preflight(schedule, asset_map, run_id=schedule["runs"][0]["run_id"], output_dir=output, development_unsequenced=True)
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
        preflight_assets.preflight(schedule, asset_map, run_id=schedule["runs"][0]["run_id"], output_dir=output, development_unsequenced=True)
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
        preflight_assets.preflight(schedule, asset_map, run_id=schedule["runs"][0]["run_id"], output_dir=output, development_unsequenced=True)
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
        preflight_assets.preflight(schedule, asset_map, run_id=schedule["runs"][0]["run_id"], output_dir=output, development_unsequenced=True)
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
        preflight_assets.preflight(schedule, asset_map, run_id=schedule["runs"][0]["run_id"], output_dir=output, development_unsequenced=True)
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
    process = _cli(schedule_path, asset_map_path, "--run-id", schedule["runs"][0]["run_id"], "--output-dir", str(output), "--development-unsequenced")
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
    process = _cli(schedule_path, asset_map_path, "--run-id", schedule["runs"][0]["run_id"], "--output-dir", "relative", "--development-unsequenced")
    assert process.returncode == 2
    assert "absolute" in process.stderr
    assert not (tmp_path / "relative").exists()


def test_check_does_not_modify_source_modes(tmp_path: Path) -> None:
    _, asset_map, schedule_path, asset_map_path = _fixture(tmp_path)
    source = Path(asset_map["inputs"]["common_prompt"])
    os.chmod(source, 0o640)
    assert _cli(schedule_path, asset_map_path, "--check").returncode == 0
    assert source.stat().st_mode & 0o777 == 0o640
