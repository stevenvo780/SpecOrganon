"""Integrated visible-content checks for unsealed, single-run releases."""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SCRIPT = SCRIPTS / "inspect_released_payload.py"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import case_package  # noqa: E402
import inspect_released_payload as inspector  # noqa: E402
import plan_confirmatory  # noqa: E402
import preflight_assets  # noqa: E402
import tool_policy  # noqa: E402
import toolkit_bundle  # noqa: E402
import verify_released_run  # noqa: E402
from toolkit_wheel_fixture import build_toolkit_wheel  # noqa: E402


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _reference(path: Path, data: bytes) -> dict[str, str]:
    path.write_bytes(data)
    return {"ref": f"synthetic/{path.name}", "sha256": _sha(data)}


def _model(family: str, tier: str) -> dict[str, Any]:
    controlled = tier == "higher"
    return {
        "family": family,
        "tier": tier,
        "model_id": f"{family}/{tier}",
        "version": "synthetic-v1",
        "effort_control": controlled,
        "efforts": (
            [
                {"label": "low", "provider_value": "low"},
                {"label": "high", "provider_value": "high"},
            ]
            if controlled
            else [{"label": "default"}]
        ),
    }


def _fixture(
    tmp_path: Path,
    *,
    corrupt_zip: bool = False,
    wrong_case_id: bool = False,
    policy_cap_mismatch: bool = False,
    corrupt_wheel: bool = False,
    toolkit_bundle_bytes: bytes | None = None,
    prompt_n: bytes = b"Arm N instructions.\n",
) -> tuple[dict[str, Any], dict[str, Any], Path, tuple[bytes, ...]]:
    source = tmp_path / "source"
    source.mkdir()
    cases: dict[str, Any] = {}
    case_manifest: list[dict[str, str]] = []
    hidden: list[bytes] = []
    for case_id in ("R-F", "R-M", "R-S"):
        package_source = source / f"case-{case_id}"
        package_source.mkdir()
        task = f"Visible task for {case_id}.\n".encode()
        data = f"value\n{case_id}\n".encode()
        (package_source / "task.md").write_bytes(task)
        (package_source / "data.csv").write_bytes(data)
        case = {
            "schema": 1,
            "classification": "executor_visible_case_package",
            "case_id": "R-M" if wrong_case_id and case_id == "R-F" else case_id,
            "task_file": "task.md",
            "files": [
                {"path": "task.md", "sha256": _sha(task), "bytes": len(task)},
                {"path": "data.csv", "sha256": _sha(data), "bytes": len(data)},
            ],
            "deliverables": ["report.md"],
        }
        (package_source / "case.json").write_text(json.dumps(case), encoding="utf-8")
        package = source / f"{case_id}.zip"
        case_package.pack_package(package_source, package)
        if corrupt_zip and case_id == "R-F":
            package.write_bytes(package.read_bytes() + b"undeclared ZIP trailer")
        reference = source / f"{case_id}.reference"
        secret = f"HIDDEN-REFERENCE-{case_id}".encode()
        hidden.append(secret)
        reference.write_bytes(secret)
        cases[case_id] = {"package": str(package), "reference": str(reference)}
        case_manifest.append(
            {
                "case_id": case_id,
                "package_sha256": _sha(package.read_bytes()),
                "reference_sha256": _sha(secret),
            }
        )

    input_paths: dict[str, Any] = {}
    input_manifest: dict[str, Any] = {}
    for role in ("task_contract", "common_prompt", "sdd_guide", "rubric", "toolkit"):
        path = source / role
        if role == "toolkit":
            payload = (
                toolkit_bundle_bytes
                if toolkit_bundle_bytes is not None
                else build_toolkit_wheel(path)
            )
            if corrupt_wheel:
                payload += b"undeclared ZIP trailer"
        elif role == "rubric":
            payload = b"HIDDEN-RUBRIC-SENTINEL"
        else:
            payload = f"Visible {role} instructions.\n".encode()
        input_paths[role] = str(path)
        input_manifest[role] = _reference(path, payload)
        if role == "rubric":
            hidden.append(payload)

    policy = {
        "schema": 1,
        "classification": "common_tool_policy_development_unenforced",
        "runtime_image_sha256": "a" * 64,
        "network": "disabled",
        "read_roots": ["/case"],
        "write_roots": ["/work"],
        "generic_tools": [
            {"id": "read_file", "version": "1.0", "executable_sha256": "b" * 64}
        ],
        "limits": {
            "measured_tokens": plan_confirmatory.TOKENS_PER_RUN,
            "active_seconds": plan_confirmatory.ACTIVE_SECONDS_PER_RUN,
            "tool_calls": 24 if policy_cap_mismatch else 23,
        },
    }
    policy_path = source / "tool_policy"
    input_paths["tool_policy"] = str(policy_path)
    input_manifest["tool_policy"] = _reference(
        policy_path, json.dumps(policy, sort_keys=True).encode()
    )

    input_paths["arm_prompts"] = {}
    input_manifest["arm_prompts"] = {}
    for arm in ("N", "S", "T"):
        path = source / f"prompt-{arm}"
        payload = prompt_n if arm == "N" else f"Arm {arm} instructions.\n".encode()
        input_paths["arm_prompts"][arm] = str(path)
        input_manifest["arm_prompts"][arm] = _reference(path, payload)

    raw = {
        "schema": 1,
        "seed": 29,
        "protocol_sha256": _sha(b"synthetic protocol"),
        "tool_call_cap": 23,
        "models": [
            _model(family, tier)
            for family in ("family-a", "family-b")
            for tier in ("lower", "higher")
        ],
        "cases": case_manifest,
        "inputs": input_manifest,
    }
    schedule = plan_confirmatory.compile_schedule(raw)
    schedule_path = tmp_path / "schedule.json"
    schedule_path.write_text(json.dumps(schedule), encoding="utf-8")
    assets = {
        "schema": 1,
        "schedule_sha256": schedule["schedule_sha256"],
        "input_sha256": schedule["input_sha256"],
        "cases": cases,
        "inputs": input_paths,
    }
    return schedule, assets, schedule_path, tuple(hidden)


