"""Synthetic parity and installed-wheel checks for the field auditors."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "tests"))

import audit_field_flows as legacy_flows  # noqa: E402
import audit_field_guardrails as legacy_guardrails  # noqa: E402
import audit_field_trial_design as legacy_trial  # noqa: E402
from specorganon import field_flows, field_guardrails, field_trial_design  # noqa: E402
from test_audit_field_flows import field_data_with_schema3_allocations  # noqa: E402
from test_audit_field_guardrails import _synthetic_inputs  # noqa: E402
from test_audit_field_trial_design import _plan, _twelve_group_field  # noqa: E402


def _synthetic_case(name: str) -> tuple[list[str], list[Any]]:
    if name == "flows":
        return ["field"], [field_data_with_schema3_allocations()]
    if name == "trial_design":
        field = _twelve_group_field()
        return ["plan", "field"], [_plan(field), field]
    if name == "guardrails":
        return ["plan", "field", "registry", "measurements"], list(_synthetic_inputs())
    raise AssertionError(name)


def _write_case(directory: Path, name: str) -> list[Path]:
    labels, values = _synthetic_case(name)
    paths = [directory / f"{label}.json" for label in labels]
    for path, value in zip(paths, values, strict=True):
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return paths


def _run_cli(
    python: Path, name: str, paths: list[Path], *, packaged: bool,
    directory: Path, installed: bool,
) -> subprocess.CompletedProcess[str]:
    module = f"specorganon.field_{name}"
    target = ["-m", module] if packaged else [str(SCRIPTS / f"audit_field_{name}.py")]
    env = os.environ.copy()
    if installed:
        env.pop("PYTHONPATH", None)
        env["PYTHONNOUSERSITE"] = "1"
    else:
        env["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run(
        [str(python), *( ["-I"] if installed else []), *target, *(str(p) for p in paths)],
        cwd=directory, env=env, capture_output=True, text=True, check=False,
    )


def test_legacy_imports_delegate_to_packaged_functions() -> None:
    assert legacy_flows.audit_field_flows is field_flows.audit_field_flows
    assert legacy_flows.FieldFlowError is field_flows.FieldFlowError
    assert legacy_flows._lineage_bounds is field_flows._lineage_bounds
    assert legacy_trial.audit_field_trial_design is field_trial_design.audit_field_trial_design
    assert legacy_trial.FieldTrialDesignError is field_trial_design.FieldTrialDesignError
    assert legacy_guardrails.audit_field_guardrails is field_guardrails.audit_field_guardrails
    assert legacy_guardrails.canonical_sha256 is field_guardrails.canonical_sha256
    assert legacy_guardrails.FieldGuardrailError is field_guardrails.FieldGuardrailError

    plan, field, registry, measurements = _synthetic_inputs()
    flow_report = legacy_flows.audit_field_flows(field)
    trial_report = legacy_trial.audit_field_trial_design(plan, field)
    guardrail_report = legacy_guardrails.audit_field_guardrails(
        plan, field, registry, measurements,
        plan_sha256=legacy_guardrails.canonical_sha256(plan),
        registry_sha256=legacy_guardrails.canonical_sha256(registry),
    )
    assert flow_report["criterion_3"]["status"] == "not_assessed"
    assert trial_report["execution_ready"] is False
    assert trial_report["criterion_3"]["status"] == "not_assessed"
    assert guardrail_report["execution_ready"] is False
    assert guardrail_report["criterion_3"]["status"] == "not_assessed"


@pytest.mark.parametrize("name", ["flows", "trial_design", "guardrails"])
def test_source_script_and_package_clis_match_on_synthetic_and_invalid_json(
    tmp_path: Path, name: str,
) -> None:
    paths = _write_case(tmp_path, name)
    before = [path.read_bytes() for path in paths]
    module = _run_cli(Path(sys.executable), name, paths, packaged=True,
                      directory=tmp_path, installed=False)
    script = _run_cli(Path(sys.executable), name, paths, packaged=False,
                      directory=tmp_path, installed=False)
    assert (script.returncode, script.stdout, script.stderr) == (
        module.returncode, module.stdout, module.stderr,
    )
    assert script.returncode == 0
    report = json.loads(script.stdout)
    assert report["criterion_3"]["status"] == "not_assessed"
    if name != "flows":
        assert report["execution_ready"] is False
    assert [path.read_bytes() for path in paths] == before

    paths[0].write_text('{"schema":1,"schema":1}', encoding="utf-8")
    module = _run_cli(Path(sys.executable), name, paths, packaged=True,
                      directory=tmp_path, installed=False)
    script = _run_cli(Path(sys.executable), name, paths, packaged=False,
                      directory=tmp_path, installed=False)
    assert (script.returncode, script.stdout, script.stderr) == (
        module.returncode, module.stdout, module.stderr,
    )
    assert script.returncode == 2
    assert "duplicate JSON object key" in script.stdout + script.stderr


def test_wheel_install_runs_packaged_functions_and_legacy_scripts_outside_repo(
    tmp_path: Path,
) -> None:
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is unavailable; installed-wheel field auditor checks were not run")
    wheel_dir = tmp_path / "wheels"
    subprocess.run(
        [uv, "build", "--wheel", "--offline", "--out-dir", str(wheel_dir), str(ROOT)],
        cwd=tmp_path, capture_output=True, text=True, check=True,
    )
    wheels = list(wheel_dir.glob("specorganon-*.whl"))
    assert len(wheels) == 1
    venv = tmp_path / "venv"
    subprocess.run(
        [uv, "venv", "--python", sys.executable, str(venv)],
        cwd=tmp_path, capture_output=True, text=True, check=True,
    )
    python = venv / "bin" / "python"
    subprocess.run(
        [uv, "pip", "install", "--offline", "--no-deps", "--python", str(python),
         str(wheels[0])],
        cwd=tmp_path, capture_output=True, text=True, check=True,
    )

    labels, values = _synthetic_case("guardrails")
    paths = _write_case(tmp_path, "guardrails")
    assert len(labels) == len(values) == len(paths) == 4
    probe = """
