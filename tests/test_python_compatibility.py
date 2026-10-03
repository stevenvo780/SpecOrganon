"""Check helper launch configuration; these doubles are not CLI/MCP evidence."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check_python_compatibility.py"


@pytest.fixture
def helper():
    spec = importlib.util.spec_from_file_location("check_python_compatibility", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def first_launch(helper, monkeypatch, tmp_path, *, offline, python=sys.executable,
                 path_entry=None, inherited_offline=None):
    uv = tmp_path / "uv"
    uv.touch(mode=0o700)
    monkeypatch.setenv("PATH", str(tmp_path) if path_entry is None else path_entry)
    if inherited_offline is None:
        monkeypatch.delenv("UV_OFFLINE", raising=False)
    else:
        monkeypatch.setenv("UV_OFFLINE", inherited_offline)
    argv = [str(SCRIPT), "--python", python, "--output", str(tmp_path / "output")]
    if offline:
        argv.append("--offline")
    monkeypatch.setattr(sys, "argv", argv)
    calls = []

    def stop_before_build(argv, **kwargs):
        calls.append((argv, kwargs))
        raise RuntimeError("test stops before running uv or downloading dependencies")

    monkeypatch.setattr(helper.subprocess, "run", stop_before_build)
    assert helper.main() == 1
    assert len(calls) == 1
    return calls[0]


@pytest.mark.parametrize("explicit_cache", [False, True])
@pytest.mark.parametrize("offline", [False, True])
def test_cache_selection_preserves_offline_defaults_and_explicit_cache(
    helper, monkeypatch, tmp_path, offline, explicit_cache,
):
    cache_home = tmp_path / "existing-cache"
    cache_home.mkdir()
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache_home))
    monkeypatch.delenv("UV_CACHE_DIR", raising=False)
    if explicit_cache:
        monkeypatch.setenv("UV_CACHE_DIR", str(cache_home / "custom-uv"))
    _, launch = first_launch(helper, monkeypatch, tmp_path, offline=offline)
    env = launch["env"]
    assert env["XDG_CACHE_HOME"] == str(cache_home)
    assert env.get("HOME") == os.environ.get("HOME")
    assert env["UV_PYTHON_DOWNLOADS"] == "never"
    assert env.get("UV_OFFLINE") == ("1" if offline else None)
    selected_cache = env.get("UV_CACHE_DIR")
    if explicit_cache:
        assert selected_cache == str(cache_home / "custom-uv")
    elif offline:
        assert selected_cache is None
    else:
        assert selected_cache == str(tmp_path / "output/uv-cache")


def test_relative_python_remains_absolute_venv_path_after_cwd_change(
    helper, monkeypatch, tmp_path,
):
    interpreter = tmp_path / ".venv/bin/python"
    interpreter.parent.mkdir(parents=True)
    interpreter.symlink_to(sys.executable)
    monkeypatch.chdir(tmp_path)
    argv, launch = first_launch(helper, monkeypatch, tmp_path, offline=True,
                               python=".venv/bin/python")
    assert launch["cwd"] == tmp_path / "output"
    assert argv[argv.index("--python") + 1] == str(interpreter)


def test_relative_uv_path_remains_absolute_symlink_after_cwd_change(
    helper, monkeypatch, tmp_path,
):
    bindir = tmp_path / "local-bin"
    bindir.mkdir()
    executable = bindir / "uv"
    executable.symlink_to(tmp_path / "uv")
    monkeypatch.chdir(tmp_path)
    argv, launch = first_launch(helper, monkeypatch, tmp_path, offline=True,
                               path_entry="local-bin")
    assert launch["cwd"] == tmp_path / "output"
    assert argv[0] == str(executable)


@pytest.mark.parametrize("offline", [False, True])
def test_relative_cache_is_anchored_without_resolving_symlink(
    helper, monkeypatch, tmp_path, offline,
):
    populated = tmp_path / "populated"
    populated.mkdir()
    cache = tmp_path / "warm-cache"
    cache.symlink_to(populated, target_is_directory=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("UV_CACHE_DIR", "warm-cache")
    _, launch = first_launch(helper, monkeypatch, tmp_path, offline=offline)
    selected_cache = launch["env"]["UV_CACHE_DIR"]
    assert selected_cache == str(cache)


@pytest.mark.parametrize("setting,flag,effective_offline", [
    ("1", False, True), ("TRUE", False, True), ("yes", False, True),
    ("on", False, True), ("0", False, False), ("false", False, False),
    ("0", True, True),
])
def test_inherited_offline_controls_cache_and_cli_flag_takes_precedence(
    helper, monkeypatch, tmp_path, setting, flag, effective_offline,
):
    monkeypatch.delenv("UV_CACHE_DIR", raising=False)
    _, launch = first_launch(helper, monkeypatch, tmp_path, offline=flag,
                            inherited_offline=setting)
    assert launch["env"]["UV_OFFLINE"] == ("1" if flag else setting)
    selected_cache = launch["env"].get("UV_CACHE_DIR")
    expected_cache = None if effective_offline else str(tmp_path / "output/uv-cache")
    assert selected_cache == expected_cache
