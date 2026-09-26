"""Static bundle round trips and hostile ZIP/lock controls without downloads."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import struct
import subprocess
import sys
import warnings
import zipfile
from pathlib import Path
from typing import Any

import pytest

from toolkit_wheel_fixture import build_toolkit_wheel


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SCRIPT = SCRIPTS / "toolkit_bundle.py"
sys.path.insert(0, str(SCRIPTS))
import toolkit_bundle as bundle  # noqa: E402


ROOT = "specorganon-0.1.0-py3-none-any.whl"
DEPENDENCY = "demo_dep-1.0-py3-none-any.whl"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sources(tmp_path: Path, *, dependency: bool = True) -> tuple[Path, Path]:
    wheel_dir = tmp_path / "wheels"
    wheel_dir.mkdir()
    build_toolkit_wheel(wheel_dir / ROOT)
    lock = tmp_path / "uv.lock"
    text = 'version = 1\n[[package]]\nname = "specorganon"\nversion = "0.1.0"\nsource = { editable = "." }\n'
    if dependency:
        payload = b"synthetic dependency wheel bytes; never installed\n"
        (wheel_dir / DEPENDENCY).write_bytes(payload)
        text += (
            '\n[[package]]\nname = "demo-dep"\nversion = "1.0"\n'
            'source = { registry = "https://example.invalid/simple" }\n'
            f'wheels = [{{ url = "https://example.invalid/{DEPENDENCY}", '
            f'hash = "sha256:{_sha(payload)}", size = {len(payload)} }}]\n'
        )
    lock.write_text(text, encoding="utf-8")
    return wheel_dir, lock


def _pack(
    tmp_path: Path, *, dependency: bool = True
) -> tuple[Path, Path, Path, dict[str, Any]]:
    wheel_dir, lock = _sources(tmp_path, dependency=dependency)
    output = tmp_path / "toolkit.bundle"
    result = bundle.pack_toolkit_bundle(wheel_dir, lock, bundle.DEFAULT_TARGET, output)
    return wheel_dir, lock, output, result


def _rewrite(
    original: Path,
    target: Path,
    *,
    replacements: dict[str, bytes] | None = None,
    extra: tuple[str, bytes] | None = None,
    missing: str | None = None,
    compression: int = zipfile.ZIP_STORED,
    mode: int = stat.S_IFREG | 0o600,
    zip_extra: bytes = b"",
) -> None:
    with zipfile.ZipFile(original) as source:
        members = [(info.filename, source.read(info)) for info in source.infolist()]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(target, "w", allowZip64=False) as output:
            for name, data in members + ([extra] if extra is not None else []):
                if name == missing:
                    continue
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = mode << 16
                info.compress_type = compression
                info.extra = zip_extra
                output.writestr(info, (replacements or {}).get(name, data))


def _manifest(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        return json.loads(archive.read("bundle.json"))


def _canonical(raw: Any) -> bytes:
    return json.dumps(
        raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()


def test_pack_inspect_extract_and_determinism(tmp_path: Path) -> None:
    wheel_dir, lock, output, packed = _pack(tmp_path)
    second = tmp_path / "second.bundle"
    assert (
        bundle.pack_toolkit_bundle(wheel_dir, lock, bundle.DEFAULT_TARGET, second)
        == packed
    )
    assert output.read_bytes() == second.read_bytes()
    assert bundle.inspect_toolkit_bundle(output) == packed
    assert packed == {
        "schema": 1,
        "classification": "development_toolkit_bundle_inspection_unsealed",
        "sha256": _sha(output.read_bytes()),
        "version": "0.1.0",
        "wheel_count": 2,
        "target": bundle.DEFAULT_TARGET,
        "uv_lock_sha256": _sha(lock.read_bytes()),
        "container_format_checked": True,
        "root_wheel_format_checked": True,
        "dependency_wheel_format_checked": False,
        "static_format_checked": False,
        "install_checked": False,
        "execution_ready": False,
    }
    with zipfile.ZipFile(output) as archive:
        assert archive.namelist() == [
            "bundle.json",
            "uv.lock",
            f"wheels/{DEPENDENCY}",
            f"wheels/{ROOT}",
        ]
        assert all(
            info.compress_type == zipfile.ZIP_STORED for info in archive.infolist()
        )
        assert archive.read("uv.lock") == lock.read_bytes()
        assert archive.read(f"wheels/{ROOT}") == (wheel_dir / ROOT).read_bytes()
    extracted = tmp_path / "extracted"
    assert bundle.extract_toolkit_bundle(output, extracted) == packed
    assert stat.S_IMODE(extracted.stat().st_mode) == 0o700
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o600
        for path in extracted.rglob("*")
        if path.is_file()
    )
    assert (extracted / "wheels" / ROOT).read_bytes() == (wheel_dir / ROOT).read_bytes()
    with pytest.raises(bundle.ToolkitBundleError, match="already exists"):
        bundle.extract_toolkit_bundle(output, extracted)
    assert (extracted / "wheels" / ROOT).read_bytes() == (wheel_dir / ROOT).read_bytes()


def test_root_only_minimal_lock_is_static_but_never_install_ready(
    tmp_path: Path,
) -> None:
    _, _, output, result = _pack(tmp_path, dependency=False)
    assert result["wheel_count"] == 1
    assert result["container_format_checked"] is True
    assert result["root_wheel_format_checked"] is True
    assert result["dependency_wheel_format_checked"] is False
    assert result["static_format_checked"] is True
    assert result["install_checked"] is False
    assert result["execution_ready"] is False
    assert bundle.inspect_toolkit_bundle(output) == result


def test_arbitrary_locked_dependency_bytes_are_reported_as_uninspected(
    tmp_path: Path,
) -> None:
    wheel_dir, _, output, result = _pack(tmp_path)
    assert not (wheel_dir / DEPENDENCY).read_bytes().startswith(b"PK")
    assert bundle.inspect_toolkit_bundle(output) == result
    assert result["container_format_checked"] is True
    assert result["root_wheel_format_checked"] is True
    assert result["dependency_wheel_format_checked"] is False
    assert result["static_format_checked"] is False
    assert result["install_checked"] is False
    assert result["execution_ready"] is False


def test_manylinux_tags_must_match_real_glibc_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bundle.platform, "libc_ver", lambda: ("glibc", "2.39"))
    monkeypatch.setattr(bundle.platform, "machine", lambda: "x86_64")
    assert bundle._compatible_tags("cp312", "cp312", "manylinux_2_39_x86_64")
    assert bundle._compatible_tags("cp311", "abi3", "manylinux2014_x86_64")
    assert not bundle._compatible_tags("cp312", "cp312", "manylinux_2_40_x86_64")
    assert not bundle._compatible_tags("cp312", "cp312", "manylinux_2_99_x86_64")
    assert not bundle._compatible_tags("cp312", "cp312", "manylinux_2_39_other")
    assert not bundle._compatible_tags("cp312", "cp312", "musllinux_1_2_x86_64")


def test_builder_rejects_future_manylinux_wheel_even_if_lock_matches(
    tmp_path: Path,
) -> None:
    wheel_dir, lock = _sources(tmp_path)
    future = "demo_dep-1.0-cp312-cp312-manylinux_2_99_x86_64.whl"
    (wheel_dir / DEPENDENCY).rename(wheel_dir / future)
    lock.write_text(
        lock.read_text(encoding="utf-8").replace(DEPENDENCY, future), encoding="utf-8"
    )
    output = tmp_path / "future.bundle"
    with pytest.raises(bundle.ToolkitBundleError, match="incompatible"):
        bundle.pack_toolkit_bundle(wheel_dir, lock, bundle.DEFAULT_TARGET, output)
    assert not output.exists()


def test_pack_cli_and_inspect_cli(tmp_path: Path) -> None:
    wheel_dir, lock = _sources(tmp_path)
    output = tmp_path / "cli.bundle"
    packed = subprocess.run(
        [
            sys.executable,
            "-B",
            str(SCRIPT),
            "pack",
            str(wheel_dir),
            str(lock),
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    inspected = subprocess.run(
        [sys.executable, "-B", str(SCRIPT), "inspect", str(output)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert packed.returncode == inspected.returncode == 0, (
        packed.stderr + inspected.stderr
    )
    assert json.loads(packed.stdout) == json.loads(inspected.stdout)


@pytest.mark.parametrize(
    "mutation",
    [
        "prefix",
        "trailer",
        "gap",
        "extra",
        "missing",
        "duplicate",
        "traversal",
        "compressed",
        "symlink",
        "zip_extra",
        "encrypted",
    ],
)
def test_reject_hostile_zip_structure(tmp_path: Path, mutation: str) -> None:
    _, _, original, _ = _pack(tmp_path)
    target = tmp_path / "hostile.bundle"
    if mutation in {"prefix", "trailer", "gap", "encrypted"}:
        data = bytearray(original.read_bytes())
        if mutation == "prefix":
            data = bytearray(b"prefix") + data
        elif mutation == "trailer":
            data += b"trailer"
        elif mutation == "gap":
            end = len(data) - 22
            central = struct.unpack_from("<I", data, end + 16)[0]
            data[central:central] = b"gap"
            struct.pack_into("<I", data, len(data) - 22 + 16, central + 3)
        else:
            data[6] |= 1
            central = struct.unpack_from("<I", data, len(data) - 22 + 16)[0]
            data[central + 8] |= 1
        target.write_bytes(data)
    else:
        options: dict[str, Any] = {}
        if mutation == "extra":
            options["extra"] = ("wheels/unlisted-1.0-py3-none-any.whl", b"extra")
        elif mutation == "missing":
            options["missing"] = f"wheels/{ROOT}"
        elif mutation == "duplicate":
            options["extra"] = (f"wheels/{ROOT}", b"duplicate")
        elif mutation == "traversal":
            options["extra"] = ("wheels/../answer.txt", b"hidden")
        elif mutation == "compressed":
            options["compression"] = zipfile.ZIP_DEFLATED
        elif mutation == "symlink":
            options["mode"] = stat.S_IFLNK | 0o777
        else:
            options["zip_extra"] = b"\x01\x00\x00\x00"
        _rewrite(original, target, **options)
    with pytest.raises(bundle.ToolkitBundleError):
        bundle.inspect_toolkit_bundle(target)


@pytest.mark.parametrize(
    "change",
    [
        "noncanonical",
        "extra_field",
        "unsorted",
        "wrong_hash",
        "wrong_size",
        "wrong_root",
        "wrong_target",
        "lock_changed",
        "forged_dep",
    ],
)
def test_reject_manifest_lock_or_member_forgery(tmp_path: Path, change: str) -> None:
    _, _, original, _ = _pack(tmp_path)
    target = tmp_path / "forged.bundle"
    manifest = _manifest(original)
    replacements: dict[str, bytes] = {}
    if change == "noncanonical":
        replacements["bundle.json"] = json.dumps(manifest).encode()
    elif change == "extra_field":
        manifest["authorized"] = True
    elif change == "unsorted":
        manifest["wheels"].reverse()
    elif change == "wrong_hash":
        manifest["wheels"][0]["sha256"] = "0" * 64
    elif change == "wrong_size":
        manifest["wheels"][0]["bytes"] += 1
    elif change == "wrong_root":
        manifest["root_wheel"] = DEPENDENCY
    elif change == "wrong_target":
        manifest["target"]["platform"] = "win_amd64"
    elif change == "lock_changed":
        replacements["uv.lock"] = b"version = 1\n"
    else:
        payload = b"forged dependency bytes"
        replacements[f"wheels/{DEPENDENCY}"] = payload
        manifest["wheels"][0]["sha256"] = _sha(payload)
        manifest["wheels"][0]["bytes"] = len(payload)
    if change not in {"noncanonical", "lock_changed"}:
        replacements["bundle.json"] = _canonical(manifest)
    _rewrite(original, target, replacements=replacements)
    with pytest.raises(bundle.ToolkitBundleError):
        bundle.inspect_toolkit_bundle(target)


@pytest.mark.parametrize(
    "change",
    ["bad_dep", "extra_wheel", "wrong_target", "existing_output", "symlink_wheel"],
)
def test_builder_rejects_invalid_inputs_without_replacing_output(
    tmp_path: Path, change: str
) -> None:
    wheel_dir, lock = _sources(tmp_path)
    output = tmp_path / "output.bundle"
    target = dict(bundle.DEFAULT_TARGET)
    if change == "bad_dep":
        (wheel_dir / DEPENDENCY).write_bytes(b"wrong")
    elif change == "extra_wheel":
        (wheel_dir / "unlisted-1.0-py3-none-any.whl").write_bytes(b"extra")
    elif change == "wrong_target":
        target["platform"] = "win_amd64"
    elif change == "existing_output":
        output.write_bytes(b"preserve")
    else:
        (wheel_dir / DEPENDENCY).unlink()
        (wheel_dir / DEPENDENCY).symlink_to(wheel_dir / ROOT)
    with pytest.raises(bundle.ToolkitBundleError):
        bundle.pack_toolkit_bundle(wheel_dir, lock, target, output)
    assert not output.exists() or output.read_bytes() == b"preserve"


def test_reject_oversized_bundle_and_does_not_extract(tmp_path: Path) -> None:
    _, _, original, _ = _pack(tmp_path)
    large = tmp_path / "large.bundle"
    large.write_bytes(original.read_bytes() + b"x" * bundle.MAX_BUNDLE_BYTES)
    extracted = tmp_path / "must-not-exist"
    with pytest.raises(bundle.ToolkitBundleError):
        bundle.extract_toolkit_bundle(large, extracted)
    assert not extracted.exists()


def test_pack_rejects_named_output_swapped_after_fsync(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wheel_dir, lock = _sources(tmp_path)
    output = tmp_path / "output.bundle"
    moved = tmp_path / "moved.bundle"
    real_fsync = os.fsync
    swapped = False

    def swap_after_fsync(fd: int) -> None:
        nonlocal swapped
        real_fsync(fd)
        if not swapped and output.exists():
            swapped = True
            output.rename(moved)
            output.write_bytes(b"attacker replacement")

    monkeypatch.setattr(bundle.os, "fsync", swap_after_fsync)
    with pytest.raises(bundle.ToolkitBundleError, match="identity changed"):
        bundle.pack_toolkit_bundle(wheel_dir, lock, bundle.DEFAULT_TARGET, output)
    assert swapped
    assert output.read_bytes() == b"attacker replacement"
    assert moved.exists()


def test_extract_rejects_destination_renamed_during_wheels_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, source, _ = _pack(tmp_path)
    output = tmp_path / "extracted"
    moved = tmp_path / "moved"
    real_mkdir = os.mkdir
    swapped = False

    def swap_after_wheels(
        name: str | bytes | os.PathLike[str],
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> None:
        nonlocal swapped
        if dir_fd is None:
            real_mkdir(name, mode)
        else:
            real_mkdir(name, mode, dir_fd=dir_fd)
        if name == "wheels" and not swapped:
            swapped = True
            output.rename(moved)
            real_mkdir(output, 0o700)
            (output / "attacker.txt").write_bytes(b"replacement directory")

    monkeypatch.setattr(bundle.os, "mkdir", swap_after_wheels)
    with pytest.raises(bundle.ToolkitBundleError, match="destination identity changed"):
        bundle.extract_toolkit_bundle(source, output)
    assert swapped
    assert (output / "attacker.txt").read_bytes() == b"replacement directory"
    assert (moved / "wheels").is_dir()
