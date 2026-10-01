"""Capture bounded offline D115 checks and exact before/after source bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--tests", nargs="+", required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[3]
    dossier = Path(__file__).resolve().parent
    target = dossier / "checks" / args.name
    target.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(repo / "scripts"))
    from managed_parallel_tools import _sources

    affected = ["scripts/c_parallel_tools.py", "scripts/development_branch_tool.py",
                "scripts/managed_parallel_tools.py", "scripts/managed_parallel_wave.py",
                "scripts/parallel_tool_broker.py", "tests/test_c_parallel_tools.py",
                "tests/test_managed_parallel_tools.py", "tests/test_parallel_tool_broker.py"]
    helper = str(Path(__file__).relative_to(repo))
    paths = sorted(set(_sources()) | set(args.tests) | set(affected) | {helper, "prototypes/core.py"})

    def pins():
        return [{"path": name, "bytes": len(raw := (repo / name).read_bytes()),
                 "sha256": hashlib.sha256(raw).hexdigest()} for name in paths]

    before = pins()
    for row in before:
        path = target / "sources" / row["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((repo / row["path"]).read_bytes())
    base = Path(tempfile.mkdtemp(prefix=f"specorganon-D115-{args.name}-")) / "cases"
    commands = [[str(args.python), "-B", "-m", "pytest", "-q", *args.tests, "--basetemp", str(base)],
                ["ruff", "check", *affected, helper],
                [str(args.python), "-I", "-B", "-c",
                 "import pathlib,sys; [compile(pathlib.Path(p).read_bytes(),p,'exec') "
                 "for p in sys.argv[1:]]; print('syntax OK')", *affected, helper],
                ["git", "diff", "--check"]]
    results = []
    for index, command in enumerate(commands, 1):
        started = time.monotonic()
        with (target / f"{index}.stdout").open("wb") as stdout, (target / f"{index}.stderr").open("wb") as stderr:
            process = subprocess.run(command, cwd=repo, stdout=stdout, stderr=stderr, check=False)
        results.append({"argv": command, "exit_code": process.returncode,
                        "wall_seconds": time.monotonic() - started,
                        "stdout": f"{index}.stdout", "stderr": f"{index}.stderr"})
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, check=True).stdout.decode().strip()
    after = pins()
    result = {"classification": "offline_mechanical_checks_no_model_calls", "commit": commit,
              "python": str(args.python), "runtime_root": str(base),
              "sources_before": before, "sources_after": after, "source_unchanged": before == after,
              "commands": results, "all_exit_zero": all(row["exit_code"] == 0 for row in results),
              "formal_cells_executed": 0}
    (target / "report.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: result[key] for key in ("runtime_root", "all_exit_zero", "source_unchanged")}))
    return 0 if result["all_exit_zero"] and result["source_unchanged"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
