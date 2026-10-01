"""Capture proportional D124 tests with exact sources and original streams."""
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
FILES = ("scripts/development_rating_ingress.py", "scripts/read_development_rating.py",
         "tests/test_development_rating_ingress.py", "tests/test_read_development_rating.py")
PREFIX = DOSSIER.relative_to(ROOT).as_posix()
FILES += tuple(PREFIX + "/" + name for name in (
    "capture_checks.py", "integration_cli.py", "archive_originals.py", "seal_evidence.py"))
ENV = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "TZ": "UTC", "PYTHONDONTWRITEBYTECODE": "1"}
sys.path.insert(0, str(DOSSIER))
import seal_evidence as sealing  # noqa: E402


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True)
    preserved_before = sealing.preserve_baseline()
    head_before = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, env=ENV)
    freeze_before = (DOSSIER / "source_freeze.json").read_bytes()
    before = {name: (ROOT / name).read_bytes() for name in FILES}
    for name, raw in before.items():
        target = args.output / "sources" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    temp = Path(tempfile.mkdtemp(prefix="specorganon-D124-local-tests-"))
    commands = [[sys.executable, "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider",
                 "tests/test_development_rating_ingress.py", "tests/test_read_development_rating.py",
                 "--basetemp", str(temp / "cases")], ["/home/dev/.local/bin/ruff", "check", *FILES],
                [sys.executable, "-I", "-B", "-c", "import pathlib,sys;[compile(pathlib.Path(p).read_bytes(),p,'exec') for p in sys.argv[1:]]", *FILES],
                ["git", "diff", "--check"],
                [sys.executable, "-I", "-B", str(DOSSIER / "integration_cli.py"),
                 "--output", str(args.output / "cli")]]
    records = []
    for index, command in enumerate(commands):
        try:
            result = subprocess.run(command, cwd=ROOT, env=ENV, capture_output=True, timeout=120)
        except subprocess.TimeoutExpired as error:
            result = subprocess.CompletedProcess(command, 124, error.stdout or b"", error.stderr or b"")
        (args.output / f"{index}.stdout").write_bytes(result.stdout)
        (args.output / f"{index}.stderr").write_bytes(result.stderr)
        records.append({"argv": command, "exit_code": result.returncode,
                        "stdout_sha256": sha(result.stdout), "stderr_sha256": sha(result.stderr)})
    integration = None
    archive_result = None
    if records[-1]["exit_code"] == 0:
        integration = json.loads((args.output / "cli/integration_result.json").read_bytes())
        command = [sys.executable, "-I", "-B", str(DOSSIER / "archive_originals.py"),
                   "--root", integration["original_root"], "--archive", str(args.output / "originals.tar.gz"),
                   "--inventory", str(args.output / "originals_inventory.json")]
        result = subprocess.run(command, cwd=ROOT, env=ENV, capture_output=True, timeout=120)
        (args.output / "5.stdout").write_bytes(result.stdout)
        (args.output / "5.stderr").write_bytes(result.stderr)
        records.append({"argv": command, "exit_code": result.returncode,
                        "stdout_sha256": sha(result.stdout), "stderr_sha256": sha(result.stderr)})
        if result.returncode == 0:
            archive_result = json.loads(result.stdout)
    preserved_after = sealing.preserve_baseline()
    value = {"python": sys.executable, "commands": records,
             "source_sha256": {name: sha(raw) for name, raw in before.items()},
             "source_unchanged": all((ROOT / name).read_bytes() == raw for name, raw in before.items()),
             "all_exit_zero": all(r["exit_code"] == 0 for r in records), "actual_human_evaluations": 0,
             "formal_cells_executed": 0, "paid_api_requests": 0, "integration": integration,
             "original_archive": archive_result, "preserved_before": preserved_before,
             "preserved_after": preserved_after, "preservation_unchanged": preserved_before == preserved_after,
             "source_freeze_sha256": sha(freeze_before),
             "source_freeze_unchanged": (DOSSIER / "source_freeze.json").read_bytes() == freeze_before,
             "head_before": head_before.decode().strip(),
             "head_after": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, env=ENV).decode().strip()}
    (args.output / "report.json").write_text(json.dumps(value, indent=2) + "\n")
    print(json.dumps({"report": str(args.output / "report.json"), "all_exit_zero": value["all_exit_zero"]}))
    return 0 if (value["all_exit_zero"] and value["source_unchanged"] and value["source_freeze_unchanged"]
                 and value["preservation_unchanged"] and value["head_before"] == value["head_after"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