def _release(
    tmp_path: Path, arm: str, case_id: str, **fixture_options: Any
) -> tuple[dict[str, Any], Path, Path, tuple[bytes, ...]]:
    schedule, assets, schedule_path, hidden = _fixture(tmp_path, **fixture_options)
    run = next(
        item
        for item in schedule["runs"]
        if item["arm"] == arm and item["case_id"] == case_id
    )
    release = tmp_path / "release"
    preflight_assets.preflight(
        schedule, assets, run_id=run["run_id"], output_dir=release,
        development_unsequenced=True,
    )
    assert (
        verify_released_run.verify_release(schedule, release)["run_id"] == run["run_id"]
    )
    return schedule, schedule_path, release, hidden


def _cli(schedule_path: Path, release: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), str(schedule_path), str(release)],
        capture_output=True,
        text=True,
        check=False,
    )


def _bundle_bytes(
    tmp_path: Path, *, dependency: bool = False, python_version: str = "3.12"
) -> bytes:
    build_dir = tmp_path / "bundle-build"
    wheels = build_dir / "wheels"
    wheels.mkdir(parents=True)
    build_toolkit_wheel(wheels / "specorganon-0.1.0-py3-none-any.whl")
    lock = build_dir / "uv.lock"
    lock_text = (
        'version = 1\n[[package]]\nname = "specorganon"\n'
        'version = "0.1.0"\nsource = { editable = "." }\n'
    )
    if dependency:
        filename = "demo_dep-1.0-py3-none-any.whl"
        payload = b"synthetic dependency bytes; wheel internals are uninspected\n"
        (wheels / filename).write_bytes(payload)
        lock_text += (
            '\n[[package]]\nname = "demo-dep"\nversion = "1.0"\n'
            'source = { registry = "https://example.invalid/simple" }\n'
            f'wheels = [{{ url = "https://example.invalid/{filename}", '
            f'hash = "sha256:{_sha(payload)}", size = {len(payload)} }}]\n'
        )
    lock.write_text(lock_text, encoding="utf-8")
    output = build_dir / "toolkit.zip"
    toolkit_bundle.pack_toolkit_bundle(
        wheels,
        lock,
        {
            "python_implementation": "CPython",
            "python_version": python_version,
            "platform": "linux_x86_64",
        },
        output,
    )
    return output.read_bytes()


