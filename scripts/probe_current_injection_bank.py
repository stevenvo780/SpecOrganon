"""Retain the existing 21 development injections against the installed D102 wheel.

Usage: ``VENVPYTHON -I SCRIPT REPO NEW_EXTERNAL_OUTPUT``. pytest must already be
installed offline. This invokes test_injection_bank.run_case once per scenario;
it does not run pytest collection, install anything, call providers, or exercise
CLI/MCP. Synthetic fixture approvals do not authenticate human authority. These
known development cases are not sealed evaluation, Q, or a C2 acceptance verdict.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import stat
import sys
import time
import traceback
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CLASSIFICATION = "development_current_installed_injection_bank_unsealed"
D102_WHEEL_SHA = "e155d010a17a1235f071da6b0d89c1773b5dc92295a85251873f1880c448390b"
VERIFIER_SHA = "3b7deea460f779234f4650f20c36788ad890ff56e7e45103f4c1f5b293583013"
INPUTS = (
    "GOAL.md", "docs/protocolo_experimental.md", "src/specorganon/engine.py",
    "src/specorganon/ledger.py", "src/specorganon/workflow.py", "tests/test_injection_bank.py",
)
# Prospective references: the unchanged existing bank and the current five
# inputs. A newly computed self-comparison cannot substitute for these pins.
INPUTS_SHA256 = {
    "GOAL.md": "e8341bea380cc357ad9e02ec4689a4ed47fe198ba06e4c98639f29264c314c36",
    "docs/protocolo_experimental.md": "3fd27c7cdb1842732f9fe37191a844e0d1e74bd1f1019331eb98ab8584eb0341",
    "src/specorganon/engine.py": "52b0a5ee102c695bd903723552c8654e0197100bf6afb8208794c93fc0fefa7d",
    "src/specorganon/ledger.py": "0d27ff5b65d5932229f88983878e55d986ae491c7272ed4ae9345d5434a17ea3",
    "src/specorganon/workflow.py": "3f3980119743962a210beffdc2b0f8d845d53bb25a0cc3eace3eacaa347ad5f2",
    "tests/test_injection_bank.py": "2be3c99905900fdad961da894454c89185346690190e2b591d36ac856d03a8b8",
}
GROUPS = {"contradiction": 6, "insufficient_evidence": 6,
          "assumption_change": 6, "unapproved_norm": 3}
CASE_IDS = tuple(f"{prefix}{number:02d}" for prefix, size in (("C", 6), ("E", 6), ("A", 6), ("N", 3))
                 for number in range(1, size + 1))
E06_FINDING = "indicator has no evidence path while study gate remains ready"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pin(raw: bytes) -> dict[str, Any]:
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def _json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def _new_file(path: Path, raw: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _pins(repo: Path) -> dict[str, Any]:
    return {name: _pin((repo / name).read_bytes()) for name in INPUTS}


def _load(path: Path, name: str, expected: dict[str, Any]):
    """Execute only the already pinned helper bytes; never its main function."""
    raw = path.read_bytes()
    _require(_pin(raw) == expected, f"helper changed before import: {path.name}")
    spec = importlib.util.spec_from_file_location(name, path)
    _require(spec is not None and spec.loader is not None, "helper import specification missing")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module


def _source_wheel_parity(repo: Path, wheel: Path) -> dict[str, Any]:
    raw = wheel.read_bytes()
    _require(_pin(raw)["sha256"] == D102_WHEEL_SHA, "wheel changed")
    modules = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for name in archive.namelist():
            if not name.startswith("specorganon/") or not name.endswith(".py"):
                continue
            path = repo / "src" / name
            _require(stat.S_ISREG(path.lstat().st_mode) and not path.is_symlink(),
                     f"source module must be regular: {name}")
            _require(path.resolve(strict=True).is_relative_to(repo / "src"), "source module escapes src")
            expected = archive.read(name)
            actual = path.read_bytes()
            modules[name] = {"source": _pin(actual), "wheel": _pin(expected), "equal": actual == expected}
    _require(len(modules) == 24, "expected exactly 24 production modules in D102 wheel")
    source_names = {str(path.relative_to(repo / "src"))
                    for path in (repo / "src/specorganon").rglob("*.py")}
    _require(source_names == set(modules), "current production source inventory differs from D102 wheel")
    return {"modules": modules, "module_count": len(modules),
            "source_matches_wheel": all(item["equal"] for item in modules.values())}


def _inventory(root: Path) -> list[dict[str, Any]]:
    return [{"path": str(path.relative_to(root)), **_pin(path.read_bytes())}
            for path in sorted(root.rglob("*")) if not path.is_symlink() and path.is_file()]


def probe(repo: Path, output: Path, wheel: Path) -> dict[str, Any]:
    repo = repo.resolve(strict=True)
    inputs_before = _pins(repo)
    _require({name: item["sha256"] for name, item in inputs_before.items()} == INPUTS_SHA256,
             "one of the six inputs differs from its prospective reference; no output created")
    output = output.absolute()
    _require(not output.exists() and not output.is_symlink(), "output directory must be new")
    output = output.parent.resolve(strict=True) / output.name
    _require(not output.is_relative_to(repo), "output must be outside repository")
    output.mkdir(mode=0o700)
    (output / "tmp").mkdir(mode=0o700)
    (output / "cases").mkdir(mode=0o700)
    (output / "results").mkdir(mode=0o700)
    original_home = os.environ.get("HOME")
    os.environ.clear()
    os.environ.update({"PATH": os.pathsep.join((str(Path(sys.executable).parent), "/usr/bin", "/bin")),
                       "TMPDIR": str(output / "tmp"), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
                       "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1",
                       "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"})
    if original_home is not None:
        os.environ["HOME"] = original_home
    sys.dont_write_bytecode = True
    receipt: dict[str, Any] = {
        "schema": 1, "classification": CLASSIFICATION, "started_at_utc": _now(), "passed": False,
        "fixture_runtime_capability": "existing run_case scopes ORGANON_ALLOW_FIXTURES and restores it",
        "environment_scope": "allowlist; original HOME preserved; credential and ORGANON pointers excluded",
        "provider_calls": 0, "private_keys_needed": False, "cli_mcp_invoked": False,
        "sealed_evaluation": False, "human_authority_authenticated": False, "Q": None,
        "criterion2_acceptance_evaluated": False, "counts_toward_required_24_runs": False,
        "inputs_expected_sha256": INPUTS_SHA256,
        "results": [],
    }
    previous_cwd, previous_path = Path.cwd(), list(sys.path)
    verifier = None
    try:
        wheel = wheel.resolve(strict=True)
        receipt["inputs_before"] = inputs_before
        verifier_path = repo / "scripts/probe_installed_signed_transports.py"
        verifier_pin = _pin(verifier_path.read_bytes())
        _require(verifier_pin["sha256"] == VERIFIER_SHA, "installed verifier differs from frozen source")
        receipt["verifier_source"] = {"path": str(verifier_path), **verifier_pin}
        receipt["helper_source"] = _pin(Path(__file__).read_bytes())
        verifier = _load(verifier_path, "_d104_installed_verifier", verifier_pin)
        installed = verifier._installed(repo, wheel)
        _require(len(installed["modules"]) == 24, "expected 24 installed production modules")
        receipt["installed"] = installed
        receipt["source_wheel_before"] = _source_wheel_parity(repo, wheel)
        _require(receipt["source_wheel_before"]["source_matches_wheel"], "current source differs from D102 wheel")
        _new_file(output / "installed.json", _json(installed))
        _new_file(output / "inputs_before.json", _json(receipt["inputs_before"]))
        # All production imports are verified before this existing test helper.
        bank = _load(repo / "tests/test_injection_bank.py", "_d104_existing_injection_bank",
                     receipt["inputs_before"]["tests/test_injection_bank.py"])
        _require(tuple(bank.CASES) == CASE_IDS, "expected the existing 21 ordered injection cases")
        actual_groups = {group: sum(value[0] == group for value in bank.CASES.values()) for group in GROUPS}
        _require(actual_groups == GROUPS, "injection distribution must be exactly 6/6/6/3")
        os.chdir(output)
        with (output / "results.jsonl").open("xb") as records:
            for case_id in CASE_IDS:
                case_path = output / "cases" / case_id
                started = time.monotonic()
                previous_flag = os.environ.get("ORGANON_ALLOW_FIXTURES")
                group, description = bank.CASES[case_id]
                result: dict[str, Any] = {"id": case_id, "group": group, "scenario": description,
                                          "status": "fail", "started_at_utc": _now()}
                with (output / "results" / f"{case_id}.stdout.txt").open("x", encoding="utf-8") as stdout, (
                    output / "results" / f"{case_id}.stderr.txt").open("x", encoding="utf-8") as stderr:
                    try:
                        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                            returned = bank.run_case(case_id, case_path)
                        result["existing_result"] = returned
                        _require(os.environ.get("ORGANON_ALLOW_FIXTURES") == previous_flag,
                                 "existing run_case did not restore fixture capability")
                        _require(returned["id"] == case_id and returned["group"] == group
                                 and returned["status"] == "pass", "existing run_case did not pass expected case")
                        ledger_path = case_path / "organon.json"
                        raw_before = ledger_path.read_bytes()
                        ledger = bank.read_project(case_path)  # verifies every event's hash chain
                        head = ledger["events"][-1]["hash"]
                        _require(raw_before == ledger_path.read_bytes(), "read_project modified ledger")
                        _require(head == returned["evidence"]["ledger_head_hash"], "report differs from ledger head")
                        _require(ledger["project"]["approval_policy"] == "fixture", "bank must use synthetic fixtures")
                        result["ledger"] = {"path": str(ledger_path.relative_to(output)), **_pin(raw_before),
                                            "events": len(ledger["events"]), "head_hash": head,
                                            "chain_valid": True, "matches_existing_result": True,
                                            "read_only_verification": True}
                        if case_id == "E06":
                            finding = returned["evidence"].get("negative_finding")
                            _require(finding == E06_FINDING, "existing E06 known negative changed")
                            result["known_negative"] = {"negative_finding": finding, "study_ready": True,
                                "study_ready_provenance": "existing run_case assertion and returned negative_finding",
                                "blocked_phase": returned["evidence"]["phase"]}
                        result["status"] = "pass"
                    except BaseException as exc:
                        result.update(error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc())
                        result["skip_detected"] = isinstance(exc, bank.pytest.skip.Exception)
                        result["xfail_detected"] = isinstance(exc, bank.pytest.xfail.Exception)
                        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                            raise
                    finally:
                        restored = os.environ.get("ORGANON_ALLOW_FIXTURES") == previous_flag
                        result["fixture_flag_restored_by_run_case"] = restored
                        if not restored:
                            result["status"] = "fail"
                            result["fixture_restore_error"] = "run_case failed to restore fixture capability"
                        if previous_flag is None:
                            os.environ.pop("ORGANON_ALLOW_FIXTURES", None)
                        else:
                            os.environ["ORGANON_ALLOW_FIXTURES"] = previous_flag
                        stdout.flush()
                        stderr.flush()
                        os.fsync(stdout.fileno())
                        os.fsync(stderr.fileno())
                        result["wall_seconds"] = time.monotonic() - started
                        result["artifacts"] = _inventory(case_path)
                        receipt["results"].append(result)
                        _new_file(output / "results" / f"{case_id}.json", _json(result))
                        records.write(_json(result))
                        records.flush()
                        os.fsync(records.fileno())
        receipt["counts"] = {"total": len(receipt["results"]),
                             "pass": sum(item["status"] == "pass" for item in receipt["results"]),
                             "fail": sum(item["status"] != "pass" for item in receipt["results"]),
                             "skips": sum(item.get("skip_detected", False) for item in receipt["results"]),
                             "xfails": sum(item.get("xfail_detected", False) for item in receipt["results"]),
                             **actual_groups}
        receipt["inputs_after"] = _pins(repo)
        receipt["source_wheel_after"] = _source_wheel_parity(repo, wheel)
        _require(receipt["inputs_before"] == receipt["inputs_after"], "one of six input sources changed")
        _require(_pin(verifier_path.read_bytes()) == verifier_pin, "installed verifier source changed")
        _require(_pin(Path(__file__).read_bytes()) == receipt["helper_source"], "probe helper changed")
        _require(receipt["source_wheel_before"] == receipt["source_wheel_after"], "source/wheel parity changed")
        verifier._origins_still_installed(installed)
        _require(verifier._installed(repo, wheel) == installed, "installed modules or executables changed")
        receipt["production_origins_verified_before_and_after"] = True
        _require(receipt["counts"]["total"] == 21 and receipt["counts"]["pass"] == 21,
                 "all 21 existing scenarios must pass; skips and original failures are retained")
        receipt["passed"] = True
    except BaseException as exc:
        receipt.update(error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc())
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
    finally:
        os.chdir(previous_cwd)
        sys.path[:] = previous_path
        if "inputs_before" in receipt:
            try:
                receipt["inputs_after"] = _pins(repo)
                receipt["six_input_pins_unchanged"] = receipt["inputs_before"] == receipt["inputs_after"]
            except Exception as exc:
                receipt["input_postcheck_error"] = f"{type(exc).__name__}: {exc}"
                receipt["six_input_pins_unchanged"] = False
            if not receipt["six_input_pins_unchanged"]:
                receipt["passed"] = False
                receipt.setdefault("error", "six input source pins could not be confirmed unchanged")
        receipt["fixture_capability_absent_at_finish"] = "ORGANON_ALLOW_FIXTURES" not in os.environ
        receipt["ended_at_utc"] = _now()
        receipt["retained_files"] = _inventory(output)
        _new_file(output / "results.json", _json(receipt))
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    try:
        repo = args.repo.resolve(strict=True)
        wheel = repo / "experiments/development/lot_journal_prospectus_2026-09-30/installed/specorganon-0.1.0-py3-none-any.whl"
        result = probe(repo, args.output, wheel)
    except (OSError, ValueError, ImportError) as exc:
        print(json.dumps({"classification": CLASSIFICATION, "passed": False,
                          "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps({"classification": CLASSIFICATION, "passed": result["passed"],
                      "counts": result.get("counts"), "results": str(args.output.absolute() / "results.json"),
                      "error": result.get("error")}, ensure_ascii=False))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
