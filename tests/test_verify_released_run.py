"""Read-only consumer checks for one unsealed development release."""

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

from test_preflight_assets import _fixture


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SCRIPT = SCRIPTS / "verify_released_run.py"
sys.path.insert(0, str(SCRIPTS))
import preflight_assets  # noqa: E402
import verify_released_run as consumer  # noqa: E402


def _release(tmp_path: Path, arm: str = "N") -> tuple[dict[str, Any], Path, Path]:
    schedule, assets, schedule_path, _assets_path = _fixture(tmp_path)
    run = next(
        item
        for item in schedule["runs"]
        if item["arm"] == arm and item["case_id"] == "R-M"
    )
    output = tmp_path / f"release-{arm}"
    preflight_assets.preflight(
        schedule, assets, run_id=run["run_id"], output_dir=output,
        development_unsequenced=True,
    )
    return schedule, schedule_path, output


def _cli(
    schedule_path: Path, release_dir: Path | str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(schedule_path), str(release_dir)],
        capture_output=True,
        text=True,
        check=False,
    )


def _manifest(path: Path) -> dict[str, Any]:
    return json.loads((path / "manifest.json").read_text(encoding="utf-8"))


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    (path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


@pytest.mark.parametrize("arm,expected_count", [("N", 5), ("S", 6), ("T", 6)])
def test_cli_verifies_valid_release_without_writes(
    tmp_path: Path, arm: str, expected_count: int
) -> None:
    schedule, schedule_path, output = _release(tmp_path, arm)
    before = {
        item: (item.stat().st_mtime_ns, item.read_bytes() if item.is_file() else None)
        for item in output.iterdir()
    }

    process = _cli(schedule_path, output)

    assert process.returncode == 0, process.stderr
    result = json.loads(process.stdout)
    assert result == {
        "schema": 1,
        "classification": "development_release_verification_unsealed",
        "notice": consumer.VERIFICATION_NOTICE,
        "run_id": _manifest(output)["run_id"],
        "run_sha256": _manifest(output)["run_sha256"],
        "schedule_sha256": schedule["schedule_sha256"],
        "verified_files": expected_count,
        "verified_bytes": sum(
            (output / role).stat().st_size for role in _manifest(output)["files"]
        ),
    }
    assert {
        item: (item.stat().st_mtime_ns, item.read_bytes() if item.is_file() else None)
        for item in output.iterdir()
    } == before
    assert (
        "receipt" not in result
        and "authorized" not in result
        and "executed" not in result
    )


def test_changed_bytes_rejected_even_after_manifest_digest_forgery(
    tmp_path: Path,
) -> None:
    _, schedule_path, output = _release(tmp_path)
    changed = b"forged package\n"
    (output / "case_package").write_bytes(changed)
    manifest = _manifest(output)
    manifest["files"]["case_package"]["sha256"] = hashlib.sha256(changed).hexdigest()
    manifest["files"]["case_package"]["bytes"] = len(changed)
    _write_manifest(output, manifest)

    process = _cli(schedule_path, output)

    assert process.returncode == 2
    assert "digest differs from schedule" in process.stderr
    assert process.stdout == ""


def test_changed_bytes_rejected_with_unchanged_manifest(tmp_path: Path) -> None:
    _, schedule_path, output = _release(tmp_path)
    target = output / "tool_policy"
    target.write_bytes(b"x" * target.stat().st_size)

    process = _cli(schedule_path, output)

    assert process.returncode == 2
    assert "bytes differ from schedule" in process.stderr


@pytest.mark.parametrize(
    "change",
    [
        "schema",
        "classification",
        "notice",
        "top_extra",
        "coordinate",
        "coordinate_extra",
        "limits",
        "run_sha256",
        "schedule_sha256",
        "unknown_run",
        "missing_role",
        "extra_role",
        "entry_extra",
        "entry_file",
        "entry_digest",
        "entry_bytes_bool",
    ],
)
def test_manifest_forgery_is_rejected(tmp_path: Path, change: str) -> None:
    _, schedule_path, output = _release(tmp_path)
    manifest = _manifest(output)
    if change == "schema":
        manifest["schema"] = True
    elif change == "classification":
        manifest["classification"] = "sealed_release"
    elif change == "notice":
        manifest["notice"] = "Execution authorized."
    elif change == "top_extra":
        manifest["receipt"] = "fake"
    elif change == "coordinate":
        manifest["coordinates"]["replica"] = (
            2 if manifest["coordinates"]["replica"] != 2 else 3
        )
    elif change == "coordinate_extra":
        manifest["coordinates"]["authorized"] = True
    elif change == "limits":
        manifest["limits"]["tool_calls"] += 1
    elif change == "run_sha256":
        manifest["run_sha256"] = "0" * 64
    elif change == "schedule_sha256":
        manifest["schedule_sha256"] = "0" * 64
    elif change == "unknown_run":
        manifest["run_id"] = "conf-unknown"
    elif change == "missing_role":
        del manifest["files"]["tool_policy"]
    elif change == "extra_role":
        manifest["files"]["rubric"] = copy.deepcopy(manifest["files"]["tool_policy"])
    elif change == "entry_extra":
        manifest["files"]["tool_policy"]["source"] = "fake"
    elif change == "entry_file":
        manifest["files"]["tool_policy"]["file"] = "../tool_policy"
    elif change == "entry_digest":
        manifest["files"]["tool_policy"]["sha256"] = "0" * 64
    else:
        manifest["files"]["tool_policy"]["bytes"] = True
    _write_manifest(output, manifest)

    process = _cli(schedule_path, output)

    assert process.returncode == 2
    assert process.stdout == ""
    assert str(tmp_path) not in process.stderr


@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "extra",
        "symlink",
        "manifest_symlink",
        "fifo",
        "hardlink",
        "world_readable",
    ],
)
def test_directory_or_asset_substitution_is_rejected(
    tmp_path: Path, change: str
) -> None:
    _, schedule_path, output = _release(tmp_path)
    target = output / "task_contract"
    if change == "missing":
        target.unlink()
    elif change == "extra":
        (output / "extra").write_text("surprise", encoding="utf-8")
    elif change == "symlink":
        outside = tmp_path / "same-bytes"
        outside.write_bytes(target.read_bytes())
        target.unlink()
        target.symlink_to(outside)
    elif change == "manifest_symlink":
        target = output / "manifest.json"
        outside = tmp_path / "same-manifest"
        outside.write_bytes(target.read_bytes())
        target.unlink()
        target.symlink_to(outside)
    elif change == "fifo":
        target.unlink()
        os.mkfifo(target)
    elif change == "hardlink":
        os.link(target, tmp_path / "outside-hardlink")
    else:
        target.chmod(0o644)

    process = _cli(schedule_path, output)

    assert process.returncode == 2
    assert process.stdout == ""
    assert str(tmp_path) not in process.stderr


