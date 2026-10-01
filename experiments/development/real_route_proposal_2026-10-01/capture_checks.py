"""Capture offline build/verify commands for proposed R1 routes, without runs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
DOSSIER = Path(__file__).resolve().parent
FREEZE = "6724df13d881e46b08c17213e440a5e231eca16c5541abc283f06ae101f4a044"
CONTRACTS = ROOT / "experiments/development/coordinated_contract_2026-10-01/public_contract"
PREPARER = ROOT / "scripts/prepare_coordinated_development.py"
OPTIONS = ("astra", "luna")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def capture(argv: list[str], output: Path, name: str) -> dict:
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=240, check=False)
    (output / f"{name}.stdout").write_bytes(result.stdout)
    (output / f"{name}.stderr").write_bytes(result.stderr)
    record = {"argv": argv, "exit_code": result.returncode,
              "stdout_sha256": digest(result.stdout), "stderr_sha256": digest(result.stderr)}
    (output / f"{name}.command.json").write_text(json.dumps(record, indent=2) + "\n")
    if result.returncode:
        raise RuntimeError(f"{name} failed; original streams retained")
    return {**record, "result": json.loads(result.stdout)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", choices=("311", "312"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    temp = Path(tempfile.mkdtemp(prefix=f"specorganon-D122-{args.label}-"))
    os.chmod(temp, 0o700)
    sys.path.insert(0, str(ROOT / "scripts"))
    from coordinated_prototype_runtime import validate_configuration
    from plan_coordinated_development import runtime_descriptor, validate_schedule

    original = {path: path.read_bytes() for option in OPTIONS
                for path in (DOSSIER / "candidates" / option).glob("*.json")}
    results = []
    for option in OPTIONS:
        candidate = DOSSIER / "candidates" / option
        bundle = temp / option
        saved = args.output / option
        saved.mkdir()
        build = capture([sys.executable, "-I", "-B", str(PREPARER), "build",
                         "--destination", str(bundle), "--configuration",
                         str(candidate / "configuration.json"), "--contract-dir", str(CONTRACTS),
                         "--source-freeze-sha256", FREEZE], saved, "build")
        verify = capture([sys.executable, "-I", "-B", str(PREPARER), "verify",
                          "--bundle", str(bundle)], saved, "verify")
        assert build["result"] == verify["result"]
        assert verify["result"]["formal_cells_executed"] == 0
        assert verify["result"]["prepared_cell_count"] == 12
        for filename in ("bundle.json", "schedule.json", "assets.json", "price_profile.json"):
            (saved / filename).write_bytes((bundle / filename).read_bytes())
        (saved / "runtime_policy.json").write_bytes((bundle / "assets/runtime_policy.json").read_bytes())
        schedule = validate_schedule(json.loads((bundle / "schedule.json").read_bytes()))
        runtime = json.loads((candidate / "runtime_configuration.json").read_bytes())
        descriptors = [runtime_descriptor(schedule, row["run_id"]) for row in schedule["runs"]]
        for descriptor in descriptors:
            validate_configuration(runtime, descriptor)
        results.append({"option": option, "build": build, "verify": verify,
                        "runtime_configurations_validated": len(descriptors),
                        "schedule_sha256": schedule["schedule_sha256"]})
    assert all(path.read_bytes() == raw for path, raw in original.items())
    report = {"schema": 1, "classification": "offline_route_proposal_not_R1",
              "python": sys.executable, "version": list(sys.version_info[:3]),
              "temporary_parent": str(temp), "results": results,
              "candidate_bytes_unchanged": True, "formal_cells_executed": 0,
              "provider_requests": 0, "runtime_release_or_step_invoked": False}
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"report": str(args.output / "report.json"),
                      "offline_cli_commands": 4, "formal_cells_executed": 0}))


if __name__ == "__main__":
    main()
