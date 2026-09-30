"""Posthoc D099 source-conflict robustness probe in new, offline sandboxes.

Run with ``python3 -I SCRIPT REPO NEW_EXTERNAL_OUTPUT`` only after its plan
and code are frozen. This is a new negative condition over preserved program
bytes, not a rerun of the original D099 condition or a model/method comparison.
It measures local conflict signalling, not Q, causal superiority, field impact,
human authority or any of the required 24 trials. Same-UID files and local pins
do not establish independent custody. Landlock limits are those documented by
the pinned replay helper, not complete host isolation.
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
import datetime as dt
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path, PurePosixPath
import stat
import sys
from typing import Any


DOSSIER = Path("experiments/development/subscription_method_trial_2026-09-30")
ARMS = ("N", "S", "T")
SOURCE_FILES = ("task.md", "source_manifest.json", "sample_first_complete_week.csv")
RECEIPT_SHA = "04334d8d0e9633ef560b8d07cc2ecd11b4fd086265ecc0f7e1a5452adb888bf7"
PLAN_SHA = "ec9c7d1a6359e91a8543e07872226c4d2009296e78b8c151843cc283dab24ed1"
GOAL_SHA = "e8341bea380cc357ad9e02ec4689a4ed47fe198ba06e4c98639f29264c314c36"
SANDBOX_SHA = "6dc4c2c4b6abb1b0fea3a0af76d20f034c297bcb96df4bbb6da6557dbbdb1d32"
PROGRAM_SHA = {
    "N": "683e1725e28adea3061578d646f5c3af982b1458ef8bd7af98e7fc0922d89226",
    "S": "d5dc9bee91ad253f7785502fb56e317bb48a61af2caf48a45f9219d2a1d23c42",
    "T": "2a621b4aab86a246dbb4b9e4ac8b4a67a32e68ceb5922c383c6e3e4520d1fd45",
}
CLASSIFICATION = "development_posthoc_source_contradiction_no_method_verdict"
MAX_FILE_BYTES = 8 * 1024 * 1024


class ProbeError(ValueError):
    """Pinned inputs, execution or the prospective comparator failed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ProbeError(message)


def _pin(raw: bytes) -> dict[str, Any]:
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def _read(path: Path, limit: int = MAX_FILE_BYTES) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(descriptor)
        _require(stat.S_ISREG(info.st_mode) and info.st_size <= limit,
                 f"not a bounded regular file: {path}")
        chunks = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(descriptor, min(remaining, 65536))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        _require(len(raw) <= limit, f"file exceeds limit: {path}")
        return raw
    finally:
        os.close(descriptor)


def _json(raw: bytes | str) -> Any:
    def pairs(values):
        result = {}
        for key, value in values:
            _require(key not in result, f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def constant(value):
        raise ProbeError(f"non-finite JSON constant: {value}")

    result = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)

    def finite(value):
        if isinstance(value, float):
            _require(math.isfinite(value), "non-finite JSON number")
        elif isinstance(value, dict):
            for child in value.values():
                finite(child)
        elif isinstance(value, list):
            for child in value:
                finite(child)

    finite(result)
    return result