@pytest.mark.parametrize(
    "change",
    [
        "release_symlink",
        "parent_symlink",
        "parent_writable",
        "release_permissive",
        "relative",
        "traversal",
        "double_slash",
    ],
)
def test_unsafe_release_path_is_rejected(tmp_path: Path, change: str) -> None:
    _, schedule_path, output = _release(tmp_path)
    candidate: Path | str = output
    if change == "release_symlink":
        candidate = tmp_path / "release-link"
        candidate.symlink_to(output, target_is_directory=True)
    elif change == "parent_symlink":
        link = tmp_path / "parent-link"
        link.symlink_to(tmp_path, target_is_directory=True)
        candidate = link / output.name
    elif change == "parent_writable":
        tmp_path.chmod(0o777)
    elif change == "release_permissive":
        output.chmod(0o755)
    elif change == "traversal":
        candidate = f"{tmp_path}/../{tmp_path.name}/{output.name}"
    elif change == "double_slash":
        candidate = f"{tmp_path}//{output.name}"
    else:
        candidate = output.name

    process = _cli(schedule_path, candidate)

    assert process.returncode == 2
    assert process.stdout == ""
    assert str(tmp_path) not in process.stderr


@pytest.mark.parametrize(
    "where,value",
    [
        ("manifest", b'{"schema":1,"schema":1}'),
        ("schedule", b'{"schema":1,"schema":1}'),
        ("manifest", b'{"schema":NaN}'),
        ("schedule", b'{"schema":Infinity}'),
        ("manifest", b'{"schema":1e999}'),
        ("schedule", b'{"schema":-1e999}'),
    ],
)
def test_duplicate_keys_and_nonfinite_json_are_rejected(
    tmp_path: Path, where: str, value: bytes
) -> None:
    _, schedule_path, output = _release(tmp_path)
    target = output / "manifest.json" if where == "manifest" else schedule_path
    target.write_bytes(value)

    process = _cli(schedule_path, output)

    assert process.returncode == 2
    assert process.stdout == ""
    assert (
        "duplicate" in process.stderr
        or "numeric" in process.stderr
        or "nonfinite" in process.stderr
    )


def test_unpaired_unicode_surrogate_is_rejected_cleanly(tmp_path: Path) -> None:
    _, schedule_path, output = _release(tmp_path)
    manifest = _manifest(output)
    manifest["coordinates"]["family"] = "\ud800"
    _write_manifest(output, manifest)

    process = _cli(schedule_path, output)

    assert process.returncode == 2
    assert "invalid JSON data" in process.stderr
    assert "Traceback" not in process.stderr


def test_invalid_candidate_schedule_is_rejected(tmp_path: Path) -> None:
    schedule, schedule_path, output = _release(tmp_path)
    schedule["runs"][0]["order_position"] = 99
    schedule_path.write_text(json.dumps(schedule), encoding="utf-8")

    process = _cli(schedule_path, output)

    assert process.returncode == 2
    assert "invalid candidate schedule" in process.stderr


@pytest.mark.parametrize("change", ["symlink", "fifo"])
def test_nonregular_schedule_source_is_rejected(tmp_path: Path, change: str) -> None:
    _, schedule_path, output = _release(tmp_path)
    if change == "symlink":
        link = tmp_path / "schedule-link.json"
        link.symlink_to(schedule_path)
        schedule_path = link
    else:
        pipe = tmp_path / "schedule-fifo"
        os.mkfifo(pipe)
        schedule_path = pipe

    process = _cli(schedule_path, output)

    assert process.returncode == 2
    assert "candidate schedule" in process.stderr
    assert process.stdout == ""


def test_directory_replacement_during_hash_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    schedule, _, output = _release(tmp_path)
    moved = tmp_path / "moved-original"
    original_hash = consumer._hash_fd
    swapped = False

    def replace_during_hash(fd: int) -> tuple[str, int]:
        nonlocal swapped
        if not swapped:
            output.rename(moved)
            output.mkdir(mode=0o700)
            swapped = True
        return original_hash(fd)

    monkeypatch.setattr(consumer, "_hash_fd", replace_during_hash)
    with pytest.raises(consumer.ReleaseVerificationError, match="identity"):
        consumer.verify_release(schedule, output)
