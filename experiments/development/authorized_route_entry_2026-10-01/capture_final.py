"""Capture final frozen gates and original baseline; all HTTP is synthetic."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

DOSSIER = Path(__file__).resolve().parent
ROOT = DOSSIER.parents[2]
sys.path.insert(0, str(DOSSIER))
from archive_runtimes import archive  # noqa: E402

ENV = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "TZ": "UTC", "PYTHONDONTWRITEBYTECODE": "1"}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True)
    freeze = json.loads((DOSSIER / "source_freeze.json").read_bytes())
    before = {row["path"]: (ROOT / row["path"]).read_bytes() for row in freeze["sources"]}
    assert all(sha(before[row["path"]]) == row["sha256"] for row in freeze["sources"])
    for name, raw in before.items():
        path = args.output / "sources" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    commands = []
    def capture(argv, name, timeout=240):
        try:
            result = subprocess.run(argv, cwd=ROOT, env=ENV, capture_output=True, timeout=timeout)
            code, stdout, stderr = result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired as exc:
            code, stdout, stderr = 124, exc.stdout or b"", exc.stderr or b""
        (args.output / (name + ".stdout")).write_bytes(stdout)
        (args.output / (name + ".stderr")).write_bytes(stderr)
        row = {"argv": argv, "exit_code": code, "timeout_seconds": timeout,
               "stdout_sha256": sha(stdout), "stderr_sha256": sha(stderr)}
        commands.append(row)
        (args.output / "commands.json").write_text(json.dumps(commands, indent=2) + "\n")
        return code
    baseline = ROOT / "experiments/development/real_route_proposal_2026-10-01/seal_evidence.py"
    temp = Path(tempfile.mkdtemp(prefix="specorganon-D123-final-"))
    capture([sys.executable, "-I", "-B", str(baseline), "verify"], "baseline_before")
    capture([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-p", "test_authorized_coordinated_runtime.py", "-v"], "entry_tests")
    capture([sys.executable, "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_provider_outcome_accounting.py",
             "--basetemp", str(temp / "unit_cases")], "accounting_tests")
    capture(["/home/dev/.local/bin/ruff", "check", *before], "ruff")
    capture([sys.executable, "-I", "-B", "-c", "import pathlib,sys; [compile(pathlib.Path(p).read_bytes(),p,'exec') for p in sys.argv[1:]]", *before], "compile")
    runtime = temp / "runtime"
    code = capture([sys.executable, "-I", "-B", str(DOSSIER / "integration_checks.py"), "--destination", str(runtime)], "integration", 1200)
    saved = archive(runtime, args.output / "runtimes.tar.gz", args.output / "runtimes_inventory.json")
    if code == 0:
        (args.output / "integration_result.json").write_bytes((runtime / "integration_result.json").read_bytes())
    capture([sys.executable, "-I", "-B", str(baseline), "verify"], "baseline_after")
    capture(["git", "diff", "--check"], "diff")
    unchanged = all((ROOT / name).read_bytes() == raw for name, raw in before.items())
    report = {"python": sys.executable, "version": list(sys.version_info[:3]), "commands": commands,
              "source_freeze_sha256": sha((DOSSIER / "source_freeze.json").read_bytes()),
              "sources_unchanged": unchanged, "archive": saved, "runtime_dir": str(runtime),
              "all_exit_zero": all(row["exit_code"] == 0 for row in commands),
              "formal_cells_executed": 0, "paid_model_requests": 0}
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"report": str(args.output / "report.json"), "all_exit_zero": report["all_exit_zero"], "sources_unchanged": unchanged}))


if __name__ == "__main__":
    main()
