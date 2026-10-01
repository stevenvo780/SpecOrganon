"""Bounded D121 gates and preservation checks; every attempt gets a new path."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import subprocess
import tempfile

DOSSIER = Path(__file__).resolve().parent
ROOT = DOSSIER.parents[2]
DOCS = {"docs/estado.md", "docs/decisiones.md", "docs/activacion_validacion.md", "docs/validacion_actual.md"}
PYTHONS = {key: Path("/tmp/specorganon-D107-deps-re8v1j45") / ("venv-" + key) / "bin/python" for key in ("311", "312")}
OLD = ROOT / "experiments/development/coordinated_measurement_2026-10-01"
spec = importlib.util.spec_from_file_location("d120_capture", OLD / "capture_measurements.py")
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
capture, runtime_inventory = old.capture, old.runtime_inventory


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write(path, value):
    with path.open("xb") as stream:
        stream.write(json.dumps(value, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n")


def source_records():
    raw = (DOSSIER / "source_freeze.json").read_bytes()
    freeze = json.loads(raw)
    for row in freeze["records"] + freeze["external_tools"]:
        data = (ROOT / row["path"]).read_bytes()
        if (len(data), sha(data)) != (row["bytes"], row["sha256"]):
            raise ValueError("frozen source differs")
    return freeze["records"] + [{"path": str((DOSSIER / "source_freeze.json").relative_to(ROOT)), "bytes": len(raw), "sha256": sha(raw)}]


def preserve_baseline():
    checked = {}
    for prefix, commit, expected in (
        ("coordinated_runtime_2026-10-01", "c64169c15c5cbe6dd35c5fc4c25704fc042332a7", "cd41baa29e59e1e75d7ed9e46412e0885b13c0b02e72629ea1af1dc55ab28b07"),
        ("coordinated_measurement_2026-10-01", "f05bb9ca00914ac5b17b2e05c95d726522bb0a2b", "87ed0c79a38e35bb6f0788b95ef1ef81029062ba68ff67e2827960e923313cdd")):
        path = ROOT / "experiments/development" / prefix / "receipt.json"
        raw = path.read_bytes()
        assert sha(raw) == expected
        records = json.loads(raw)["records"]
        for row in records:
            if row["path"] in DOCS:
                data = subprocess.check_output(["git", "show", commit + ":" + row["path"]], cwd=ROOT)
            else:
                source = ROOT / row["path"]
                info = source.lstat()
                assert stat.S_ISREG(info.st_mode)
                assert ("100755" if info.st_mode & 0o111 else "100644") == row["mode"]
                data = source.read_bytes()
            assert (len(data), sha(data)) == (row["bytes"], row["sha256"]), row["path"]
        checked[prefix] = {"receipt_sha256": expected, "pins": len(records) + 1, "historical_docs": sorted(DOCS)}
    # Old original runs remain read-only; compare full inventories before/after.
    checked["original_runtimes"] = [runtime_inventory(root / label / "run") for root in old.RUNTIME_ROOTS.values()
                                    for label in (arm + "-" + case for arm in "ABC" for case in ("D-F", "D-E"))]
    return checked


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    parser.add_argument("--python", choices=PYTHONS, required=True)
    parser.add_argument("--integration", action="store_true")
    args = parser.parse_args(argv)
    assert args.name.isalnum()
    output = DOSSIER / "checks" / args.name
    output.mkdir(parents=True, exist_ok=False)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    before, baseline = source_records(), preserve_baseline()
    write(output / "sources_before.json", before)
    write(output / "baseline_before.json", baseline)
    python = str(PYTHONS[args.python])
    affected = ["scripts/coordinated_observation_journal.py", "scripts/observed_coordinated_runtime.py",
                "tests/test_coordinated_observation_journal.py", "tests/test_observed_coordinated_runtime.py"]
    helpers = [str(path.relative_to(ROOT)) for path in sorted(DOSSIER.glob("*.py"))]
    if args.integration:
        destination = Path(tempfile.mkdtemp(prefix="specorganon-D121-integration" + args.python + "-"))
        commands = [[python, "-B", str(DOSSIER / "integration_checks.py"), "--destination", str(destination)]]
    else:
        commands = [[python, "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider", *affected[2:]],
                    ["/home/dev/.local/bin/ruff", "check", *affected, *helpers],
                    [python, "-B", "-c", "import pathlib,sys;[compile(pathlib.Path(p).read_bytes(),p,'exec') for p in sys.argv[1:]];print('syntax OK')", *affected, *helpers],
                    ["git", "diff", "--check"]]
    results = [capture(command, output / str(index), timeout=1800 if args.integration else 300)
               for index, command in enumerate(commands, 1)]
    after, baseline_after = source_records(), preserve_baseline()
    write(output / "sources_after.json", after)
    write(output / "baseline_after.json", baseline_after)
    assert head == subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    result = {"schema": 1, "head": head, "head_before": head, "sources_unchanged": before == after,
              "baseline_unchanged": baseline == baseline_after, "commands": results,
              "all_exit_zero": all(row["exit_code"] == 0 for row in results), "formal_cells_executed": 0,
              "external_spending_authorized": False, "paid_model_requests": 0,
              "integration": args.integration, "interpreter": args.python}
    if args.integration:
        result["runtime_destination"] = str(destination)
        if (destination / "integration_result.json").exists():
            result["integration_result"] = json.loads((destination / "integration_result.json").read_bytes())
        from archive_runtimes import archive
        result["archive"] = archive(destination, output / "runtimes.tar.gz", output / "runtime_inventory.json")
    write(output / "report.json", result)
    return 0 if result["all_exit_zero"] and result["sources_unchanged"] and result["baseline_unchanged"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
