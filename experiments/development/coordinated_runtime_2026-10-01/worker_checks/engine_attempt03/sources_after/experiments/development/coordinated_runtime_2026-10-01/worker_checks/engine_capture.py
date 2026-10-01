"""Capture bounded engine gates and exact before/after evidence without erasure."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "scripts"))
import coordinated_prototype_runtime as runtime  # noqa: E402


def main():
    name, interpreter = sys.argv[1:]
    target = Path(__file__).parent / ("engine_" + name)
    target.mkdir(mode=0o700, exist_ok=False)
    sources = set(runtime._runtime_sources()) | {
        "tests/test_managed_coordinated_prototype.py", "tests/coordinated_runtime_fixture.py", "GOAL.md",
        "experiments/development/coordinated_runtime_2026-10-01/plan.md",
        str(Path(__file__).relative_to(ROOT)),
    }
    def snapshot(folder):
        records = []
        for name in sorted(sources):
            raw = (ROOT / name).read_bytes()
            path = target / folder / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            records.append({"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
        return records
    before = snapshot("sources_before")
    runtime_root = Path(tempfile.mkdtemp(prefix="specorganon-D119-engine-" + name + "-"))
    files = ["scripts/managed_coordinated_prototype.py", "tests/test_managed_coordinated_prototype.py"]
    commands = [[interpreter, "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider", files[1],
                 "--basetemp", str(runtime_root / "cases")], ["ruff", "check", *files],
                [interpreter, "-I", "-B", "-c", "import pathlib,sys;[compile(pathlib.Path(p).read_bytes(),p,'exec') for p in sys.argv[1:]];print('syntax OK')", *files],
                ["git", "diff", "--check", "--", *files]]
    results = []
    for number, argv in enumerate(commands, 1):
        started = time.monotonic()
        with (target / f"{number}.stdout").open("xb") as stdout, (target / f"{number}.stderr").open("xb") as stderr:
            done = subprocess.run(argv, cwd=ROOT, stdout=stdout, stderr=stderr, timeout=900, check=False)
        results.append({"argv": argv, "exit_code": done.returncode, "wall_seconds": time.monotonic() - started,
                        "stdout": f"{number}.stdout", "stderr": f"{number}.stderr"})
        (target / f"{number}.json").write_text(json.dumps(results[-1], indent=2) + "\n")
    after = snapshot("sources_after")
    report = {"schema": 1, "classification": "real_local_engine_tools_with_synthetic_model_responses_no_Q",
              "runtime_root": str(runtime_root), "sources_before": before, "sources_after": after,
              "source_unchanged": before == after, "commands": results,
              "all_exit_zero": all(row["exit_code"] == 0 for row in results), "formal_cells_executed": 0}
    (target / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in ("runtime_root", "source_unchanged", "all_exit_zero")}))
    return 0 if report["source_unchanged"] and report["all_exit_zero"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
