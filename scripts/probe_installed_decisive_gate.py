"""Probe decisive intervention lineage through an installed wheel and CLI.

Usage: ``/fresh-venv/bin/python scripts/probe_installed_decisive_gate.py REPO``.
The case and approvals are disposable synthetic fixtures. This does not prove
that a test command ran, a measurement is authentic, or field impact occurred.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from specorganon import engine


CLASSIFICATION = "development_installed_wheel_decisive_lineage_probe_unsealed"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _cli_gate(case: Path) -> dict[str, Any]:
    command = Path(sys.executable).parent / "organon"
    response = subprocess.run(
        [str(command), "gate", str(case), "validate"],
        text=True,
        capture_output=True,
        check=False,
    )
    _require(response.returncode == 0, f"installed CLI gate failed: {response.stderr}")
    return json.loads(response.stdout)


def probe(repo: Path) -> dict[str, Any]:
    repo = repo.resolve()
    module_path = Path(engine.__file__).resolve()
    venv_path = Path(sys.prefix).resolve()
    _require(sys.prefix != sys.base_prefix, "probe needs a clean virtual environment")
    _require(
        module_path.is_relative_to(venv_path)
        and not module_path.is_relative_to(repo / "src"),
        "specorganon must be imported from the installed environment",
    )
    manifest = json.loads((repo / "workflows" / "synthetic_full.json").read_text())
    os.environ.pop("ORGANON_APPROVERS_FILE", None)
    os.environ.pop("ORGANON_LEDGER_ANCHORS_FILE", None)
    os.environ["ORGANON_ALLOW_FIXTURES"] = "1"
    with tempfile.TemporaryDirectory(
        prefix="specorganon-decisive-installed-"
    ) as directory:
        case = Path(directory) / "case"
        engine.create_case(
            case,
            "Installed decisive lineage fixture",
            "synthetic",
            "agent:lead",
            approval_policy="fixture",
        )
        result_data: dict[str, Any] = {}
        assessment_data: dict[str, Any] = {}
        for step in manifest["steps"]:
            if step["op"] == "advance" and step["phase"] == "validate":
                break
            if step["op"] == "put":
                item = dict(step)
                if item["id"] == "e0":
                    # The decisive claim needs a typed measurement on i1's own
                    # current protocol path. All values remain invented fixtures.
                    item["text"] = "Invented predeclared count measurement for the indicator."
                    item["data"] = {
                        **item["data"],
                        "metric_key": "count",
                        "scope": "fixture",
                        "unit": "count",
                        "value": 10,
                    }
                elif item["id"] == "crit1":
                    item["data"] = {
                        "metric": "count",
                        "threshold": {
                            "operator": ">=",
                            "value": 0.1,
                            "statistic": "lower_ci",
                        },
                        "reject": "below threshold",
                    }
                elif item["id"] == "base1":
                    item["data"] = {
                        "origin": "simulation",
                        "source": "installed synthetic fixture",
                        "date": "2026-09-27",
                        "metric": "count",
                        "value": 0.2,
                        "unit": "count",
                    }
                elif item["id"] == "res1":
                    item["data"] = {
                        "origin": "simulation",
                        "source": "installed synthetic fixture",
                        "date": "2026-09-27",
                        "effect": {
                            "metric": "count",
                            "estimate": 0.3,
                            "interval": [0.15, 0.4],
                            "unit": "count",
                        },
                    }
                    result_data = item["data"]
                elif item["id"] == "ass1":
                    item["data"] = {
                        "verdict": "cumplido",
                        "claim_scope": "simulation",
                        "uncertainty": "synthetic interval",
                        "adverse_effects": "synthetic only",
                        "cost": "synthetic only",
                    }
                    assessment_data = item["data"]
                engine.put_item(
                    case,
                    item["id"],
                    item["kind"],
                    item["text"],
                    item["refs"],
                    item["data"],
                    "agent:author",
                )
                if item["id"] in {"n1", "d1"}:
                    engine.approve(
                        case, item["id"], "synthetic fixture", "human:fixture"
                    )
            elif step["op"] == "advance":
                phase = step["phase"]
                status = engine.gate(case, phase)
                _require(
                    status["ready"],
                    f"{phase} unexpectedly blocked: {status['blockers']}",
                )
                engine.review_phase(
                    case, phase, "accept", "synthetic fixture review", "agent:reviewer"
                )
                engine.advance(case, phase, "agent:lead")

        missing = _cli_gate(case)
        expected = (
            "ass1 success needs a current passed test linked to res1 for crit1 "
            "and implementation of req1"
        )
        _require(
            not missing["ready"]
            and missing["blockers"] == [expected],
            f"missing-test result passed or failed for another reason: {missing}",
        )
        engine.put_item(
            case,
            "res1",
            "result",
            "Synthetic result count.",
            ["base1", "crit1", "t1"],
            result_data,
            "agent:author",
        )
        engine.put_item(
            case,
            "ass1",
            "assessment",
            "Field effectiveness is not demonstrated by this fixture.",
            ["res1", "r1"],
            assessment_data,
            "agent:author",
        )
        linked = _cli_gate(case)
        _require(linked["ready"], f"linked test did not restore readiness: {linked}")
        engine.review_phase(
            case, "validate", "accept", "synthetic fixture review", "agent:reviewer"
        )
        engine.advance(case, "validate", "agent:lead")
        accepted = _cli_gate(case)
        _require(
            accepted["ready"] and accepted["accepted"] and not accepted["blockers"],
            "linked synthetic result was not accepted",
        )
        return {
            "schema": 1,
            "classification": CLASSIFICATION,
            "missing_test_blocked": True,
            "linked_test_accepted": True,
            "final_revision": engine.get_state(case)["revision"],
            "field_impact_tested": False,
            "test_command_execution_authenticated": False,
        }


def main() -> int:
    if len(sys.argv) != 2:
        print(f"Usage: {Path(sys.argv[0]).name} REPO", file=sys.stderr)
        return 2
    try:
        report = probe(Path(sys.argv[1]))
    except (OSError, ValueError, RuntimeError, engine.MethodError) as exc:
        print(f"Installed decisive lineage probe failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
