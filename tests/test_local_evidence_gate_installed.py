"""Real offline wheel CLI/MCP reject changed local PDF bytes without ledger writes."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "scripts" / "probe_local_evidence_gate.py"
PDFS = ("source_lca.pdf", "source_survey.pdf")


def _run(argv: list[str], cwd: Path, env: dict[str, str], *, timeout: int = 90
         ) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=cwd, env=env, text=True, capture_output=True,
                          timeout=timeout, check=False)


def _offline_result(result: subprocess.CompletedProcess[str], operation: str) -> None:
    if result.returncode == 0:
        return
    missing_cache = (
        "was not found in the cache", "not available in the cache",
        "not found in cache", "no cached version", "not available locally",
    )
    if any(marker in result.stderr.lower() for marker in missing_cache):
        pytest.skip(f"{operation} unavailable: required dependency is absent from the offline uv cache; "
                    "installed CLI/MCP PDF integrity checks were not run. " + result.stderr.strip())
    pytest.fail(f"{operation} failed: {result.stderr.strip()}")


@pytest.fixture(scope="module")
def offline_wheel(tmp_path_factory) -> tuple[Path, Path, dict[str, str]]:
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv unavailable; offline wheel build/install and real installed CLI/MCP PDF checks were not run")
    cache_setting = os.environ.get("UV_CACHE_DIR")
    xdg_cache = os.environ.get("XDG_CACHE_HOME")
    cache = (Path(cache_setting) if cache_setting else Path(xdg_cache) / "uv" if xdg_cache
             else Path.home() / ".cache" / "uv")
    if not cache.is_absolute() or not cache.is_dir():
        pytest.skip("offline uv cache directory unavailable; installed CLI/MCP PDF checks were not run")
    work = tmp_path_factory.mktemp("local-evidence-wheel")
    home = work / "home"
    scratch = work / "tmp"
    home.mkdir()
    scratch.mkdir()
    env = {
        "PATH": os.pathsep.join((str(Path(uv).parent), str(Path(sys.executable).parent),
                                 "/usr/bin", "/bin")),
        "HOME": str(home), "TMPDIR": str(scratch), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
        "PYTHONNOUSERSITE": "1", "UV_CACHE_DIR": str(cache),
        "UV_OFFLINE": "1", "UV_NO_CONFIG": "1", "UV_PYTHON_DOWNLOADS": "never",
    }
    wheel_dir = work / "dist"
    built = _run([uv, "build", "--offline", "--wheel", "--out-dir", str(wheel_dir), str(ROOT)],
                 work, env)
    _offline_result(built, "offline toolkit wheel build")
    wheels = list(wheel_dir.glob("specorganon-*.whl"))
    assert len(wheels) == 1, "offline build did not produce exactly one toolkit wheel"
    return Path(uv), wheels[0], env


@pytest.mark.parametrize("python_minor", ["3.11", "3.12", "3.13"])
def test_installed_signed_local_pdf_gate_reopens_and_recovers_both_transports(
    tmp_path: Path, offline_wheel: tuple[Path, Path, dict[str, str]], python_minor: str,
) -> None:
    interpreter = shutil.which(f"python{python_minor}")
    if interpreter is None and ".".join(map(str, sys.version_info[:2])) == python_minor:
        interpreter = sys.executable
    if interpreter is None:
        pytest.skip(f"Python {python_minor} unavailable locally; installed CLI/MCP PDF integrity "
                    "checks for that interpreter were not run; no interpreter download was attempted")
    uv, wheel, build_env = offline_wheel
    env = dict(build_env)
    home = tmp_path / "home"
    scratch = tmp_path / "tmp"
    home.mkdir()
    scratch.mkdir()
    env.update({"HOME": str(home), "TMPDIR": str(scratch)})
    venv = tmp_path / "wheel-env"
    created = _run([str(uv), "venv", "--offline", "--no-project", "--python", interpreter, str(venv)],
                   tmp_path, env)
    assert created.returncode == 0, created.stderr
    python = venv / "bin" / "python"
    installed = _run([str(uv), "pip", "install", "--offline", "--python", str(python), str(wheel)],
                     tmp_path, env)
    _offline_result(installed, f"offline toolkit wheel install on Python {python_minor}")
    checked = _run([str(uv), "pip", "check", "--python", str(python)], tmp_path, env)
    assert checked.returncode == 0, checked.stderr
    output = tmp_path / "receipt.json"
    originals = {name: (ROOT / "cases" / "bread_norway" / name).read_bytes() for name in PDFS}
    process = _run([str(python), str(PROBE), str(ROOT), "--cli", str(venv / "bin" / "organon"),
                    "--mcp", str(venv / "bin" / "organon-mcp"), "--output", str(output)],
                   tmp_path, env, timeout=180)
    assert process.returncode == 0, process.stderr
    receipt = json.loads(process.stdout)
    assert receipt == json.loads(output.read_text(encoding="utf-8"))
    assert receipt["python_version"].startswith(python_minor + ".")
    assert receipt["classification"] == "signed_local_pdf_evidence_gate_installed_cli_stdio_mcp"
    assert receipt["receipt_kind"] == "rerunnable_summary_not_detached_attestation"
    assert receipt["probe_sha256"] == hashlib.sha256(PROBE.read_bytes()).hexdigest()
    assert receipt["manifest_sha256"] == hashlib.sha256(
        (ROOT / "cases" / "bread_norway" / "frame_manifest.json").read_bytes()
    ).hexdigest()
    assert receipt["executed_puts_manifest_sha256"] != receipt["manifest_sha256"]
    assert receipt["stripped_operation_counts"] == {"advance": 1}
    assert receipt["original_sources"] == [
        {"archive": name, "original_sha256": hashlib.sha256(originals[name]).hexdigest(),
         "source_sha256": hashlib.sha256(originals[name]).hexdigest(), "size_bytes": len(originals[name])}
        for name in PDFS
    ]
    assert receipt["transport"] == {
        "stdio_mcp_real": True, "wheel_module_under_site_packages": True,
        "cli_mcp_status_and_gate_equal": True, "status_gate_pairs": 9,
        "required_tools_discovered": ["advance", "gate", "phase_review_challenge", "review_phase", "run", "status"],
    }
    assert receipt["child_environment_keys"] == sorted({
        "PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "PYTHONNOUSERSITE",
        "ORGANON_ROOT", "ORGANON_APPROVERS_FILE",
    })
    accepted = receipt["accepted"]
    assert accepted["revision"] == 21
    assert all(accepted["frame"][field] for field in (
        "ready", "reviewed", "accepted", "review_signature_verified",
    ))
    assert set(receipt["controls"]) == {"mutate", "remove", "symlink"}
    expected_evidence = sorted({
        "e_product_mass", "e_wheat_origin", "e_mill_energy", "e_mill_bran",
        "e_mill_transport", "e_baker_energy", "e_retail_waste", "e_household_est",
    })
    expected_dependents = sorted({
        "p_bread_value", "a_bread_chain", "b_bread_scope", "c_bread_value", "s_bread_history",
        "f_bread_mass", "f_bread_service", "n_bread_harm", "q_bread_chain", "h_bread_packaging",
    })
    for mode, control in receipt["controls"].items():
        assert not control["frame"]["ready"] and not control["frame"]["accepted"]
        assert not control["frame"]["reviewed"]
        assert control["frame"]["snapshot"] != accepted["frame"]["snapshot"]
        assert control["affected_evidence_ids"] == expected_evidence
        assert control["dependent_issue_ids"] == expected_dependents
        assert control["evidence_issue"] == (
            "local archive bytes differ from source_sha256" if mode == "mutate"
            else "local archive is missing or unsafe to read"
        )
        assert control["other_pdf_evidence_valid"] is True
        assert control["cli_advance_exit_code"] == 1
        assert control["mcp_advance_is_error"] is True
        assert control["run"] == {
            "status": "waiting", "reason": "invalid_or_stale_artifact",
            "cli_applied": 0, "mcp_applied": 0, "skipped_each": 19,
        }
        assert control["ledger_byte_identical"] is True
        assert control["restoration_recovered_status"] is True
        assert control["replay"] == {
            "cli_applied": 0, "mcp_applied": 0, "skipped_each": 20, "ledger_byte_identical": True,
        }
    assert receipt["controls"]["symlink"]["symlink_target_has_original_digest"] is True
    final = receipt["final"]
    assert final["revision"] == 21 and final["item_count"] == 19
    assert final["event_counts"] == {"item_put": 19, "phase_review": 1, "phase_advance": 1}
    assert final["frame"] == accepted["frame"]
    assert final["ledger_byte_identical"] is True
    assert final["original_case_pdf_bytes_unchanged"] is True
    assert receipt["limits"] == {
        "changed_archive": "source_lca.pdf", "changed_archives": 1, "copied_archives": 2,
        "accepted_phases_tested": ["frame"], "local_archive_max_bytes": 32 * 1024 * 1024,
        "archive_size_boundary_tested": False, "concurrent_file_replacement_tested": False,
        "local_byte_integrity_tested": True, "recursive_dependency_invalidation_tested": True,
        "synthetic_reviewer_signature_tested": True, "publisher_custody_authenticated": False,
        "human_identity_authenticated": False, "independent_human_judgment_tested": False,
        "pdf_claims_semantically_verified": False, "field_impact_tested": False,
        "private_keys_written_to_disk": False, "paid_model_calls": 0,
    }
    assert str(tmp_path) not in process.stdout and str(ROOT) not in process.stdout
    assert '"signature":' not in process.stdout and '"message_base64":' not in process.stdout
    assert all((ROOT / "cases" / "bread_norway" / name).read_bytes() == raw
               for name, raw in originals.items())
