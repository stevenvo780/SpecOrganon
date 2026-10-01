"""Capture D117 offline gates, exact source bytes and separate runtime roots."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import time


def source_paths(repo: Path) -> list[str]:
    pending = ["parent_analysis_broker", "managed_parent_analysis", "c_parent_analysis", "prepare_development_round"]
    seen = set()
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        path = repo / "scripts" / (name + ".py")
        seen.add(name)
        for node in ast.walk(ast.parse(path.read_bytes())):
            names = ([entry.name.split(".")[0] for entry in node.names] if isinstance(node, ast.Import)
                     else [node.module.split(".")[0]] if isinstance(node, ast.ImportFrom) and node.module else [])
            pending.extend(item for item in names if (repo / "scripts" / (item + ".py")).is_file())
    return ["scripts/" + name + ".py" for name in sorted(seen)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--tests", nargs="+", required=True)
    args = parser.parse_args()
    dossier = Path(__file__).resolve().parent
    repo = dossier.parents[2]
    target = dossier / "checks" / args.name
    target.mkdir(parents=True, exist_ok=False)
    helper = str(Path(__file__).relative_to(repo))
    affected = ["scripts/parent_analysis_broker.py", "scripts/managed_parent_analysis.py", "scripts/c_parent_analysis.py",
                "tests/test_parent_analysis_broker.py", "tests/test_managed_parent_analysis.py", "tests/test_c_parent_analysis.py"]
    extras = {helper, "prototypes/core.py", "GOAL.md", "docs/protocolo_experimental.md",
              "experiments/development/parallel_analysis_2026-10-01/integration_checks.py"}
    for name in ("integration_checks.py", "verify_traces.py", "archive_runtimes.py"):
        path = dossier / name
        if path.exists():
            extras.add(str(path.relative_to(repo)))
    paths = sorted(set(source_paths(repo)) | set(args.tests) | set(affected) | extras)

    def pins():
        return [{"path": path, "bytes": len(raw := (repo / path).read_bytes()),
                 "sha256": hashlib.sha256(raw).hexdigest()} for path in paths]

    before = pins()
    for record in before:
        dest = target / "sources" / record["path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((repo / record["path"]).read_bytes())
    metadata = subprocess.run([str(args.python), "-I", "-B", "-c",
        "import json,sys;print(json.dumps({'version':sys.version,'executable':sys.executable}))"],
        cwd=repo, capture_output=True, check=True)
    (target / "python_metadata.json").write_bytes(metadata.stdout)
    runtime = Path(tempfile.mkdtemp(prefix="specorganon-D117-" + args.name + "-")) / "cases"
    commands = [[str(args.python), "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider", *args.tests,
                 "--basetemp", str(runtime)], ["ruff", "check", *affected, helper],
                [str(args.python), "-I", "-B", "-c",
                 "import pathlib,sys;[compile(pathlib.Path(p).read_bytes(),p,'exec') for p in sys.argv[1:]];print('syntax OK')",
                 *affected, helper], ["git", "diff", "--check", "--", "scripts", "tests", "docs", helper]]
    results = []
    for number, argv in enumerate(commands, 1):
        started = time.monotonic()
        with (target / f"{number}.stdout").open("wb") as out, (target / f"{number}.stderr").open("wb") as err:
            result = subprocess.run(argv, cwd=repo, stdout=out, stderr=err, timeout=1200, check=False)
        results.append({"argv": argv, "exit_code": result.returncode, "wall_seconds": time.monotonic() - started,
                        "stdout": f"{number}.stdout", "stderr": f"{number}.stderr"})
    after = pins()
    report = {"classification": "offline_mechanical_checks_not_model_quality",
              "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo).decode().strip(),
              "python": str(args.python), "runtime_root": str(runtime), "interpreter": json.loads(metadata.stdout),
              "sources_before": before, "sources_after": after, "source_unchanged": before == after,
              "commands": results, "all_exit_zero": all(row["exit_code"] == 0 for row in results),
              "formal_cells_executed": 0}
    (target / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in ("runtime_root", "all_exit_zero", "source_unchanged")}))
    return 0 if report["source_unchanged"] and report["all_exit_zero"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
