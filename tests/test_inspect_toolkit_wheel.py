"""Static inspection of a released toolkit wheel, including hostile ZIP forms."""

from __future__ import annotations

import io
import hashlib
import json
import stat
import struct
import subprocess
import sys
import warnings
import zipfile
from pathlib import Path

import pytest

from toolkit_wheel_fixture import DIST_INFO, build_toolkit_wheel


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import inspect_toolkit_wheel as inspector  # noqa: E402


def _candidate(tmp_path: Path) -> Path:
    path = tmp_path / "toolkit"
    build_toolkit_wheel(path)
    return path


def _rewrite_member(path: Path, name: str, replacement: bytes) -> None:
    with zipfile.ZipFile(path) as source:
        members = [(info, source.read(info)) for info in source.infolist()]
    with zipfile.ZipFile(path, "w", allowZip64=False) as target:
        for info, data in members:
            target.writestr(info, replacement if info.filename == name else data)


def _central_offset(raw: bytes) -> int:
    return struct.unpack_from("<IHHHHIIH", raw, len(raw) - 22)[6]


def _patch_headers(
    path: Path,
    *,
    local_field: tuple[int, str, int] | None = None,
    central_field: tuple[int, str, int] | None = None,
) -> None:
    raw = bytearray(path.read_bytes())
    if local_field is not None:
        offset, fmt, value = local_field
        struct.pack_into(fmt, raw, offset, value)
    if central_field is not None:
        offset, fmt, value = central_field
        struct.pack_into(fmt, raw, _central_offset(raw) + offset, value)
    path.write_bytes(raw)


