"""Installed CLI and real stdio MCP complete every signed synthetic phase."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "scripts" / "probe_signed_full_workflow.py"
PHASES = [
    "frame", "critique", "study", "observe", "explain", "compare",
    "specify", "build", "validate",
]


def test_signed_full_workflow_cli_mcp_resume_replay_and_revocation(tmp_path: Path) -> None:
    output = tmp_path / "receipt.json"
    uv = shutil.which("uv")
    assert uv is not None, "uv is required for the installed-wheel integration test"
    home = tmp_path / "home"
    scratch = tmp_path / "tmp"
    home.mkdir()
    scratch.mkdir()
    cache_setting = os.environ.get("UV_CACHE_DIR")
    xdg_cache = os.environ.get("XDG_CACHE_HOME")
    cache = (Path(cache_setting) if cache_setting else
             Path(xdg_cache) / "uv" if xdg_cache else Path.home() / ".cache" / "uv")
    assert cache.is_absolute() and cache.is_dir(), "offline uv cache is required"
    env = {
        "PATH": os.pathsep.join((str(Path(uv).parent), str(Path(sys.executable).parent),
                                 "/usr/bin", "/bin")),
        "HOME": str(home),
        "TMPDIR": str(scratch),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONNOUSERSITE": "1",
        "UV_CACHE_DIR": str(cache),
        "UV_OFFLINE": "1",
        "UV_NO_CONFIG": "1",
    }
    wheel_dir = tmp_path / "wheel-dist"
    built = subprocess.run(
        [uv, "build", "--offline", "--wheel", "--out-dir", str(wheel_dir), str(ROOT)],
        cwd=tmp_path, env=env, text=True, capture_output=True,
        timeout=90, check=False,
    )
    assert built.returncode == 0, built.stderr
    wheels = list(wheel_dir.glob("specorganon-*.whl"))
    assert len(wheels) == 1
    venv = tmp_path / "wheel-env"
    created = subprocess.run(
        [uv, "venv", "--offline", "--no-project", "--python", sys.executable, str(venv)],
        cwd=tmp_path, env=env, text=True, capture_output=True,
        timeout=90, check=False,
    )
    assert created.returncode == 0, created.stderr
    python = venv / "bin" / "python"
    installed = subprocess.run(
        [uv, "pip", "install", "--offline", "--python", str(python), str(wheels[0])],
        cwd=tmp_path, env=env, text=True, capture_output=True,
        timeout=90, check=False,
    )
    assert installed.returncode == 0, installed.stderr
    process = subprocess.run(
        [str(python), str(PROBE), str(ROOT), "--output", str(output)],
        cwd=tmp_path, env=env, text=True, capture_output=True,
        timeout=120, check=False,
    )
    assert process.returncode == 0, process.stderr
    receipt = json.loads(process.stdout)
    assert receipt == json.loads(output.read_text(encoding="utf-8"))
    assert receipt["classification"] == "synthetic_signed_full_workflow_installed_cli_stdio_mcp"
    assert receipt["receipt_kind"] == "rerunnable_summary_not_detached_attestation"
    assert receipt["probe_sha256"] == hashlib.sha256(PROBE.read_bytes()).hexdigest()
    assert receipt["child_environment_keys"] == sorted({
        "PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "PYTHONNOUSERSITE",
        "ORGANON_ROOT", "ORGANON_APPROVERS_FILE",
    })
    assert receipt["manifest_sha256"] == hashlib.sha256(
        (ROOT / "workflows" / "synthetic_full.json").read_bytes()
    ).hexdigest()
    assert receipt["transport"] == {
        "run_sequence": ["cli", "mcp"] * 6,
        "cli_mcp_status_equal": True,
        "stdio_mcp_real": True,
        "wheel_module_under_site_packages": True,
    }
    decisions = receipt["decisions"]
    assert [entry["target"] for entry in decisions if entry["kind"] == "phase_review"] == PHASES
    assert {entry["target"] for entry in decisions if entry["kind"] == "approval"} == {"n1", "d1"}
    assert len({entry["seq"] for entry in decisions}) == 11
    assert receipt["final"]["revision"] == 49
    assert receipt["final"]["event_counts"] == {
        "approval": 2, "item_put": 29, "phase_advance": 9, "phase_review": 9,
    }
    assert receipt["final"]["artifact_count"] == 29
    assert receipt["final"]["accepted_phases"] == PHASES
    snapshots = receipt["final"]["phase_snapshots"]
    assert set(snapshots) == set(PHASES)
    assert all(len(value) == 64 and set(value) <= set("0123456789abcdef")
               for value in snapshots.values())
    assert receipt["final"]["assessment_verdict"] == "no_demostrado"
    assert receipt["final"]["assessment_claim_scope"] == "field"
    assert receipt["negative_controls"] == {
        "unsigned_normative_mcp_no_write": True,
        "unsigned_phase_cli_no_write": True,
    }
    assert receipt["replay"] == {
        "cli_applied": 0, "mcp_applied": 0, "ledger_byte_identical": True,
    }
    assert receipt["reviewer_key_revocation"] == {
        "all_phases_reopened": True,
        "ledger_byte_identical": True,
        "restoration_recovered_status": True,
    }
    assert receipt["scope"] == {
        "human_identity_authenticated": False,
        "independent_human_judgment_tested": False,
        "field_impact_tested": False,
        "t1_passed_is_invented_manifest_data": True,
        "t1_command_executed_or_authenticated": False,
        "content_is_synthetic": True,
        "private_keys_written_to_disk": False,
    }
