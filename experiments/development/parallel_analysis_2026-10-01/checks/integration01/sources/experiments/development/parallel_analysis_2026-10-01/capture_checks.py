"""Capture offline D116 gates with source bytes and independent runtime roots."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
import tempfile
import time
from pathlib import Path


def source_paths(repo: Path) -> list[str]:
    pending = ["parallel_analysis_broker", "managed_parallel_analysis", "c_parallel_analysis"]
    seen = set()
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        path = repo / "scripts" / f"{name}.py"
        raw = path.read_bytes()
        seen.add(name)
        for node in ast.walk(ast.parse(raw)):
            names = ([entry.name.split(".")[0] for entry in node.names]
                     if isinstance(node, ast.Import) else
                     [node.module.split(".")[0]]
                     if isinstance(node, ast.ImportFrom) and node.module else [])
            pending.extend(item for item in names
                           if (repo / "scripts" / f"{item}.py").is_file())
    return [f"scripts/{name}.py" for name in sorted(seen)]


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
    affected = ["scripts/parallel_analysis_broker.py", "scripts/managed_parallel_analysis.py",
                "scripts/c_parallel_analysis.py", "tests/test_parallel_analysis_broker.py",
                "tests/test_managed_parallel_analysis.py", "tests/test_c_parallel_analysis.py"]
    paths = sorted(set(source_paths(repo)) | set(args.tests) | set(affected) |
                   {helper, "prototypes/core.py", "GOAL.md", "docs/protocolo_experimental.md"})

    def pins() -> list[dict]:
        return [{"path": name, "bytes": len(raw := (repo / name).read_bytes()),
                 "sha256": hashlib.sha256(raw).hexdigest()} for name in paths]

    before = pins()
    metadata = subprocess.run([str(args.python), "-I", "-c",
        "import json,sys; print(json.dumps({'version':sys.version,'executable':sys.executable}))"],
        cwd=repo, capture_output=True, check=True)
    (target / "python_metadata.json").write_bytes(metadata.stdout)
    for row in before:
        destination = target / "sources" / row["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((repo / row["path"]).read_bytes())
    runtime = Path(tempfile.mkdtemp(prefix=f"specorganon-D116-{args.name}-")) / "cases"
    commands = [[str(args.python), "-B", "-m", "pytest", "-q", *args.tests,
                 "--basetemp", str(runtime)],
                ["ruff", "check", *affected, helper],
                [str(args.python), "-I", "-B", "-c",
                 "import pathlib,sys; [compile(pathlib.Path(p).read_bytes(),p,'exec') "
                 "for p in sys.argv[1:]]; print('syntax OK')", *affected, helper],
                ["git", "diff", "--check", "--", "scripts", "tests", "docs", helper]]
    results = []
    for number, command in enumerate(commands, 1):
        started = time.monotonic()
        with (target / f"{number}.stdout").open("wb") as stdout, (target / f"{number}.stderr").open("wb") as stderr:
            process = subprocess.run(command, cwd=repo, stdout=stdout, stderr=stderr,
                                     check=False, timeout=900)
        results.append({"argv": command, "exit_code": process.returncode,
                        "wall_seconds": time.monotonic() - started,
                        "stdout": f"{number}.stdout", "stderr": f"{number}.stderr"})
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo,
                          capture_output=True, check=True).stdout.decode().strip()
    after = pins()
    report = {"classification": "offline_mechanical_checks_not_model_quality",
              "head": head, "python": str(args.python), "runtime_root": str(runtime),
              "interpreter": json.loads(metadata.stdout),
              "sources_before": before, "sources_after": after,
              "source_unchanged": before == after, "commands": results,
              "all_exit_zero": all(row["exit_code"] == 0 for row in results),
              "formal_cells_executed": 0}
    (target / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in
                      ("runtime_root", "all_exit_zero", "source_unchanged")}))
    return 0 if report["all_exit_zero"] and report["source_unchanged"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
