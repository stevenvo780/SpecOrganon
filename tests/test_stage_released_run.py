"""A visible release becomes a private stage without hidden inputs or execution claims."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SCRIPT = SCRIPTS / "stage_released_run.py"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import case_package  # noqa: E402
import local_block_release_gate as gate  # noqa: E402
import preflight_assets  # noqa: E402
import stage_released_run as staging  # noqa: E402
import test_inspect_released_payload as fixture  # noqa: E402


def _released(
    tmp_path: Path, arm: str, *, toolkit_bundle_bytes: bytes | None = None
) -> tuple[dict, Path, Path, tuple[bytes, ...]]:
    schedule, assets, schedule_path, hidden = fixture._fixture(
        tmp_path, toolkit_bundle_bytes=toolkit_bundle_bytes
    )
    run = next(
        item
        for item in schedule["runs"]
        if item["arm"] == arm and item["case_id"] == "R-F"
    )
    release = tmp_path / "release"
    preflight_assets.preflight(
        schedule,
        assets,
        run_id=run["run_id"],
        output_dir=release,
        development_unsequenced=True,
    )
    return schedule, schedule_path, release, hidden


@pytest.mark.parametrize(
    "arm,expected_roles",
    [
        (
            "N",
            {
                "case_package",
                "task_contract",
                "common_prompt",
                "arm_prompt",
                "tool_policy",
            },
        ),
        (
            "S",
            {
                "case_package",
                "task_contract",
                "common_prompt",
                "arm_prompt",
                "tool_policy",
                "sdd_guide",
            },
        ),
        (
            "T",
            {
                "case_package",
                "task_contract",
                "common_prompt",
                "arm_prompt",
                "tool_policy",
                "toolkit",
            },
        ),
    ],
)
def test_stage_real_release_with_only_selected_visible_bytes(
    tmp_path: Path, arm: str, expected_roles: set[str]
) -> None:
    schedule, schedule_path, release, hidden = _released(tmp_path, arm)
    release_before = {
        path.name: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in release.iterdir()
    }
    output = tmp_path / "stage"
    process = subprocess.run(
        [
            sys.executable,
            "-B",
            str(SCRIPT),
            str(schedule_path),
            str(release),
            str(output),
            "--development-unsequenced",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 0, process.stderr
    report = json.loads(process.stdout)
    assert json.loads((output / "stage.json").read_text()) == report
    assert report["classification"] == staging.CLASSIFICATION
    assert report["coordinates"]["arm"] == arm
    assert report["coordinates"]["case_id"] == "R-F"
    assert report["schedule_sha256"] == schedule["schedule_sha256"]
    assert report["execution_ready"] is False
    assert report["runtime_enforced"] is False
    assert report["provider_receipts_checked"] is False
    assert report["custody_verified"] is False
    assert set(report["visible_files"]) == expected_roles
    assert {path.name for path in output.iterdir()} == {
        "case",
        "inputs",
        "work",
        "stage.json",
    }
    assert {path.name for path in (output / "inputs").iterdir()} == expected_roles
    assert list((output / "work").iterdir()) == []
    assert (output / "case" / "task.md").read_text() == "Visible task for R-F.\n"
    assert (output / "case" / "data.csv").read_text() == "value\nR-F\n"
    assert report["case_task_file"] == "task.md"
    assert report["deliverables"] == ["report.md"]
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    for directory in (output / "case", output / "inputs", output / "work"):
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    for role, item in report["visible_files"].items():
        source = (output / "inputs" / role).read_bytes()
        assert item["bytes"] == len(source)
        assert item["sha256"] == hashlib.sha256(source).hexdigest()
    for path in output.rglob("*"):
        assert not path.is_symlink()
        if path.is_file():
            assert stat.S_IMODE(path.stat().st_mode) == 0o600
            for secret in hidden:
                assert secret not in path.read_bytes()
    assert release_before == {
        path.name: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in release.iterdir()
    }


def test_stage_t_bundle_keeps_311_target_and_does_not_install(
    tmp_path: Path,
) -> None:
    bundle = fixture._bundle_bytes(tmp_path, dependency=True, python_version="3.11")
    schedule, _, release, _ = _released(tmp_path, "T", toolkit_bundle_bytes=bundle)
    output = tmp_path / "stage"
    report = staging.stage_released_run(
        schedule, release, output, development_unsequenced=True
    )
    assert report["toolkit_format"] == "bundle"
    assert report["toolkit_target"]["python_version"] == "3.11"
    assert report["toolkit_install_checked"] is False
    assert report["execution_ready"] is False
    assert (output / "inputs" / "toolkit").read_bytes() == bundle
    assert not (output / "work" / "organon.json").exists()


@pytest.mark.parametrize("mutation", ["changed_prompt", "extra_file"])
def test_rejects_bad_release_before_creating_stage(
    tmp_path: Path, mutation: str
) -> None:
    schedule, _, release, _ = _released(tmp_path, "N")
    if mutation == "changed_prompt":
        (release / "arm_prompt").write_bytes(b"different instructions\n")
    else:
        (release / "rubric").write_bytes(b"hidden data must not be released")
    output = tmp_path / "stage"
    with pytest.raises(staging.StageError, match="verification or visible inspection"):
        staging.stage_released_run(schedule, release, output, development_unsequenced=True)
    assert not output.exists()


def test_mutation_after_inspection_fails_before_stage_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    schedule, _, release, _ = _released(tmp_path, "S")
    original_inspect = staging.inspect_released_payload

    def change_after_inspection(schedule_raw: dict, release_dir: Path) -> dict:
        report = original_inspect(schedule_raw, release_dir)
        (release / "arm_prompt").write_bytes(b"Altered arm S instructions.\n")
        return report

    monkeypatch.setattr(staging, "inspect_released_payload", change_after_inspection)
    output = tmp_path / "stage"
    with pytest.raises(staging.StageError):
        staging.stage_released_run(schedule, release, output, development_unsequenced=True)
    assert not (output / "stage.json").exists()


def test_replaced_case_archive_during_extraction_does_not_stage_hidden_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    schedule, _, release, hidden = _released(tmp_path, "N")
    alternate_source = tmp_path / "alternate-case"
    shutil.copytree(tmp_path / "source" / "case-R-F", alternate_source)
    (alternate_source / "task.md").write_bytes(hidden[0])
    manifest_path = alternate_source / "case.json"
    manifest = json.loads(manifest_path.read_text())
    task = next(item for item in manifest["files"] if item["path"] == "task.md")
    task["bytes"] = len(hidden[0])
    task["sha256"] = hashlib.sha256(hidden[0]).hexdigest()
    manifest_path.write_text(json.dumps(manifest))
    alternate = tmp_path / "alternate.zip"
    case_package.pack_package(alternate_source, alternate)
    real_extract = staging.extract_package

    def swap_during_extract(
        archive_path: Path, destination: Path, **kwargs: str
    ) -> dict:
        source = Path(archive_path)
        original = source.read_bytes()
        source.write_bytes(alternate.read_bytes())
        try:
            return real_extract(archive_path, destination, **kwargs)
        finally:
            source.write_bytes(original)

    monkeypatch.setattr(staging, "extract_package", swap_during_extract)
    output = tmp_path / "stage"
    with pytest.raises(staging.StageError):
        staging.stage_released_run(schedule, release, output, development_unsequenced=True)
    assert hidden[0] == (output / "case" / "task.md").read_bytes()
    assert not (output / "stage.json").exists()


@pytest.mark.parametrize("mutation", ["case_file", "work_symlink"])
def test_post_extraction_mutation_cannot_gain_stage_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    schedule, _, release, hidden = _released(tmp_path, "N")
    outside = tmp_path / "outside"
    outside.mkdir()
    real_extract = staging.extract_package

    def mutate_after_extract(
        archive_path: Path, destination: Path, **kwargs: str
    ) -> dict:
        result = real_extract(archive_path, destination, **kwargs)
        if mutation == "case_file":
            (Path(destination) / "task.md").write_bytes(hidden[0])
        else:
            work = Path(destination).parent / "work"
            work.rmdir()
            work.symlink_to(outside, target_is_directory=True)
        return result

    monkeypatch.setattr(staging, "extract_package", mutate_after_extract)
    output = tmp_path / "stage"
    with pytest.raises(staging.StageError):
        staging.stage_released_run(schedule, release, output, development_unsequenced=True)
    assert not (output / "stage.json").exists()


def test_existing_destination_is_not_replaced(tmp_path: Path) -> None:
    schedule, _, release, _ = _released(tmp_path, "N")
    output = tmp_path / "stage"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("preserve me")
    with pytest.raises(staging.StageError):
        staging.stage_released_run(schedule, release, output, development_unsequenced=True)
    assert sentinel.read_text() == "preserve me"


def test_failure_after_pending_write_does_not_publish_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    schedule, _, release, _ = _released(tmp_path, "N")
    original_write = staging._write_pending_manifest

    def fail_after_pending(root_fd: int, manifest: dict) -> None:
        original_write(root_fd, manifest)
        raise OSError("injected failure after pending write")

    monkeypatch.setattr(staging, "_write_pending_manifest", fail_after_pending)
    output = tmp_path / "stage"
    with pytest.raises(staging.StageError):
        staging.stage_released_run(schedule, release, output, development_unsequenced=True)
    assert (output / ".stage.json.pending").exists()
    assert not (output / "stage.json").exists()


def test_mutating_caller_schedule_cannot_change_published_limits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    schedule, _, release, _ = _released(tmp_path, "N")
    original_limits = schedule["per_run_limits"].copy()
    original_sha256 = schedule["schedule_sha256"]
    original_write = staging._write_pending_manifest

    def mutate_before_write(root_fd: int, manifest: dict) -> None:
        schedule["per_run_limits"]["tool_calls"] = original_limits["tool_calls"] + 1
        original_write(root_fd, manifest)

    monkeypatch.setattr(staging, "_write_pending_manifest", mutate_before_write)
    output = tmp_path / "stage"
    report = staging.stage_released_run(
        schedule, release, output, development_unsequenced=True
    )
    published = json.loads((output / "stage.json").read_text())
    assert schedule["per_run_limits"] != original_limits
    assert report == published
    assert published["limits"] == original_limits
    assert published["schedule_sha256"] == original_sha256
    assert (
        json.loads((release / "manifest.json").read_text())["limits"] == original_limits
    )


def test_nested_case_tree_is_rehashed_and_detects_tampering(tmp_path: Path) -> None:
    source = tmp_path / "nested-source"
    (source / "nested").mkdir(parents=True)
    (source / "task.md").write_bytes(b"Visible nested task\n")
    (source / "nested" / "data.csv").write_bytes(b"value\n42\n")
    files = [
        {
            "path": path,
            "sha256": hashlib.sha256((source / path).read_bytes()).hexdigest(),
            "bytes": (source / path).stat().st_size,
        }
        for path in ("task.md", "nested/data.csv")
    ]
    (source / "case.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "classification": "executor_visible_case_package",
                "case_id": "R-F",
                "task_file": "task.md",
                "files": files,
                "deliverables": ["report.md"],
            }
        )
    )
    archive = tmp_path / "nested.zip"
    case_package.pack_package(source, archive)
    case = tmp_path / "case"
    manifest = case_package.extract_package(archive, case, expected_case_id="R-F")
    with zipfile.ZipFile(archive) as zipped:
        case_json = zipped.read("case.json")
    case_fd = os.open(case, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        staging._verify_case_tree(case_fd, manifest, case_json)
        (case / "nested" / "data.csv").write_bytes(b"value\n43\n")
        with pytest.raises(staging.StageError, match="extracted case bytes differ"):
            staging._verify_case_tree(case_fd, manifest, case_json)
    finally:
        os.close(case_fd)


def test_requires_absolute_new_destination(tmp_path: Path) -> None:
    schedule, _, release, _ = _released(tmp_path, "N")
    with pytest.raises(staging.StageError, match="must be absolute"):
        staging.stage_released_run(
            schedule, release, Path("relative-stage"), development_unsequenced=True
        )
    assert not (Path.cwd() / "relative-stage").exists()


def test_cli_requires_an_explicit_stage_mode(tmp_path: Path) -> None:
    _, schedule_path, release, _ = _released(tmp_path, "N")
    output = tmp_path / "stage"
    process = subprocess.run(
        [sys.executable, "-B", str(SCRIPT), str(schedule_path), str(release), str(output)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 2
    assert "--gate-dir" in process.stderr
    assert "--development-unsequenced" in process.stderr
    assert not output.exists()


def test_gate_rejects_missing_claim_before_stage_output(tmp_path: Path) -> None:
    schedule, _, release, _ = _released(tmp_path, "N")
    output = tmp_path / "stage"
    with pytest.raises(staging.StageError, match="release gate rejected stage"):
        staging.stage_released_run(
            schedule, release, output, gate_root=tmp_path / "unclaimed-gate"
        )
    assert not output.exists()


def test_gate_binds_stage_to_claimed_run_and_release(tmp_path: Path) -> None:
    schedule, assets, schedule_path, _ = fixture._fixture(tmp_path)
    run = schedule["runs"][0]
    gate_root = tmp_path / "gate"
    release = tmp_path / "release"
    preflight_assets.preflight(
        schedule,
        assets,
        run_id=run["run_id"],
        output_dir=release,
        gate_root=gate_root,
    )
    claim = gate.verify_claim(schedule, run["run_id"], gate_root, release)
    assert claim["run_id"] == run["run_id"]

    other_release = tmp_path / "other-release"
    shutil.copytree(release, other_release)
    rejected_stage = tmp_path / "rejected-stage"
    with pytest.raises(staging.StageError, match="release gate rejected stage"):
        staging.stage_released_run(
            schedule, other_release, rejected_stage, gate_root=gate_root
        )
    assert not rejected_stage.exists()

    stage = tmp_path / "stage"
    process = subprocess.run(
        [
            sys.executable,
            "-B",
            str(SCRIPT),
            str(schedule_path),
            str(release),
            str(stage),
            "--gate-dir",
            str(gate_root),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 0, process.stderr
    report = json.loads(process.stdout)
    assert report["run_id"] == run["run_id"]
    assert (stage / "stage.json").is_file()


def test_api_rejects_ambiguous_stage_mode(tmp_path: Path) -> None:
    schedule, _, release, _ = _released(tmp_path, "N")
    output = tmp_path / "stage"
    with pytest.raises(staging.StageError, match="exactly one"):
        staging.stage_released_run(schedule, release, output)
    with pytest.raises(staging.StageError, match="exactly one"):
        staging.stage_released_run(
            schedule,
            release,
            output,
            gate_root=tmp_path / "gate",
            development_unsequenced=True,
        )
    assert not output.exists()
