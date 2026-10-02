"""Prepare actual local development projects; leave phase reviews to real agents.

Run with an existing owner mandate. This helper records that mandate as a
local declaration, executes bounded local checks, and creates draft artifacts.
It never manufactures a review or advances a phase. Use the native-agent skill
and the emitted manifest to finish and resume each case.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from specorganon import engine
from specorganon.runner import run_manifest


ROOT = Path(__file__).resolve().parents[1]
AUTHOR = "agent:mvp-builder"
OWNER = "human:owner"


def _write(path: Path, value: Any) -> None:
    encoded = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if path.exists():
        raise ValueError(f"refusing to replace {path}")
    path.write_text(encoded, encoding="utf-8")


def _check(argv: list[str], output: Path, timeout: int = 120) -> dict[str, Any]:
    process = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=timeout, check=False)
    output.mkdir()
    (output / "stdout.txt").write_bytes(process.stdout)
    (output / "stderr.txt").write_bytes(process.stderr)
    data: dict[str, Any] = {
        "passed": process.returncode == 0,
        "argv": argv,
        "command": shlex.join(argv),
        "receipt": {
            "argv": argv, "exit_code": process.returncode, "timed_out": False,
            "stdout_sha256": hashlib.sha256(process.stdout).hexdigest(),
            "stderr_sha256": hashlib.sha256(process.stderr).hexdigest(),
        },
    }
    data["receipt"]["result_sha256"] = engine.local_test_result_sha256(data)
    _write(output / "receipt.json", data)
    if process.returncode:
        raise ValueError(f"local check failed; original streams retained at {output}")
    return data


def _project(directory: Path, mode: str, mandate: str, date: str, baseline: dict) -> None:
    case = directory / "case"
    title = "Entrada y entrega local de SpecOrganon" if mode == "entry" else "Reproducción local del análisis escolar"
    engine.create_case(case, title, "desarrollo de software" if mode == "entry" else "análisis reproducible", OWNER,
                       approval_policy="local")
    manifest: dict[str, Any] = {"schema": 1, "steps": []}

    def put(id: str, kind: str, text: str, refs: list[str], data: dict | None = None) -> None:
        engine.put_item(case, id, kind, text, refs, data or {}, AUTHOR)
        manifest["steps"].append({"op": "put", "id": id, "kind": kind, "text": text,
                                  "refs": refs, "data": data or {}})

    def phase(id: str) -> None:
        manifest["steps"].append({"op": "advance", "phase": id})

    problem = ("La entrada del toolkit requiere configurar revisiones externas antes de aceptar fases; "
               "necesitamos un recorrido local con agentes y una entrega legible.") if mode == "entry" else (
               "Necesitamos comprobar que un agente puede reproducir el análisis del XLSX escolar disponible "
               "sin cambiar la fuente, el plan o los resultados históricos.")
    put("p1", "problem", problem, [])
    put("a1", "actor", "El dueño fija el propósito; un agente implementa y otro revisa los resultados locales.", ["p1"])
    put("b1", "boundary", "Workspace de desarrollo y archivos disponibles. Sin API adicional ni acciones de campo.", ["p1"])
    phase("frame")
    put("c1", "concept", "Autonomía es ejecutar dentro del encargo; reproducibilidad es poder repetir y cotejar resultados.", ["p1"])
    put("s1", "assumption", "Las herramientas y archivos locales permiten comprobar este proyecto en el entorno actual.", ["p1"])
    put("f1", "frame_option", "Encuadrar el problema como falta de garantías externas en cada transición.", ["p1"])
    put("f2", "frame_option", "Encuadrar el problema como una experiencia local usable con confianza declarada y evidencia verificable.", ["p1"])
    put("n1", "norm", "Aplicar el mandato del dueño al MVP: usar recursos presentes, preservar historia, "
        "delegar decisiones técnicas reversibles y mantener explícitos los límites de las conclusiones.", ["p1", "a1"],
        {"authorization_scope": mandate, "origin": "existing_owner_mandate", "identity_authenticated": False})
    engine.approve(case, "n1", "Registro del mandato existente del dueño para el MVP local; identidad declarada.", OWNER)
    phase("critique")
    put("q1", "question", "¿Podemos producir y revisar una entrega local reproducible con los recursos presentes?", ["p1"])
    put("h1", "hypothesis", "Un recorrido local explícito permite ejecutar y revisar el proyecto sin un registro de firmas externo." if mode == "entry" else
        "El analizador existente reproduce exactamente el JSON de referencia al conservar fuente y plan fijados.", ["q1"])
    put("pr1", "protocol", "Registrar criterios, ejecutar comandos reales, conservar streams y cotejar resultados antes de evaluar.", ["q1", "h1"], {
        "population": "Este proyecto de desarrollo expuesto, en el entorno actual",
        "method": "Ejecución local, hashes de originales, cotejo objetivo y revisión nativa separada",
        "comparison": "Entrada firmada sin registro" if mode == "entry" else "JSON histórico del análisis escolar",
        "uncertainty": "Un entorno y un proyecto; sin causalidad de campo ni comparación confirmatoria",
    })
    if mode == "entry":
        metric, unit, threshold = "accepted_phases", "phase", 9
        evidence = {"source": str(directory.parent / "signed_baseline.json"), "locator": "accepted_phases",
                    "value": baseline["accepted_phases"], "scope": "signed entry without external registry"}
    else:
        metric, unit, threshold = "exact_reproduction", "match", 1
        reference = ROOT / "experiments/development/school_waste_2026-09-26.json"
        evidence = {"source": str(reference),
                    "locator": "SHA256 " + hashlib.sha256(reference.read_bytes()).hexdigest(),
                    "scope": "reference available; reproduction not yet measured"}
    evidence.update({"origin": "observed", "date": date, "method": "Read actual local files and case state",
                     "metric_key": metric, "unit": unit})
    put("e0", "evidence", "Material local disponible y situación anterior al recorrido de este proyecto.", ["pr1"], evidence)
    put("i1", "indicator", "Contar fases aceptadas del recorrido local." if mode == "entry" else "Coincidencia exacta de la reproducción con el resultado histórico.",
        ["p1", "n1", "e0"], {"metric": metric, "unit": unit})
    phase("study")
    put("inf1", "inference", "La entrada firmada conserva su bloqueo si no hay registro; el modo local declara otra confianza." if mode == "entry" else
        "La referencia disponible permite fijar antes de ejecutar un criterio de coincidencia exacta; la reproducción aún debe medirse.", ["e0", "h1"])
    phase("observe")
    put("syn1", "synthesis", "Este proyecto necesita mediciones locales y revisión separada; no necesita un ensayo pagado para empezar.", ["inf1", "e0"])
    put("u1", "uncertainty", "La ejecución local no autentica custodios, personas ni mejoras causales fuera del software observado.", ["syn1"])
    phase("explain")
    put("o1", "option", "Configurar firmas externas para todas las revisiones y reportes." if mode == "entry" else
        "Recalcular manualmente en una hoja de trabajo nueva, conservando las reglas del plan.", ["syn1", "n1"])
    put("o2", "option", "Usar un modo local explícito, agentes separados y comprobaciones reales, preservando el modo firmado." if mode == "entry" else
        "Reutilizar el analizador con hashes fijados y cotejar los bytes de salida contra la referencia.", ["syn1", "n1"])
    put("cmp1", "comparison", "La primera opción aporta control de claves externo; la segunda permite operar en el workspace "
        "de confianza con menor configuración inicial y sin afirmar autenticación." if mode == "entry" else
        "La reproducción manual requiere verificar transcripción y redondeo; el analizador existente conserva reglas versionadas "
        "y permite cotejar salida exacta con las herramientas presentes. No se midió ahorro de tiempo.", ["o1", "o2"])
    put("risk1", "risk", "Una etiqueta o un recibo declarados pueden ser falsos; conservar streams y revisar las fuentes; "
        "no extrapolar el resultado local a campo o superioridad metodológica.", ["o2"])
    phase("compare")
    put("d1", "decision", "Elegir la ruta local para este proyecto, dentro de la delegación técnica del dueño. "
        "El dueño no seleccionó personalmente esta arquitectura." if mode == "entry" else
        "Reutilizar el analizador con pines y cotejo exacto, dentro de la delegación técnica del dueño.", ["cmp1", "n1", "e0"])
    engine.approve(case, "d1", "El mandato existente delega la elección técnica reversible dentro del MVP local.", OWNER)
    put("req1", "requirement", "Conservar compuertas y trazabilidad, ejecutar una prueba real y producir un informe reproducible.", ["d1"])
    put("crit1", "criterion", "Completar las nueve fases con revisión real." if mode == "entry" else "Reproducir exactamente el JSON existente sin modificar originales.",
        ["req1", "i1"], {"metric": metric, "unit": unit,
         "threshold": {"operator": ">=", "statistic": "estimate", "value": threshold},
         "reject": f"No cerrar si el resultado es menor que {threshold} o hay prueba fallida",
         "reject_test": {"operator": "<", "statistic": "estimate", "value": threshold}})
    phase("specify")
    put("impl1", "implementation", "Política local, informe CLI/MCP y entrada de agente." if mode == "entry" else "Analizador escolar existente, con fuente y plan fijados por hashes.",
        ["req1"], {"paths": ["src/specorganon/report.py", ".agents/skills/specorganon/SKILL.md"] if mode == "entry" else ["scripts/analyze_school_waste.py"]})
    if mode == "entry":
        argv = [sys.executable, "-m", "pytest", "-q", "tests/test_local_workflow.py", "tests/test_local_interfaces.py", "tests/test_case_report.py"]
        check = _check(argv, directory / "execution")
        measured = 0  # Actual reviews and phase advances have not happened yet.
    else:
        original = ROOT / "experiments/development/school_waste_2026-09-26.json"
        output = directory / "school_waste_reproduced.json"
        argv = [sys.executable, "scripts/analyze_school_waste.py", "--output", str(output)]
        check = _check(argv, directory / "execution")
        measured = int(output.read_bytes() == original.read_bytes())
        if measured != 1:
            raise ValueError("school reproduction differs; preserve the output for investigation")
        _write(directory / "source_checks.json", {
            "source_sha256": hashlib.sha256((ROOT / "cases/school_waste/source.xlsx").read_bytes()).hexdigest(),
            "plan_sha256": hashlib.sha256((ROOT / "docs/plan_escuela_residuos.md").read_bytes()).hexdigest(),
            "historical_sha256": hashlib.sha256(original.read_bytes()).hexdigest(),
            "reproduced_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "byte_equal": True,
        })
    put("t1", "test", "Ejecución real conservada en execution/; recibo local no autenticado externamente.", ["impl1", "crit1"], check)
    phase("build")
    put("base1", "baseline", "Estado local previo o comparador histórico disponible.", ["crit1"], {
        "origin": "technical", "source": evidence["source"], "date": date, "metric": metric, "unit": unit,
        "value": 0 if mode == "entry" else 1,
        "meaning": "Fases aceptadas medidas en control firmado" if mode == "entry" else
        "Referencia fijada del cotejo exacto, cuyo objetivo es coincidencia=1; no es una reproducción fallida anterior"})
    put("res1", "result", "Medición del proyecto en el momento de preparar el expediente; las revisiones siguen pendientes." if mode == "entry" else "La reproducción actual coincide byte por byte con el JSON histórico.",
        ["base1", "crit1", "t1"], {"origin": "technical", "source": str(directory / "execution"), "date": date,
         "effect": {"metric": metric, "unit": unit, "estimate": measured, "interval": [measured, measured]}})
    put("ass1", "assessment", "Completitud del recorrido pendiente de revisión real; actualizar tras observarla." if mode == "entry" else "Reproducción técnica exacta; las diferencias escolares siguen siendo descriptivas, sin atribución causal.",
        ["res1", "risk1"], {"verdict": "no_demostrado" if mode == "entry" else "cumplido", "claim_scope": "technical",
         "uncertainty": "Conteo o coincidencia exactos en esta ejecución; sin intervalo estadístico poblacional",
         "adverse_effects": "Originales preservados; ninguna intervención externa",
         "cost": "Agentes y herramientas presentes; sin API adicional. Consumo total no medido."})
    phase("validate")
    _write(directory / "workflow.json", manifest)
    first = run_manifest(case, manifest, AUTHOR)
    assert first["status"] == "waiting" and first["reason"] == "independent_review_required"
    _write(directory / "prepared.json", {"status": first["status"], "reason": first["reason"],
                                        "revision": engine.get_state(case)["revision"], "next_phase": first["next"]["phase"]})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New directory for draft projects and measured streams")
    parser.add_argument("--owner-mandate", required=True, help="Already authorized local scope; never invented consent")
    args = parser.parse_args()
    if not args.owner_mandate.strip():
        parser.error("owner mandate must be nonempty")
    destination = args.output.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    date = datetime.now(timezone.utc).date().isoformat()
    baseline_case = destination / "signed_baseline"
    engine.create_case(baseline_case, "Control de entrada firmada", "desarrollo", OWNER)
    for id, kind, refs in (("p1", "problem", []), ("a1", "actor", ["p1"]), ("b1", "boundary", ["p1"])):
        engine.put_item(baseline_case, id, kind, "Control real de configuración de la entrada", refs, {}, AUTHOR)
    baseline_state = engine.get_state(baseline_case)
    baseline = {"approval_policy": "signed", "accepted_phases": sum(phase["accepted"] for phase in baseline_state["phases"].values()),
                "review_trust": baseline_state["phase_review_trust"], "gate": engine.gate(baseline_case, "frame")}
    _write(destination / "signed_baseline.json", baseline)
    for mode in ("entry", "school"):
        directory = destination / mode
        directory.mkdir()
        _project(directory, mode, args.owner_mandate, date, baseline)
    print(json.dumps({"prepared": str(destination), "review_required": True,
                      "cases": [str(destination / mode / "case") for mode in ("entry", "school")]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
