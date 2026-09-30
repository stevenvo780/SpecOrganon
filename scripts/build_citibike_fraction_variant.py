"""Prepare a new Citi Bike fraction variant from the frozen 42-event ledger.

Usage: ``VENVPYTHON -I SCRIPT REPO NEW_EXTERNAL_OUTPUT``. The D102 wheel must
already be installed outside REPO. This builder copies public inputs, audits
two existing claims and emits nine guarded put instructions; it never applies
them. The historical indicator stays unchanged. Any later technical rejection
of that indicator belongs to the integration probe, not this builder.

Ratios describe published eligible station-snapshot rows, not station-minutes,
realized access, intervention effects or authenticated field observations.
Exact fractions accompany explicitly rounded decimal representations. Their
representation bound is not a new efficacy or normative acceptance threshold.
Local pins and guards do not establish external custody or atomicity against
same-UID changes to paths and source files.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from fractions import Fraction
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import stat
import sys
from typing import Any


SOURCE_LEDGER = "cases/citibike_march2024_lineage/organon.json"
PUBLISHED = "experiments/development/citibike_sample_status_2026-09-27.json"
ANALYSIS = "cases/citibike/analyze_sample_status.py"
CONTRACT = "cases/citibike_march2024/ratio_contract_2026-09-27.json"
CLAIMS = {
    "rental_service_fraction": "cases/citibike_march2024/ratio_claim_rental_2026-09-27.json",
    "return_service_fraction": "cases/citibike_march2024/ratio_claim_return_2026-09-27.json",
}
HELPER = "scripts/probe_installed_signed_transports.py"
WHEEL = "experiments/development/lot_journal_prospectus_2026-09-30/installed/specorganon-0.1.0-py3-none-any.whl"
PINS = {
    "GOAL.md": "e8341bea380cc357ad9e02ec4689a4ed47fe198ba06e4c98639f29264c314c36",
    SOURCE_LEDGER: "7cb7f451e953a02a7254edd2e6713ad7acc470181b2cc0966b5d9b88c51692e3",
    PUBLISHED: "352ef988b91813912d15c465ba1e597c76eedc1461c33b29afc928c9f88c7ee1",
    ANALYSIS: "e384b43d24bf2b928c1772c7781e38c8abbbface8f92bfb98dc5ad804b3bf949",
    CONTRACT: "44f016ce11b3e07ad0309221a5f9f285ea3d0b16c643328a5fc0f37dec705255",
    CLAIMS["rental_service_fraction"]: "48813b54b7ce4d393b0a803f38f0caf1cc66a8717fbddc34f1157e31e949b666",
    CLAIMS["return_service_fraction"]: "013c4bd67e9168efb301148590acfa6f9a9466655ceac0f851d6d6c1fb325f30",
    HELPER: "3b7deea460f779234f4650f20c36788ad890ff56e7e45103f4c1f5b293583013",
    WHEEL: "e155d010a17a1235f071da6b0d89c1773b5dc92295a85251873f1880c448390b",
}
RATIO_MODULE_SHA = "55bf8b9174d49985ce69b503b113541bc313f992ca4fced9532fb0f0201121d1"
HEAD = "4585a56f27701d824de5d82f3e7f66428e5c5ee20efb97cdd23cce11cb96b620"
ACTOR = "agent:d105_fraction_builder"
MAX_BYTES = 16 * 1024 * 1024


class VariantError(ValueError):
    """The pinned source or prepared variant cannot support publication."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise VariantError(message)


def _pin(raw: bytes) -> dict[str, Any]:
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def _read(path: Path) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(descriptor)
        _require(stat.S_ISREG(info.st_mode) and info.st_size <= MAX_BYTES,
                 f"not a bounded regular file: {path}")
        chunks, remaining = [], MAX_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(remaining, 65536))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        _require(len(raw) <= MAX_BYTES, f"file exceeds limit: {path}")
        return raw
    finally:
        os.close(descriptor)


