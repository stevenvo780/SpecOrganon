"""Publish and resume a source-audited documentary bread recipe.

The recipe admission checks are a workflow boundary, not a new engine rule.
Direct CLI/MCP puts still require independent review of their factual content.
No phase review, advancement, normative approval or field trial is performed.
Concurrent archive changes can leave a rejected partial ledger; admission is
not an atomic transaction across the ledger and its external source files.
"""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import hashlib
import json
import os
import stat
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import audit_bread_sources as auditor  # noqa: E402
from specorganon import engine, source_passages  # noqa: E402
from specorganon.ledger import read_project  # noqa: E402


ACTOR = "agent:d101_controller"
TITLE = "D101 source-audited bread documentary case"
DOMAIN = "food"
ARCHIVES = {
    "claims": "source_claims.json", "table": "survey_table1.json",
    "contract": "audit_contract.json", "audit": "audit_report.json",
}


class RecipeError(ValueError):
    """The recipe cannot publish from its current inputs or checkpoint."""


def _raw(path: Path) -> bytes:
    try:
        if any(parent.is_symlink() for parent in (path, *path.parents)):
            raise RecipeError("recipe file has a symlink component")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or not 0 <= info.st_size <= 3_000_000:
                raise RecipeError("recipe file is not a bounded regular file")
            return stream.read(3_000_001)
    except OSError as exc:
        raise RecipeError(f"cannot read recipe file: {path.name}") from exc


