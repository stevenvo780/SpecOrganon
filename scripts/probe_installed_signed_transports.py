"""Retain six signed operations over real CLI/MCP from the installed D102 wheel.

Usage: ``VENVPYTHON -I probe_installed_signed_transports.py REPO NEW_OUTPUT``.
pytest must already be installed offline in that environment. No installation,
provider call, historical replay, or real human/field approval is performed.
Three existing tests supply synthetic fixtures and ephemeral in-memory keys.
The observation test inspects a prefabricated bundle: it does not execute or
repeat that bundle. A separate signed_observed workflow probe supplies repeat
evidence. Captures preserve subprocess results and SDK response objects, not
MCP wire framing or externally authenticated provenance.
Repository test helpers can add import paths inside this process; every
production module's wheel origin and bytes are checked before and after them.
"""

from __future__ import annotations

import argparse
import ast
import base64
import contextlib
import hashlib
import importlib
import io
import json
import os
import stat
import subprocess
import sys
import sysconfig
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CLASSIFICATION = "development_installed_d102_signed_transport_probe_unsealed"
D102_WHEEL_SHA = "e155d010a17a1235f071da6b0d89c1773b5dc92295a85251873f1880c448390b"
TESTS = (
    "test_approval_security.py::test_synthetic_attestation_report_cannot_authorize_field_success",
    "test_signed_test_execution_transport.py::test_installed_cli_and_mcp_record_actual_synthetic_test",
    "test_test_observation_transport.py::test_valid_observation_roundtrips_through_cli_and_real_mcp",
)
OPERATIONS = (
    "field_attestation_challenge", "attest_field",
    "test_execution_challenge", "record_test_execution",
    "test_observation_challenge", "record_test_observation",
)