def _json(raw: bytes) -> Any:
    def pairs(values):
        result = {}
        for key, value in values:
            _require(key not in result, f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def constant(value):
        raise VariantError(f"non-finite JSON constant: {value}")

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


def _encode(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode()


def _write(path: Path, raw: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _sources(repo: Path) -> dict[str, bytes]:
    sources = {}
    for name, expected in PINS.items():
        path = repo / name
        _require(path.resolve(strict=True).is_relative_to(repo), f"source escapes repository: {name}")
        raw = _read(path)
        _require(_pin(raw)["sha256"] == expected, f"fixed source pin mismatch: {name}")
        sources[name] = raw
    return sources


def _minimal_env() -> None:
    # HOME is preserved unchanged. No credential/config environment values
    # are copied, retained, logged or passed to any child (there is no child).
    for name in tuple(os.environ):
        if name != "HOME":
            del os.environ[name]
    os.environ.update({"PATH": os.pathsep.join((str(Path(sys.executable).parent), "/usr/bin", "/bin")),
                       "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
                       "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"})


def _installed(repo: Path, output: Path, sources: dict[str, bytes]):
    snapshot = output / "installed_checks.snapshot.py"
    raw = sources[HELPER]
    _require(_pin(raw)["sha256"] == PINS[HELPER], "installed-check helper pin mismatch")
    _write(snapshot, raw)
    spec = importlib.util.spec_from_file_location("_d105_installed_checks", snapshot)
    _require(spec is not None and spec.loader is not None, "installed-check module is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    exec(compile(raw, str(snapshot), "exec"), module.__dict__)
    installed = module._installed(repo, repo / WHEEL)
    _require(len(installed["modules"]) == 24, "expected exactly 24 installed production modules")
    _require(installed["modules"]["specorganon.ratio_audit"]["sha256"] == RATIO_MODULE_SHA,
             "installed ratio audit differs from frozen D102 bytes")
    _write(output / "installed.json", _encode(installed))
    return module, installed, sys.modules["specorganon.ratio_audit"]


def _latest(ledger: dict) -> dict[str, dict]:
    _require(len(ledger["events"]) == 42 and ledger["events"][-1]["hash"] == HEAD,
             "expected frozen 42-event ledger/head")
    _require(ledger["project"].get("approval_policy") == "signed" and
             ledger["project"].get("case_id") == "4df9f84c-4340-4c88-81b5-110b33fd0e55",
             "source project identity/policy differs")
    items = {}
    historical_events = {
        23: ("phase_review", "ddab73d4262c9691d4049cfbcc927e94d25abcccdb535c77909f0362396675b1"),
        24: ("phase_advance", "061f398b0d252550ff05501fd2c7e02a708ae438b35092b42bfa5b028e221355"),
    }
    for seq, event in enumerate(ledger["events"], 1):
        expected_kind = historical_events.get(seq, ("item_put", None))[0]
        _require(event["seq"] == seq and event["kind"] == expected_kind,
                 "source ledger contains an unexpected event")
        if seq in historical_events:
            # Retain these exact source events; they do not define item versions
            # or grant any new approval in this variant.
            _require(event["hash"] == historical_events[seq][1],
                     "source historical event identity differs")
            continue
        item = event["payload"]
        _require(item["version"] == items.get(item["id"], {}).get("version", 0) + 1,
                 "source item version sequence differs")
        items[item["id"]] = copy.deepcopy(item)
    expected_versions = {"p_access": 1, "n_scope": 1, "pr_reanalysis": 1,
                         "e_eligible": 2, "e_rental": 2, "e_return": 2,
                         "e_excluded": 1, "e_gaps": 1, "i_rows": 3,
                         "syn_limit": 2, "o_rows_report": 2, "o_access_study": 2,
                         "cmp_reporting": 2, "d_reporting": 2, "req_row_report": 2}
    _require(all(items[key]["version"] == version for key, version in expected_versions.items()),
             "source checkpoint versions differ")
    _require(items["i_rows"]["kind"] == "indicator", "legacy indicator kind differs")
    return items


def _locator(source: dict, locator: str) -> Any:
    value = source
    for part in locator.split("."):
        value = value[part]
    return value


def _check_counts(report: dict, items: dict) -> dict[str, int]:
    rows = report["rows"]
    excluded = report["quality"]["excluded_rows"]
    eligible = report["quality"]["conservative_dock_rows"]
    denominator = report["snapshot_row_service"]["denominator"]
    rental = report["snapshot_row_service"]["rental_enabled_with_bike"]
    returns = report["snapshot_row_service"]["return_enabled_with_dock"]
    _require(all(type(value) is int for value in (rows, excluded, eligible, denominator, rental, returns)),
             "published row counts must be integers")
    _require((rows, excluded, eligible, rental, returns) ==
             (1812548, 3512, 1809036, 1725248, 1682386), "published counts differ from frozen baseline")
    _require(rows - excluded == eligible == denominator and 0 <= rental <= eligible
             and 0 <= returns <= eligible, "eligible subset denominator is inconsistent")
    _require(report["classification"] == "published_historical_station_snapshot_analysis_development"
             and report["criterion_5"] == "not_assessed", "published scope classification differs")
    for key in ("e_eligible", "e_rental", "e_return", "e_excluded", "e_gaps"):
        data = items[key]["data"]
        _require(data["sha256_source"] == PINS[PUBLISHED] and data["sha256_script"] == PINS[ANALYSIS]
                 and data["source"] == PUBLISHED and data["script"] == ANALYSIS,
                 f"source evidence provenance differs: {key}")
        actual = _locator(report, data["locator"])
        _require(type(actual) is int and type(data["value"]) is int and actual == data["value"],
                 f"source evidence count/locator differs: {key}")
    _require(items["e_eligible"]["data"]["value"] == eligible,
             "legacy eligible evidence differs from contracted denominator")
    return {"rows": rows, "excluded_rows": excluded, "eligible_rows": eligible,
            "rental_rows": rental, "return_rows": returns, "gaps_over_30_minutes": report["gaps_over_30_minutes"]}


def _representation(exact_ratio: dict) -> dict[str, Any]:
    numerator, denominator = exact_ratio["numerator"], exact_ratio["denominator"]
    _require(type(numerator) is int and type(denominator) is int and denominator > 0,
             "audited ratio must have integer numerator and positive denominator")
    exact = Fraction(numerator, denominator)
    with localcontext() as context:
        context.prec = 80
        rounded = (Decimal(numerator) / Decimal(denominator)).quantize(
            Decimal("1e-24"), rounding=ROUND_HALF_EVEN)
    rendered = format(rounded, ".24f")
    error = abs(Fraction(rendered) - exact)
    _require(error <= Fraction(1, 2 * 10**24), "decimal representation exceeds half-unit bound")
    return {"value": rendered, "decimal_places": 24, "rounding": "ROUND_HALF_EVEN",
            "tolerance": "1e-24", "max_abs_representation_error": "5e-25",
            "actual_abs_representation_error": {"numerator": error.numerator,
                                                "denominator": error.denominator},
            "exact": False,
            "interpretation": "rounded representation of pinned published counts; not a field measurement",
            "bound_is_representation_only_not_an_efficacy_or_normative_threshold": True}


def _audits(ratio_module, sources: dict[str, bytes], counts: dict) -> dict[str, Any]:
    results = []
    expected_metrics = {
        "rental_service_fraction": "rental_enabled_with_bike_share_of_quality_eligible_rows",
        "return_service_fraction": "return_enabled_with_dock_share_of_quality_eligible_rows",
    }
    for target, claim_path in CLAIMS.items():
        result = ratio_module.audit_derived_ratio(sources[PUBLISHED], sources[CONTRACT],
                                                 sources[claim_path], PINS[CONTRACT])
        _require(result["target_id"] == target and result["metric"] == expected_metrics[target]
                 and result["unit"] == "fraction" and
                 result["observation_unit"] == "station_snapshot_row" and
                 result["population"] == "quality_eligible_citibike_station_snapshot_rows",
                 "audited target labels differ from the existing contract")
        _require(result["denominator"]["value"] == counts["eligible_rows"]
                 and result["denominator"]["locator"] == "snapshot_row_service.denominator"
                 and result["denominator"]["unit"] == "station_snapshot_rows"
                 and result["numerator"]["unit"] == "station_snapshot_rows",
                 "ratio does not use the contracted eligible denominator")
        expected_numerator = counts["rental_rows" if target == "rental_service_fraction" else "return_rows"]
        _require(result["numerator"]["value"] == expected_numerator and
                 Fraction(result["exact_ratio"]["numerator"], result["exact_ratio"]["denominator"]) ==
                 Fraction(expected_numerator, counts["eligible_rows"]), "audited rational differs from counts")
        result["representation"] = _representation(result["exact_ratio"])
        results.append(result)
    return {"schema": 1, "classification": "citibike_published_count_fractions_development_variant",
            "source_pins": {"published_report": _pin(sources[PUBLISHED]),
                            "contract": _pin(sources[CONTRACT]),
                            "claims": {target: _pin(sources[path]) for target, path in CLAIMS.items()},
                            "analysis_script": _pin(sources[ANALYSIS]),
                            "installed_ratio_module_sha256": RATIO_MODULE_SHA},
            "counts": counts, "results": results,
            "source_truth_authenticated": False, "subset_membership_verified_from_rows": False,
            "contract_pre_registered": False, "contract_external_custody_verified": False,
            "sampling_uncertainty": "not estimated; irregular snapshots are not station-minute coverage",
            "representation_precision_is_not_measurement_accuracy": True,
            "field_impact": "not_assessed", "criterion_5": "not_assessed"}


def build_manifest(ratio_report: dict, items: dict, archive_sha: str, date: str) -> dict:
    versions = {key: item["version"] for key, item in items.items()}
    steps = []

    def put(item_id, kind, text, refs, data):
        _require(len(refs) == len(set(refs)) and all(ref in versions for ref in refs),
                 f"manifest has duplicate or unknown refs: {item_id}")
        if item_id in items:
            _require(items[item_id]["kind"] == kind, f"manifest cannot change kind: {item_id}")
        expected = versions.get(item_id, 0)
        steps.append({"op": "put", "id": item_id, "kind": kind, "text": text,
                      "refs": refs, "data": data, "expected_version": expected,
                      "expected_deps": {ref: versions[ref] for ref in refs}})
        versions[item_id] = expected + 1

    pairs = []
    for index, result in enumerate(ratio_report["results"]):
        action = "rental" if result["target_id"] == "rental_service_fraction" else "return"
        evidence_id, indicator_id = f"e_{action}_fraction", f"i_{action}_fraction"
        _require(evidence_id not in items and indicator_id not in items, "fraction IDs already exist")
        representation = result["representation"]
        metadata = {"exact_ratio": copy.deepcopy(result["exact_ratio"]),
                    "numerator": copy.deepcopy(result["numerator"]),
                    "denominator": copy.deepcopy(result["denominator"]),
                    "value": representation["value"], "tolerance": representation["tolerance"],
                    "decimal_places": 24, "rounding": "ROUND_HALF_EVEN",
                    "max_abs_representation_error": "5e-25",
                    "representation_precision_is_not_measurement_accuracy": True,
                    "sampling_uncertainty": ratio_report["sampling_uncertainty"],
                    "numeric_interpretation": representation["interpretation"],
                    "observation_unit": result["observation_unit"], "population": result["population"],
                    "time_scope": copy.deepcopy(result["time_scope"]), "unit": "fraction"}
        data = {**metadata, "origin": "derived", "source": "derived_ratios.json", "date": date,
                "archive": "derived_ratios.json", "source_sha256": archive_sha,
                "locator": f"/results/{index}/representation/value",
                "exact_ratio_locator": f"/results/{index}/exact_ratio",
                "metric_key": result["metric"], "scope": result["time_scope"]["id"],
                "method": "specorganon.ratio_audit.audit_derived_ratio",
                "method_module_sha256": RATIO_MODULE_SHA,
                "numerator_locator": result["numerator"]["locator"],
                "denominator_locator": result["denominator"]["locator"],
                "published_report": "published_report.json", "published_report_sha256": PINS[PUBLISHED],
                "contract_archive": "ratio_contract.json", "contract_sha256": PINS[CONTRACT],
                "claim_archive": f"ratio_claim_{action}.json", "claim_sha256": result["claim_sha256"],
                "analysis_script_archive": "source_analysis.py", "analysis_script_sha256": PINS[ANALYSIS],
                "source_truth_authenticated": False, "subset_membership_verified_from_rows": False}
        exact = result["exact_ratio"]
        text = (f"Fracción descriptiva {result['metric']}: {result['numerator']['value']}/"
                f"{result['denominator']['value']} filas elegibles; racional reducido "
                f"{exact['numerator']}/{exact['denominator']}. El value decimal es una representación "
                "redondeada, no acceso efectivo ni resultado de intervención.")
        put(evidence_id, "evidence", text,
            ["p_access", "n_scope", "pr_reanalysis", "e_eligible", f"e_{action}"], data)
        pairs.append((indicator_id, evidence_id, result, metadata))
    for indicator_id, evidence_id, result, metadata in pairs:
        put(indicator_id, "indicator", f"Indicador escalar descriptivo: {result['metric']}; "
            "unidad fraction de filas elegibles, sin umbral de eficacia o aprobación normativa.",
            ["p_access", "n_scope", "pr_reanalysis", evidence_id],
            {**metadata, "metric": result["metric"], "classification": "development_candidate"})
    _require("s_rows_pair" not in items, "pair synthesis already exists")
    typed = ["i_rental_fraction", "i_return_fraction"]
    put("s_rows_pair", "synthesis", "Síntesis descriptiva del par de indicadores de alquiler y devolución; "
        "cada uno conserva su métrica escalar, denominador elegible y racional. Esta síntesis no tiene "
        "una métrica única ni afirma acceso vivido, cobertura temporal completa o eficacia.",
        ["p_access", "n_scope", "pr_reanalysis", *typed, "e_eligible", "e_rental", "e_return",
         "e_excluded", "e_gaps"],
        {"components": typed, "supersedes_kind": "indicator", "no_single_scalar_metric": True,
         "legacy_indicator": "i_rows", "legacy_indicator_version": 3,
         "legacy_indicator_untouched": True, "classification": "development_candidate"})
    refresh_refs = {
        "o_rows_report": ["s_rows_pair", *typed, "n_scope", "syn_limit"],
        "cmp_reporting": ["o_rows_report", "o_access_study", "e_eligible", "e_gaps", "s_rows_pair"],
        "d_reporting": ["cmp_reporting", "e_eligible", "s_rows_pair", *typed, "n_scope"],
        "req_row_report": ["d_reporting", "s_rows_pair", *typed, "e_rental_fraction", "e_return_fraction",
                           "e_eligible", "e_rental", "e_return", "e_excluded", "e_gaps"],
    }
    for item_id, refs in refresh_refs.items():
        original = items[item_id]
        data = {**copy.deepcopy(original["data"]), "classification": "development_candidate",
                "field_impact": "not_assessed", "fraction_components": typed}
        text = original["text"] + " Variante candidata: usar los dos indicadores escalares auditados "
        text += "y su síntesis descriptiva; el racional exacto acompaña a la representación decimal acotada."
        put(item_id, original["kind"], text, refs, data)
    _require(len(steps) == 9 and all(step["id"] != "i_rows" for step in steps),
             "expected nine puts with legacy indicator untouched")
    return {"schema": 1, "name": "D105 pinned Citi Bike scalar fraction variant",
            "description": "Nine candidate puts only; norm/decision approvals and phase advances absent.",
            "steps": steps}


def prepare(repo: Path, output: Path) -> dict[str, Any]:
    repo = repo.resolve(strict=True)
    output = output.absolute()
    _require(not output.exists() and not output.is_symlink(), "output must be new")
    output = output.parent.resolve(strict=True) / output.name
    _require(not output.is_relative_to(repo), "output must be outside repository")
    output.mkdir(mode=0o700)
    receipt: dict[str, Any] = {"schema": 1, "study_id": "D105", "state": "failed",
                              "output": str(output), "case": str(output / "case"),
                              "manifest": str(output / "manifest.json"),
                              "commands_executed": 0, "puts_applied": 0, "provider_calls": 0,
                              "field_impact": "not_assessed", "human_approvals": 0,
                              "phase_advances": 0, "same_uid_custody_authenticated": False,
                              "path_and_ledger_atomicity_claimed": False,
                              "sampling_uncertainty_is_not_representation_error": True}
    prior_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    _minimal_env()
    try:
        sources = _sources(repo)
        receipt["source_pins_before"] = {name: _pin(raw) for name, raw in sources.items()}
        _write(output / "source_pins.before.json", _encode(receipt["source_pins_before"]))
        ledger = _json(sources[SOURCE_LEDGER])
        items = _latest(ledger)
        counts = _check_counts(_json(sources[PUBLISHED]), items)
        helper, installed, ratio_module = _installed(repo, output, sources)
        ratio_report = _audits(ratio_module, sources, counts)
        ratio_bytes = _encode(ratio_report)
        ratio_pin = _pin(ratio_bytes)
        manifest = build_manifest(ratio_report, items, ratio_pin["sha256"],
                                  dt.datetime.now(dt.timezone.utc).date().isoformat())
        runner = sys.modules["specorganon.runner"]
        steps = runner._manifest_steps(manifest)
        _require(runner._expected_step_deps(steps) == [step["expected_deps"] for step in steps],
                 "installed runner dependency guards differ")
        case = output / "case"
        case.mkdir(mode=0o700)
        snapshots = {"organon.json": SOURCE_LEDGER, "published_report.json": PUBLISHED,
                     "ratio_contract.json": CONTRACT, "source_analysis.py": ANALYSIS,
                     "ratio_claim_rental.json": CLAIMS["rental_service_fraction"],
                     "ratio_claim_return.json": CLAIMS["return_service_fraction"]}
        for name, source in snapshots.items():
            _write(case / name, sources[source])
        _write(case / "derived_ratios.json", ratio_bytes)
        _write(output / "manifest.json", _encode(manifest))
        _write(output / "GOAL.snapshot.md", sources["GOAL.md"])
        _require(_read(case / "organon.json") == sources[SOURCE_LEDGER], "ledger copy is not byte-identical")
        helper._origins_still_installed(installed)
        _require(_sources(repo) == sources, "pinned original inputs changed during preparation")
        receipt["source_pins_after"] = {name: _pin(raw) for name, raw in _sources(repo).items()}
        _write(output / "source_pins.after.json", _encode(receipt["source_pins_after"]))
        receipt.update(state="prepared", source_event_count=42, manifest_steps=9,
                       ledger_copied_byte_identically=True, original_files_unchanged=True,
                       installed_origins_verified_before_and_after=True,
                       planned_event_count_after_puts=51, legacy_indicator_version=3,
                       legacy_indicator_untouched=True, technical_rejection_not_in_manifest=True)
        receipt["source_prefix"] = {"ledger": SOURCE_LEDGER, "ledger_pin": _pin(sources[SOURCE_LEDGER]),
                                    "event_count": 42, "head_hash": HEAD,
                                    "canonical_events_pin": _pin(_encode(ledger["events"]))}
        receipt["derived_ratios"] = ratio_pin
        receipt["manifest_pin"] = _pin(_encode(manifest))
        receipt["case_files"] = {path.name: _pin(_read(path)) for path in sorted(case.iterdir())}
        receipt["limits"] = {"exact_ratio_metadata_automatically_validated_by_engine": False,
                             "engine_numeric_checks_use_rounded_decimal_value": True,
                             "contract_pre_registered": False, "source_truth_authenticated": False,
                             "subset_membership_verified_from_rows": False,
                             "representation_precision_is_not_measurement_accuracy": True,
                             "criterion_5": "not_assessed"}
    except Exception as exc:
        receipt["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        sys.dont_write_bytecode = prior_bytecode
        _write(output / "receipt.json", _encode(receipt))
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = prepare(args.repo, args.output)
    except (OSError, ValueError, ImportError) as exc:
        print(json.dumps({"state": "failed", "error": f"{type(exc).__name__}: {exc}"}), file=sys.stderr)
        return 2
    print(json.dumps({key: result.get(key) for key in
                      ("state", "output", "case", "manifest", "manifest_steps", "source_event_count", "error")}))
    return 0 if result["state"] == "prepared" else 2


if __name__ == "__main__":
    raise SystemExit(main())
