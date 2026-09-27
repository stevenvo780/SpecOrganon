"""Visible case round trip and hostile-package controls."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import warnings
import zipfile
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "case_package.py"
ENERGY = ROOT / "cases" / "building_energy"
sys.path.insert(0, str(SCRIPT.parent))
import case_package  # noqa: E402


def _cli(*args: Path | str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *(str(arg) for arg in args)],
        capture_output=True,
        text=True,
        check=False,
    )


def _source(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    source = tmp_path / "source"
    source.mkdir()
    task = b"Solve the visible case.\n"
    data = b"value\n2\n"
    (source / "task.md").write_bytes(task)
    (source / "data.csv").write_bytes(data)
    manifest = {
        "schema": 1,
        "classification": "executor_visible_case_package",
        "case_id": "R-F",
        "task_file": "task.md",
        "files": [
            {
                "path": "task.md",
                "sha256": hashlib.sha256(task).hexdigest(),
                "bytes": len(task),
            },
            {
                "path": "data.csv",
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
            },
        ],
        "deliverables": ["analysis.py", "report.md"],
    }
    (source / "case.json").write_text(json.dumps(manifest), encoding="utf-8")
    return source, manifest


def _zip(
    target: Path,
    manifest_bytes: bytes,
    members: dict[str, bytes],
    *,
    method: int = zipfile.ZIP_STORED,
    mode: int = stat.S_IFREG | 0o600,
) -> None:
    with zipfile.ZipFile(target, "w", allowZip64=False) as archive:
        for name, payload in {"case.json": manifest_bytes, **members}.items():
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = method
            info.create_system = 3
            info.external_attr = mode << 16
            archive.writestr(info, payload)


def _reject_before_destination(package: Path, destination: Path) -> None:
    with pytest.raises(case_package.CasePackageError):
        case_package.extract_package(package, destination)
    assert not destination.exists()


def test_exposed_development_case_round_trip_and_determinism(tmp_path: Path) -> None:
    source = tmp_path / "energy"
    shutil.copytree(ENERGY, source)
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    extracted = tmp_path / "extracted"

    packed = _cli("pack", source, first)
    assert packed.returncode == 0, packed.stderr
    inspected = _cli("inspect", first, "--expected-case-id", "D-E")
    assert inspected.returncode == 0, inspected.stderr
    manifest = json.loads(inspected.stdout)
    assert manifest["case_id"] == "D-E"
    assert manifest["classification"] == "executor_visible_case_package"
    assert {item["path"] for item in manifest["files"]} == {
        "task.md",
        "source_manifest.json",
        "sample_first_complete_week.csv",
    }
    assert manifest["deliverables"] == ["analysis.py", "report.md"]

    for file in source.iterdir():
        os.utime(file, ns=(1_000_000_000_000_000_000, 1_000_000_000_000_000_000))
    assert _cli("pack", source, second).returncode == 0
    assert first.read_bytes() == second.read_bytes()
    assert (
        _cli("extract", first, extracted, "--expected-case-id", "D-E").returncode == 0
    )
    for path in ("case.json", *(item["path"] for item in manifest["files"])):
        assert (source / path).read_bytes() == (extracted / path).read_bytes()
    assert stat.S_IMODE(extracted.stat().st_mode) == 0o700
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o600 for path in extracted.iterdir()
    )
    assert _cli("extract", first, extracted).returncode == 2
    assert extracted.is_dir()
    assert _cli("pack", source, first).returncode == 2
    assert first.read_bytes() == second.read_bytes()
    assert _cli("inspect", first, "--expected-case-id", "R-F").returncode == 2
    assert (
        _cli(
            "extract", first, tmp_path / "wrong", "--expected-case-id", "R-F"
        ).returncode
        == 2
    )
    assert not (tmp_path / "wrong").exists()


@pytest.mark.parametrize(
    "change",
    [
        "hidden_reference",
        "duplicate_json_key",
        "nonfinite",
        "huge_exponent",
        "wrong_schema",
        "missing_task",
        "traversal",
        "absolute",
        "backslash",
        "nul",
        "drive",
        "case_alias",
        "casefold_duplicate",
        "source_collision",
        "nested_deliverable",
        "oversized_entry",
        "wrong_hash",
        "wrong_size",
    ],
)
def test_invalid_source_manifest_never_creates_archive(
    tmp_path: Path, change: str
) -> None:
    source, manifest = _source(tmp_path)
    if change == "hidden_reference":
        manifest["reference"] = "secret.md"
    elif change == "duplicate_json_key":
        (source / "case.json").write_bytes(
            (source / "case.json")
            .read_bytes()
            .replace(b'"schema": 1', b'"schema": 1, "schema": 1')
        )
    elif change == "nonfinite":
        (source / "case.json").write_bytes(
            (source / "case.json")
            .read_bytes()
            .replace(b'"schema": 1', b'"schema": NaN')
        )
    elif change == "huge_exponent":
        (source / "case.json").write_bytes(
            (source / "case.json")
            .read_bytes()
            .replace(b'"schema": 1', b'"schema": 1e999')
        )
    elif change == "wrong_schema":
        manifest["schema"] = True
    elif change == "missing_task":
        manifest["task_file"] = "missing.md"
    elif change in {"traversal", "absolute", "backslash", "nul", "drive", "case_alias"}:
        manifest["files"][1]["path"] = {
            "traversal": "../data.csv",
            "absolute": "/tmp/data.csv",
            "backslash": "dir\\data.csv",
            "nul": "data\x00.csv",
            "drive": "C:/data.csv",
            "case_alias": "CASE.JSON",
        }[change]
    elif change == "casefold_duplicate":
        manifest["files"][1]["path"] = "TASK.md"
    elif change == "source_collision":
        manifest["deliverables"] = ["TASK.MD"]
    elif change == "nested_deliverable":
        manifest["deliverables"] = ["out/report.md"]
    elif change == "oversized_entry":
        manifest["files"][1]["bytes"] = case_package.MAX_ENTRY_BYTES + 1
    elif change == "wrong_hash":
        manifest["files"][1]["sha256"] = "0" * 64
    else:
        manifest["files"][1]["bytes"] += 1
    if change not in {"duplicate_json_key", "nonfinite", "huge_exponent"}:
        (source / "case.json").write_text(json.dumps(manifest), encoding="utf-8")
    package = tmp_path / "invalid.zip"
    with pytest.raises(case_package.CasePackageError):
        case_package.pack_package(source, package)
    assert not package.exists()


def test_pack_rejects_symlinked_source_file(tmp_path: Path) -> None:
    source, _ = _source(tmp_path)
    (source / "data.csv").rename(source / "outside.csv")
    (source / "data.csv").symlink_to("outside.csv")
    with pytest.raises(case_package.CasePackageError):
        case_package.pack_package(source, tmp_path / "case.zip")
    assert not (tmp_path / "case.zip").exists()


@pytest.mark.parametrize(
    "attack",
    [
        "compressed",
        "symlink",
        "directory",
        "extra_member",
        "traversal_member",
        "casefold_member",
        "wrong_payload",
        "zip_comment",
        "prefix",
        "suffix",
        "encrypted_flag",
        "local_name_mismatch",
        "unlisted_nested",
    ],
)
def test_inspection_rejects_malicious_zip_before_extract(
    tmp_path: Path, attack: str
) -> None:
    source, manifest = _source(tmp_path)
    raw_manifest = (source / "case.json").read_bytes()
    members = {
        "task.md": (source / "task.md").read_bytes(),
        "data.csv": (source / "data.csv").read_bytes(),
    }
    package = tmp_path / "hostile.zip"
    if attack == "wrong_payload":
        members["data.csv"] = b"value\n9\n"
    elif attack == "extra_member":
        members["reference.md"] = b"hidden answer"
    elif attack == "traversal_member":
        members["../escape"] = b"outside"
    elif attack == "casefold_member":
        members["DATA.csv"] = b"duplicate"
    elif attack == "unlisted_nested":
        members["answers/rubric.md"] = b"secret"
    mode = (
        stat.S_IFLNK | 0o777
        if attack == "symlink"
        else (stat.S_IFDIR | 0o700 if attack == "directory" else stat.S_IFREG | 0o600)
    )
    _zip(
        package,
        raw_manifest,
        members,
        method=zipfile.ZIP_DEFLATED if attack == "compressed" else zipfile.ZIP_STORED,
        mode=mode,
    )
    if attack == "zip_comment":
        with zipfile.ZipFile(package, "a") as archive:
            archive.comment = b"hidden metadata"
    elif attack == "prefix":
        package.write_bytes(b"junk" + package.read_bytes())
    elif attack == "suffix":
        package.write_bytes(package.read_bytes() + b"junk")
    elif attack == "encrypted_flag":
        payload = bytearray(package.read_bytes())
        payload[6] |= 1
        central = payload.index(b"PK\x01\x02")
        payload[central + 8] |= 1
        package.write_bytes(payload)
    elif attack == "local_name_mismatch":
        payload = bytearray(package.read_bytes())
        first_name = payload.index(b"case.json")
        payload[first_name : first_name + 9] = b"cAse.json"
        package.write_bytes(payload)
    assert manifest["case_id"] == "R-F"
    _reject_before_destination(package, tmp_path / "extracted")


def test_independent_regular_zip_and_bogus_format(tmp_path: Path) -> None:
    source, manifest = _source(tmp_path)
    package = tmp_path / "plain.zip"
    _zip(
        package,
        (source / "case.json").read_bytes(),
        {name: (source / name).read_bytes() for name in ("task.md", "data.csv")},
    )
    assert case_package.inspect_package(package, expected_case_id="R-F") == manifest
    assert (
        case_package.extract_package(
            package, tmp_path / "plain", expected_case_id="R-F"
        )
        == manifest
    )
    assert (tmp_path / "plain" / "data.csv").read_bytes() == (
        source / "data.csv"
    ).read_bytes()
    bogus = tmp_path / "bogus.zip"
    bogus.write_bytes(b"not a ZIP package")
    _reject_before_destination(bogus, tmp_path / "bogus-out")


def test_inspect_pinned_fd_survives_path_replacement_and_preserves_offset(
    tmp_path: Path,
) -> None:
    source, manifest = _source(tmp_path)
    package = tmp_path / "case.zip"
    _zip(
        package,
        (source / "case.json").read_bytes(),
        {name: (source / name).read_bytes() for name in ("task.md", "data.csv")},
    )
    fd = os.open(package, os.O_RDONLY)
    try:
        os.lseek(fd, 7, os.SEEK_SET)
        package.rename(tmp_path / "original.zip")
        package.write_bytes(b"replacement is not a case package")
        assert case_package.inspect_package_fd(fd, expected_case_id="R-F") == manifest
        assert os.lseek(fd, 0, os.SEEK_CUR) == 7
        with pytest.raises(case_package.CasePackageError, match="case_id differs"):
            case_package.inspect_package_fd(fd, expected_case_id="D-E")
        with pytest.raises(case_package.CasePackageError):
            case_package.inspect_package(package)
    finally:
        os.close(fd)


def test_inspect_pinned_fd_rejects_corrupt_member(tmp_path: Path) -> None:
    source, _ = _source(tmp_path)
    package = tmp_path / "corrupt.zip"
    _zip(
        package,
        (source / "case.json").read_bytes(),
        {"task.md": (source / "task.md").read_bytes(), "data.csv": b"forged"},
    )
    fd = os.open(package, os.O_RDONLY)
    try:
        with pytest.raises(case_package.CasePackageError):
            case_package.inspect_package_fd(fd, expected_case_id="R-F")
    finally:
        os.close(fd)


def test_duplicate_zip_member_rejected(tmp_path: Path) -> None:
    source, _ = _source(tmp_path)
    package = tmp_path / "duplicate.zip"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(package, "w") as archive:
            for name in ("case.json", "task.md", "data.csv", "task.md"):
                info = zipfile.ZipInfo(name)
                info.compress_type = zipfile.ZIP_STORED
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o600) << 16
                archive.writestr(info, (source / name).read_bytes())
    _reject_before_destination(package, tmp_path / "duplicate-out")


def test_directory_prefix_collision_rejected_before_destination(tmp_path: Path) -> None:
    source, manifest = _source(tmp_path)
    data = b"x"
    manifest["files"].append(
        {
            "path": "data.csv/nested",
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": 1,
        }
    )
    package = tmp_path / "collision.zip"
    _zip(
        package,
        json.dumps(manifest).encode(),
        {
            "task.md": (source / "task.md").read_bytes(),
            "data.csv": (source / "data.csv").read_bytes(),
            "data.csv/nested": data,
        },
    )
    _reject_before_destination(package, tmp_path / "collision-out")


def test_nested_source_file_extracts_without_following_parent_symlink(
    tmp_path: Path,
) -> None:
    source, manifest = _source(tmp_path)
    nested = source / "data"
    nested.mkdir()
    (source / "data.csv").rename(nested / "values.csv")
    manifest["files"][1]["path"] = "data/values.csv"
    (source / "case.json").write_text(json.dumps(manifest), encoding="utf-8")
    package = tmp_path / "nested.zip"
    case_package.pack_package(source, package)
    output = tmp_path / "nested-out"
    case_package.extract_package(package, output)
    assert (output / "data" / "values.csv").read_bytes() == (
        nested / "values.csv"
    ).read_bytes()
    assert stat.S_IMODE((output / "data").stat().st_mode) == 0o700

    parent = tmp_path / "real-parent"
    parent.mkdir()
    (tmp_path / "linked-parent").symlink_to(parent, target_is_directory=True)
    with pytest.raises(case_package.CasePackageError):
        case_package.extract_package(package, tmp_path / "linked-parent" / "new")
    assert not (parent / "new").exists()


def test_bounded_zip_metadata_rejected_before_extraction(tmp_path: Path) -> None:
    source, _ = _source(tmp_path)
    package = tmp_path / "large-manifest.zip"
    _zip(
        package,
        b" " * (case_package.MAX_CASE_JSON_BYTES + 1),
        {
            "task.md": (source / "task.md").read_bytes(),
            "data.csv": (source / "data.csv").read_bytes(),
        },
    )
    _reject_before_destination(package, tmp_path / "large-manifest-out")


def test_extraction_requires_controlled_parent_and_stable_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, _ = _source(tmp_path)
    package = tmp_path / "case.zip"
    case_package.pack_package(source, package)

    writable = tmp_path / "writable"
    writable.mkdir()
    writable.chmod(0o777)
    with pytest.raises(case_package.CasePackageError, match="destination parent"):
        case_package.extract_package(package, writable / "new")
    assert not (writable / "new").exists()

    destination = tmp_path / "substituted"
    original_copy = case_package._copy_member
    copied = 0

    def replace_after_first(*args: Any, **kwargs: Any) -> None:
        nonlocal copied
        original_copy(*args, **kwargs)
        copied += 1
        if copied == 1:
            destination.rename(tmp_path / "moved-original")
            destination.mkdir(mode=0o700)

    monkeypatch.setattr(case_package, "_copy_member", replace_after_first)
    with pytest.raises(
        case_package.CasePackageError,
        match="destination identity.*partial destination is untrusted",
    ):
        case_package.extract_package(package, destination)
    assert (tmp_path / "moved-original" / "case.json").exists()
    assert not (destination / "task.md").exists()


def test_inspection_rejects_symlinked_archive_parent(tmp_path: Path) -> None:
    source, _ = _source(tmp_path)
    parent = tmp_path / "actual"
    parent.mkdir()
    package = parent / "case.zip"
    case_package.pack_package(source, package)
    (tmp_path / "alias").symlink_to(parent, target_is_directory=True)
    with pytest.raises(case_package.CasePackageError):
        case_package.inspect_package(tmp_path / "alias" / "case.zip")


def test_extraction_fails_if_ancestor_is_replaced_during_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, _ = _source(tmp_path)
    package = tmp_path / "case.zip"
    case_package.pack_package(source, package)
    unstable = tmp_path / "unstable"
    unstable.mkdir()
    safe = unstable / "safe"
    safe.mkdir()
    destination = safe / "new"
    original_copy = case_package._copy_member
    moved = False

    def move_parent_during_copy(*args: Any, **kwargs: Any) -> None:
        nonlocal moved
        original_copy(*args, **kwargs)
        if not moved:
            moved = True
            safe.rename(unstable / "safe_moved")
            safe.mkdir()

    monkeypatch.setattr(case_package, "_copy_member", move_parent_during_copy)
    with pytest.raises(
        case_package.CasePackageError,
        match="destination ancestor identity.*partial destination is untrusted",
    ):
        case_package.extract_package(package, destination)
    assert moved
    assert not destination.exists()
    assert (unstable / "safe_moved" / "new" / "case.json").exists()
