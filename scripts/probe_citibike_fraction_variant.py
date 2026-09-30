"""Probe the installed D102 toolkit on a new Citi fraction development derivative.

Usage: ``VENVPYTHON -I SCRIPT REPO NEW_EXTERNAL_OUTPUT``. The separately pinned
builder prepares the case; real CLI/MCP operations and their original outputs
are retained. Known public historical observations are reused, not recollected.
This is not sealed evaluation, human approval, field efficacy, Q, or C2/C5 PASS.
Run only after the root's prospective plan and instrument freeze.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
import zipfile
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from fractions import Fraction
from pathlib import Path
from typing import Any


CLASSIFICATION = "development_installed_citibike_fraction_variant_unsealed"
D102_WHEEL_SHA = "e155d010a17a1235f071da6b0d89c1773b5dc92295a85251873f1880c448390b"
BUILDER_SHA = "d54b329dce6a6b0d53736ee8e00edfbce85949d4f6daa325d4817c7a002eee03"
VERIFIER_SHA = "3b7deea460f779234f4650f20c36788ad890ff56e7e45103f4c1f5b293583013"
SOURCE_PINS = {
    "GOAL.md": "e8341bea380cc357ad9e02ec4689a4ed47fe198ba06e4c98639f29264c314c36",
    "docs/protocolo_experimental.md": "3fd27c7cdb1842732f9fe37191a844e0d1e74bd1f1019331eb98ab8584eb0341",
    "cases/citibike_march2024/organon.json": "af6b95cc40c3b6b44c04c47b713fa8db4ff2339a2b1fffefdce53a720688ddc4",
    "cases/citibike_march2024_lineage/organon.json": "7cb7f451e953a02a7254edd2e6713ad7acc470181b2cc0966b5d9b88c51692e3",
    "cases/citibike_march2024_lineage/manifest.json": "b2e540940d08e296b69505cb88c437652a82fed2fd6fb8385661f3c0815db2bc",
    "experiments/development/citibike_sample_status_2026-09-27.json": "352ef988b91813912d15c465ba1e597c76eedc1461c33b29afc928c9f88c7ee1",
    "cases/citibike_march2024/ratio_contract_2026-09-27.json": "44f016ce11b3e07ad0309221a5f9f285ea3d0b16c643328a5fc0f37dec705255",
    "cases/citibike_march2024/ratio_claim_rental_2026-09-27.json": "48813b54b7ce4d393b0a803f38f0caf1cc66a8717fbddc34f1157e31e949b666",
    "cases/citibike_march2024/ratio_claim_return_2026-09-27.json": "013c4bd67e9168efb301148590acfa6f9a9466655ceac0f851d6d6c1fb325f30",
    "cases/citibike/analyze_sample_status.py": "e384b43d24bf2b928c1772c7781e38c8abbbface8f92bfb98dc5ad804b3bf949",
    "scripts/build_citibike_fraction_variant.py": BUILDER_SHA,
    "scripts/probe_installed_signed_transports.py": VERIFIER_SHA,
}
NEW_IDS = ("e_rental_fraction", "e_return_fraction", "i_rental_fraction", "i_return_fraction", "s_rows_pair")
REFRESH_IDS = ("o_rows_report", "cmp_reporting", "d_reporting", "req_row_report")
PHASES = ("frame", "critique", "study", "observe", "explain", "compare", "specify", "build", "validate")
ACTOR = "agent:D105-installed-fraction-probe"
REVIEWER = "agent:D105-technical-negative-reviewer"
REVIEW_REASON = "Technical rejection of legacy compound indicator; no normative decision or human approval"
BUILDER_BOOTSTRAP = (
    "import sys; p=sys.argv[1]; raw=sys.stdin.buffer.read(); sys.argv=sys.argv[1:]; "
    "exec(compile(raw,p,'exec'),{'__name__':'__main__','__file__':p,'__package__':None})"
)


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


def _source_bytes(repo: Path) -> dict[str, bytes]:
    result = {}
    for name in SOURCE_PINS:
        path = repo / name
        _require(not path.is_symlink() and path.resolve(strict=True).is_relative_to(repo),
                 "pinned source must stay inside repository without a file symlink")
        result[name] = path.read_bytes()
    _require({name: _pin(raw)["sha256"] for name, raw in result.items()} == SOURCE_PINS,
             "a source differs from its prospective fixed pin")
    return result


def _load_verifier(raw: bytes, path: Path):
    _require(_pin(raw)["sha256"] == VERIFIER_SHA, "verifier pin differs")
    spec = importlib.util.spec_from_file_location("_d105_installed_verifier", path)
    _require(spec is not None, "verifier import specification missing")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module


def _source_wheel(repo: Path, wheel: Path) -> dict[str, Any]:
    raw = wheel.read_bytes()
    _require(_pin(raw)["sha256"] == D102_WHEEL_SHA, "D102 wheel differs")
    result = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for name in archive.namelist():
            if name.startswith("specorganon/") and name.endswith(".py"):
                source = repo / "src" / name
                _require(not source.is_symlink(), "source module must not be a symlink")
                actual, expected = source.read_bytes(), archive.read(name)
                _require(actual == expected, f"current production source differs from wheel: {name}")
                result[name] = _pin(actual)
    _require(len(result) == 24, "expected all 24 production modules")
    _require({str(path.relative_to(repo / "src")) for path in (repo / "src/specorganon").rglob("*.py")}
             == set(result), "production source inventory differs from wheel")
    return result


def _inventory(root: Path) -> list[dict[str, Any]]:
    result = []
    for path in sorted(root.rglob("*")):
        _require(not path.is_symlink(), "probe artifacts must not contain symlinks")
        if path.is_file():
            result.append({"path": str(path.relative_to(root)), **_pin(path.read_bytes())})
    return result


class Captures:
    """Keep original process streams and raw SDK models before interpreting them."""

    def __init__(self, output: Path, env: dict[str, str], cli: str):
        self.output, self.env, self.cli = output, env, cli
        (output / "calls").mkdir(mode=0o700)
        self.stream = (output / "calls.jsonl").open("xb")
        self.records: list[dict[str, Any]] = []

    def append(self, record: dict[str, Any]) -> None:
        record = {"seq": len(self.records) + 1, **record}
        self.stream.write(_json(record))
        self.stream.flush()
        os.fsync(self.stream.fileno())
        self.records.append(record)

    def process(self, argv: list[str], label: str, *, payload: bytes | None = None):
        stem = f"{len(self.records) + 1:03d}-{label}"
        start = time.monotonic()
        metadata = {"transport": "cli" if argv[0] == self.cli else "builder",
                    "argv": argv, "started_at_utc": _now(), "cwd": str(self.output)}
        try:
            result = subprocess.run(argv, input=payload, cwd=self.output, env=self.env,
                                    capture_output=True, timeout=90, check=False)
            stdout, stderr = result.stdout, result.stderr
            metadata["exit_code"] = result.returncode
        except (OSError, subprocess.SubprocessError) as exc:
            stdout, stderr = getattr(exc, "stdout", None) or b"", getattr(exc, "stderr", None) or b""
            metadata.update(exception=type(exc).__name__, error=str(exc))
            result = None
        for name, raw in (("stdout", stdout), ("stderr", stderr)):
            path = self.output / "calls" / f"{stem}.{name}"
            _new_file(path, raw)
            metadata[name] = {"path": str(path.relative_to(self.output)), **_pin(raw)}
        self.append({**metadata, "wall_seconds": time.monotonic() - start})
        _require(result is not None, f"{label} failed; original partial streams retained")
        return result

    def command(self, *args: str, rejected: bool = False) -> dict[str, Any]:
        result = self.process([self.cli, *args], args[0])
        if rejected:
            _require(result.returncode != 0 and not result.stdout and b"phase cannot advance:" in result.stderr,
                     "advance did not fail for the expected blocked phase")
            return {"exit_code": result.returncode, "stderr": result.stderr.decode("utf-8")}
        _require(result.returncode == 0, f"CLI {args[0]} failed; original streams retained")
        value = json.loads(result.stdout)
        _require(isinstance(value, dict), "CLI response must be an object")
        return value

    async def tool(self, client, name: str, arguments: dict, *, rejected: bool = False) -> dict:
        start = time.monotonic()
        try:
            response = await asyncio.wait_for(client.call_tool(name, arguments), timeout=90)
        except Exception as exc:
            self.append({"transport": "mcp", "operation": name, "arguments": arguments,
                         "exception": type(exc).__name__, "error": str(exc)})
            raise
        raw = response.model_dump(mode="json", by_alias=True)
        self.append({"transport": "mcp", "operation": name, "arguments": arguments,
                     "response": raw, "wall_seconds": time.monotonic() - start,
                     "response_scope": "raw_sdk_model_not_wire_framing"})
        if rejected:
            text = " ".join(getattr(part, "text", "") for part in response.content)
            _require(response.is_error is True and "phase cannot advance:" in text,
                     "MCP advance did not report the expected blocked phase")
            return {"is_error": True, "text": text}
        _require(response.is_error is False, f"MCP {name} failed; original SDK response retained")
        value = response.structured_content
        if value is None:
            _require(len(response.content) == 1, "MCP requires one response object")
            value = json.loads(response.content[0].text)
        _require(isinstance(value, dict), "MCP response must be an object")
        return value


def _ancestors(items: dict, item_id: str) -> set[str]:
    result, pending = set(), list(items[item_id]["deps"])
    while pending:
        ref = pending.pop()
        if ref not in result:
            result.add(ref)
            pending.extend(items[ref]["deps"])
    return result


def _pending(state: dict) -> None:
    _require(not state["items"]["n_scope"]["approved"] and not state["items"]["d_reporting"]["approved"],
             "norm and candidate decision must stay unapproved")
    _require(not any(phase["accepted"] for phase in state["phases"].values()), "no phase may be accepted")


async def _pair(captures: Captures, client, case: Path, operation: str, **fields) -> dict:
    ledger = case / "organon.json"
    before = ledger.read_bytes()
    argv = [operation, str(case)]
    if operation in {"trace", "gate"}:
        argv.append(fields["id"] if operation == "trace" else fields["phase"])
    cli = captures.command(*argv)
    mcp = await captures.tool(client, operation, {"path": str(case), **fields})
    _require(cli == mcp and ledger.read_bytes() == before, f"{operation} parity or read-only check failed")
    captures.append({"transport": "comparison", "operation": operation, "case": str(case),
                     "fields": fields, "responses_equal": True, "ledger_unchanged": True,
                     "ledger": _pin(before)})
    return cli


async def _blocked(captures: Captures, client, case: Path, *, gate: dict | None = None) -> dict:
    before = (case / "organon.json").read_bytes()
    if gate is None:
        gate = await _pair(captures, client, case, "gate", phase="specify")
    _require(not gate["ready"] and not gate["accepted"] and gate["blockers"], "specify must remain blocked")
    cli = captures.command("advance", str(case), "specify", "--actor", ACTOR, rejected=True)
    mcp = await captures.tool(client, "advance", {"path": str(case), "phase": "specify", "actor": ACTOR},
                              rejected=True)
    _require((case / "organon.json").read_bytes() == before, "rejected advances wrote an event")
    return {"gate": gate, "cli_rejection": cli, "mcp_rejection": mcp,
            "ledger_unchanged": True, "multiple_blockers_not_isolated_norm_effect": True}


def _check_ratios(state: dict, audited: list[dict], archive_raw: bytes) -> None:
    items = state["items"]
    _require(len(audited) == 2, "expected exactly two ratio results")
    for label, audited_result in zip(("rental", "return"), audited, strict=True):
        exact = audited_result["exact_ratio"]
        fraction = Fraction(exact["numerator"], exact["denominator"])
        for item_id in (f"e_{label}_fraction", f"i_{label}_fraction"):
            item = items[item_id]
            data = item["data"]
            metric_field = "metric_key" if item["kind"] == "evidence" else "metric"
            _require(data[metric_field] == audited_result["metric"] and data["unit"] == "fraction",
                     "scalar metric and unit must match the typed claim exactly")
            _require(data["exact_ratio"] == exact and isinstance(data["value"], str),
                     "exact rational and explicit decimal string are required")
            value = Decimal(data["value"])
            _require(value.is_finite() and value.as_tuple().exponent == -24, "expected finite 24-place decimal")
            with localcontext() as context:
                context.prec = 80
                rounded = (Decimal(exact["numerator"]) / Decimal(exact["denominator"])).quantize(
                    Decimal("1e-24"), rounding=ROUND_HALF_EVEN)
            _require(value == rounded and abs(Fraction(value) - fraction) <= Fraction(5, 10**25),
                     "decimal representation exceeds the prospective error bound")
            _require(Decimal(str(data["tolerance"])) == Decimal("1e-24"), "numeric tolerance must be 1e-24")
            _require(not item["issues"] and not item["stale"] and not item["contested"],
                     "new typed items must be current and free of issues")
            _require("pr_reanalysis" in _ancestors(items, item_id), "typed measurement lacks protocol lineage")
            if item["kind"] == "evidence":
                _require(data["archive"] == data["source"] == "derived_ratios.json"
                         and data["source_sha256"] == _pin(archive_raw)["sha256"], "ratio archive binding differs")
    for item_id in ("s_rows_pair", "req_row_report"):
        _require("i_rows" not in _ancestors(items, item_id), "new synthesis/requirement depends on rejected i_rows")
        _require(not items[item_id]["issues"] and not items[item_id]["stale"], "new dependent branch is not current")
    _require(items["i_rows"]["version"] == 3 and items["i_rows"]["kind"] == "indicator"
             and any("review rejected" in issue for issue in items["i_rows"]["issues"]),
             "legacy compound indicator must retain version 3 and its technical rejection")


def _contract_negatives(case: Path) -> list[dict]:
    from specorganon.ratio_audit import RatioAuditError, audit_derived_ratio

    source = (case / "published_report.json").read_bytes()
    contract = (case / "ratio_contract.json").read_bytes()
    claim = (case / "ratio_claim_rental.json").read_bytes()
    expected = SOURCE_PINS["cases/citibike_march2024/ratio_contract_2026-09-27.json"]
    tests = []
    bad_unit = json.loads(claim)
    bad_unit["unit"] = "station_minutes"
    tests.append(("claim_unit", contract, _json(bad_unit), "claim.unit"))
    bad_period = json.loads(claim)
    bad_period["time_scope"]["start_utc"] = "2026-03-12T21:40:49Z"
    bad_period["time_scope"]["end_utc"] = "2026-03-23T14:49:01Z"
    tests.append(("claim_period", contract, _json(bad_period), "claim.time_scope"))
    bad_target = json.loads(claim)
    bad_target["target_id"] = "unknown_target"
    tests.append(("claim_unknown_target", contract, _json(bad_target), "not predeclared"))
    bad_denominator = json.loads(contract)
    bad_denominator["quantities"]["eligible_rows"]["locator"] = "rows"
    tests.append(("contract_raw_denominator", _json(bad_denominator), claim, "external expected digest"))
    results = []
    for label, contract_raw, claim_raw, fragment in tests:
        try:
            audit_derived_ratio(source, contract_raw, claim_raw, expected)
        except RatioAuditError as exc:
            _require(fragment in str(exc), f"{label} rejected for an unexpected reason")
            results.append({"id": label, "rejected": True, "error": str(exc),
                            "contract_input": json.loads(contract_raw), "claim_input": json.loads(claim_raw),
                            "expected_contract_sha256": expected,
                            "pin_binding_not_semantic_truth": label == "contract_raw_denominator"})
        else:
            raise ValueError(f"{label} was unexpectedly accepted")
    return results


async def _execute(captures: Captures, installed: dict, output: Path, source: dict[str, bytes], report: dict) -> None:
    from mcp.client import Client
    from mcp.client.stdio import StdioServerParameters
    from specorganon.ledger import read_project
    from specorganon.ratio_audit import audit_derived_ratio

    prepared = output / "prepared"
    case = prepared / "case"
    manifest_path = prepared / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    steps = manifest["steps"]
    _require(manifest["schema"] == 1 and len(steps) == 9
             and {step["id"] for step in steps} == set(NEW_IDS + REFRESH_IDS), "expected exactly nine agreed puts")
    baseline = json.loads(source["cases/citibike_march2024_lineage/organon.json"])
    prepared_ledger = read_project(case)
    _require(prepared_ledger == baseline and len(baseline["events"]) == 42, "prepared case is not the frozen 42-event source")
    versions = {event["payload"]["id"]: event["payload"]["version"]
                for event in baseline["events"] if event["kind"] == "item_put"}
    for step in steps:
        _require(step["op"] == "put" and step["expected_version"] == versions.get(step["id"], 0)
                 and step["expected_deps"] == {ref: versions[ref] for ref in step["refs"]},
                 "manifest version/dependency guard differs from its prospective step")
        versions[step["id"]] = step["expected_version"] + 1
    report["manifest"] = manifest
    applied = captures.command("run", str(case), "--manifest", str(manifest_path), "--actor", ACTOR)
    _require(applied["applied"] == 9 and applied["skipped"] == 0 and applied["total_steps"] == 9,
             "installed CLI did not apply exactly nine puts")
    report["cli_manifest_run"] = applied
    params = StdioServerParameters(command=installed["executables"]["organon-mcp"]["path"],
                                  cwd=str(output), env=captures.env)
    async with Client(params, mode="legacy") as client:
        discovery = await asyncio.wait_for(client.list_tools(), timeout=90)
        raw_discovery = discovery.model_dump(mode="json", by_alias=True)
        _new_file(output / "mcp_discovery.json", _json(raw_discovery))
        report["mcp_tools"] = sorted(tool.name for tool in discovery.tools)
        _require(len(report["mcp_tools"]) == len(set(report["mcp_tools"])) == 22, "expected 22 discovered tools")
        before_replay = (case / "organon.json").read_bytes()
        replay = await captures.tool(client, "run", {"path": str(case), "manifest": manifest, "actor": ACTOR})
        _require(replay["applied"] == 0 and replay["skipped"] == 9
                 and (case / "organon.json").read_bytes() == before_replay, "real MCP replay changed the checkpoint")
        report["mcp_manifest_replay"] = replay
        captures.command("review", str(case), "i_rows", "--verdict", "reject",
                         "--reason", REVIEW_REASON, "--actor", REVIEWER)
        ledger = read_project(case)
        _require(len(ledger["events"]) == 52 and ledger["events"][:42] == baseline["events"]
                 and ledger["project"] == baseline["project"], "positive ledger lost its source prefix/project")
        _require(all(event["kind"] == "item_put" for event in ledger["events"][42:51])
                 and ledger["events"][-1]["kind"] == "item_review"
                 and ledger["events"][-1]["payload"]["id"] == "i_rows"
                 and ledger["events"][-1]["payload"]["version"] == 3
                 and ledger["events"][-1]["payload"]["verdict"] == "reject", "unexpected derivative events")
        state = await _pair(captures, client, case, "status")
        _pending(state)
        archive_raw = (case / "derived_ratios.json").read_bytes()
        archived = json.loads(archive_raw)
        audited = [audit_derived_ratio((case / "published_report.json").read_bytes(),
                                     (case / "ratio_contract.json").read_bytes(),
                                     (case / f"ratio_claim_{label}.json").read_bytes(),
                                     SOURCE_PINS["cases/citibike_march2024/ratio_contract_2026-09-27.json"])
                   for label in ("rental", "return")]
        _require(len(archived["results"]) == 2, "expected two archived typed ratios")
        for result, expected in zip(archived["results"], audited, strict=True):
            _require(all(result[key] == value for key, value in expected.items()), "archived ratio differs from installed audit")
        _check_ratios(state, audited, archive_raw)
        report["positive_state"] = state
        report["positive_traces"] = {item_id: await _pair(captures, client, case, "trace", id=item_id)
                                     for item_id in NEW_IDS}
        report["positive_gates"] = {phase: await _pair(captures, client, case, "gate", phase=phase) for phase in PHASES}
        report["positive_advance_rejections"] = await _blocked(
            captures, client, case, gate=report["positive_gates"]["specify"])
        positive = output / "positive_case"
        shutil.copytree(case, positive)
        positive_inventory = _inventory(positive)
        report["positive_ledger"] = {**_pin((positive / "organon.json").read_bytes()),
                                     "events": 52, "prefix_events": 42, "prefix_preserved": True,
                                     "project_and_case_id_preserved": True, "chain_valid": True}
        report["positive_files"] = positive_inventory
        challenge = output / "denominator_challenge"
        shutil.copytree(positive, challenge)
        before = await _pair(captures, client, challenge, "status")
        eligible = before["items"]["e_eligible"]
        _require(eligible["version"] == 2, "denominator challenge must start at version 2")
        argv = ["put", str(challenge), "e_eligible", "--kind", eligible["kind"], "--text", eligible["text"],
                "--data", _json(eligible["data"]).decode(), "--actor", ACTOR, "--expected-version", "2",
                "--expected-deps", _json(eligible["deps"]).decode()]
        for ref in eligible["deps"]:
            argv.extend(("--ref", ref))
        captures.command(*argv)
        changed = await _pair(captures, client, challenge, "status")
        _require(changed["items"]["e_eligible"]["version"] == 3
                 and changed["items"]["e_eligible"]["data"] == eligible["data"], "challenge changed observed denominator data")
        _require(all(changed["items"][item_id]["stale"] for item_id in NEW_IDS + REFRESH_IDS),
                 "denominator revision did not invalidate every new dependent")
        _require(all(not changed["items"][item_id]["stale"] and not changed["items"][item_id]["issues"]
                     for item_id in ("e_excluded", "e_gaps")), "unrelated sibling evidence was invalidated")
        _pending(changed)
        report["denominator_revision"] = {"state": changed, "same_valid_data": True, "version_from": 2,
                                          "version_to": 3, "all_new_dependents_stale": True,
                                          "siblings_current": True, "rejections": await _blocked(captures, client, challenge)}
        archive_case = output / "archive_challenge"
        shutil.copytree(positive, archive_case)
        archive = archive_case / "derived_ratios.json"
        original = archive.read_bytes()
        archived_before = await _pair(captures, client, archive_case, "status")
        report["archive_controls"] = []
        for control in ("changed_bytes", "missing_file"):
            before_ledger = (archive_case / "organon.json").read_bytes()
            if control == "changed_bytes":
                archive.write_bytes(original + b"\n")
            else:
                archive.unlink()
            troubled = await _pair(captures, client, archive_case, "status")
            _require(all(troubled["items"][item_id]["issues"] for item_id in NEW_IDS + REFRESH_IDS),
                     "bad archive did not mark all dependent branches")
            _pending(troubled)
            rejected = await _blocked(captures, client, archive_case)
            _require((archive_case / "organon.json").read_bytes() == before_ledger, "archive control changed ledger")
            archive.write_bytes(original)
            restored = await _pair(captures, client, archive_case, "status")
            _require(restored == archived_before, "restoring exact bytes did not restore previous current state")
            _pending(restored)
            report["archive_controls"].append({"id": control, "state": troubled, "rejections": rejected,
                                               "restored_exact_bytes": True, "restored_prior_state": True,
                                               "ledger_unchanged": True, "restoration_is_not_acceptance": True})
        report["contract_negatives"] = _contract_negatives(positive)
        _require(_inventory(positive) == positive_inventory, "challenge controls mutated positive checkpoint")
        report["positive_unchanged_after_challenges"] = True


def probe(repo: Path, output: Path) -> dict[str, Any]:
    repo = repo.resolve(strict=True)
    source = _source_bytes(repo)  # fixed references checked before mkdir/import
    wheel = repo / "experiments/development/lot_journal_prospectus_2026-09-30/installed/specorganon-0.1.0-py3-none-any.whl"
    modules_before = _source_wheel(repo, wheel)
    output = output.absolute()
    _require(not output.exists() and not output.is_symlink(), "output directory must be new")
    output = output.parent.resolve(strict=True) / output.name
    _require(not output.is_relative_to(repo), "output must be external to repository")
    output.mkdir(mode=0o700)
    (output / "tmp").mkdir(mode=0o700)
    home = os.environ.get("HOME")
    os.environ.clear()
    os.environ.update({"PATH": os.pathsep.join((str(Path(sys.executable).parent), "/usr/bin", "/bin")),
                       "TMPDIR": str(output / "tmp"), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
                       "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1",
                       "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"})
    if home is not None:
        os.environ["HOME"] = home
    sys.dont_write_bytecode = True
    report: dict[str, Any] = {"schema": 1, "classification": CLASSIFICATION, "started_at_utc": _now(),
                              "passed": False, "provider_calls": 0, "sealed_evaluation": False, "Q": None,
                              "human_authority_authenticated": False, "field_impact_evaluated": False,
                              "criterion2_or_5_acceptance_evaluated": False, "counts_toward_required_24_runs": False,
                              "numeric_values_are_rounded_not_exact": True,
                              "technical_item_rejection_is_not_normative_approval": True,
                              "blocking_has_multiple_causes": True,
                              "inputs_before": {name: _pin(raw) for name, raw in source.items()},
                              "production_sources_before": modules_before,
                              "helper_source": _pin(Path(__file__).read_bytes())}
    captures = None
    try:
        verifier = _load_verifier(source["scripts/probe_installed_signed_transports.py"],
                                  repo / "scripts/probe_installed_signed_transports.py")
        installed = verifier._installed(repo, wheel)
        _require(len(installed["modules"]) == 24, "expected 24 installed production modules")
        report["installed"] = installed
        captures = Captures(output, dict(os.environ), installed["executables"]["organon"]["path"])
        builder = repo / "scripts/build_citibike_fraction_variant.py"
        builder_raw = source["scripts/build_citibike_fraction_variant.py"]
        _new_file(output / "builder.executed.py", builder_raw)
        result = captures.process([sys.executable, "-I", "-c", BUILDER_BOOTSTRAP, str(builder),
                                   str(repo), str(output / "prepared")], "builder", payload=builder_raw)
        _require(result.returncode == 0, "pinned builder failed; original outputs and artifacts retained")
        report["builder_receipt"] = json.loads((output / "prepared/receipt.json").read_bytes())
        _require(report["builder_receipt"]["state"] == "prepared", "builder did not produce a prepared case")
        asyncio.run(_execute(captures, installed, output, source, report))
        verifier._origins_still_installed(installed)
        _require(verifier._installed(repo, wheel) == installed, "installed files changed during probe")
        after = _source_bytes(repo)
        report["inputs_after"] = {name: _pin(raw) for name, raw in after.items()}
        report["production_sources_after"] = _source_wheel(repo, wheel)
        _require(report["inputs_before"] == report["inputs_after"]
                 and modules_before == report["production_sources_after"], "frozen sources changed during probe")
        _require(_pin(Path(__file__).read_bytes()) == report["helper_source"], "probe helper changed")
        report["installed_and_source_pins_verified_before_and_after"] = True
        report["passed"] = True
    except Exception as exc:
        report.update(error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc())
    finally:
        if captures is not None:
            captures.stream.close()
            report["captured_calls"] = len(captures.records)
        report["ended_at_utc"] = _now()
        report["retained_files"] = _inventory(output)
        _new_file(output / "report.json", _json(report))
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    try:
        report = probe(args.repo, args.output)
    except (OSError, ValueError, ImportError) as exc:
        print(json.dumps({"classification": CLASSIFICATION, "passed": False,
                          "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps({"classification": CLASSIFICATION, "passed": report["passed"],
                      "report": str(args.output.absolute() / "report.json"), "error": report.get("error")},
                     ensure_ascii=False))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