import json
import sys
from decimal import Decimal
from pathlib import Path
from specorganon import field_flows, field_trial_design, field_guardrails

plan, field, registry, measurements = [
    json.loads(Path(name).read_text(encoding='utf-8'), parse_float=Decimal)
    for name in sys.argv[1:]
]
flow = field_flows.audit_field_flows(field)
trial = field_trial_design.audit_field_trial_design(plan, field)
guard = field_guardrails.audit_field_guardrails(
    plan, field, registry, measurements,
    plan_sha256=field_guardrails.canonical_sha256(plan),
    registry_sha256=field_guardrails.canonical_sha256(registry),
)
assert all(report['criterion_3']['status'] == 'not_assessed'
           for report in (flow, trial, guard))
assert trial['execution_ready'] is False and guard['execution_ready'] is False
print(json.dumps({'modules': [field_flows.__file__, field_trial_design.__file__,
                              field_guardrails.__file__],
                  'guardrail_rows': guard['group_period_cell_rows']}))
"""
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    installed_probe = subprocess.run(
        [str(python), "-I", "-c", probe, *(str(path) for path in paths)],
        cwd=tmp_path, env=env, capture_output=True, text=True, check=True,
    )
    result = json.loads(installed_probe.stdout)
    assert result["guardrail_rows"] == 720
    assert all(Path(path).resolve().is_relative_to(venv.resolve())
               for path in result["modules"])

    for name in ("flows", "trial_design", "guardrails"):
        case_paths = paths[1:2] if name == "flows" else paths[:2] if name == "trial_design" else paths
        module = _run_cli(python, name, case_paths, packaged=True,
                          directory=tmp_path, installed=True)
        script = _run_cli(python, name, case_paths, packaged=False,
                          directory=tmp_path, installed=True)
        assert (script.returncode, script.stdout, script.stderr) == (
            module.returncode, module.stdout, module.stderr,
        )
        assert script.returncode == 0
        report = json.loads(script.stdout)
        assert report["criterion_3"]["status"] == "not_assessed"
        if name != "flows":
            assert report["execution_ready"] is False