def _write(path: Path, raw: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _write_json(path: Path, value: Any) -> None:
    _write(path, (json.dumps(value, ensure_ascii=False, indent=2,
                             allow_nan=False) + "\n").encode())


def _snapshot_pins(repo: Path, observed: dict | None = None) -> dict[str, Any]:
    observed = {} if observed is None else observed
    fixed = observed.setdefault("fixed_sources", {})
    pins = observed.setdefault("original_files", {})
    dossier = repo / DOSSIER
    receipt_raw = _read(dossier / "receipt.json")
    fixed[str(DOSSIER / "receipt.json")] = _pin(receipt_raw)
    _require(_pin(receipt_raw)["sha256"] == RECEIPT_SHA, "D099 receipt pin mismatch")
    receipt = _json(receipt_raw)
    originals = receipt["original_files_copied"]
    _require(isinstance(originals, dict) and len(originals) == 147,
             "expected 147 D099 original pins")
    observed["original_file_count"] = len(originals)
    for name, expected in originals.items():
        relative = PurePosixPath(name)
        _require(not relative.is_absolute() and ".." not in relative.parts,
                 "unsafe original path in receipt")
        path = dossier / relative
        _require(path.resolve(strict=True).is_relative_to(dossier), "original path escaped dossier")
        actual = _pin(_read(path))
        pins[name] = actual
        _require(actual == {key: expected[key] for key in ("bytes", "sha256")},
                 f"D099 original pin mismatch: {name}")
    for name, expected in (("GOAL.md", GOAL_SHA),
                           ("scripts/local_replay_sandbox.py", SANDBOX_SHA),
                           (str(DOSSIER / "plan.json"), PLAN_SHA),
                           (str(DOSSIER / "receipt.json"), RECEIPT_SHA)):
        actual = _pin(_read(repo / name))
        fixed[name] = actual
        _require(actual["sha256"] == expected, f"fixed source pin mismatch: {name}")
    return observed


def _review_program(raw: bytes) -> dict[str, Any]:
    allowed_imports = {"csv", "datetime", "hashlib", "json", "math", "pathlib", "sys"}
    allowed_calls = {"main", "len", "list", "float", "int", "ValueError", "SystemExit",
                     "all", "any", "zip", "sum", "bool", "sorted", "print", "str"}
    allowed_methods = {"Path", "loads", "read_text", "read_bytes", "sha256", "hexdigest",
                       "open", "DictReader", "strptime", "total_seconds", "isfinite", "get",
                       "strftime", "dumps", "timedelta", "items", "append", "issubset"}
    tree = ast.parse(raw.decode("utf-8"))
    imports, calls = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                _require(alias.name in allowed_imports, f"unreviewed import: {alias.name}")
                imports.add(alias.name)
        _require(not isinstance(node, (ast.ImportFrom, ast.AsyncFunctionDef, ast.Await)),
                 "unsupported import or async execution")
        if isinstance(node, ast.Attribute):
            _require(not node.attr.startswith("__"), "dunder attribute access is unsupported")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                _require(node.func.id in allowed_calls, f"unreviewed call: {node.func.id}")
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                _require(node.func.attr in allowed_methods, f"unreviewed method: {node.func.attr}")
                calls.add(node.func.attr)
                if node.func.attr == "open":
                    modes = [node.args[0]] if node.args else []
                    modes += [keyword.value for keyword in node.keywords if keyword.arg == "mode"]
                    _require(len(modes) == 1 and isinstance(modes[0], ast.Constant)
                             and modes[0].value in ("r", "rt", "rb"),
                             "file open must have a literal read-only mode")
                    _require(all(keyword.arg in ("mode", "encoding", "newline")
                                 for keyword in node.keywords), "unsupported file open option")
            else:
                raise ProbeError("indirect call is unsupported")
    return {"program": _pin(raw), "imports": sorted(imports), "calls": sorted(calls),
            "review": "fixed original bytes plus conservative AST call/import allowlists",
            "subprocess_network_external_import_eval_exec_writes_allowed": False,
            "not_a_general_proof_for_arbitrary_python": True}


def _load_sandbox(repo: Path, output: Path):
    raw = _read(repo / "scripts/local_replay_sandbox.py")
    _require(_pin(raw)["sha256"] == SANDBOX_SHA, "sandbox pin changed before import")
    snapshot = output / "local_replay_sandbox.py"
    _write(snapshot, raw)
    spec = importlib.util.spec_from_file_location("_d104_local_replay_sandbox", snapshot)
    _require(spec is not None and spec.loader is not None, "sandbox module cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    # Execute the verified in-memory snapshot, without a second parent-side
    # read through the import loader. __file__/sys.modules remain available
    # for the helper's bootstrap and dataclass declarations.
    exec(compile(raw, str(snapshot), "exec"), module.__dict__)
    return module


def _prepare_arm(repo: Path, output: Path, arm: str, before: dict) -> dict[str, Any]:
    original = repo / DOSSIER / "attempts" / arm
    directory = output / arm
    directory.mkdir(mode=0o700)
    packet = directory / "input"
    packet.mkdir(mode=0o700)
    raw = _read(original / "first.analysis.py", 32768)
    _require(_pin(raw)["sha256"] == PROGRAM_SHA[arm], f"original program changed: {arm}")
    review = _review_program(raw)
    _write(directory / "program.py", raw)
    _write_json(directory / "program_review.json", review)
    pins = {"program.py": _pin(raw)}
    for name in SOURCE_FILES:
        source = _read(original / "input" / name)
        expected = before["original_files"][f"attempts/{arm}/input/{name}"]
        _require(_pin(source) == expected, f"source changed during copy: {arm}/{name}")
        if name == "source_manifest.json":
            _write(directory / "source_manifest.original.json", source)
            manifest = _json(source)
            original_digest = manifest["selection"]["sample_sha256"]
            _require(isinstance(original_digest, str) and len(original_digest) == 64
                     and all(char in "0123456789abcdef" for char in original_digest)
                     and original_digest != "0" * 64, "source has an invalid original digest")
            encoded_digest = original_digest.encode("ascii")
            _require(source.count(encoded_digest) == 1, "original digest must occur exactly once")
            offset = source.index(encoded_digest)
            changed = source.replace(encoded_digest, b"0" * 64, 1)
            restored = _json(changed)
            restored["selection"]["sample_sha256"] = original_digest
            _require(restored == _json(source), "manifest mutation changed other properties")
            _write(packet / name, changed)
            pins["source_manifest.original.json"] = _pin(source)
            pins[f"input/{name}"] = _pin(changed)
            mutation = {"json_pointer": "/selection/sample_sha256", "before": original_digest,
                        "after": "0" * 64, "changed_json_properties": 1,
                        "replaced_byte_span": [offset, offset + 64],
                        "encoding_note": "original serialization retained; only one 64-byte value substituted"}
            _write_json(directory / "mutation.json", mutation)
        else:
            _write(packet / name, source)
            pins[f"input/{name}"] = _pin(source)
    _require(pins["input/sample_first_complete_week.csv"]["sha256"] == original_digest,
             "original manifest does not identify the retained CSV")
    _write_json(directory / "pins.prepared.json", pins)
    return {"arm": arm, "directory": str(directory), "pins": pins,
            "review": review, "mutation": mutation, "program_bytes": raw}


def _classify(arm: str, result: dict, stdout: bytes, stderr: bytes) -> dict[str, Any]:
    parsed = None
    parse_error = None
    if stdout.strip():
        try:
            parsed = _json(stdout)
        except (ValueError, UnicodeError) as exc:
            parse_error = f"{type(exc).__name__}: {exc}"
    aggregate_keys = ("appliances_total_kwh", "daily_appliances_kwh", "lights_total_kwh", "units")
    aggregate = isinstance(parsed, dict) and all(key in parsed for key in aggregate_keys)
    messages = {"N": "sample SHA-256 does not match manifest", "T": "sample_sha256 mismatch"}
    infrastructure_ok = (not result["timed_out"] and result["launch_error"] is None
                         and result["exit_code"] is not None)
    if arm == "S":
        detected = isinstance(parsed, dict) and parsed.get("sample_hash_matches_manifest") is False
        expected = infrastructure_ok and result["exit_code"] == 0 and detected and aggregate
        signal = "false hash-match flag with descriptive aggregates" if detected else "unclassified"
    else:
        detected = (result["exit_code"] not in (None, 0)
                    and f"ValueError: {messages[arm]}" in stderr.decode("utf-8", errors="replace"))
        expected = infrastructure_ok and detected and not stdout.strip()
        signal = "SHA exception before aggregates in the pinned control flow" if detected else "unclassified"
    return {"detected_conflict": detected, "aggregate_output": aggregate,
            "integrity_verified": False, "decision_admission": False,
            "observation": {"signal": signal, "parsed_stdout": parsed,
                            "stdout_parse_error": parse_error, "infrastructure_ok": infrastructure_ok,
                            "candidate_decision_output_observed": False,
                            "prior_to_aggregates_basis": "original static control flow plus exception stream"
                            if arm in messages and detected else None},
            "comparator": {"source_conflict": "retained CSV SHA differs from mutated manifest SHA",
                           "integrity_verified": False, "decision_admission": False,
                           "these_are_comparator_decisions_not_model_approval": True,
                           "zero_exit_with_false_flag_is_not_automatically_noncompliance": True,
                           "expected_local_observation": expected,
                           "no_quality_or_causal_method_verdict": True}}


def _check_prepared(prepared: dict) -> dict[str, Any]:
    directory = Path(prepared["directory"])
    actual = {name: _pin(_read(directory / name)) for name in prepared["pins"]}
    _require(actual == prepared["pins"], f"prepared bytes changed: {prepared['arm']}")
    return actual


def _execute_arm(sandbox, prepared: dict, python: Path, python_bytes: bytes) -> dict[str, Any]:
    directory = Path(prepared["directory"])
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    # -c passes the unmodified original source in the sandbox configuration;
    # a same-UID change of program.py cannot substitute the executed program.
    # Input files remain subject to the documented local same-UID limits.
    program = prepared["program_bytes"]
    _require(_pin(program) == prepared["pins"]["program.py"], "retained program bytes changed")
    argv = [str(python), "-I", "-S", "-B", "-c", program.decode("utf-8"), str(directory / "input")]
    metadata: dict[str, Any] = {"arm": prepared["arm"], "started_at_utc": started,
                               "argv": argv, "program": _pin(program),
                               "execution_source": "unmodified original source as Python -c argument",
                               "read_roots": [str(directory / "input")], "write_roots": [],
                               "timeout_seconds": 30, "cpu_seconds": 10,
                               "address_space_bytes": 536870912,
                               "file_bytes_per_file": 2097152,
                               "runtime_roots": [], "sandbox_api_invocations": 0}
    _write_json(directory / "started.json", metadata)
    try:
        _check_prepared(prepared)
        runtime_roots = sandbox.default_python_runtime_roots()
        metadata["runtime_roots"] = [str(path) for path in runtime_roots]
        metadata["sandbox_api_invocations"] = 1
        result = sandbox.run_sandboxed(
            argv=argv, cwd=directory, read_roots=[directory / "input"], write_roots=[],
            runtime_roots=runtime_roots, stdout_path=directory / "stdout.txt",
            stderr_path=directory / "stderr.txt", timeout_seconds=30, cpu_seconds=10,
            address_space_bytes=536870912, file_bytes_per_file=2097152,
            env={"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
                 "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1"},
            sealed_executable_bytes=python_bytes,
            sealed_executable_sha256=hashlib.sha256(python_bytes).hexdigest())
        metadata["sandbox_result"] = dataclasses.asdict(result)
    except Exception as exc:
        metadata["sandbox_result"] = {"exit_code": None, "timed_out": False,
                                      "launch_error": f"{type(exc).__name__}: {exc}",
                                      "duration_seconds": None, "landlock_abi": None,
                                      "sealed_executable_sha256": None}
    stdout = _read(directory / "stdout.txt") if (directory / "stdout.txt").exists() else b""
    stderr = _read(directory / "stderr.txt") if (directory / "stderr.txt").exists() else b""
    metadata["streams"] = {name: {"retained": (directory / name).exists(),
                                   "pin": _pin(raw) if (directory / name).exists() else None}
                           for name, raw in (("stdout.txt", stdout), ("stderr.txt", stderr))}
    metadata["classification"] = _classify(prepared["arm"], metadata["sandbox_result"], stdout, stderr)
    try:
        metadata["snapshot_pins_after"] = _check_prepared(prepared)
        metadata["snapshot_bytes_unchanged"] = True
    except Exception as exc:
        metadata["snapshot_bytes_unchanged"] = False
        metadata["snapshot_check_error"] = f"{type(exc).__name__}: {exc}"
    metadata["finished_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    _write_json(directory / "metadata.json", metadata)
    return metadata


def _inventory(output: Path) -> dict[str, Any]:
    return {str(path.relative_to(output)): _pin(_read(path))
            for path in sorted(output.rglob("*")) if path.is_file() and not path.is_symlink()}


def probe(repo: Path, output: Path) -> dict[str, Any]:
    repo = repo.resolve(strict=True)
    output = output.absolute()
    _require(not output.exists() and not output.is_symlink(), "output must be new")
    output = output.parent.resolve(strict=True) / output.name
    _require(not output.is_relative_to(repo), "output must be outside repository")
    # This original runtime root is itself named in the pinned D099 receipt.
    _require(not output.is_relative_to(Path("/tmp/specorganon-D099-fdjvxrnq")),
             "output must stay outside the preserved original runtime")
    output.mkdir(mode=0o700)
    report: dict[str, Any] = {"schema": 1, "study_id": "D104", "classification": CLASSIFICATION,
                              "output": str(output),
                              "started_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                              "passed": False, "Q": None, "cost": None, "provider_calls": 0,
                              "method_winner_selected": False, "causal_method_effect_assessed": False,
                              "counts_toward_required_24_runs": False,
                              "historical_conditions_replayed": False,
                              "field_intervention_authorized": False,
                              "human_approvals": 0, "phase_advances": 0,
                              "criterion_4": "no_demostrado", "arms": [],
                              "same_uid_custody_authenticated": False}
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    prior_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        probe_path = Path(__file__).resolve(strict=True)
        probe_bytes = _read(probe_path)
        report["probe_source"] = {"path": str(probe_path), **_pin(probe_bytes)}
        _write(output / "probe.snapshot.py", probe_bytes)
        _snapshot_pins(repo, before)
        _write_json(output / "pins.before.json", before)
        for source, destination, expected in (
            (repo / "GOAL.md", "GOAL.snapshot.md", GOAL_SHA),
            (repo / DOSSIER / "receipt.json", "d099.receipt.snapshot.json", RECEIPT_SHA),
            (repo / DOSSIER / "plan.json", "d099.plan.snapshot.json", PLAN_SHA),
        ):
            raw = _read(source)
            _require(_pin(raw)["sha256"] == expected, f"source changed during copy: {source}")
            _write(output / destination, raw)
        common = _read(repo / DOSSIER / "attempts/S/prompts/common")
        _require(_pin(common) == before["original_files"]["attempts/S/prompts/common"],
                 "common prompt changed during copy")
        _write(output / "common.snapshot.md", common)
        _write_json(output / "comparator.json", {
            "condition": "only /selection/sample_sha256 becomes 64 zeroes; original CSV remains identical",
            "common_contract": "Verifica integridad, filas y continuidad y calcula las magnitudes solicitadas.",
            "common_requires_nonzero_exit_before_calculation": False,
            "s_own_requirement": "Comprobar filas, hash del extracto y continuidad de intervalos antes de interpretar los agregados.",
            "expected_integrity_verified": False, "decision_admission": False,
            "expected_local_signals": {"N": "SHA ValueError before aggregates",
                                       "S": "false hash-match flag plus descriptive aggregates",
                                       "T": "SHA ValueError before aggregates"},
            "expected_signals_are_posthoc_static_predictions_not_pretrial_quality_criteria": True,
            "zero_exit_with_false_flag_is_not_automatically_noncompliance": True,
            "Q": None, "ranking": None})
        prepared = [_prepare_arm(repo, output, arm, before) for arm in ARMS]
        sandbox = _load_sandbox(repo, output)
        python = Path(sys.executable).resolve(strict=True)
        python_bytes = _read(python, 16 * 1024 * 1024)
        report["python"] = {"path": str(python), "version": sys.version, **_pin(python_bytes)}
        _write_json(output / "run.started.json", {"arms": list(ARMS), "program_calls_max": 3,
                                                    "python": report["python"]})
        for arm in prepared:
            report["arms"].append(_execute_arm(sandbox, arm, python, python_bytes))
        _snapshot_pins(repo, after)
        _write_json(output / "pins.after.json", after)
        _require(before == after, "original or runtime helper bytes changed during probe")
        _require(_pin(_read(output / "local_replay_sandbox.py"))["sha256"] == SANDBOX_SHA,
                 "sandbox snapshot bytes changed during probe")
        _require(_pin(_read(python, 16 * 1024 * 1024)) == _pin(python_bytes),
                 "interpreter bytes changed during probe")
        _require(_pin(_read(probe_path)) == _pin(probe_bytes), "probe source changed during execution")
        report["original_bytes_unchanged"] = True
        report["sandbox_api_invocations"] = sum(arm["sandbox_api_invocations"] for arm in report["arms"])
        _require(report["sandbox_api_invocations"] == 3, "expected exactly three sandbox invocations")
        _require(all(arm["snapshot_bytes_unchanged"] and
                     arm["classification"]["comparator"]["expected_local_observation"]
                     for arm in report["arms"]), "execution or comparator observation failed")
        report["passed"] = True
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if not (output / "pins.before.json").exists():
            _write_json(output / "pins.before.json", before)
        if not (output / "pins.after.json").exists():
            _write_json(output / "pins.after.json", after)
        sys.dont_write_bytecode = prior_bytecode
        report["finished_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        report["retained_files"] = _inventory(output)
        _write_json(output / "report.json", report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = probe(args.repo, args.output)
    except (OSError, ValueError, ImportError) as exc:
        print(json.dumps({"classification": CLASSIFICATION, "passed": False,
                          "error": f"{type(exc).__name__}: {exc}"}), file=sys.stderr)
        return 2
    runs = sum(arm["sandbox_result"]["exit_code"] is not None
               and arm["sandbox_result"]["launch_error"] is None for arm in result["arms"])
    signals = {arm["arm"]: {key: arm["classification"][key] for key in
                           ("detected_conflict", "aggregate_output", "integrity_verified",
                            "decision_admission")} for arm in result["arms"]}
    print(json.dumps({"passed": result["passed"], "runs": runs, "signals": signals,
                      "output": result["output"], "error": result.get("error")},
                     ensure_ascii=False, allow_nan=False))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