def test_valid_copied_wheel_and_cli(tmp_path: Path) -> None:
    path = _candidate(tmp_path)
    result = inspector.inspect_toolkit_wheel(path)
    assert result == {
        "schema": 1,
        "classification": "development_toolkit_wheel_inspection_unsealed",
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "version": "0.1.0",
        "dependencies": ["cryptography<51,>=41", "mcp==2.2.0"],
        "file_count": 13,
        "static_format_checked": True,
        "install_checked": False,
        "execution_ready": False,
    }
    cli = subprocess.run(
        [sys.executable, "-B", str(SCRIPTS / "inspect_toolkit_wheel.py"), str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert cli.returncode == 0
    assert json.loads(cli.stdout) == result


def test_bytes_entrypoint_matches_path_without_writing(tmp_path: Path) -> None:
    path = _candidate(tmp_path)
    before = path.read_bytes()
    assert inspector.inspect_toolkit_wheel_bytes(
        before
    ) == inspector.inspect_toolkit_wheel(path)
    assert path.read_bytes() == before
    with pytest.raises(inspector.ToolkitWheelError, match="size bounds"):
        inspector.inspect_toolkit_wheel_bytes(b"invalid")


def test_existing_dist_wheel_if_present() -> None:
    path = SCRIPTS.parent / "dist" / "specorganon-0.1.0-py3-none-any.whl"
    if not path.is_file():
        pytest.skip("prebuilt wheel is optional for unit tests")
    result = inspector.inspect_toolkit_wheel(path)
    assert result["version"] == "0.1.0"
    assert result["dependencies"] == ["cryptography<51,>=41", "mcp==2.2.0"]
    assert result["static_format_checked"] is True
    assert result["install_checked"] is False


def test_reject_symlink_for_file_or_parent(tmp_path: Path) -> None:
    path = _candidate(tmp_path)
    link = tmp_path / "link"
    link.symlink_to(path)
    with pytest.raises(inspector.ToolkitWheelError):
        inspector.inspect_toolkit_wheel(link)
    parent = tmp_path / "linked_parent"
    parent.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(inspector.ToolkitWheelError):
        inspector.inspect_toolkit_wheel(parent / "toolkit")


def test_reject_file_path_with_trailing_slash(tmp_path: Path) -> None:
    path = _candidate(tmp_path)
    with pytest.raises(inspector.ToolkitWheelError, match="path is invalid"):
        inspector.inspect_toolkit_wheel(str(path) + "/")


def test_reject_parent_replaced_during_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    unstable = tmp_path / "unstable"
    safe = unstable / "safe"
    safe.mkdir(parents=True)
    path = _candidate(safe)
    original_read = inspector.os.read
    swapped = False

    def swap_then_read(fd: int, count: int) -> bytes:
        nonlocal swapped
        if not swapped:
            swapped = True
            safe.rename(unstable / "safe_moved")
            safe.mkdir()
            (safe / "toolkit").write_bytes(b"not a wheel")
        return original_read(fd, count)

    monkeypatch.setattr(inspector.os, "read", swap_then_read)
    with pytest.raises(inspector.ToolkitWheelError, match="directory chain changed"):
        inspector.inspect_toolkit_wheel(path)
    assert swapped


@pytest.mark.parametrize("mutation", ["prefix", "trailer", "central_gap"])
def test_reject_undeclared_zip_bytes(tmp_path: Path, mutation: str) -> None:
    path = _candidate(tmp_path)
    raw = path.read_bytes()
    if mutation == "prefix":
        path.write_bytes(b"hidden prefix" + raw)
    elif mutation == "trailer":
        path.write_bytes(raw + b"hidden trailer")
    else:
        changed = bytearray(raw)
        struct.pack_into("<I", changed, len(changed) - 6, _central_offset(raw) + 1)
        path.write_bytes(changed)
    with pytest.raises(inspector.ToolkitWheelError):
        inspector.inspect_toolkit_wheel(path)


def test_reject_duplicate_and_unsafe_paths(tmp_path: Path) -> None:
    path = _candidate(tmp_path)
    with zipfile.ZipFile(path, "a") as archive:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            archive.writestr("specorganon/__init__.py", b"duplicate")
    with pytest.raises(inspector.ToolkitWheelError, match="duplicate"):
        inspector.inspect_toolkit_wheel(path)

    path = tmp_path / "unsafe_toolkit"
    build_toolkit_wheel(path, extra={"specorganon/../escape.py": b"bad"})
    with pytest.raises(inspector.ToolkitWheelError, match="unsafe path"):
        inspector.inspect_toolkit_wheel(path)


@pytest.mark.parametrize("nested", ["blocked/nested.py", "Blocked/nested.py"])
def test_reject_file_as_implicit_directory(tmp_path: Path, nested: str) -> None:
    path = tmp_path / "toolkit"
    build_toolkit_wheel(
        path,
        extra={
            "specorganon/blocked": b"flat member",
            f"specorganon/{nested}": b"nested member",
        },
    )
    with pytest.raises(inspector.ToolkitWheelError, match="collides with a directory"):
        inspector.inspect_toolkit_wheel(path)


@pytest.mark.parametrize("mode", [stat.S_IFLNK | 0o777, stat.S_IFDIR | 0o755])
def test_reject_nonregular_members(tmp_path: Path, mode: int) -> None:
    path = _candidate(tmp_path)
    _patch_headers(path, central_field=(38, "<I", mode << 16))
    with pytest.raises(inspector.ToolkitWheelError, match="regular file"):
        inspector.inspect_toolkit_wheel(path)


@pytest.mark.parametrize(
    "field,value,expected",
    [
        ("flags", 1, "flags"),
        ("method", 99, "compression"),
    ],
)
def test_reject_encryption_and_unsupported_compression(
    tmp_path: Path, field: str, value: int, expected: str
) -> None:
    path = _candidate(tmp_path)
    if field == "flags":
        _patch_headers(
            path, local_field=(6, "<H", value), central_field=(8, "<H", value)
        )
    else:
        _patch_headers(
            path, local_field=(8, "<H", value), central_field=(10, "<H", value)
        )
    with pytest.raises(inspector.ToolkitWheelError, match=expected):
        inspector.inspect_toolkit_wheel(path)


def test_reject_size_bomb_and_bad_local_metadata(tmp_path: Path) -> None:
    path = tmp_path / "bomb"
    build_toolkit_wheel(path, extra={"specorganon/bomb.txt": b"0" * 200_000})
    with pytest.raises(inspector.ToolkitWheelError, match="compression bounds"):
        inspector.inspect_toolkit_wheel(path)

    path = _candidate(tmp_path)
    _patch_headers(path, local_field=(14, "<I", 12345))
    with pytest.raises(inspector.ToolkitWheelError, match="local sizes or CRC"):
        inspector.inspect_toolkit_wheel(path)


def test_reject_archive_above_read_limit(tmp_path: Path) -> None:
    path = tmp_path / "toolkit"
    path.write_bytes(b"x" * (inspector.MAX_WHEEL_BYTES + 1))
    with pytest.raises(inspector.ToolkitWheelError, match="size bounds"):
        inspector.inspect_toolkit_wheel(path)


@pytest.mark.parametrize(
    "local,central,expected",
    [
        ((14, "<I", 1), (16, "<I", 1), "CRC"),
        ((22, "<I", 1), (24, "<I", 1), "size"),
    ],
)
def test_reject_crc_or_uncompressed_size_even_when_headers_agree(
    tmp_path: Path,
    local: tuple[int, str, int],
    central: tuple[int, str, int],
    expected: str,
) -> None:
    path = _candidate(tmp_path)
    _patch_headers(path, local_field=local, central_field=central)
    with pytest.raises(inspector.ToolkitWheelError, match=expected):
        inspector.inspect_toolkit_wheel(path)


def test_reject_corrupt_compressed_member(tmp_path: Path) -> None:
    path = _candidate(tmp_path)
    raw = bytearray(path.read_bytes())
    name_size = struct.unpack_from("<H", raw, 26)[0]
    raw[30 + name_size] ^= 0x40
    path.write_bytes(raw)
    with pytest.raises(inspector.ToolkitWheelError):
        inspector.inspect_toolkit_wheel(path)


@pytest.mark.parametrize(
    "old,new",
    [
        (b"Name: specorganon", b"Name: anotherpkg"),
        (b"Version: 0.1.0", b"Version: nonsense"),
        (b"Requires-Python: >=3.11", b"Requires-Python: >=3.8"),
        (b"Requires-Dist: mcp==2.2.0", b"Requires-Dist: surprise>=1"),
        (b"Requires-Dist: mcp==2.2.0", b"Requires-Dist: mcp<3,>=2.2"),
    ],
)
def test_reject_wrong_core_metadata(tmp_path: Path, old: bytes, new: bytes) -> None:
    path = tmp_path / "toolkit"
    from toolkit_wheel_fixture import wheel_members

    metadata = wheel_members()[f"{DIST_INFO}/METADATA"].replace(old, new)
    build_toolkit_wheel(path, overrides={f"{DIST_INFO}/METADATA": metadata})
    with pytest.raises(inspector.ToolkitWheelError):
        inspector.inspect_toolkit_wheel(path)


@pytest.mark.parametrize(
    "name,old,new",
    [
        ("WHEEL", b"Root-Is-Purelib: true", b"Root-Is-Purelib: false"),
        ("WHEEL", b"Tag: py3-none-any", b"Tag: cp311-cp311-linux_x86_64"),
        (
            "entry_points.txt",
            b"organon = specorganon.cli:main",
            b"organon = surprise:main",
        ),
    ],
)
def test_reject_wrong_wheel_or_entry_points(
    tmp_path: Path, name: str, old: bytes, new: bytes
) -> None:
    path = tmp_path / "toolkit"
    from toolkit_wheel_fixture import wheel_members

    payload = wheel_members()[f"{DIST_INFO}/{name}"].replace(old, new)
    build_toolkit_wheel(path, overrides={f"{DIST_INFO}/{name}": payload})
    with pytest.raises(inspector.ToolkitWheelError):
        inspector.inspect_toolkit_wheel(path)


def test_reject_missing_core_module_and_outside_member(tmp_path: Path) -> None:
    path = tmp_path / "toolkit"
    build_toolkit_wheel(path, omit=("specorganon/server.py",))
    with pytest.raises(inspector.ToolkitWheelError, match="missing core"):
        inspector.inspect_toolkit_wheel(path)
    build_toolkit_wheel(path, extra={"otherpackage/payload.py": b"x"})
    with pytest.raises(inspector.ToolkitWheelError, match="outside"):
        inspector.inspect_toolkit_wheel(path)


@pytest.mark.parametrize("kind", ["digest", "size", "missing", "duplicate"])
def test_reject_record_mismatch(tmp_path: Path, kind: str) -> None:
    path = _candidate(tmp_path)
    with zipfile.ZipFile(path) as archive:
        record = archive.read(f"{DIST_INFO}/RECORD").decode("utf-8")
    rows = record.splitlines()
    if kind == "digest":
        name, digest, size = rows[0].split(",")
        digest = digest[:-1] + ("A" if digest[-1] != "A" else "B")
        rows[0] = ",".join((name, digest, size))
    elif kind == "size":
        name, digest, _size = rows[0].split(",")
        rows[0] = ",".join((name, digest, "999"))
    elif kind == "missing":
        rows.pop(0)
    else:
        rows.insert(0, rows[0])
    _rewrite_member(path, f"{DIST_INFO}/RECORD", ("\n".join(rows) + "\n").encode())
    with pytest.raises(inspector.ToolkitWheelError, match="RECORD"):
        inspector.inspect_toolkit_wheel(path)


def test_accept_consistent_data_descriptors(tmp_path: Path) -> None:
    path = _candidate(tmp_path)
    with zipfile.ZipFile(path) as archive:
        members = [(info, archive.read(info)) for info in archive.infolist()]

    class NonSeekable(io.BytesIO):
        def seek(self, *_args: object, **_kwargs: object) -> int:
            raise OSError("nonseekable fixture")

    stream = NonSeekable()
    with zipfile.ZipFile(stream, "w", allowZip64=False) as archive:
        for info, payload in members:
            archive.writestr(info, payload)
    path.write_bytes(stream.getvalue())
    assert inspector.inspect_toolkit_wheel(path)["static_format_checked"] is True
