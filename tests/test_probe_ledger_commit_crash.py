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