@pytest.mark.parametrize(
    "arm,case_id,expected_roles",
    [
        (
            "N",
            "R-F",
            {
                "case_package",
                "tool_policy",
                "task_contract",
                "common_prompt",
                "arm_prompt",
            },
        ),
        (
            "S",
            "R-M",
            {
                "case_package",
                "tool_policy",
                "task_contract",
                "common_prompt",
                "arm_prompt",
                "sdd_guide",
            },
        ),
        (
            "T",
            "R-S",
            {
                "case_package",
                "tool_policy",
                "task_contract",
                "common_prompt",
                "arm_prompt",
                "toolkit",
            },
        ),
    ],
)
def test_integrated_inspection_is_read_only_and_never_claims_execution(
    tmp_path: Path, arm: str, case_id: str, expected_roles: set[str]
) -> None:
    schedule, schedule_path, release, hidden = _release(tmp_path, arm, case_id)
    before = {
        path.name: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in release.iterdir()
    }

    process = _cli(schedule_path, release)

    assert process.returncode == 0, process.stderr
    result = json.loads(process.stdout)
    assert result["classification"] == inspector.CLASSIFICATION
    assert result["schema"] == 1
    assert result["attempt_number"] == 1
    assert result["arm"] == arm
    assert result["case_id"] == case_id
    assert result["run_sha256"] in {run["run_sha256"] for run in schedule["runs"]}
    assert result["schedule_sha256"] == schedule["schedule_sha256"]
    assert result["case_package_sha256"] == next(
        case["package_sha256"]
        for case in schedule["cases"]
        if case["case_id"] == case_id
    )
    assert result["tool_policy_sha256"] == schedule["inputs"]["tool_policy"]["sha256"]
    assert set(result["validated_roles"]) == expected_roles
    assert set(result["outer_hash_verified_roles"]) == expected_roles | (
        {"toolkit"} if arm == "T" else set()
    )
    assert result["case_manifest_summary"] == {
        "classification": "executor_visible_case_package",
        "case_id": case_id,
        "file_count": 2,
        "source_bytes": len(f"Visible task for {case_id}.\n".encode())
        + len(f"value\n{case_id}\n".encode()),
        "deliverable_count": 1,
    }
    assert result["toolkit_format_checked"] is (arm == "T")
    assert result["toolkit_format"] == ("wheel" if arm == "T" else None)
    assert result["toolkit_bundle_checked"] is False
    assert result["toolkit_container_format_checked"] is False
    assert result["toolkit_root_wheel_format_checked"] is (arm == "T")
    assert result["toolkit_dependency_wheel_format_checked"] is False
    assert result["toolkit_wheel_count"] == (1 if arm == "T" else None)
    assert result["toolkit_target"] is None
    assert result["toolkit_version"] == ("0.1.0" if arm == "T" else None)
    assert result["toolkit_dependencies_checked"] is False
    assert result["toolkit_install_checked"] is False
    assert result["execution_ready"] is False
    assert "unauthenticated" in " ".join(result["limitations"])
    assert "telemetry" in " ".join(result["limitations"])
    assert "receipts" in " ".join(result["limitations"])
    assert ("toolkit" in result["validated_roles"]) is (arm == "T")
    assert {
        path.name: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in release.iterdir()
    } == before
    released_bytes = b"".join(path.read_bytes() for path in release.iterdir())
    for marker in hidden:
        assert marker not in released_bytes
        assert marker not in process.stdout.encode()
    assert str(tmp_path) not in process.stdout + process.stderr


def test_inspection_carries_retry_attempt_and_rejects_tampered_number(tmp_path: Path) -> None:
    schedule, schedule_path, release, _ = _release(tmp_path, "N", "R-F")
    manifest_path = release / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema"] = 2
    manifest["attempt_number"] = 2
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    valid = _cli(schedule_path, release)

    assert valid.returncode == 0, valid.stderr
    assert json.loads(valid.stdout)["attempt_number"] == 2
    assert inspector.inspect_released_payload(schedule, release)["attempt_number"] == 2

    manifest["attempt_number"] = True
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    tampered = _cli(schedule_path, release)
    assert tampered.returncode == 2
    assert tampered.stdout == ""


@pytest.mark.parametrize("arm", ["N", "S", "T"])
def test_bundle_is_inspected_only_when_released_to_t(tmp_path: Path, arm: str) -> None:
    bundle = _bundle_bytes(tmp_path)
    schedule, schedule_path, release, _ = _release(
        tmp_path,
        arm,
        "R-F",
        toolkit_bundle_bytes=bundle,
    )
    result = _cli(schedule_path, release)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["execution_ready"] is False
    assert report["toolkit_install_checked"] is False
    assert report["toolkit_dependencies_checked"] is False
    assert report["toolkit_bundle_checked"] is (arm == "T")
    assert report["toolkit_container_format_checked"] is (arm == "T")
    assert report["toolkit_root_wheel_format_checked"] is (arm == "T")
    assert report["toolkit_dependency_wheel_format_checked"] is False
    assert report["toolkit_format"] == ("bundle" if arm == "T" else None)
    assert report["toolkit_wheel_count"] == (1 if arm == "T" else None)
    assert report["toolkit_target"] == (
        {
            "python_implementation": "CPython",
            "python_version": "3.12",
            "platform": "linux_x86_64",
        }
        if arm == "T"
        else None
    )
    assert (release / "toolkit").exists() is (arm == "T")
    if arm == "T":
        assert (release / "toolkit").read_bytes() == bundle
        assert report["toolkit_version"] == "0.1.0"
        assert report["toolkit_format_checked"] is True
        assert schedule["inputs"]["toolkit"]["sha256"] == _sha(bundle)