class ProbeError(ValueError):
    """Installed bytes, test effects, or retained evidence failed the probe."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ProbeError(message)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pin(raw: bytes) -> dict[str, Any]:
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def _json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n").encode()


def _new_file(path: Path, raw: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _installed(repo: Path, wheel: Path) -> dict[str, Any]:
    _require(sys.prefix != sys.base_prefix, "an installed virtual environment is required")
    purelib = Path(sysconfig.get_path("purelib")).resolve(strict=True)
    _require(not purelib.is_relative_to(repo), "installed purelib must be outside repository")
    raw = wheel.read_bytes()
    _require(_pin(raw)["sha256"] == D102_WHEEL_SHA, "wheel differs from frozen D102 bytes")
    modules = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for name in archive.namelist():
            if not name.startswith("specorganon/") or not name.endswith(".py"):
                continue
            installed = purelib / name
            expected = archive.read(name)
            _require(stat.S_ISREG(installed.lstat().st_mode), f"installed module is not regular: {name}")
            _require(installed.resolve(strict=True).is_relative_to(purelib), f"module escapes purelib: {name}")
            _require(installed.read_bytes() == expected, f"installed module differs from wheel: {name}")
            module_name = name[:-3].replace("/", ".")
            if module_name.endswith(".__init__"):
                module_name = module_name[:-9]
            module = importlib.import_module(module_name)
            _require(Path(module.__file__).resolve(strict=True) == installed.resolve(strict=True),
                     f"module imported outside installed wheel: {module_name}")
            modules[module_name] = {"path": str(installed), **_pin(expected)}
    _require("specorganon" in modules and "specorganon.engine" in modules,
             "wheel lacks the package and engine")
    bin_dir = Path(sys.executable).parent
    executables = {}
    for name in ("organon", "organon-mcp"):
        path = bin_dir / name
        _require(path.is_file() and os.access(path, os.X_OK), f"installed {name} is missing")
        executables[name] = {"path": str(path), **_pin(path.read_bytes())}
    return {"python": sys.version, "executable": sys.executable, "purelib": str(purelib),
            "wheel": {"path": str(wheel), **_pin(raw)}, "modules": modules,
            "executables": executables, "verified_before_test_helpers": True}


def _stream(value: str | bytes | None) -> dict[str, Any]:
    if value is None:
        return {"type": "not_captured"}
    if isinstance(value, bytes):
        return {"type": "bytes", "base64": base64.b64encode(value).decode("ascii"), **_pin(value)}
    return {"type": "text", "value": value, **_pin(value.encode("utf-8"))}


def _argv(value: Any) -> list[str]:
    _require(isinstance(value, (list, tuple)), "probe subprocess must use explicit argv")
    return [os.fspath(part) for part in value]


def _test_source_pins(repo: Path) -> dict[str, Any]:
    """Pin selected tests and their transitive local test-module imports."""
    root = (repo / "tests").resolve(strict=True)
    pending = [node.split("::")[0] for node in TESTS]
    pins = {}
    while pending:
        name = pending.pop()
        if name in pins:
            continue
        path = (root / name).resolve(strict=True)
        _require(path.parent == root, "test helper must stay in the test directory")
        raw = path.read_bytes()
        pins[name] = _pin(raw)
        for node in ast.walk(ast.parse(raw, filename=name)):
            modules = ([node.module] if isinstance(node, ast.ImportFrom) else
                       [alias.name for alias in node.names] if isinstance(node, ast.Import) else [])
            for module in modules:
                if module and module.startswith("test_") and module.isidentifier():
                    pending.append(module + ".py")
    return pins


def _mcp_object(response: Any) -> dict:
    value = response.structured_content
    if value is None:
        _require(len(response.content) == 1, "challenge MCP response must contain one object")
        value = json.loads(response.content[0].text)
    _require(isinstance(value, dict), "challenge MCP response must be an object")
    return value


class Captures:
    """Forward original transports and append the returned values durably."""

    def __init__(self, output: Path, cli: str) -> None:
        self.path = output / "transports.jsonl"
        self.stream = self.path.open("xb")
        self.cli = cli
        self.current = "collection"
        self.records: list[dict[str, Any]] = []

    def append(self, record: dict[str, Any]) -> None:
        record = {"seq": len(self.records) + 1, "test": self.current, **record}
        self.stream.write(_json(record))
        self.stream.flush()
        os.fsync(self.stream.fileno())
        self.records.append(record)

    @contextlib.contextmanager
    def forward(self):
        from mcp.client import Client

        original_run, original_call = subprocess.run, Client.call_tool

        def observed_run(*args, **kwargs):
            command = _argv(args[0] if args else kwargs["args"])
            operation = command[1].replace("-", "_") if command[0] == self.cli and len(command) > 1 else None
            start, utc = time.monotonic(), _now()
            metadata = {"transport": "cli" if operation else "local_process", "operation": operation,
                        "argv": command, "started_at_utc": utc,
                        "cwd": str(kwargs.get("cwd") or Path.cwd())}
            try:
                result = original_run(*args, **kwargs)
            except (OSError, subprocess.SubprocessError) as exc:
                self.append({**metadata, "wall_seconds": time.monotonic() - start,
                             "successful": False, "exception": type(exc).__name__,
                             "error": str(exc), "stdout": _stream(getattr(exc, "stdout", None)),
                             "stderr": _stream(getattr(exc, "stderr", None))})
                raise
            self.append({**metadata, "wall_seconds": time.monotonic() - start,
                         "exit_code": result.returncode, "successful": result.returncode == 0,
                         "stdout": _stream(result.stdout), "stderr": _stream(result.stderr)})
            return result

        async def observed_call(client, *args, **kwargs):
            name = args[0] if args else kwargs["name"]
            arguments = args[1] if len(args) > 1 else kwargs.get("arguments")
            start, utc = time.monotonic(), _now()
            metadata = {"transport": "mcp", "operation": name, "arguments": arguments,
                        "started_at_utc": utc, "response_scope": "raw_sdk_model_not_wire_frames"}
            pair = None
            if name == "field_attestation_challenge":
                _require(isinstance(arguments, dict), "field challenge arguments must be an object")
                ledger = Path(arguments["path"]) / "organon.json"
                before = ledger.read_bytes()
                command = [self.cli, "field-attestation-challenge", arguments["path"], arguments["id"],
                           "--actor", arguments["actor"], "--reason", arguments["reason"],
                           "--source-manifest-path", arguments["source_manifest_path"],
                           "--report-path", arguments["report_path"]]
                cli_result = observed_run(command, text=True, capture_output=True, check=False, timeout=30)
                _require(cli_result.returncode == 0, "paired field challenge CLI failed")
                _require(ledger.read_bytes() == before, "paired field challenge CLI modified ledger")
                pair = (ledger, before, json.loads(cli_result.stdout), len(self.records))
            try:
                response = await original_call(client, *args, **kwargs)
            except Exception as exc:
                self.append({**metadata, "wall_seconds": time.monotonic() - start,
                             "successful": False, "exception": type(exc).__name__, "error": str(exc)})
                raise
            self.append({**metadata, "wall_seconds": time.monotonic() - start,
                         "successful": getattr(response, "is_error", None) is False,
                         "response": response.model_dump(mode="json", by_alias=True)})
            if pair is not None:
                ledger, before, cli_value, cli_seq = pair
                after = ledger.read_bytes()
                equivalent = cli_value == _mcp_object(response)
                unchanged = before == after
                self.append({"transport": "comparison", "operation": name,
                             "cli_seq": cli_seq, "mcp_seq": len(self.records),
                             "comparison": "cli_mcp_same_ledger_head",
                             "ledger_before": _pin(before), "ledger_after": _pin(after),
                             "responses_equal": equivalent, "ledger_unchanged": unchanged,
                             "successful": equivalent and unchanged and response.is_error is False})
                _require(equivalent and unchanged and response.is_error is False,
                         "field challenge CLI/MCP pair differed or modified ledger")
            return response

        subprocess.run, Client.call_tool = observed_run, observed_call
        try:
            yield
        finally:
            subprocess.run, Client.call_tool = original_run, original_call

    def close(self) -> None:
        self.stream.close()


class TestReports:
    """Collect exact selected test outcomes, including skips and collection errors."""

    def __init__(self, captures: Captures) -> None:
        self.captures = captures
        self.reports: list[dict[str, Any]] = []
        self.collected: list[str] = []
        self.collection_errors: list[str] = []
        self.case_roots: dict[str, str] = {}

    def pytest_collection_modifyitems(self, items):
        self.collected = [item.nodeid for item in items]

    def pytest_collectreport(self, report):
        if report.failed:
            self.collection_errors.append(str(report.longrepr))

    def pytest_runtest_setup(self, item):
        self.captures.current = item.nodeid

    def pytest_runtest_call(self, item):
        if "tmp_path" in item.funcargs:
            self.case_roots[item.nodeid] = str(item.funcargs["tmp_path"])

    def pytest_runtest_logreport(self, report):
        self.reports.append({"test": report.nodeid, "phase": report.when,
                             "outcome": report.outcome, "duration": report.duration,
                             "error": str(report.longrepr) if report.failed or report.skipped else None})


def _case_inventory(directory: Path) -> list[dict[str, Any]]:
    files = []
    if directory.exists():
        for path in sorted(directory.rglob("*")):
            if path.is_symlink() or not path.is_file():
                continue
            files.append({"path": str(path.relative_to(directory)), **_pin(path.read_bytes())})
    return files


def _origins_still_installed(installed: dict) -> None:
    purelib = Path(installed["purelib"])
    for name, module in tuple(sys.modules.items()):
        if name == "specorganon" or name.startswith("specorganon."):
            path = Path(module.__file__).resolve(strict=True)
            _require(path.is_relative_to(purelib), f"test imported source checkout: {name}")
            _require(name in installed["modules"], f"test loaded a module absent from D102 wheel: {name}")
            _require(_pin(path.read_bytes()) == {key: installed["modules"][name][key]
                                               for key in ("bytes", "sha256")},
                     f"installed bytes changed while testing: {name}")


def probe(repo: Path, output: Path, wheel: Path) -> dict[str, Any]:
    repo = repo.resolve(strict=True)
    output = output.absolute()
    _require(not output.exists() and not output.is_symlink(), "output directory must be new")
    output = output.parent.resolve(strict=True) / output.name
    _require(not output.is_relative_to(repo), "output must be outside repository")
    output.mkdir(mode=0o700)
    (output / "tmp").mkdir(mode=0o700)
    # Preserve caller HOME unchanged. Credentials, external ORGANON/config
    # pointers and Python injection are excluded; no configuration is copied.
    original_home = os.environ.get("HOME")
    os.environ.clear()
    os.environ.update({"PATH": os.pathsep.join((str(Path(sys.executable).parent), "/usr/bin", "/bin")),
                       "TMPDIR": str(output / "tmp"),
                       "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PYTHONNOUSERSITE": "1",
                       "PYTHONDONTWRITEBYTECODE": "1", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"})
    if original_home is not None:
        os.environ["HOME"] = original_home
    sys.dont_write_bytecode = True
    receipt: dict[str, Any] = {"schema": 1, "classification": CLASSIFICATION,
                              "started_at_utc": _now(), "passed": False,
                              "field_impact_tested": False, "human_authority_authenticated": False,
                              "historical_test_replay_performed": False,
                              "observation_bundle_is_prefabricated_synthetic": True,
                              "field_challenge_paired_same_head": False,
                              "provider_calls": 0, "global_acceptance": "0/5"}
    captures = None
    prior_cwd, prior_path = Path.cwd(), list(sys.path)
    try:
        installed = _installed(repo, wheel.resolve(strict=True))
        receipt["installed"] = installed
        _new_file(output / "installed.json", _json(installed))
        # Production modules were checked and imported before helpers. Their
        # in-process path additions remain visible and are recorded below.
        sys.path.insert(0, str(repo / "tests"))
        import pytest

        config = output / "pytest.ini"
        _new_file(config, b"[pytest]\n")
        nodes = [str(repo / "tests" / node) for node in TESTS]
        receipt["test_source_pins"] = _test_source_pins(repo)
        captures = Captures(output, installed["executables"]["organon"]["path"])
        reports = TestReports(captures)
        pytest_args = ["-c", str(config), "--rootdir", str(output), "--confcutdir", str(output),
                       "--basetemp", str(output / "cases"), "--import-mode=importlib",
                       "-q", "--tb=short", "--color=no", *nodes]
        receipt["pytest_argv"] = pytest_args
        os.chdir(output)
        with (output / "pytest.stdout.txt").open("x", encoding="utf-8") as stdout, (
            output / "pytest.stderr.txt").open("x", encoding="utf-8") as stderr:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr), captures.forward():
                exit_code = int(pytest.main(pytest_args, plugins=[reports]))
            stdout.flush()
            stderr.flush()
            os.fsync(stdout.fileno())
            os.fsync(stderr.fileno())
        receipt.update(pytest_exit_code=exit_code, collected_tests=reports.collected,
                       test_reports=reports.reports, collection_errors=reports.collection_errors)
        receipt["helper_paths_added"] = sorted(set(sys.path) - set(prior_path))
        receipt["helper_path_scope"] = "repository test helpers in-process; child Python environment injection cleared"
        receipt["tests"] = []
        for node in reports.collected:
            records = [record for record in captures.records if record["test"] == node]
            inventory = {transport: {operation: sum(record["transport"] == transport
                         and record["operation"] == operation and record["successful"] for record in records)
                         for operation in OPERATIONS} for transport in ("cli", "mcp")}
            root = reports.case_roots.get(node)
            receipt["tests"].append({"node": node, "transports": inventory,
                                      "case_root": root,
                                      "artifacts": _case_inventory(Path(root)) if root else []})
        _origins_still_installed(installed)
        _require(exit_code == 0 and not reports.collection_errors, "selected pytest run failed")
        _require(len(reports.collected) == 3 and all(any(node.endswith(test) for node in reports.collected)
                                                    for test in TESTS), "expected exactly three selected tests")
        _require(len(reports.reports) == 9 and all(record["outcome"] == "passed" for record in reports.reports),
                 "each selected test must pass setup, call and teardown without skips")
        inventory = {transport: {operation: sum(record["transport"] == transport
                     and record["operation"] == operation and record["successful"] for record in captures.records)
                     for operation in OPERATIONS} for transport in ("cli", "mcp")}
        receipt["positive_operations"] = inventory
        _require(all(count > 0 for counts in inventory.values() for count in counts.values()),
                 "six positive signed operations must be observed through both CLI and MCP")
        pairs = [record for record in captures.records if record["transport"] == "comparison"
                 and record["operation"] == "field_attestation_challenge"]
        _require(pairs and all(record["successful"] for record in pairs),
                 "field challenge requires a successful same-head CLI/MCP pair")
        receipt["field_challenge_paired_same_head"] = True
        receipt["production_origins_verified_after_helpers"] = True
        receipt["passed"] = True
        receipt["selected_tests_verified_challenge_parity_and_effects"] = True
    except Exception as exc:
        receipt["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if captures is not None:
            captures.close()
        os.chdir(prior_cwd)
        sys.path[:] = prior_path
        receipt["ended_at_utc"] = _now()
        receipt["retained_files"] = _case_inventory(output)
        _new_file(output / "receipt.json", _json(receipt))
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--wheel", type=Path)
    args = parser.parse_args(argv)
    repo = args.repo.resolve(strict=True)
    wheel = args.wheel or repo / "experiments/development/lot_journal_prospectus_2026-09-30/installed/specorganon-0.1.0-py3-none-any.whl"
    try:
        result = probe(repo, args.output, wheel)
    except (OSError, ValueError, ImportError) as exc:
        print(json.dumps({"classification": CLASSIFICATION, "passed": False,
                          "error": f"{type(exc).__name__}: {exc}"}), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
