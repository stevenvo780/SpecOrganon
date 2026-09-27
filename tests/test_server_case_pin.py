"""MCP case directory pinning across path replacement races."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from specorganon import server
from specorganon.cli import invoke as engine_invoke


pytestmark = pytest.mark.usefixtures("enable_fixture_policy")


def _init(path: Path, title: str) -> None:
    engine_invoke("init", path=str(path), title=title, domain="test", actor="human:fixture",
                  approval_policy="fixture")


@pytest.mark.parametrize("operation", ("status", "run", "init"))
def test_case_fd_survives_replacement_before_invoke(tmp_path, monkeypatch, operation):
    root = tmp_path / "root"
    root.mkdir()
    case = root / "case"
    parked = root / "parked"
    outside = tmp_path / "outside"
    _init(outside, "Outside")
    outside_before = (outside / "organon.json").read_bytes()
    if operation != "init":
        _init(case, "Inside")
    monkeypatch.setenv("ORGANON_ROOT", str(root))

    def replace_then_invoke(name, **kwargs):
        pinned_fd = int(kwargs["path"].removeprefix("/proc/self/fd/"))
        assert os.fstat(pinned_fd).st_ino == case.stat().st_ino
        case.rename(parked)
        case.symlink_to(outside, target_is_directory=True)
        assert os.fstat(pinned_fd).st_ino == parked.stat().st_ino
        return engine_invoke(name, **kwargs)

    monkeypatch.setattr(server, "invoke", replace_then_invoke)
    if operation == "status":
        result = server._invoke("status", path="case")
        assert result["project"]["title"] == "Inside"
    elif operation == "run":
        manifest = {"schema": 1, "steps": [
            {"op": "put", "id": "p1", "kind": "problem", "text": "Pinned case", "refs": [], "data": {}},
        ]}
        result = server._invoke("run", path="case", manifest=manifest, actor="agent:writer")
        assert result["applied"] == 1
        assert "p1" in engine_invoke("status", path=str(parked))["items"]
    else:
        result = server._invoke("init", path="case", title="Pinned init", domain="test",
                                actor="human:fixture", approval_policy="fixture")
        assert result["project"]["title"] == "Pinned init"
        assert (parked / "organon.json").is_file()
    assert case.is_symlink()
    assert (outside / "organon.json").read_bytes() == outside_before


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="a same-UID rename can move the pinned case inode outside the root before a write",
)
def test_relocated_pinned_inode_can_still_be_written_outside_root(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    case = root / "case"
    _init(case, "Inside")
    before = (case / "organon.json").read_bytes()
    outside = tmp_path / "outside"
    outside.mkdir()
    moved = outside / "case"
    monkeypatch.setenv("ORGANON_ROOT", str(root))

    original_case_path = server._case_path
    relocated = False

    @contextmanager
    def relocate_after_pin(path, *, create=False):
        nonlocal relocated
        with original_case_path(path, create=create) as pinned_path:
            pinned_fd = int(pinned_path.removeprefix("/proc/self/fd/"))
            case.rename(moved)
            relocated = True
            if os.fstat(pinned_fd).st_ino != moved.stat().st_ino:
                raise RuntimeError("case inode was not pinned across relocation")
            yield pinned_path

    monkeypatch.setattr(server, "_case_path", relocate_after_pin)
    try:
        server._invoke("put", path="case", id="p1", kind="problem", text="After relocation",
                       refs=[], data={}, actor="agent:writer")
    except ToolError:
        if not relocated:
            raise RuntimeError("relocation hook was not reached") from None
        assert (moved / "organon.json").read_bytes() == before, "write preceded rejection outside the root"
        return  # Rejection would be an unexpected pass of the ideal boundary.
    if not relocated:
        raise RuntimeError("relocation hook was not reached")
    assert (moved / "organon.json").read_bytes() == before, "write reached the case inode outside the root"


def test_canonical_ancestor_replaced_by_symlink_before_open_is_rejected(tmp_path, monkeypatch):
    root = tmp_path / "root"
    nested = root / "nested"
    nested.mkdir(parents=True)
    _init(nested / "case", "Inside")
    outside = tmp_path / "outside"
    _init(outside / "case", "Outside")
    outside_before = (outside / "case" / "organon.json").read_bytes()
    monkeypatch.setenv("ORGANON_ROOT", str(root))

    real_open = os.open
    swapped = False

    def swap_before_open(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal swapped
        if path == "nested" and dir_fd is not None and not swapped:
            swapped = True
            nested.rename(root / "parked")
            nested.symlink_to(outside, target_is_directory=True)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(server.os, "open", swap_before_open)
    with pytest.raises(ToolError):
        server._invoke("status", path="nested/case")
    assert swapped
    assert (outside / "case" / "organon.json").read_bytes() == outside_before


def test_root_canonical_ancestor_replaced_before_open_is_rejected(tmp_path, monkeypatch):
    parent = tmp_path / "parent"
    root = parent / "root"
    root.mkdir(parents=True)
    _init(root / "case", "Inside")
    outside = tmp_path / "outside"
    _init(outside / "root" / "case", "Outside")
    monkeypatch.setenv("ORGANON_ROOT", str(root))
    outside_before = (outside / "root" / "case" / "organon.json").read_bytes()

    real_open = os.open
    swapped = False

    def swap_before_open(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal swapped
        if path == "parent" and dir_fd is not None and not swapped:
            swapped = True
            parent.rename(tmp_path / "parked")
            parent.symlink_to(outside, target_is_directory=True)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(server.os, "open", swap_before_open)
    with pytest.raises(ToolError):
        server._invoke("status", path="case")
    assert swapped
    assert (outside / "root" / "case" / "organon.json").read_bytes() == outside_before


def test_internal_case_and_root_aliases_and_nested_init_work(tmp_path, monkeypatch):
    root = tmp_path / "root"
    nested = root / "nested"
    nested.mkdir(parents=True)
    _init(nested / "case", "Inside")
    (root / "alias").symlink_to(nested, target_is_directory=True)
    root_alias = tmp_path / "root-alias"
    root_alias.symlink_to(root, target_is_directory=True)
    monkeypatch.setenv("ORGANON_ROOT", str(root_alias))

    assert server._invoke("status", path="alias/case")["project"]["title"] == "Inside"
    result = server._invoke("init", path="alias/new/deep", title="Nested", domain="test",
                            actor="human:fixture", approval_policy="fixture")
    assert result["project"]["title"] == "Nested"
    assert (nested / "new" / "deep" / "organon.json").is_file()


@pytest.mark.parametrize("bad_kwargs", (
    {"title": " "},
    {"domain": ""},
    {"actor": ""},
    {"approval_policy": "invalid"},
))
def test_invalid_init_arguments_create_no_directories(tmp_path, monkeypatch, bad_kwargs):
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setenv("ORGANON_ROOT", str(root))
    kwargs = {"title": "Title", "domain": "test", "actor": "human:fixture", "approval_policy": "fixture"}
    kwargs.update(bad_kwargs)
    with pytest.raises(ToolError):
        server._invoke("init", path="new/deep", **kwargs)
    assert not (root / "new").exists()


def test_anchor_setting_blocks_init_before_creating_directories(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setenv("ORGANON_ROOT", str(root))
    monkeypatch.setenv("ORGANON_LEDGER_ANCHORS_FILE", str(tmp_path / "anchors.json"))
    with pytest.raises(ToolError, match="initialize a case before enabling"):
        server._invoke("init", path="new/deep", title="Title", domain="test",
                       actor="human:fixture", approval_policy="fixture")
    assert not (root / "new").exists()