def test_bundle_outer_hash_passes_but_tampered_member_fails_content_gate(
    tmp_path: Path,
) -> None:
    bundle = bytearray(_bundle_bytes(tmp_path))
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        member = next(
            info
            for info in archive.infolist()
            if info.filename == "wheels/specorganon-0.1.0-py3-none-any.whl"
        )
    position = member.header_offset + 30 + len(member.filename.encode()) + 10
    bundle[position] ^= 1
    _, schedule_path, release, _ = _release(
        tmp_path,
        "T",
        "R-F",
        toolkit_bundle_bytes=bytes(bundle),
    )
    result = _cli(schedule_path, release)
    assert result.returncode == 2
    assert result.stdout == ""
    assert "toolkit content inspection failed" in result.stderr


def test_bundle_with_dependency_reports_uninspected_wheel_in_release(
    tmp_path: Path,
) -> None:
    bundle = _bundle_bytes(tmp_path, dependency=True)
    _, schedule_path, release, _ = _release(
        tmp_path,
        "T",
        "R-F",
        toolkit_bundle_bytes=bundle,
    )
    result = _cli(schedule_path, release)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["toolkit_bundle_checked"] is True
    assert report["toolkit_container_format_checked"] is True
    assert report["toolkit_root_wheel_format_checked"] is True
    assert report["toolkit_dependency_wheel_format_checked"] is False
    assert report["toolkit_format_checked"] is False
    assert report["toolkit_wheel_count"] == 2
    assert report["execution_ready"] is False


def test_bundle_target_311_is_preserved_in_released_t(tmp_path: Path) -> None:
    bundle = _bundle_bytes(tmp_path, python_version="3.11")
    _, schedule_path, release, _ = _release(
        tmp_path,
        "T",
        "R-F",
        toolkit_bundle_bytes=bundle,
    )
    result = _cli(schedule_path, release)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["toolkit_format"] == "bundle"
    assert report["toolkit_target"]["python_version"] == "3.11"
    assert report["execution_ready"] is False


@pytest.mark.parametrize(
    "arm,case_id,options,error",
    [
        ("N", "R-F", {"corrupt_zip": True}, "case_package inspection failed"),
        ("N", "R-F", {"wrong_case_id": True}, "case_package inspection failed"),
        ("S", "R-M", {"policy_cap_mismatch": True}, "tool_policy inspection failed"),
        ("N", "R-F", {"prompt_n": b"\xffbad UTF-8"}, "arm_prompt is not strict UTF-8"),
        ("N", "R-F", {"prompt_n": b"bad\x00prompt"}, "arm_prompt must be nonempty"),
        ("T", "R-S", {"corrupt_wheel": True}, "toolkit content inspection failed"),
    ],
)
def test_outer_hashes_can_pass_while_content_gate_rejects(
    tmp_path: Path, arm: str, case_id: str, options: dict[str, Any], error: str
) -> None:
    _, schedule_path, release, hidden = _release(tmp_path, arm, case_id, **options)

    process = _cli(schedule_path, release)

    assert process.returncode == 2
    assert process.stdout == ""
    assert error in process.stderr
    assert str(tmp_path) not in process.stderr
    assert all(marker not in process.stderr.encode() for marker in hidden)


def test_final_release_reverification_detects_substitution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    schedule, _, release, _ = _release(tmp_path, "N", "R-F")
    original = tool_policy.inspect_tool_policy

    def change_after_policy(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = original(*args, **kwargs)
        (release / "tool_policy").write_bytes(b"changed after policy inspection")
        return result

    monkeypatch.setattr(inspector, "inspect_tool_policy", change_after_policy)
    with pytest.raises(
        inspector.PayloadInspectionError, match="release changed during inspection"
    ):
        inspector.inspect_released_payload(schedule, release)
