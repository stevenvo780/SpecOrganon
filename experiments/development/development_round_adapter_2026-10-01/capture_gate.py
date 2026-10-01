"""Preserve source bytes and raw streams for one explicit public offline gate."""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DOSSIER = Path(__file__).resolve().parent
SOURCES = (
    "scripts/plan_development_round.py", "scripts/development_method_tool.py",
    "scripts/prepare_development_round.py", "scripts/preflight_assets.py",
    "scripts/run_managed_team.py", "scripts/run_managed_tool_conversation.py",
    "scripts/managed_run_context.py", "scripts/staged_tool_session.py",
    "scripts/verify_released_run.py", "scripts/verify_staged_run.py",
    "scripts/stage_released_run.py", "prototypes/core.py",
    "tests/test_plan_development_round.py", "tests/test_development_method_tool.py",
    "tests/test_prepare_development_round.py", "tests/test_run_managed_team.py",
    "tests/test_preflight_assets.py", "tests/test_staged_tool_session.py",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("label")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command and args.command[0] == "--" else args.command
    if not re.fullmatch(r"[a-z0-9_]{1,64}", args.label) or not command:
        parser.error("bounded label and explicit command required")
    target = DOSSIER / "gates" / args.label
    target.mkdir(parents=True, exist_ok=False)
    pins = []
    for source in SOURCES:
        raw = (ROOT / source).read_bytes()
        copied = target / "source" / source
        copied.parent.mkdir(parents=True, exist_ok=True)
        copied.write_bytes(raw)
        pins.append({"path": source, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    before = time.monotonic()
    with (target / "stdout").open("wb") as out, (target / "stderr").open("wb") as err:
        result = subprocess.run(command, cwd=ROOT, stdout=out, stderr=err, check=False)
    unchanged = all(hashlib.sha256((ROOT / pin["path"]).read_bytes()).hexdigest() == pin["sha256"] for pin in pins)
    streams = [{"path": str((target / name).relative_to(ROOT)),
                "bytes": (target / name).stat().st_size,
                "sha256": hashlib.sha256((target / name).read_bytes()).hexdigest()}
               for name in ("stdout", "stderr")]
    metadata = {"schema": "specorganon.d112.offline_gate.v1", "command": command,
                "classification": "public_cases_synthetic_workflow_fake_provider",
                "cwd": str(ROOT), "started_at_utc": started, "elapsed_seconds": time.monotonic() - before,
                "exit_code": result.returncode, "source_bytes_unchanged_after": unchanged,
                "sources": pins, "streams": streams, "real_provider_requests": 0,
                "formal_development_cells_executed": 0, "real_reserved_inputs": 0}
    (target / "metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"label": args.label, "exit_code": result.returncode,
                      "elapsed_seconds": metadata["elapsed_seconds"], "source_bytes_unchanged_after": unchanged}))
    return result.returncode if unchanged else 2


if __name__ == "__main__":
    raise SystemExit(main())
