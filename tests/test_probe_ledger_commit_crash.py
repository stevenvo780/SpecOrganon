"""A wheel-installed CLI crash must resume through a real stdio MCP client."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
PROBE = REPO / "scripts" / "probe_ledger_commit_crash.py"
MCP_PROBE = REPO / "scripts" / "probe_mcp_server_crash.py"


def _run(
    args: list[str],
    *,
    cwd: Path,
    timeout: int = 90,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"PYTHONPATH", "PYTHONHOME"}
    }
    env.update(extra_env or {})
    return subprocess.run(
        args,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def test_installed_wheel_commit_windows_and_missing_hook_control(
    tmp_path: Path,
) -> None:
    uv = shutil.which("uv")
    assert uv is not None, "uv is required to build and install the wheel fixture"
    wheel_dir = tmp_path / "wheels"
    built = _run(
        [uv, "build", "--offline", "--wheel", "--out-dir", str(wheel_dir), str(REPO)],
        cwd=tmp_path,
    )
    assert built.returncode == 0, built.stderr
    wheels = list(wheel_dir.glob("specorganon-*.whl"))
    assert len(wheels) == 1
    venv = tmp_path / "wheel-env"
    created = _run(
        [
            uv,
            "venv",
            "--offline",
            "--no-project",
            "--python",
            sys.executable,
            str(venv),
        ],
        cwd=tmp_path,
    )
    assert created.returncode == 0, created.stderr
    python = venv / "bin" / "python"
    installed = _run(
        [uv, "pip", "install", "--offline", "--python", str(python), str(wheels[0])],
        cwd=tmp_path,
    )
    assert installed.returncode == 0, installed.stderr

    probed = _run([str(python), str(PROBE), str(REPO)], cwd=tmp_path)
    assert probed.returncode == 0, probed.stderr
    report = json.loads(probed.stdout)
    assert (
        report["classification"]
        == "installed_wheel_process_sigkill_commit_window_probe"
    )
    assert report["hook_activations_per_window"] == 1
    assert report["host_or_power_loss_durability_tested"] is False
    assert report["windows"] == {
        "before_replace": {
            "checkpoint_revision": 1,
            "resume_applied": 2,
            "resume_skipped": 1,
            "final_revision": 3,
            "unique_manifest_ids": 3,
            "byte_identical_replay": True,
        },
        "after_replace": {
            "checkpoint_revision": 2,
            "resume_applied": 1,
            "resume_skipped": 2,
            "final_revision": 3,
            "unique_manifest_ids": 3,
            "byte_identical_replay": True,
        },
    }
    optimized = _run(
        [str(python), str(PROBE), str(REPO)],
        cwd=tmp_path,
        extra_env={"PYTHONOPTIMIZE": "1"},
    )
    assert optimized.returncode == 0, optimized.stderr
    assert json.loads(optimized.stdout) == report

    # The same runner with an empty sitecustomize must fail the probe closed.
    control = _run(
        [
            str(python),
            "-c",
            (
                "import asyncio, importlib.util, sys; "
                "spec = importlib.util.spec_from_file_location('commit_probe', sys.argv[1]); "
                "probe = importlib.util.module_from_spec(spec); spec.loader.exec_module(probe); "
                "probe.HOOK = ''; asyncio.run(probe._exercise())"
            ),
            str(PROBE),
        ],
        cwd=tmp_path,
    )
    assert control.returncode != 0
    assert "commit-window injection did not fire" in control.stderr
    optimized_control = _run(
        [
            str(python),
            "-O",
            "-c",
            (
                "import asyncio, importlib.util, sys; "
                "spec = importlib.util.spec_from_file_location('commit_probe', sys.argv[1]); "
                "probe = importlib.util.module_from_spec(spec); spec.loader.exec_module(probe); "
                "probe.HOOK = ''; asyncio.run(probe._exercise())"
            ),
            str(PROBE),
        ],
        cwd=tmp_path,
        extra_env={"PYTHONOPTIMIZE": "1"},
    )
    assert optimized_control.returncode != 0
    assert "commit-window injection did not fire" in optimized_control.stderr

    mcp_probed = _run([str(python), str(MCP_PROBE), str(REPO)], cwd=tmp_path)
    assert mcp_probed.returncode == 0, mcp_probed.stderr
    mcp_report = json.loads(mcp_probed.stdout)
    assert mcp_report["classification"] == (
        "installed_wheel_mcp_server_sigkill_commit_window_probe"
    )
    assert mcp_report["hook_activations_per_window"] == 1
    assert mcp_report["host_or_power_loss_durability_tested"] is False
    for phase, checkpoint in (("before_replace", 1), ("after_replace", 2)):
        window = mcp_report["windows"][phase]
        assert window["checkpoint_revision"] == checkpoint
        assert window["resume_applied"] == 3 - checkpoint
        assert window["resume_skipped"] == checkpoint
        assert window["final_revision"] == window["unique_manifest_ids"] == 3
        assert window["byte_identical_replay"] is True
        assert window["transport_failed"] is True
        assert window["transport_error_types"]
        assert "TimeoutError" not in window["transport_error_types"]
        assert window["cli_mcp_status_equal"] is True

    mcp_optimized = _run(
        [str(python), "-O", str(MCP_PROBE), str(REPO)],
        cwd=tmp_path,
        extra_env={"PYTHONOPTIMIZE": "1"},
    )
    assert mcp_optimized.returncode == 0, mcp_optimized.stderr
    assert json.loads(mcp_optimized.stdout) == mcp_report

    # Without the injected SIGKILL, an ordinary successful MCP result is not
    # accepted as evidence of crash recovery, including under optimized Python.
    no_hook = (
        "import asyncio, importlib.util, pathlib, sys; "
        "sys.path.insert(0, str(pathlib.Path(sys.argv[1]).parent)); "
        "spec = importlib.util.spec_from_file_location('mcp_probe', sys.argv[1]); "
        "probe = importlib.util.module_from_spec(spec); spec.loader.exec_module(probe); "
        "probe.HOOK = ''; asyncio.run(probe._exercise())"
    )
    for flags in ([], ["-O"]):
        mcp_control = _run(
            [str(python), *flags, "-c", no_hook, str(MCP_PROBE)],
            cwd=tmp_path,
            extra_env={"PYTHONOPTIMIZE": "1"} if flags else None,
        )
        assert mcp_control.returncode != 0
        assert "MCP run returned without a server crash" in mcp_control.stderr

    wrong_exit = (
        "import asyncio, importlib.util, pathlib, sys; "
        "sys.path.insert(0, str(pathlib.Path(sys.argv[1]).parent)); "
        "spec = importlib.util.spec_from_file_location('mcp_probe', sys.argv[1]); "
        "probe = importlib.util.module_from_spec(spec); spec.loader.exec_module(probe); "
        "probe.HOOK = probe.HOOK.replace('os.kill(os.getpid(), signal.SIGKILL)', "
        "'os._exit(17)'); asyncio.run(probe._exercise())"
    )
    mcp_wrong_exit = _run(
        [str(python), "-c", wrong_exit, str(MCP_PROBE)], cwd=tmp_path
    )
    assert mcp_wrong_exit.returncode != 0
    assert "MCP server did not exit with SIGKILL (17)" in mcp_wrong_exit.stderr

    unrelated_error = """
import asyncio, importlib.util, pathlib, sys
sys.path.insert(0, str(pathlib.Path(sys.argv[1]).parent))
spec = importlib.util.spec_from_file_location('mcp_probe', sys.argv[1])
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
original = probe.Client.call_tool
async def unrelated(self, *args, **kwargs):
    try:
        return await original(self, *args, **kwargs)
    except Exception:
        raise ValueError('synthetic unrelated decoder failure') from None
probe.Client.call_tool = unrelated
asyncio.run(probe._exercise())
"""
    mcp_unrelated = _run(
        [str(python), "-c", unrelated_error, str(MCP_PROBE)], cwd=tmp_path
    )
    assert mcp_unrelated.returncode != 0
    assert "reason other than connection closure" in mcp_unrelated.stderr
