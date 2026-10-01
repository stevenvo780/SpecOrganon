"""Exercise only build/prepare CLI with the explicit fake configuration."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DOSSIER = Path(__file__).resolve().parent


def main() -> int:
    workspace = Path(tempfile.mkdtemp(prefix="specorganon-D112-cli-"))
    bundle, attempt = workspace / "bundle", workspace / "attempt"
    script = ROOT / "scripts/prepare_development_round.py"
    build = subprocess.run([sys.executable, str(script), "build",
                            str(DOSSIER / "fixture_configuration.json"), str(bundle)],
                           capture_output=True, check=False)
    (workspace / "build.stdout").write_bytes(build.stdout)
    (workspace / "build.stderr").write_bytes(build.stderr)
    if build.returncode != 0:
        sys.stdout.buffer.write(build.stdout)
        sys.stderr.buffer.write(build.stderr)
        return build.returncode
    schedule = json.loads((bundle / "schedule.json").read_text())
    run = next(item for item in schedule["runs"]
               if item["arm"] == "C" and item["case_id"] == "D-E" and item["replica"] == 2)
    prepare = subprocess.run([sys.executable, str(script), "prepare", str(bundle),
                              run["run_id"], str(attempt)], capture_output=True, check=False)
    (workspace / "prepare.stdout").write_bytes(prepare.stdout)
    (workspace / "prepare.stderr").write_bytes(prepare.stderr)
    if prepare.returncode != 0:
        sys.stdout.buffer.write(prepare.stdout)
        sys.stderr.buffer.write(prepare.stderr)
        return prepare.returncode
    status = json.loads(prepare.stdout)
    metadata = json.loads((attempt / "preparation.json").read_text())
    if (status["state"] != "prepared" or status["budget"]["request_count"] != 0
            or metadata["formal_cell_executed"] is not False
            or metadata["execution_authorized"] is not False):
        raise ValueError("CLI preparation unexpectedly executed or authorized a cell")
    print(json.dumps({"workspace": str(workspace), "classification": "offline_fixture_cli_smoke",
                      "build_exit_code": build.returncode, "prepare_exit_code": prepare.returncode,
                      "scheduled_preparations": schedule["run_count"], "run_id": run["run_id"],
                      "coordinates": {key: run[key] for key in ("arm", "case_id", "replica")},
                      "state": status["state"], "model_requests": 0, "formal_cells_executed": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