def _render(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()


def _pin(raw: bytes) -> dict:
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RecipeError(f"duplicate recipe JSON key: {key}")
        result[key] = value
    return result


def _json(path: Path) -> dict:
    try:
        value = json.loads(_raw(path), object_pairs_hook=_pairs,
                           parse_constant=lambda value: (_ for _ in ()).throw(
                               RecipeError(f"nonfinite recipe JSON: {value}")))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RecipeError(f"invalid recipe JSON: {path.name}") from exc
    if type(value) is not dict:
        raise RecipeError("recipe JSON must be an object")
    return value


def _code_pins() -> dict:
    return {name: _pin(_raw(path)) for name, path in {
        "controller": Path(__file__), "auditor": Path(auditor.__file__),
        "passages": Path(source_passages.__file__),
    }.items()}


def build_manifest(report: dict, archive_pins: dict) -> dict:
    steps = []

    def put(id, kind, text, refs=(), data=None):
        steps.append({"op": "put", "id": id, "kind": kind, "text": text,
                      "refs": list(refs), "data": data or {}})

    put("p_seed", "problem", "Investigar conservación de servicio alimentario inocuo en la cadena del pan estudiado y perjuicios por actor; eficacia de una intervención aún desconocida.")
    put("a_chain", "actor", "Agricultores, trabajadores, molino, panadería, transporte, comercios, hogares, productores de envases, usuarios de coproductos y autoridades requieren consulta directa antes de un ensayo.", ["p_seed"])
    put("b_seed", "boundary", "Recorrido documental histórico de cultivo, almacenamiento, molienda, transporte, panificación, comercio y hogares; sin un lote observado enlazado o campo autorizado.", ["p_seed"])
    put("s_historical", "assumption", "Las fuentes publicadas agregadas y autoinformes permiten formular preguntas; no representan línea base actual de lotes identificados ni efecto causal.", ["p_seed"])
    put("q_docs", "question", "¿Qué cantidades, unidades, bases y desacuerdos internos reportan las fuentes fijadas, y qué falta medir en una cadena actual?", ["p_seed", "s_historical"])
    put("h_docs", "hypothesis", "La transcripción de valores puede concordar con tablas publicadas sin que las bases o categorías permitan combinarse como tasas secuenciales o evidencia causal.", ["q_docs"])
    put("pr_docs", "protocol", "Repetir extracción PDF fijada y cotejo de pasajes, filas, unidades y bases antes de publicar evidencia documental.", ["q_docs", "h_docs"], {
        "population": "Dos artículos archivados y sus transcripciones expuestas",
        "method": "D100: PDF y extractor fijados, snapshots sellados, pasajes únicos y revisión de contrato",
        "comparison": "Valores y filas publicados frente a la transcripción; sin brazo de intervención",
        "uncertainty": "Agregados históricos, autoinformes, desacuerdos de prosa/tablas, host y bases interpretadas",
    })
    sources = {"claims": "D100 transcripción de 17 valores", "table": "https://doi.org/10.3390/su10072251",
               "contract": "D100 contrato de pasajes revisado por Codex", "audit": "D100 repetición local del cotejo"}
    for key, archive in ARCHIVES.items():
        refs = ["p_seed", "pr_docs"]
        if key == "audit":
            refs += ["e_bundle_claims", "e_bundle_table", "e_bundle_contract"]
        put("e_bundle_" + key, "evidence", sources[key] + "; sin aceptación humana o efecto de campo.", refs, {
            "origin": "published" if key == "table" else "derived", "source": sources[key],
            "date": "2018-06-29" if key == "table" else "2026-09-30", "locator": archive,
            "archive": archive, "source_sha256": archive_pins[archive]["sha256"],
        })
    evidence_ids = []
    for key, claim in report["claims"].items():
        id = "e_" + key
        evidence_ids.append(id)
        source = claim["source"]
        passage = report["passages"][claim["passage"]]
        put(id, "evidence", f"Publicado: {key} = {claim['value']} {claim['unit']}. Base: {claim['base']}. Procedencia: {claim['provenance']}; dato documental sin efecto causal.",
            ["p_seed", "pr_docs", "s_historical", "e_bundle_audit"], {
                "origin": "published", "source": "https://doi.org/10.3390/" + ("su11010043" if source == "lca" else "su10072251"),
                "date": "2018-12-21" if source == "lca" else "2018-06-29",
                "locator": json.dumps(claim["locator"], ensure_ascii=False, sort_keys=True),
                "audited_locator": claim["locator"], "archive": "source_" + source + ".pdf",
                "source_sha256": report["source_extraction"][source]["sha256"],
                "metric_key": key, "scope": "published_historical_documentary_quantity_not_current_lot",
                "value": claim["value"], "unit": claim["unit"], "base": claim["base"],
                "classification": claim["classification"], "provenance": claim["provenance"],
                "audit_report_sha256": archive_pins[ARCHIVES["audit"]]["sha256"],
                "audit_contract_sha256": archive_pins[ARCHIVES["contract"]]["sha256"],
                "page_sha256": passage["page_sha256"], "passage_sha256": passage["passage_sha256"],
                "matched_sha256": passage["matched_sha256"],
            })
    put("p_refined", "problem", "Las cantidades históricas auditadas delimitan preguntas sobre pérdidas de servicio alimentario por etapa y actor; no prueban eficacia, inocuidad o una línea base actual.", ["p_seed", *evidence_ids])
    put("b_audited", "boundary", "La receta publica 17 cantidades documentales y archiva las siete filas auditadas de encuesta. Múltiples entradas/salidas y coproductos permanecen distintos de desperdicio; no se reconstruye un lote ni se mezclan bases.", ["p_refined", "e_bundle_table", "e_bundle_audit"])
    put("c_value", "concept", "Valor alimentario propuesto: consumo inocuo y útil, nutrición, aceptación, recursos, costes y perjuicios por actor. Masa y precio no son equivalentes automáticos; salvado es coproducto.", ["p_refined", "a_chain", "e_wheat_bran_mass_share"])
    put("f_mass", "frame_option", "Formulación rival: reducir masa descartada; requiere examinar coproductos, cambios de humedad y daños desplazados, sin aceptar esos equivalentes por defecto.", ["p_refined", "a_chain"])
    put("f_service", "frame_option", "Formulación rival: conservar servicio alimentario inocuo efectivamente consumido y evaluar distribución de perjuicios entre etapas y actores.", ["p_refined", "a_chain"])
    put("n_harm", "norm", "Compromiso propuesto y pendiente de aprobación humana competente: no compensar mayor riesgo de inocuidad o perjuicios inadmisibles con menor descarte; valores, márgenes y consentimiento requieren consulta antes de ensayo.", ["p_refined", "a_chain"])
    put("i_doc_mass", "indicator", "Indicador documental de masa por pieza publicada; verifica transcripción, sin medir consumo útil, desperdicio o efecto de intervención.", ["p_refined", "n_harm", "pr_docs", "e_piece_mass"], {"metric": "piece_mass", "unit": "g/piece"})
    put("inf_bases", "inference", "Las fracciones másicas de molienda, asignación económica, energía por harina/pan y desperdicio por base publicada no son cantidades intercambiables ni tasas condicionales de una misma cohorte.", ["pr_docs", "h_docs", "e_wheat_bran_mass_share", "e_wheat_bran_economic_allocation", "e_mill_electricity", "e_bakery_electricity", "e_consumer_bread_waste_estimate"])
    put("u_sources", "uncertainty", "Persisten desacuerdos de prosa y tablas, fuentes empresariales agregadas y autoinformes, sin pesajes por lote, consentimiento, comparador causal o custodia externa.", ["p_refined", "e_bundle_audit", "inf_bases"], {"source_disagreements": report["warnings"]})
    return {"schema": 1, "name": "D101 audited documentary bread recipe",
            "description": "Initial pending framing and documentary science; no phase approval or field intervention.", "steps": steps}


def prepare(repo: Path, directory: Path, claims_path: Path | None = None,
            table_path: Path | None = None) -> dict:
    directory = directory.absolute()
    if directory.exists():
        raise RecipeError("recipe destination must be new")
    directory.mkdir(parents=True)
    case = directory / "case"
    case.mkdir()
    (directory / "public_keys.json").write_bytes(_render({"schema": 2, "cases": {}}))
    source = repo / "cases/bread_norway"
    files = {
        "source_claims.json": claims_path or repo / "cases/bread_development/source_claims.json",
        "survey_table1.json": table_path or source / "survey_table1.json",
        "source_lca.pdf": source / "source_lca.pdf", "source_survey.pdf": source / "source_survey.pdf",
        "audit_contract.json": auditor.CONTRACT,
    }
    for name, path in files.items():
        (case / name).write_bytes(_raw(path))
    try:
        report = auditor.audit_bread_sources(case / "source_claims.json", case / "survey_table1.json", case)
    except auditor.SourceAuditError as exc:
        (directory / "precondition_rejection.json").write_bytes(_render({"state": "rejected", "reason": str(exc), "ledger_created": False}))
        raise RecipeError(f"source precondition rejected: {exc}") from exc
    (case / "audit_report.json").write_bytes(_render(report))
    pins = {p.name: _pin(_raw(p)) for p in case.iterdir()}
    manifest = build_manifest(report, pins)
    (directory / "manifest.json").write_bytes(_render(manifest))
    binding = {"schema": 1, "study_id": "D101", "actor": ACTOR, "files": pins,
               "code": _code_pins(), "manifest": _pin(_render(manifest)),
               "coverage": {"published_numeric_claims": 17, "audited_archived_survey_rows": 7},
               "approval_policy": "signed", "phase_advances": 0, "human_approvals": 0}
    (directory / "binding.json").write_bytes(_render(binding))
    return validate(directory)


def validate(directory: Path, manifest: dict | None = None) -> dict:
    binding = _json(directory / "binding.json")
    case = directory / "case"
    metadata = {"schema": 1, "study_id": "D101", "actor": ACTOR,
                "coverage": {"published_numeric_claims": 17, "audited_archived_survey_rows": 7},
                "approval_policy": "signed", "phase_advances": 0, "human_approvals": 0}
    if (set(binding) != set(metadata) | {"files", "code", "manifest"}
            or _render({k: binding.get(k) for k in metadata}) != _render(metadata)):
        raise RecipeError("recipe binding identity differs")
    if binding.get("code") != _code_pins():
        raise RecipeError("recipe code differs from prepared snapshot")
    required = {*ARCHIVES.values(), "source_lca.pdf", "source_survey.pdf"}
    if type(binding.get("files")) is not dict or set(binding["files"]) != required:
        raise RecipeError("recipe archive set differs")
    for name, expected in binding["files"].items():
        if _pin(_raw(case / name)) != expected:
            raise RecipeError(f"recipe archived bytes differ: {name}")
    if _raw(case / "audit_contract.json") != _raw(auditor.CONTRACT):
        raise RecipeError("recipe contract differs from reviewed D100 contract")
    try:
        fresh = auditor.audit_bread_sources(case / "source_claims.json", case / "survey_table1.json", case)
    except auditor.SourceAuditError as exc:
        raise RecipeError(f"source precondition rejected: {exc}") from exc
    if _render(fresh) != _raw(case / "audit_report.json"):
        raise RecipeError("persisted audit differs from fresh extraction")
    expected_manifest = build_manifest(fresh, binding["files"])
    actual = _json(directory / "manifest.json") if manifest is None else manifest
    if _render(actual) != _render(expected_manifest) or _pin(_render(actual)) != binding["manifest"]:
        raise RecipeError("publication manifest differs from audited claim bindings")
    ledger = case / "organon.json"
    state = None
    if ledger.exists():
        state = engine.get_state(case)
        project = state["project"]
        if any(project.get(key) != value for key, value in {
            "approval_policy": "signed", "title": TITLE, "domain": DOMAIN,
            "created_by": ACTOR,
        }.items()) or project.get("test_gate_policy", "signed_report") != "signed_report":
            raise RecipeError("checkpoint project differs from signed recipe identity")
        events = read_project(case)["events"]
        if len(events) > len(actual["steps"]):
            raise RecipeError("checkpoint contains unplanned events; explicit recipe revision required")
        for event, step in zip(events, actual["steps"]):
            expected_payload = {"id": step["id"], "kind": step["kind"],
                                "text": step["text"], "data": step["data"],
                                "deps": {ref: 1 for ref in step["refs"]}, "version": 1}
            # Key order is irrelevant to ledger objects; strict JSON types are not.
            if (event["kind"] != "item_put" or event["actor"] != ACTOR
                    or json.dumps(event["payload"], sort_keys=True, allow_nan=False)
                    != json.dumps(expected_payload, sort_keys=True, allow_nan=False)):
                raise RecipeError("checkpoint events differ from recipe prefix; explicit recipe revision required")
        planned = {step["id"]: step for step in actual["steps"]}
        if set(state["items"]) - set(planned):
            raise RecipeError("checkpoint contains unplanned items; explicit recipe revision required")
        for id, item in state["items"].items():
            step = planned[id]
            if (item["version"] != 1 or item["kind"] != step["kind"] or item["text"] != step["text"]
                    or item["data"] != step["data"] or item["deps"] != {ref: 1 for ref in step["refs"]}):
                raise RecipeError(f"checkpoint diverged: {id}; explicit recipe revision required")
    return {"state": "prepared" if state is None else "checkpoint_verified", "coverage": binding["coverage"],
            "manifest_steps": len(actual["steps"]), "ledger_created": state is not None,
            "global_acceptance": "0/5"}


@contextmanager
def sealed_manifest(manifest: dict):
    """Keep the validated publication payload unchanged during CLI admission."""
    fd = os.memfd_create("organon-audited-manifest", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
    try:
        with os.fdopen(os.dup(fd), "wb") as stream:
            stream.write(_render(manifest))
        fcntl.fcntl(fd, getattr(fcntl, "F_ADD_SEALS", 1033), 0x01 | 0x02 | 0x04 | 0x08)
        yield f"/proc/self/fd/{fd}", fd
    finally:
        os.close(fd)


def _cli(executable: Path, *args: str, pass_fds: tuple[int, ...] = ()) -> dict:
    result = subprocess.run([str(executable), *args], capture_output=True, text=True,
                            timeout=60, pass_fds=pass_fds)
    if result.returncode:
        raise RecipeError(f"CLI rejected: {result.stderr.strip()}")
    return json.loads(result.stdout)


async def execute(directory: Path, transport: str = "cli", cli: Path | None = None,
                  mcp: Path | None = None) -> dict:
    directory = directory.absolute()
    manifest = _json(directory / "manifest.json")
    verified = validate(directory, manifest=manifest)
    case = str(directory / "case")
    kwargs = {"path": case, "title": TITLE, "domain": DOMAIN,
              "actor": ACTOR, "approval_policy": "signed"}
    if transport == "cli":
        cli = cli or Path(sys.executable).parent / "organon"
        if not verified["ledger_created"]:
            _cli(cli, "init", case, "--title", kwargs["title"], "--domain", "food", "--actor", ACTOR, "--approval-policy", "signed")
        with sealed_manifest(manifest) as (snapshot, fd):
            result = _cli(cli, "run", case, "--manifest", snapshot, "--actor", ACTOR,
                          pass_fds=(fd,))
    elif transport == "mcp":
        from mcp.client import Client
        from mcp.client.stdio import StdioServerParameters
        mcp = mcp or Path(sys.executable).parent / "organon-mcp"
        params = StdioServerParameters(command=str(mcp), args=[], env={
            "ORGANON_ROOT": str(directory),
            "ORGANON_APPROVERS_FILE": str(directory / "public_keys.json"),
        })
        async with Client(params) as client:
            tools = {tool.name for tool in (await client.list_tools()).tools}
            if not {"init", "run", "status", "gate", "next_task"} <= tools:
                raise RecipeError("MCP discovery missing required recipe tools")
            async def call(name, args):
                response = await client.call_tool(name, args)
                if response.is_error:
                    raise RecipeError(f"MCP rejected {name}")
                return response.structured_content or json.loads(response.content[0].text)
            if not verified["ledger_created"]:
                await call("init", kwargs)
            result = await call("run", {"path": case, "manifest": manifest, "actor": ACTOR})
    else:
        raise RecipeError("recipe transport must be cli or mcp")
    final = validate(directory)
    state = engine.get_state(Path(case)) if final["ledger_created"] else None
    if (not final["ledger_created"] or state["revision"] != len(manifest["steps"])
            or type(result) is not dict or result.get("status") != "waiting"
            or result.get("reason") != "independent_review_required"
            or type(result.get("cursor")) is not int or result["cursor"] != len(manifest["steps"])
            or any(type(result.get(key)) is not int or result[key] < 0 for key in ("applied", "skipped"))
            or result["applied"] + result["skipped"] != len(manifest["steps"])
            or not state["phases"]["frame"]["ready"] or state["phases"]["frame"]["accepted"]):
        raise RecipeError("transport result differs from complete pending recipe checkpoint")
    return {"transport": transport, "result": result, "coverage": verified["coverage"],
            "phase_advances_requested": 0, "human_approvals_requested": 0, "global_acceptance": "0/5"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("directory", type=Path)
    prepare_parser.add_argument("--repo", type=Path, default=ROOT)
    prepare_parser.add_argument("--claims", type=Path)
    prepare_parser.add_argument("--table", type=Path)
    for name in ("status", "run"):
        child = commands.add_parser(name)
        child.add_argument("directory", type=Path)
        if name == "run":
            child.add_argument("--transport", choices=("cli", "mcp"), default="cli")
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            result = prepare(args.repo, args.directory, args.claims, args.table)
        elif args.command == "status":
            result = validate(args.directory)
        else:
            result = asyncio.run(execute(args.directory, args.transport))
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    except (RecipeError, engine.MethodError) as exc:
        print(f"audited recipe rejected: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
