"""Installed CLI SIGKILL during a published March seed, then real MCP resume."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "probe_citibike_march_crash_recovery.py"
SEED = ROOT / "cases" / "citibike_march2024" / "seed.json"
PUBLISHED = ROOT / "experiments" / "development" / "citibike_sample_status_2026-09-27.json"
REAL_LEDGERS = (
    ROOT / "cases" / "citibike_march2024" / "organon.json",
    ROOT / "cases" / "citibike" / "organon.json",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_installed_march_seed_recovers_after_durable_sigkill(tmp_path: Path) -> None:
    before = {path: path.read_bytes() for path in REAL_LEDGERS}
    uv = shutil.which("uv")
    assert uv is not None, "uv is required for the clean-wheel integration test"
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
        "HOME": str(home), "TMPDIR": str(scratch), "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8", "PYTHONNOUSERSITE": "1",
        "UV_CACHE_DIR": str(cache), "UV_OFFLINE": "1", "UV_NO_CONFIG": "1",
    }
    wheel_dir = tmp_path / "wheel-dist"
    built = subprocess.run(
        [uv, "build", "--offline", "--wheel", "--out-dir", str(wheel_dir), str(ROOT)],
        cwd=tmp_path, env=env, text=True, capture_output=True, timeout=90, check=False,
    )
    assert built.returncode == 0, built.stderr
    wheels = list(wheel_dir.glob("specorganon-*.whl"))
    assert len(wheels) == 1
    venv = tmp_path / "wheel-env"
    created = subprocess.run(
        [uv, "venv", "--offline", "--no-project", "--python", sys.executable, str(venv)],
        cwd=tmp_path, env=env, text=True, capture_output=True, timeout=90, check=False,
    )
    assert created.returncode == 0, created.stderr
    python = venv / "bin" / "python"
    installed = subprocess.run(
        [uv, "pip", "install", "--offline", "--python", str(python), str(wheels[0])],
        cwd=tmp_path, env=env, text=True, capture_output=True, timeout=90, check=False,
    )
    assert installed.returncode == 0, installed.stderr
    output = tmp_path / "receipt.json"
    process = subprocess.run(
        [str(python), str(SCRIPT), "--output", str(output)],
        cwd=tmp_path, env=env, text=True, capture_output=True, timeout=120, check=False,
    )
    assert process.returncode == 0, process.stderr
    receipt = json.loads(process.stdout)
    assert receipt == json.loads(output.read_text(encoding="utf-8"))
    assert receipt["classification"] == "development_citibike_march_durable_crash_recovery"
    assert receipt["receipt_kind"] == "rerunnable_summary_not_detached_attestation"
    assert receipt["sha256"]["seed"] == _sha256(SEED)
    assert receipt["sha256"]["published_result"] == _sha256(PUBLISHED)
    assert receipt["sha256"]["manifest"] == (
        "27bc567d7435b5a0accbe9e3653f817323e7925c160f7a88d223f40dc6f04244"
    )
    assert receipt["crash"]["signal"] == "SIGKILL"
    assert receipt["crash"]["returncode"] == -9
    assert receipt["crash"]["after_durable_item_put_seq"] == 16
    assert receipt["crash"]["item_id"] == "e_rental"
    assert receipt["crash"]["prefix_events"] == 16
    assert len(receipt["crash"]["prefix_head_hash"]) == 64
    assert receipt["transport"]["wheel_module_under_site_packages"] is True
    assert {"run", "status", "trace", "gate"} <= set(receipt["transport"]["discovered_tools"])
    assert receipt["mcp_resume"] == {
        "status": "waiting", "cursor": 22, "applied": 6, "skipped": 16,
        "reason": "independent_review_required",
    }
    assert receipt["cli_pre_review_retry"] == {
        "status": "waiting", "cursor": 22, "applied": 0, "skipped": 22,
        "reason": "independent_review_required",
    }
    assert receipt["mcp_advance"] == {
        "status": "waiting", "cursor": 23, "applied": 1, "skipped": 22,
        "reason": "human_approval_required",
    }
    assert receipt["cli_final_retry"] == {
        "status": "waiting", "cursor": 23, "applied": 0, "skipped": 23,
        "reason": "human_approval_required",
    }
    assert receipt["final"]["revision"] == 24
    assert receipt["final"]["event_counts"] == {
        "item_put": 22, "phase_advance": 1, "phase_review": 1,
    }
    assert receipt["final"]["frame_accepted"] is True
    assert receipt["final"]["critique"] == {
        "ready": False, "accepted": False,
        "blockers": ["n_scope requires a verified human approval"],
    }
    assert receipt["final"]["norm_approved"] is False
    for item_id in ("e_eligible", "e_rental", "e_return", "e_excluded", "e_gaps"):
        assert {"p_access", "pr_reanalysis"} <= set(
            receipt["final"]["evidence_ancestors"][item_id]
        )
    assert receipt["criterion_5"] == "not_assessed"
    assert receipt["real_ledgers_unchanged"] is True
    assert receipt["scope"] == {
        "historical_sample_exposed": True,
        "crash_injection_in_temporary_process_only": True,
        "hook_removed_from_mcp_and_retry_environment": True,
        "power_loss_or_storage_fault_tested": False,
        "source_parquet_reopened_in_this_probe": False,
        "independent_human_review": False,
        "reserved_case_or_field_intervention": False,
    }
    assert {path: path.read_bytes() for path in before} == before
