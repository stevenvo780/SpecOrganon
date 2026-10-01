"""Capture proportional offline D116 adapter/wrapper gates without providers."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
import tempfile
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("python", type=Path)
    parser.add_argument("attempt")
    args = parser.parse_args()
    helper = Path(__file__).resolve()
    repo = helper.parents[4]
    target = helper.parent / args.attempt
    target.mkdir(mode=0o700, exist_ok=False)
    affected = ["scripts/managed_parallel_analysis.py", "scripts/c_parallel_analysis.py",
                "tests/test_managed_parallel_analysis.py", "tests/test_c_parallel_analysis.py"]
    pending = ["managed_parallel_analysis", "c_parallel_analysis"]
    seen = set()
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        path = repo / "scripts" / f"{name}.py"
        seen.add(name)
        for node in ast.walk(ast.parse(path.read_bytes())):
            names = ([entry.name.split(".")[0] for entry in node.names]
                     if isinstance(node, ast.Import) else
                     [node.module.split(".")[0]]
                     if isinstance(node, ast.ImportFrom) and node.module else [])
            pending.extend(item for item in names if (repo / "scripts" / f"{item}.py").is_file())
    paths = sorted(set(affected + [str(helper.relative_to(repo)), "prototypes/core.py"] +
                       [f"scripts/{name}.py" for name in seen]))

    def pins():
        return [{"path": name, "bytes": len(raw := (repo / name).read_bytes()),
                 "sha256": hashlib.sha256(raw).hexdigest()} for name in paths]

    before = pins()
    for row in before:
        dest = target / "sources" / row["path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        raw = (repo / row["path"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != row["sha256"]:
            raise RuntimeError("source changed during prelaunch capture")
        dest.write_bytes(raw)
    runtime = Path(tempfile.mkdtemp(prefix=f"specorganon-D116-{args.attempt}-")) / "cases"
    commands = [[str(args.python), "-B", "-m", "pytest", "-q", *affected[2:],
                 "--basetemp", str(runtime)],
                ["ruff", "check", *affected, str(helper.relative_to(repo))],
                [str(args.python), "-I", "-B", "-c",
                 "import pathlib,sys; [compile(pathlib.Path(p).read_bytes(),p,'exec') "
                 "for p in sys.argv[1:]]; print('syntax OK')", *affected]]
    (target / "command.json").write_text(json.dumps({"cwd": str(repo), "commands": commands}, indent=2) + "\n")
    results = []
    for index, command in enumerate(commands, 1):
        started = time.monotonic()
        with (target / f"{index}.stdout").open("wb") as stdout, (target / f"{index}.stderr").open("wb") as stderr:
            process = subprocess.run(command, cwd=repo, stdout=stdout, stderr=stderr,
                                     check=False, timeout=900)
        results.append({"argv": command, "exit_code": process.returncode,
                        "wall_seconds": time.monotonic() - started,
                        "stdout": f"{index}.stdout", "stderr": f"{index}.stderr"})
    after = pins()
    report = {"classification": "offline_mechanical_fixture_not_model_quality",
              "formal_cells_executed": 0, "runtime_root": str(runtime),
              "sources_before": before, "sources_after": after,
              "source_unchanged": before == after, "commands": results,
              "all_exit_zero": all(row["exit_code"] == 0 for row in results)}
    (target / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in ("runtime_root", "source_unchanged", "all_exit_zero")}))
    return 0 if report["source_unchanged"] and report["all_exit_zero"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
