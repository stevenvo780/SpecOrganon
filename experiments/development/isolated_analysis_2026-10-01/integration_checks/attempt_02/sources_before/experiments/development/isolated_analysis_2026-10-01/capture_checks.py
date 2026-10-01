"""Capture D113 local checks with exact source copies and command streams."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
from run_managed_team import _source_closure  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("attempt")
    parser.add_argument("--python", required=True)
    parser.add_argument("--basetemp", required=True)
    parser.add_argument("--select")
    parser.add_argument("tests", nargs="+")
    args = parser.parse_args()
    output = Path(__file__).resolve().parent / "integration_checks" / args.attempt
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    sources = set(_source_closure()) | set(args.tests) | {
        "scripts/development_method_tool.py", "scripts/development_analysis_tool.py",
        "scripts/development_analysis_inputs.py", "scripts/verify_development_analysis.py",
        "scripts/prepare_development_round.py", "scripts/plan_development_round.py",
        "GOAL.md", "docs/protocolo_experimental.md", "prototypes/core.py",
        str(Path(__file__).resolve().relative_to(ROOT)),
        "tests/test_prepare_development_round.py", "tests/test_run_managed_team.py",
        "tests/test_staged_tool_session.py",
    }
    sources.update(str(path.relative_to(ROOT)) for path in
                   (Path(__file__).resolve().parent / "fixtures").iterdir() if path.is_file())
    before = {}
    for name in sorted(sources):
        raw = (ROOT / name).read_bytes()
        before[name] = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
        copied = output / "sources_before" / name
        copied.parent.mkdir(parents=True, exist_ok=True)
        copied.write_bytes(raw)
    environment = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8",
                   "PYTHONDONTWRITEBYTECODE": "1"}
    pytest = [args.python, "-m", "pytest", "-q", *args.tests, "--basetemp=" + args.basetemp]
    if args.select:
        pytest += ["-k", args.select]
    python_sources = [name for name in sorted(sources) if name.endswith(".py")]
    commands = [["ruff", "check", *python_sources],
                [args.python, "-m", "py_compile", *python_sources], pytest]
    results = []
    for number, argv in enumerate(commands, 1):
        print("START", number, json.dumps(argv), flush=True)
        started = time.monotonic()
        child = subprocess.run(argv, cwd=ROOT, env=environment, capture_output=True)
        (output / f"{number:02d}.stdout").write_bytes(child.stdout)
        (output / f"{number:02d}.stderr").write_bytes(child.stderr)
        record = {"argv": argv, "exit_code": child.returncode,
                  "elapsed_seconds": time.monotonic() - started,
                  "stdout_sha256": hashlib.sha256(child.stdout).hexdigest(),
                  "stderr_sha256": hashlib.sha256(child.stderr).hexdigest()}
        results.append(record)
        print(json.dumps(record), child.stdout.decode(errors="replace")[-5000:],
              child.stderr.decode(errors="replace")[-2000:], flush=True)
    after = {name: {"sha256": hashlib.sha256((ROOT / name).read_bytes()).hexdigest(),
                    "bytes": (ROOT / name).stat().st_size} for name in sorted(sources)}
    passed = before == after and all(item["exit_code"] == 0 for item in results)
    receipt = {"classification": "local_mechanical_checks_not_formal_model_cells", "passed": passed,
               "sources_before": before, "sources_after": after, "source_unchanged": before == after,
               "commands": results, "basetemp": args.basetemp}
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
