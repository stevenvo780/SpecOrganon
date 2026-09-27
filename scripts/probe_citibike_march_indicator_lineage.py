"""Probe and repair the March 2024 indicator's missing evidence lineage.

Both experiments start from byte-identical temporary copies of the historical
ledger. The optional derived case is a development artifact, never a rewrite of
that ledger or evidence of human approval, criterion 5, or field impact.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from mcp.client import Client
from mcp.client.stdio import StdioServerParameters


ROOT = Path(__file__).resolve().parents[1]
SOURCE_CASE = ROOT / "cases/citibike_march2024"
SOURCE_LEDGER = SOURCE_CASE / "organon.json"
JUNE_LEDGER = ROOT / "cases/citibike/organon.json"
SEED = SOURCE_CASE / "seed.json"
PUBLISHED_RESULT = (
    ROOT / "experiments/development/citibike_sample_status_2026-09-27.json"
)
ANALYSIS_SCRIPT = ROOT / "cases/citibike/analyze_sample_status.py"
CLI = Path(sys.executable).with_name("organon")
MCP = Path(sys.executable).with_name("organon-mcp")
ACTOR = "agent:march_indicator_lineage_probe"
EVIDENCE_IDS = ("e_eligible", "e_rental", "e_return", "e_excluded", "e_gaps")
INDICATOR_REFS = ("p_access", "n_scope", "pr_reanalysis", *EVIDENCE_IDS)
REPAIR_ORDER = (
    "e_rental",
    "e_return",
    "inf_scope",
    "syn_limit",
    "unc_coverage",
    "i_rows",
    "o_rows_report",
    "o_access_study",
    "cmp_reporting",
    "d_reporting",
    "req_row_report",
)
DERIVED_ARTIFACT_NAMES = ("organon.json", "manifest.json", "README.md")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _encode(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def check_eligible_denominator(candidate: int, published: dict[str, Any]) -> int:
    """Require the conservative denominator, not the unfiltered row count."""
    rows = published["rows"]
    excluded = published["quality"]["excluded_rows"]
    eligible = published["quality"]["conservative_dock_rows"]
    reported = published["snapshot_row_service"]["denominator"]
    if any(
        type(value) is not int
        for value in (candidate, rows, excluded, eligible, reported)
    ):
        raise ValueError("row counts must be integers")
    if rows != 1_812_548 or eligible != 1_809_036 or excluded != 3_512:
        raise ValueError(
            "March 2024 pinned row counts differ from the archived analysis"
        )
    if eligible != rows - excluded or reported != eligible:
        raise ValueError("published denominator fails the exclusion cross-check")
    if candidate != eligible:
        raise ValueError(
            f"candidate denominator {candidate} differs from eligible {eligible}"
        )
    return eligible


def _check_sources(
    source_ledger: dict[str, Any], published: dict[str, Any]
) -> dict[str, str]:
    items = {
        event["payload"]["id"]: event["payload"]
        for event in source_ledger["events"]
        if event["kind"] == "item_put"
    }
    if len(source_ledger["events"]) != 24 or set(EVIDENCE_IDS) - set(items):
        raise AssertionError(
            "historical March ledger no longer has its expected baseline"
        )
    if items["i_rows"]["version"] != 1 or any(
        ref in items["i_rows"]["deps"] for ref in EVIDENCE_IDS
    ):
        raise AssertionError(
            "historical indicator no longer exposes the missing dependency"
        )
    result_hash = _sha256(PUBLISHED_RESULT.read_bytes())
    script_hash = _sha256(ANALYSIS_SCRIPT.read_bytes())
    for item_id in EVIDENCE_IDS:
        data = items[item_id]["data"]
        if data["sha256_source"] != result_hash or data["sha256_script"] != script_hash:
            raise AssertionError(f"source digest mismatch for {item_id}")
        if (
            ROOT / data["source"] != PUBLISHED_RESULT
            or ROOT / data["script"] != ANALYSIS_SCRIPT
        ):
            raise AssertionError(f"source path mismatch for {item_id}")
        value: Any = published
        for key in data["locator"].split("."):
            value = value[key]
        if type(value) is not int or data["value"] != value:
            raise AssertionError(f"source locator mismatch for {item_id}")
    check_eligible_denominator(items["e_eligible"]["data"]["value"], published)
    if items["e_archive"]["data"]["sha256_source"] != published["input_sha256"]:
        raise AssertionError("declared Parquet hash differs from the archived analysis")
    if published["criterion_5"] != "not_assessed":
        raise AssertionError("archived criterion 5 classification changed")
    return {
        "published_result": result_hash,
        "analysis_script": script_hash,
        "declared_parquet": published["input_sha256"],
    }


def _cli(env: dict[str, str], *args: str) -> dict[str, Any]:
    completed = subprocess.run(
        [str(CLI), *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
        timeout=60,
    )
    return json.loads(completed.stdout)


def _put_cli(
    env: dict[str, str],
    case: Path,
    item_id: str,
    kind: str,
    text: str,
    refs: tuple[str, ...] | list[str],
    data: dict[str, Any],
) -> dict[str, Any]:
    state = _cli(env, "status", str(case))
    existing = state["items"].get(item_id)
    expected_deps = {ref: state["items"][ref]["version"] for ref in refs}
    return _cli(
        env,
        "put",
        str(case),
        item_id,
        "--kind",
        kind,
        "--text",
        text,
        *(part for ref in refs for part in ("--ref", ref)),
        "--data",
        _encode(data),
        "--actor",
        ACTOR,
        "--expected-version",
        str(existing["version"] if existing else 0),
        "--expected-deps",
        _encode(expected_deps),
    )


def _revise_eligible(env: dict[str, str], case: Path) -> dict[str, Any]:
    item = _cli(env, "status", str(case))["items"]["e_eligible"]
    return _put_cli(
        env,
        case,
        "e_eligible",
        "evidence",
        item["text"]
        + " Denominador reconfirmado contra el resultado publicado fijado.",
        tuple(item["deps"]),
        item["data"],
    )


def _refresh(env: dict[str, str], case: Path, item_id: str) -> dict[str, Any]:
    item = _cli(env, "status", str(case))["items"][item_id]
    return _put_cli(
        env,
        case,
        item_id,
        item["kind"],
        item["text"],
        tuple(item["deps"]),
        item["data"],
    )


def _mcp_data(result: Any) -> dict[str, Any]:
    if result.is_error:
        raise AssertionError(f"MCP operation failed: {result.content}")
    return result.structured_content or json.loads(result.content[0].text)


async def _link_indicator_mcp(
    env: dict[str, str],
    case: Path,
    original: dict[str, Any],
    expected_deps: dict[str, int],
) -> tuple[list[str], dict[str, Any]]:
    params = StdioServerParameters(command=str(MCP), cwd=str(ROOT), env=env)
    async with Client(params, mode="legacy") as client:
        discovered = sorted(tool.name for tool in (await client.list_tools()).tools)
        if not {"put", "status", "trace", "gate"} <= set(discovered):
            raise AssertionError("real MCP server lacks lineage tools")
        linked = _mcp_data(
            await client.call_tool(
                "put",
                {
                    "path": str(case),
                    "id": "i_rows",
                    "kind": "indicator",
                    "text": original["text"]
                    + " Las cinco evidencias derivadas quedan enlazadas explícitamente.",
                    "refs": list(INDICATOR_REFS),
                    "data": original["data"],
                    "actor": ACTOR,
                    "expected_version": 1,
                    "expected_deps": expected_deps,
                },
            )
        )
        mcp_status = _mcp_data(await client.call_tool("status", {"path": str(case)}))
        mcp_trace = _mcp_data(
            await client.call_tool("trace", {"path": str(case), "id": "i_rows"})
        )
        mcp_gate = _mcp_data(
            await client.call_tool("gate", {"path": str(case), "phase": "study"})
        )
    if mcp_status != _cli(env, "status", str(case)):
        raise AssertionError("MCP and CLI states differ after indicator repair")
    if mcp_gate != _cli(env, "gate", str(case), "study"):
        raise AssertionError("MCP and CLI gates differ after indicator repair")
    if set(EVIDENCE_IDS) - {item["id"] for item in mcp_trace["ancestors"]}:
        raise AssertionError("repaired indicator is missing an evidence ancestor")
    return discovered, linked


def _add_candidate_chain(env: dict[str, str], case: Path) -> None:
    """Trace a descriptive reporting requirement without approving an intervention."""
    candidates = (
        (
            "o_rows_report",
            "option",
            "Informar dos fracciones por filas elegibles con exclusiones y huecos visibles; no afirmar acceso vivido.",
            ("syn_limit", "n_scope", "i_rows"),
        ),
        (
            "o_access_study",
            "option",
            "Reservar las afirmaciones sobre acceso vivido para otro estudio con intentos y cobertura temporal.",
            ("syn_limit", "n_scope", "e_gaps"),
        ),
        (
            "cmp_reporting",
            "comparison",
            "La primera opción permite reporte descriptivo acotado; la segunda exige nueva evidencia para acceso vivido. Ninguna prueba impacto.",
            ("o_rows_report", "o_access_study", "e_eligible", "e_gaps"),
        ),
        (
            "d_reporting",
            "decision",
            "Decisión candidata de desarrollo, sin aprobación humana: usar solo el reporte descriptivo acotado hasta contar con otro estudio.",
            ("cmp_reporting", "n_scope", "e_eligible", "i_rows"),
        ),
        (
            "req_row_report",
            "requirement",
            "Requisito candidato, no implementado: mostrar numeradores de alquiler y devolución sobre 1.809.036 filas elegibles, y advertir 3.512 exclusiones y 37 huecos largos.",
            ("d_reporting", "i_rows", *EVIDENCE_IDS),
        ),
    )
    for item_id, kind, description, refs in candidates:
        _put_cli(
            env,
            case,
            item_id,
            kind,
            description,
            refs,
            {"classification": "development_candidate", "field_impact": "not_assessed"},
        )


def _copy_source(destination: Path, source_bytes: bytes) -> Path:
    destination.mkdir()
    ledger = destination / "organon.json"
    ledger.write_bytes(source_bytes)
    if ledger.read_bytes() != source_bytes:
        raise AssertionError("temporary ledger copy differs from historical bytes")
    return destination


def _record(state: dict[str, Any], *item_ids: str) -> dict[str, dict[str, Any]]:
    return {
        item_id: {
            "version": state["items"][item_id]["version"],
            "stale": state["items"][item_id]["stale"],
            "deps": state["items"][item_id]["deps"],
        }
        for item_id in item_ids
    }


def _save_derived(
    destination: Path,
    final_bytes: bytes,
    source_hash: str,
    source_events: int,
    final_events: int,
    case_id: str,
    prefix_sha256: str,
    prefix_head_hash: str,
) -> None:
    if destination.exists():
        raise FileExistsError(f"derived case already exists: {destination}")
    destination.mkdir(parents=True)
    (destination / "organon.json").write_bytes(final_bytes)
    manifest = {
        "schema": 1,
        "classification": "development_append_only_lineage_derivative",
        "source": str(SOURCE_LEDGER.relative_to(ROOT)),
        "source_sha256": source_hash,
        "source_event_count": source_events,
        "source_event_prefix_sha256": prefix_sha256,
        "historical_prefix_head_hash": prefix_head_hash,
        "derived_sha256": _sha256(final_bytes),
        "derived_event_count": final_events,
        "inherited_case_id": case_id,
        "human_approval": "absent",
        "criterion_5": "not_assessed",
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    (destination / "README.md").write_text(
        "# Citi Bike March 2024: development lineage derivative\n\n"
        "This ledger retains the historical case ID and every original event and hash "
        "in its prefix. New events repair the indicator's explicit evidence references, "
        "exercise invalidation, and append fresh dependent revisions. It is a development "
        "derivative, not an independent case or a new historical observation.\n\n"
        "Regenerate the logic with `uv run python "
        "scripts/probe_citibike_march_indicator_lineage.py`. Event timestamps and hashes "
        "in a new run will differ. The original ledger and seed stay untouched. The norm "
        "and candidate decision remain unapproved; criterion 5 and field impact remain "
        "unassessed.\n",
        encoding="utf-8",
    )


def _validate_output_destination(output: Path, derived_case: Path | None) -> None:
    resolved_output = output.resolve()
    historical_sources = (
        SOURCE_LEDGER,
        JUNE_LEDGER,
        SEED,
        PUBLISHED_RESULT,
        ANALYSIS_SCRIPT,
    )
    if resolved_output in {path.resolve() for path in historical_sources}:
        raise ValueError("--output must not replace a historical source")
    if derived_case is not None:
        derived_root = derived_case.resolve()
        derived_artifacts = {
            (derived_case / name).resolve() for name in DERIVED_ARTIFACT_NAMES
        }
        if resolved_output == derived_root or resolved_output in derived_artifacts:
            raise ValueError("--output collides with a derived-case artifact")


def _write_receipt_atomic(output: Path, encoded: str) -> None:
    expected = _sha256(encoded.encode("utf-8"))
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output)
        temporary = None
        directory_fd = os.open(output.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        if _sha256(output.read_bytes()) != expected:
            raise AssertionError("receipt hash differs after atomic publication")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def run_probe(derived_case: Path | None = None) -> dict[str, Any]:
    if not CLI.is_file() or not MCP.is_file():
        raise FileNotFoundError(
            "installed organon and organon-mcp executables are required"
        )
    protected = (SOURCE_LEDGER, JUNE_LEDGER, SEED, PUBLISHED_RESULT, ANALYSIS_SCRIPT)
    protected_hashes = {
        str(path.relative_to(ROOT)): _sha256(path.read_bytes()) for path in protected
    }
    source_bytes = SOURCE_LEDGER.read_bytes()
    source = json.loads(source_bytes)
    published = json.loads(PUBLISHED_RESULT.read_bytes())
    source_hashes = _check_sources(source, published)
    false_count_rejected = False
    try:
        check_eligible_denominator(published["rows"], published)
    except ValueError:
        false_count_rejected = True
    if not false_count_rejected:
        raise AssertionError(
            "the unfiltered 1,812,548 count was accepted as denominator"
        )

    with tempfile.TemporaryDirectory(prefix="organon-march-indicator-") as temporary:
        work = Path(temporary)
        control = _copy_source(work / "control", source_bytes)
        linked = _copy_source(work / "linked", source_bytes)
        env = os.environ.copy()
        for key in (
            "ORGANON_APPROVERS_FILE",
            "ORGANON_ALLOW_FIXTURES",
            "ORGANON_LEDGER_ANCHORS_FILE",
        ):
            env.pop(key, None)
        env["ORGANON_ROOT"] = str(work)

        initial = _cli(env, "status", str(control))
        if initial != _cli(env, "status", str(linked)) or initial["revision"] != 24:
            raise AssertionError(
                "temporary branches do not share the historical baseline"
            )
        if (
            initial["items"]["i_rows"]["stale"]
            or initial["items"]["e_eligible"]["stale"]
        ):
            raise AssertionError("historical baseline unexpectedly stale")

        _revise_eligible(env, control)
        control_state = _cli(env, "status", str(control))
        control_gate = _cli(env, "gate", str(control), "study")
        if (
            control_state["items"]["i_rows"]["version"] != 1
            or control_state["items"]["i_rows"]["stale"]
            or not control_state["items"]["e_rental"]["stale"]
            or not control_state["items"]["e_return"]["stale"]
            or "i_rows"
            in {
                item["id"]
                for item in _cli(env, "trace", str(control), "e_eligible")["dependents"]
            }
            or "i_rows depends on an older revision" in control_gate["blockers"]
        ):
            raise AssertionError(
                "negative dependency control did not reproduce the gap"
            )

        original_indicator = initial["items"]["i_rows"]
        expected_deps = {
            ref: initial["items"][ref]["version"] for ref in INDICATOR_REFS
        }
        discovered, linked_event = asyncio.run(
            _link_indicator_mcp(env, linked, original_indicator, expected_deps)
        )
        if linked_event["version"] != 2 or linked_event["deps"] != expected_deps:
            raise AssertionError(
                "MCP did not append the explicit indicator dependencies"
            )
        _add_candidate_chain(env, linked)
        before = _cli(env, "status", str(linked))
        before_study = _cli(env, "gate", str(linked), "study")
        before_specify = _cli(env, "gate", str(linked), "specify")
        requirement_ancestors = {
            item["id"]
            for item in _cli(env, "trace", str(linked), "req_row_report")["ancestors"]
        }
        if (
            before["items"]["i_rows"]["stale"]
            or before["items"]["req_row_report"]["stale"]
            or not {
                "p_access",
                "n_scope",
                "pr_reanalysis",
                "d_reporting",
                *EVIDENCE_IDS,
            }
            <= requirement_ancestors
        ):
            raise AssertionError(
                "candidate requirement lacks its declared current ancestry"
            )
        if any(
            "req_row_report lacks" in blocker for blocker in before_specify["blockers"]
        ):
            raise AssertionError(
                "candidate requirement failed the engine's structural lineage gate"
            )

        _revise_eligible(env, linked)
        invalidated = _cli(env, "status", str(linked))
        invalid_study = _cli(env, "gate", str(linked), "study")
        invalid_specify = _cli(env, "gate", str(linked), "specify")
        if (
            not invalidated["items"]["i_rows"]["stale"]
            or not invalidated["items"]["req_row_report"]["stale"]
            or "i_rows depends on an older revision" not in invalid_study["blockers"]
            or "req_row_report depends on an older revision"
            not in invalid_specify["blockers"]
            or invalid_study["ready"]
            or invalid_specify["ready"]
        ):
            raise AssertionError(
                "source revision did not invalidate indicator, requirement and gates"
            )

        repaired_versions = {}
        for item_id in REPAIR_ORDER:
            repaired_versions[item_id] = _refresh(env, linked, item_id)["version"]
        repaired = _cli(env, "status", str(linked))
        repaired_study = _cli(env, "gate", str(linked), "study")
        repaired_specify = _cli(env, "gate", str(linked), "specify")
        if any(
            repaired["items"][item_id]["stale"]
            for item_id in (*EVIDENCE_IDS, *REPAIR_ORDER)
        ):
            raise AssertionError("append-only repair left a dependent item stale")
        if (
            "i_rows depends on an older revision" in repaired_study["blockers"]
            or "req_row_report depends on an older revision"
            in repaired_specify["blockers"]
            or any(
                "req_row_report lacks" in blocker
                for blocker in repaired_specify["blockers"]
            )
        ):
            raise AssertionError("repair did not clear lineage-specific blockers")
        if (
            repaired["items"]["n_scope"]["approved"]
            or repaired["items"]["d_reporting"]["approved"]
        ):
            raise AssertionError("probe must not manufacture human approval")

        final_bytes = (linked / "organon.json").read_bytes()
        final_ledger = json.loads(final_bytes)
        if (
            final_ledger["project"] != source["project"]
            or final_ledger["events"][:24] != source["events"]
        ):
            raise AssertionError(
                "derived ledger did not retain the historical event prefix"
            )
        prefix_sha256 = _sha256(_encode(source["events"]).encode("utf-8"))
        if (
            _sha256(_encode(final_ledger["events"][:24]).encode("utf-8"))
            != prefix_sha256
            or final_ledger["events"][23]["hash"] != source["events"][23]["hash"]
        ):
            raise AssertionError(
                "historical event prefix hash differs in derived ledger"
            )
        if any(event["kind"] == "approval" for event in final_ledger["events"][24:]):
            raise AssertionError("derived ledger added an approval")
        if derived_case is not None:
            _save_derived(
                derived_case,
                final_bytes,
                _sha256(source_bytes),
                24,
                len(final_ledger["events"]),
                source["project"]["case_id"],
                prefix_sha256,
                source["events"][23]["hash"],
            )

        receipt = {
            "schema": 1,
            "classification": "development_lineage_probe",
            "source": str(SOURCE_LEDGER.relative_to(ROOT)),
            "sha256": {
                "source_ledger": _sha256(source_bytes),
                "seed": protected_hashes[str(SEED.relative_to(ROOT))],
                **source_hashes,
                "control_ledger": _sha256((control / "organon.json").read_bytes()),
                "derived_ledger": _sha256(final_bytes),
                "historical_event_prefix": prefix_sha256,
                "historical_prefix_head": source["events"][23]["hash"],
            },
            "numeric_source_check": {
                "raw_rows": published["rows"],
                "excluded_rows": published["quality"]["excluded_rows"],
                "eligible_denominator": published["quality"]["conservative_dock_rows"],
                "false_raw_row_denominator_rejected": false_count_rejected,
            },
            "control": {
                "revision": control_state["revision"],
                "items": _record(
                    control_state, "e_eligible", "e_rental", "e_return", "i_rows"
                ),
                "study_blockers": control_gate["blockers"],
            },
            "linked": {
                "transport": {
                    "indicator_revision": "real_stdio_mcp",
                    "other_writes": "installed_cli",
                },
                "mcp_discovered": discovered,
                "before_source_revision": {
                    "revision": before["revision"],
                    "items": _record(
                        before, "e_eligible", "i_rows", "d_reporting", "req_row_report"
                    ),
                    "study_blockers": before_study["blockers"],
                    "specify_blockers": before_specify["blockers"],
                },
                "invalidated": {
                    "revision": invalidated["revision"],
                    "items": _record(
                        invalidated,
                        "e_eligible",
                        "i_rows",
                        "d_reporting",
                        "req_row_report",
                    ),
                    "study_blockers": invalid_study["blockers"],
                    "specify_blockers": invalid_specify["blockers"],
                },
                "repaired": {
                    "revision": repaired["revision"],
                    "items": _record(
                        repaired,
                        "e_eligible",
                        "i_rows",
                        "d_reporting",
                        "req_row_report",
                    ),
                    "repaired_versions": repaired_versions,
                    "study_blockers": repaired_study["blockers"],
                    "specify_blockers": repaired_specify["blockers"],
                    "human_approvals_present": False,
                },
            },
            "append_only_source_event_prefix": True,
            "protected_sources_unchanged": all(
                _sha256(path.read_bytes())
                == protected_hashes[str(path.relative_to(ROOT))]
                for path in protected
            ),
            "criterion_5": "not_assessed",
            "field_impact": "not_assessed",
        }
        if not receipt["protected_sources_unchanged"]:
            raise AssertionError("a protected source changed during the probe")
        return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, help="Write development receipt in addition to stdout"
    )
    parser.add_argument(
        "--derived-case", type=Path, help="Create a new append-only development case"
    )
    args = parser.parse_args()
    if args.output:
        try:
            _validate_output_destination(args.output, args.derived_case)
        except ValueError as exc:
            parser.error(str(exc))
    result = run_probe(args.derived_case)
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        _validate_output_destination(args.output, args.derived_case)
        _write_receipt_atomic(args.output, encoded)
    print(encoded, end="")


if __name__ == "__main__":
    main()
