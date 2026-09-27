"""An independently read stage is still only an unsealed observation."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SCRIPT = SCRIPTS / "verify_staged_run.py"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage_released_run as staging  # noqa: E402
import plan_confirmatory  # noqa: E402
import test_inspect_released_payload as fixture  # noqa: E402
import test_stage_released_run as stage_fixture  # noqa: E402
import verify_staged_run as verifier  # noqa: E402


def _stage(
    tmp_path: Path, arm: str, *, bundle: bool = False
) -> tuple[dict, Path, Path, dict]:
    bundle_bytes = fixture._bundle_bytes(tmp_path, dependency=True) if bundle else None
    schedule, schedule_path, release, _ = stage_fixture._released(
        tmp_path, arm, toolkit_bundle_bytes=bundle_bytes
    )
    stage = tmp_path / "stage"
    published = staging.stage_released_run(schedule, release, stage)
    return schedule, schedule_path, stage, published


def _write_manifest(path: Path, manifest: dict) -> None:
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    )


@pytest.mark.parametrize("arm", ["N", "S", "T"])
def test_verifies_published_stage_by_api_and_cli(tmp_path: Path, arm: str) -> None:
    schedule, schedule_path, stage, published = _stage(tmp_path, arm)
    before = {
        str(path.relative_to(stage)): (path.stat().st_mtime_ns, path.read_bytes())
        for path in stage.rglob("*")
        if path.is_file()
    }
    result = verifier.verify_stage(schedule, published["run_id"], stage)
    assert result["classification"] == verifier.CLASSIFICATION
    assert result["run_id"] == published["run_id"]
    assert result["schedule_sha256"] == schedule["schedule_sha256"]
    assert result["verified_files"] == len(published["visible_files"])
    assert result["verified_case_files"] == 3
    assert result["stage_verified_at_read"] is True
    assert result["execution_ready"] is False
    assert result["runtime_enforced"] is False
    assert result["custody_verified"] is False
    process = subprocess.run(
        [
            sys.executable,
            "-B",
            str(SCRIPT),
            str(schedule_path),
            published["run_id"],
            str(stage),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout) == result
    assert before == {
        str(path.relative_to(stage)): (path.stat().st_mtime_ns, path.read_bytes())
        for path in stage.rglob("*")
        if path.is_file()
    }


def test_verifies_bundle_stage_without_installing(tmp_path: Path) -> None:
    schedule, _, stage, published = _stage(tmp_path, "T", bundle=True)
    assert published["toolkit_format"] == "bundle"
    assert (
        verifier.verify_stage(schedule, published["run_id"], stage)[
            "stage_verified_at_read"
        ]
        is True
    )
    assert list((stage / "work").iterdir()) == []


@pytest.mark.parametrize(
    "mutation",
    [
        "altered_input",
        "extra_input",
        "case_mutation",
        "work_symlink",
        "work_replaced_by_symlink",
        "hardlinked_input",
        "symlinked_input",
        "hardlinked_case_file",
    ],
)
def test_rejects_stage_mutation(tmp_path: Path, mutation: str) -> None:
    schedule, _, stage, published = _stage(tmp_path, "N")
    if mutation == "altered_input":
        (stage / "inputs" / "arm_prompt").write_bytes(b"Changed arm N instructions.\n")
    elif mutation == "extra_input":
        (stage / "inputs" / "rubric").write_text("hidden extra role")
    elif mutation == "case_mutation":
        (stage / "case" / "task.md").write_text("Changed task")
    elif mutation == "work_symlink":
        (stage / "work" / "escape").symlink_to(tmp_path)
    elif mutation == "work_replaced_by_symlink":
        (stage / "work").rmdir()
        (stage / "work").symlink_to(tmp_path, target_is_directory=True)
    elif mutation == "hardlinked_input":
        os.link(stage / "inputs" / "arm_prompt", tmp_path / "linked_prompt")
    elif mutation == "symlinked_input":
        prompt = stage / "inputs" / "arm_prompt"
        prompt.rename(tmp_path / "moved_prompt")
        prompt.symlink_to(tmp_path / "moved_prompt")
    else:
        os.link(stage / "case" / "task.md", tmp_path / "linked_task")
    with pytest.raises(verifier.StageVerificationError):
        verifier.verify_stage(schedule, published["run_id"], stage)


def test_rejects_swapped_arm_and_schedule_mismatch(tmp_path: Path) -> None:
    schedule, _, stage, published = _stage(tmp_path, "N")
    other_run_id = next(
        run["run_id"]
        for run in schedule["runs"]
        if run["arm"] == "S" and run["case_id"] == "R-F"
    )
    with pytest.raises(verifier.StageVerificationError):
        verifier.verify_stage(schedule, other_run_id, stage)
    altered_schedule = copy.deepcopy(schedule)
    altered_schedule["per_run_limits"]["tool_calls"] += 1
    with pytest.raises(verifier.StageVerificationError, match="candidate schedule"):
        verifier.verify_stage(altered_schedule, published["run_id"], stage)


@pytest.mark.parametrize(
    "field,value",
    [
        ("execution_ready", True),
        ("runtime_enforced", True),
        ("provider_receipts_checked", True),
        ("custody_verified", True),
        ("toolkit_install_checked", True),
        ("classification", "development_release_unsealed"),
        ("schema", True),
        ("extra", "unapproved"),
    ],
)
def test_rejects_altered_manifest(tmp_path: Path, field: str, value: object) -> None:
    schedule, _, stage, published = _stage(tmp_path, "N")
    manifest = json.loads((stage / "stage.json").read_text())
    manifest[field] = value
    _write_manifest(stage / "stage.json", manifest)
    with pytest.raises(verifier.StageVerificationError):
        verifier.verify_stage(schedule, published["run_id"], stage)


def test_rejects_duplicate_manifest_key(tmp_path: Path) -> None:
    schedule, _, stage, published = _stage(tmp_path, "N")
    original = (stage / "stage.json").read_text()
    (stage / "stage.json").write_text(
        original.replace('"schema":1', '"schema":1,"schema":1', 1)
    )
    with pytest.raises(verifier.StageVerificationError):
        verifier.verify_stage(schedule, published["run_id"], stage)


def test_caller_mutation_after_snapshot_cannot_change_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    schedule, _, stage, published = _stage(tmp_path, "S")
    original_limits = copy.deepcopy(schedule["per_run_limits"])
    original_read = verifier._read_stage_manifest

    def mutate_after_snapshot(root_fd: int, stack: object) -> tuple:
        schedule["per_run_limits"]["tool_calls"] += 1
        return original_read(root_fd, stack)

    monkeypatch.setattr(verifier, "_read_stage_manifest", mutate_after_snapshot)
    report = verifier.verify_stage(schedule, published["run_id"], stage)
    assert report["stage_verified_at_read"] is True
    assert schedule["per_run_limits"] != original_limits
    assert published["limits"] == original_limits


def test_rejects_case_mutation_between_two_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    schedule, _, stage, published = _stage(tmp_path, "N")
    original_inspection = verifier._inspect_visible_content

    def mutate_between_reads(*args: object) -> tuple:
        result = original_inspection(*args)
        task = stage / "case" / "task.md"
        original = task.read_bytes()
        task.write_bytes(b"different")
        task.write_bytes(original)
        return result

    monkeypatch.setattr(verifier, "_inspect_visible_content", mutate_between_reads)
    with pytest.raises(verifier.StageVerificationError):
        verifier.verify_stage(schedule, published["run_id"], stage)


def test_rejects_role_mutation_during_last_case_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    schedule, _, stage, published = _stage(tmp_path, "N")
    original_tree = verifier._verify_case_tree
    calls = 0

    def mutate_during_last_case_check(*args: object) -> tuple:
        nonlocal calls
        calls += 1
        result = original_tree(*args)
        if calls == 2:
            prompt = stage / "inputs" / "arm_prompt"
            original = prompt.read_bytes()
            prompt.write_bytes(b"different")
            prompt.write_bytes(original)
        return result

    monkeypatch.setattr(verifier, "_verify_case_tree", mutate_during_last_case_check)
    with pytest.raises(verifier.StageVerificationError):
        verifier.verify_stage(schedule, published["run_id"], stage)


def test_rejects_pinned_package_despite_temporary_ancestor_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    schedule, _, stage, published = _stage(tmp_path, "N")
    package = stage / "inputs" / "case_package"
    clean_bytes = package.read_bytes()
    malformed_bytes = clean_bytes + b"undeclared ZIP trailer"
    package.write_bytes(malformed_bytes)
    malformed_sha = hashlib.sha256(malformed_bytes).hexdigest()

    raw = {
        key: copy.deepcopy(schedule[key])
        for key in ("schema", "seed", "protocol_sha256", "models", "cases", "inputs")
    }
    raw["tool_call_cap"] = schedule["per_run_limits"]["tool_calls"]
    next(case for case in raw["cases"] if case["case_id"] == "R-F")[
        "package_sha256"
    ] = malformed_sha
    candidate = plan_confirmatory.compile_schedule(raw)
    old_run = next(
        run for run in schedule["runs"] if run["run_id"] == published["run_id"]
    )
    candidate_run = next(
        run
        for run in candidate["runs"]
        if all(
            run[key] == old_run[key]
            for key in ("arm", "case_id", "model_id", "effort", "agents", "replica")
        )
    )
    manifest_path = stage / "stage.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["run_id"] = candidate_run["run_id"]
    manifest["run_sha256"] = candidate_run["run_sha256"]
    manifest["schedule_sha256"] = candidate["schedule_sha256"]
    manifest["visible_files"]["case_package"]["sha256"] = malformed_sha
    manifest["visible_files"]["case_package"]["bytes"] = len(malformed_bytes)
    _write_manifest(manifest_path, manifest)

    with pytest.raises(verifier.StageVerificationError):
        verifier.verify_stage(candidate, candidate_run["run_id"], stage)

    holder = stage.parent
    alternate = tmp_path.parent / f"{tmp_path.name}-alternate"
    alternate.mkdir(mode=0o700)
    shutil.copytree(stage, alternate / stage.name)
    (alternate / stage.name / "inputs" / "case_package").write_bytes(clean_bytes)
    original = verifier.inspect_package_fd
    calls = 0

    def inspect_while_ancestor_swapped(*args: object, **kwargs: object) -> dict:
        nonlocal calls
        calls += 1
        saved = tmp_path.parent / f"{tmp_path.name}-saved"
        os.rename(holder, saved)
        os.rename(alternate, holder)
        try:
            return original(*args, **kwargs)
        finally:
            os.rename(holder, alternate)
            os.rename(saved, holder)

    monkeypatch.setattr(verifier, "inspect_package_fd", inspect_while_ancestor_swapped)
    with pytest.raises(verifier.StageVerificationError):
        verifier.verify_stage(candidate, candidate_run["run_id"], stage)
    assert calls == 1
    assert package.read_bytes() == malformed_bytes
