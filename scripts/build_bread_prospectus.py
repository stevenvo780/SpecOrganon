"""Prepare a new D102 food intervention prospectus and pending SDD workflow.

No field records, normative approvals, efficacy thresholds or effect estimates
are fabricated. The journal example is a synthetic arithmetic control.
Existing D101 cases and their strict 37-put contract are not extended in place.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import run_audited_bread_recipe as base  # noqa: E402
from specorganon import lot_journal  # noqa: E402

ACTOR = "agent:d102_prospectus_controller"
TITLE = "D102 bread intervention prospectus; unapproved, no field results"


def build_plan(report: dict) -> dict:
    claims = report["claims"]
    shares = {key: Fraction(claims[key]["value"]) for key in (
        "wheat_refined_flour_mass_share", "wheat_whole_flour_mass_share", "wheat_bran_mass_share")}
    if sum(shares.values()) != 100:
        raise base.RecipeError("published wheat fractions do not sum to 100")
    energy = (Fraction(claims["bakery_electricity"]["value"])
              + Fraction(claims["bakery_natural_gas"]["value"]))
    per_kg = energy / (Fraction(claims["piece_mass"]["value"]) / 1000)
    actors = ["agriculture", "mill_workers", "bakery_workers", "transport_workers", "retail",
              "households", "packaging_producers", "coproduct_users", "competent_authorities"]
    dimensions = ["safe_useful_food_consumed", "nutrition_and_acceptance", "net_income_and_cost",
                  "work_and_safety", "energy_water_emissions", "coproduct_destination"]
    options = [
        {"id": "o_control", "name": "Práctica actual", "mechanism": "Comparador contemporáneo documentado, sin reemplazarlo por tasas históricas.",
         "burdens": "Medición y participación también cuestan tiempo; variabilidad de demanda y lotes pendiente."},
        {"id": "o_pack", "name": "Variante de envase/vida útil", "mechanism": "Hipótesis: conservación cambia frescura y descarte; no se presume más consumo útil.",
         "burdens": "Material/envase, energía, trabajo y acceso por actor; riesgos de inocuidad y de desplazar descarte al hogar."},
        {"id": "o_rotation", "name": "Rotación e inventario", "mechanism": "Hipótesis: ajustar producción/rotación reduce excedentes; no se presume utilidad ni ausencia de desabastecimiento.",
         "burdens": "Trabajo, costes y riesgo de transferir faltantes/devoluciones o menor acceso a hogares."},
    ]
    return {
        "schema": 1, "classification": "food_intervention_prospectus_unapproved", "study_id": "D102",
        "scope": "Norwegian commercial bread documented historically; no current linked lots",
        "source_coverage": {"published_numeric_claims": 17, "archived_survey_rows": 7},
        "derived_documentary_quantities": {
            "wheat_outputs_per_normalized_tonne_kg": {k: str(v * 10) for k, v in shares.items()},
            "normalization_input_kg": 1000, "normalization_is_observed_lot": False,
            "bakery_total_energy_per_piece_kwh": str(energy),
            "bakery_total_energy_per_kg": {"numerator": per_kg.numerator, "denominator": per_kg.denominator,
                                          "unit": "kWh/kg bread", "classification": "derived_from_published_piece_values"},
            "source_keys": [*shares, "bakery_electricity", "bakery_natural_gas", "piece_mass"],
            "limitations": "Published fractions and documentary conversion; no measured balance, actual lot, environmental rerun or causal effect.",
        },
        "value_matrix": [{"actor": actor, "dimension": dimension, "status": "pending_actor_consultation",
                          "equivalence_or_margin": None, "competent_approval": None}
                         for actor in actors for dimension in dimensions],
        "options": [{**option, "efficacy_estimate": None, "cost_estimate": None,
                     "selection": "unselected", "evidence_status": "mechanism_hypothesis_not_demonstrated"}
                    for option in options],
        "measurement_protocol": {
            "status": "prospective_draft_not_registered_trial", "population": "Site, SKU, lots and consenting participants not yet identified",
            "operations": ["production", "storage", "transport", "milling", "baking", "retail", "household_consumption"],
            "records": ["pseudonymous_load_ids", "timestamp_and_stage", "actor_and_source_pointer",
                        "inputs_outputs_material_and_mass", "wet_basis_and_dry_fraction_or_missing",
                        "measurement_uncertainty_and_calibration", "storage_time_temperature_and_conditions",
                        "coproducts_water_added_evaporation_and_destinations", "actual_consumption_not_sale_proxy",
                        "safety_nutrition_acceptance", "costs_work_resources_and_harms_by_actor"],
            "comparison": "Current baseline plus contemporaneous comparator; assignment unit, spillovers and analysis remain to be fixed prospectively",
            "sample_size": None, "uncertainty": "Pilot variability, allocation, custody, consumption coverage and missingness not established",
            "primary_value_metric": None, "success_threshold": None, "rejection_threshold": None,
            "human_approved_equivalences": None, "human_approved_harm_margins": None,
        },
        "engineering_obligations": [
            {"id": "r_capture", "objective": "Capture incremental lot operations without inventing experimental arms or periods", "metric": "journal_contract_valid", "unit": "dimensionless", "status": "prototype_available_only"},
            {"id": "r_basis", "objective": "Keep wet mass, dry matter, water and coproducts distinct; missing dry fractions remain pending", "metric": "basis_and_missingness_preserved", "unit": "dimensionless", "status": "prototype_available_only"},
            {"id": "r_safety", "objective": "Competent safety/consent approval and harm coverage before assignment", "metric": "competent_approval_and_harm_coverage", "unit": "dimensionless", "status": "pending_human_and_site_evidence"},
            {"id": "r_service", "objective": "Evaluate safe useful consumption, nutrition, access, costs and displaced harms against baseline", "metric": "safe_useful_consumed_service", "unit": "pending_approved_equivalence", "status": "pending_field_evidence"},
        ],
        "stop_before_assignment_if_missing": ["site_and_participant_permission", "competent_normative_approval",
            "current_linked_baseline", "source_custody_and_calibration", "consumption_observation",
            "assignment_unit_and_comparator", "prospective_analysis_sample_size_thresholds_and_harm_margins"],
        "source_disagreements": report["warnings"],
        "survey_bins_instrument_confirmed": False, "slices_to_kg_conversion": None,
        "historical_waste_rates_are_sequential_lot_measurements": False,
        "norms_approved": False, "field_intervention": False, "execution_ready": False,
        "effect_estimate": None, "Q": None, "global_acceptance": "0/5",
    }


def example_journal(plan: dict) -> dict:
    """Normalize published milling shares; baking quantities are invented controls."""
    def load(id, kind, mass, material, fraction=None, unit="kg"):
        return {"load_id": id, "material_id": material, "kind": kind,
                "mass": {"value": mass, "unit": unit, "uncertainty": 0},
                "basis": "wet", "dry_fraction": fraction}
    def event(id, hour, inputs, outputs):
        at = f"2026-09-30T{hour}:00:00Z"
        return {"id": id, "stage": "Synthetic " + id, "stage_role": "transformation", "actor": "agent:synthetic_example",
                "at_utc": at, "inputs": inputs, "outputs": outputs, "balance_tolerance_kg": 0,
                "source": {"source_id": "synthetic_example_not_field_record", "locator": id,
                           "observed_at_utc": at, "method": "Synthetic arithmetic; no operation observed",
                           "record_sha256": base._pin(base._render(plan))["sha256"]}}
    masses = plan["derived_documentary_quantities"]["wheat_outputs_per_normalized_tonne_kg"]
    flour = load("normalized_flour", "product", int(masses["wheat_refined_flour_mass_share"]), "flour")
    return {"schema": 1, "classification": "lot_journal_declared_only", "journal_id": "D102_synthetic_control",
            "events": [event("milling", "08", [load("normalized_wheat", "feed", 1000, "wheat")], [
                flour, load("normalized_whole", "product", int(masses["wheat_whole_flour_mass_share"]), "whole_flour"),
                load("normalized_bran", "coproduct", int(masses["wheat_bran_mass_share"]), "bran")]),
                       event("baking", "09", [copy.deepcopy(flour), load("invented_ingredient", "ingredient", 10000, "ingredient", unit="g"),
                            load("invented_water", "water_addition", 0.2, "water", 0, "t")], [
                            load("invented_bread", "product", 761, "bread"), load("invented_evaporation", "evaporation", 120, "water", 0)])]}


def build_manifest(original: dict, plan: dict) -> dict:
    manifest = copy.deepcopy(original)
    manifest["name"] = "D102 prospective food comparison and SDD, pending human decisions"
    manifest["description"] = "New variant, not an extension/reapproval of a D101 ledger. No field outcomes."
    # Reinsert the uncertainty after its synthesis, satisfying the real explain dependency.
    uncertainty = manifest["steps"].pop()
    if uncertainty["id"] != "u_sources":
        raise base.RecipeError("D101 documentary manifest order changed")
    steps = manifest["steps"]
    def put(id, kind, text, refs, data=None):
        steps.append({"op": "put", "id": id, "kind": kind, "text": text, "refs": refs, "data": data or {}})
    put("sy_documentary", "synthesis", "Los pasajes auditados y balances normalizados sólo sustentan diseño de captura. Encuesta no identifica este pan; ni frescura ni tasas históricas miden eficacia de una intervención actual.", ["p_refined", "inf_bases", "e_piece_mass", "e_bundle_audit"], {"classification": "documentary_synthesis_not_field_effect", "source_disagreements": plan["source_disagreements"]})
    uncertainty["refs"].append("sy_documentary")
    steps.append(uncertainty)
    put("n_service", "norm", "Propuesta pendiente: acordar servicio alimentario inocuo y útil, nutrición, aceptación y acceso; pesos y equivalencias no fijados.", ["p_refined", "a_chain"], {"approved_equivalences": None})
    put("n_permission", "norm", "Propuesta pendiente: permisos, consentimiento, confidencialidad y revisión competente antes de recoger o asignar participantes/lotes.", ["p_refined", "a_chain"])
    put("q_lots", "question", "¿Qué lotes, entradas/salidas y consumo real permiten observar valor y perjuicios por actor sin usar venta, masa o frescura como sustitutos automáticos?", ["p_refined", "s_historical"])
    put("h_material", "hypothesis", "Envase y rotación pueden modificar conservación, disponibilidad y costes; signo y magnitud del consumo útil y perjuicios permanecen desconocidos.", ["q_lots"])
    put("pr_lots", "protocol", "Borrador prospectivo para captura enlazada de cargas y posterior comparador; no estudio de campo iniciado.", ["q_lots", "h_material", "n_permission"], {key: plan["measurement_protocol"][key] for key in ("population", "comparison", "uncertainty")} | {"method": plan["measurement_protocol"]["records"]})
    for option in plan["options"]:
        put(option["id"], "option", option["name"] + ": " + option["mechanism"], ["sy_documentary", "n_harm", "n_service"], option)
    put("cmp_material", "comparison", "Tres alternativas sin ranking: costes, consumo útil, inocuidad y perjuicios no medidos. Cambios materiales y organizativos; ninguna variante se declara mejor.", [o["id"] for o in plan["options"]], {"selected": None, "efficacy": None, "costs": None})
    put("risk_displaced", "risk", "Puede aumentar envase, trabajo, riesgo o descarte doméstico, o reducir acceso. Márgenes y condiciones competentes faltan; detener antes de asignar.", ["o_pack", "o_rotation", "n_harm"], {"stop_before_assignment_if_missing": plan["stop_before_assignment_if_missing"]})
    put("d_pending", "decision", "Propuesta sin aprobar: desarrollar captura documental, mantener intervención no seleccionada y no desplegar hasta cumplir permisos, normas, baseline y diseño previo.", ["cmp_material", "n_harm", "n_service", "n_permission", "e_bundle_audit"], {"intervention_selected": None, "normative_approval": None})
    for obligation in plan["engineering_obligations"]:
        id = obligation["id"]
        put(id, "requirement", obligation["objective"], ["p_refined", "n_harm", "n_service", "n_permission", "d_pending", "e_bundle_audit"], obligation)
        put("i_" + id, "indicator", "Medida propuesta sin medición de campo: " + obligation["metric"], [id, "pr_lots"], {"metric": obligation["metric"], "unit": obligation["unit"], "field_measurement_available": False})
        put("c_" + id, "criterion", "Criterio pendiente de definición competente antes de resultados del piloto; no derivar umbral de porcentajes históricos.", [id, "i_" + id], {"metric": obligation["metric"], "threshold": None, "reject": "Detener sin aprobación o datos necesarios; condición cuantitativa no registrada", "status": "pending_not_approved"})
    put("impl_capture", "implementation", "Prototipo de auditor incremental lot_journal y operaciones CLI/MCP; sólo consistencia declarada, no intervención material.", ["r_capture", "r_basis"], {"classification": "technical_support_prototype_not_field_intervention"})
    put("t_capture", "test", "El test del caso y aprobación quedan pendientes; las pruebas técnicas de biblioteca tienen recibos separados, sin firmar este ítem.", ["impl_capture", "c_r_capture", "c_r_basis"], {"passed": False, "command": "not executed as a signed case test"})
    put("as_field_pending", "assessment", "Resolución de campo no demostrada: sin lote observado, baseline, resultado, autorización, umbral o atribución.", ["risk_displaced", "r_service"], {"verdict": "no_demostrado", "claim_scope": "field", "uncertainty": "Current linked baseline and effects absent", "adverse_effects": {"status": "missing"}, "cost": {"status": "missing"}})
    return manifest


def prepare(directory: Path) -> dict:
    directory = directory.absolute()
    base.prepare(ROOT, directory)
    original_binding = base._json(directory / "binding.json")
    original_manifest = base._json(directory / "manifest.json")
    report = base._json(directory / "case/audit_report.json")
    plan = build_plan(report)
    example = example_journal(plan)
    observed = lot_journal.audit_lot_journal(example)
    manifest = build_manifest(original_manifest, plan)
    for name, value in (("prospectus.json", plan), ("example_journal.json", example),
                        ("example_audit.json", observed), ("prospectus_manifest.json", manifest)):
        (directory / name).write_bytes(base._render(value))
    # Re-audit after the prospectus is built, while the D101 packet still has
    # its original names. Never bless changed source bytes with a new pin.
    base.validate(directory)
    archive_pins = {name: base._pin(base._raw(directory / "case" / name))
                    for name in original_binding["files"]}
    if archive_pins != original_binding["files"]:
        raise base.RecipeError("documentary source packet changed during prospectus preparation")
    (directory / "binding.json").rename(directory / "documentary_binding.json")
    (directory / "manifest.json").rename(directory / "documentary_manifest.json")
    (directory / "prospectus_manifest.json").rename(directory / "manifest.json")
    pins = {"case/" + name: pin for name, pin in archive_pins.items()}
    for name in ("documentary_binding.json", "documentary_manifest.json", "public_keys.json",
                 "prospectus.json", "example_journal.json", "example_audit.json", "manifest.json"):
        pins[name] = base._pin(base._raw(directory / name))
    binding = {"schema": 1, "study_id": "D102", "variant_of": "D101 documentary preparation, new case only",
               "actor": ACTOR, "title": TITLE, "files": pins,
               "code": {**base._code_pins(), "prospectus": base._pin(Path(__file__).read_bytes()),
                        "lot_journal": base._pin(Path(lot_journal.__file__).read_bytes())},
               "phase_advances": 0, "human_approvals": 0, "global_acceptance": "0/5"}
    (directory / "binding.json").write_bytes(base._render(binding))
    return {"state": "prepared", "manifest_steps": len(manifest["steps"]), "ledger_created": False,
            "example_classification": "synthetic_arithmetic_not_observed_lot", "execution_ready": False, "global_acceptance": "0/5"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.directory), ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
