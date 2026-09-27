"""MCP case directory pinning across path replacement races."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters
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


def test_real_stdio_mcp_blocks_write_after_peer_moves_pinned_case(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    case = root / "case"
    outside = tmp_path / "outside"
    outside.mkdir()
    moved = outside / "case"
    ready = root / "ready.fifo"
    go = root / "go.fifo"
    trigger = root / "relocate"
    os.mkfifo(ready)
    os.mkfifo(go)

    # The child runs the real stdio transport and policy. The test-only hook
    # pauses after _case_path pins the directory, so the parent can move it.
    child_code = """
import os
from contextlib import contextmanager
from pathlib import Path
from specorganon import server

original = server._case_path
@contextmanager
def pause_after_pin(path, *, create=False):
    with original(path, create=create) as pinned:
        if not create and Path(os.environ["CASE_RELOCATE_TRIGGER"]).exists():
            with open(os.environ["CASE_RELOCATE_READY"], "wb", buffering=0) as pipe:
                pipe.write(b"1")
            with open(os.environ["CASE_RELOCATE_GO"], "rb", buffering=0) as pipe:
                if pipe.read(1) != b"1":
                    raise RuntimeError("case relocation handshake failed")
        yield pinned

server._case_path = pause_after_pin
server.main()
"""
    environment = {
        **os.environ,
        "ORGANON_ROOT": str(root),
        "ORGANON_ALLOW_FIXTURES": "1",
        "CASE_RELOCATE_TRIGGER": str(trigger),
        "CASE_RELOCATE_READY": str(ready),
        "CASE_RELOCATE_GO": str(go),
    }

    def read_ready() -> bytes:
        with ready.open("rb", buffering=0) as pipe:
            return pipe.read(1)

    def release_case() -> None:
        with go.open("wb", buffering=0) as pipe:
            pipe.write(b"1")

    async def exercise() -> None:
        params = StdioServerParameters(
            command=sys.executable, args=["-c", child_code], cwd=str(tmp_path), env=environment
        )
        async with Client(params, mode="auto") as client:
            created = await client.call_tool("init", {
                "path": "case", "title": "Inside", "domain": "test",
                "actor": "human:fixture", "approval_policy": "fixture",
            })
            assert not created.is_error, created.content
            allowed = await client.call_tool("put", {
                "path": "case", "id": "p1", "kind": "problem", "text": "Inside root",
                "refs": [], "data": {}, "actor": "agent:writer",
            })
            assert not allowed.is_error, allowed.content
            run_result = await client.call_tool("run", {
                "path": "case", "actor": "agent:writer",
                "manifest": {"schema": 1, "steps": [
                    {"op": "put", "id": "p_run", "kind": "problem",
                     "text": "Inside manifest", "refs": [], "data": {}},
                ]},
            })
            assert not run_result.is_error, run_result.content
            state = await client.call_tool("status", {"path": "case"})
            assert not state.is_error, state.content
            status_data = state.structured_content or json.loads(state.content[0].text)
            assert {"p1", "p_run"} <= status_data["items"].keys()
            before = (case / "organon.json").read_bytes()

            trigger.touch()
            pending = asyncio.create_task(client.call_tool("put", {
                "path": "case", "id": "p2", "kind": "problem", "text": "After relocation",
                "refs": [], "data": {}, "actor": "agent:writer",
            }))
            assert await asyncio.wait_for(asyncio.to_thread(read_ready), 10) == b"1"
            case.rename(moved)  # Same-UID peer is outside the MCP process's rule.
            await asyncio.wait_for(asyncio.to_thread(release_case), 10)
            rejected = await asyncio.wait_for(pending, 10)
            assert rejected.is_error, rejected.content
            assert (moved / "organon.json").read_bytes() == before

    asyncio.run(exercise())


def test_explicit_root_fails_closed_if_landlock_cannot_be_installed(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    script = """
import errno
from specorganon import server
def unavailable(*args):
    raise OSError(errno.ENOSYS, "Landlock unavailable")
server._landlock_syscall = unavailable
server.main()
"""
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=tmp_path,
        env={**os.environ, "ORGANON_ROOT": str(root)},
        text=True, capture_output=True, timeout=10, check=False,
    )
    assert result.returncode != 0
    assert "Landlock" in result.stderr
    assert not list(root.iterdir())


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
