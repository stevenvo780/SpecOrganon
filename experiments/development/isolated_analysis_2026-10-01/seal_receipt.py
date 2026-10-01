"""Seal D113 local evidence after its frozen gates and independent review."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DOSSIER = Path(__file__).resolve().parent


def checked(pin: dict) -> None:
    raw = (ROOT / pin["path"]).read_bytes()
    if len(raw) != pin["bytes"] or hashlib.sha256(raw).hexdigest() != pin["sha256"]:
        raise ValueError("evidence pin differs from current file: " + pin["path"])


def main() -> int:
    target = DOSSIER / "receipt.json"
    if target.exists() or not (DOSSIER / "review.md").is_file():
        raise ValueError("new receipt requires the independent review first")
    freeze = json.loads((DOSSIER / "source_freeze.json").read_text())
    baseline = json.loads((DOSSIER / "baseline_pins.json").read_text())
    paths = set()
    for pin in freeze["files"] + baseline["files"]:
        checked(pin)
        paths.add(pin["path"])
    for pin in freeze["files"]:
        raw = subprocess.check_output(["git", "show", freeze["source_freeze_commit"] + ":" + pin["path"]], cwd=ROOT)
        if hashlib.sha256(raw).hexdigest() != pin["sha256"]:
            raise ValueError("source pin differs from frozen Git bytes")
    gates = {}
    for label in ("final311", "final312"):
        gate = json.loads((DOSSIER / "integration_checks" / label / "receipt.json").read_text())
        if (gate.get("passed") is not True or gate.get("source_unchanged") is not True
                or any(item["exit_code"] != 0 for item in gate["commands"])):
            raise ValueError("final gate is incomplete or failed")
        for name, pin in gate["sources_after"].items():
            checked({"path": name, **pin})
        gates[label] = {"command_count": len(gate["commands"]),
                        "source_count": len(gate["sources_after"])}
    paths.update({"docs/estado.md", "docs/decisiones.md", "docs/presupuesto_solicitudes_modelo.md",
                  "docs/activacion_validacion.md"})
    dossier_files = []
    for path in DOSSIER.rglob("*"):
        if any(part in {"__pycache__", ".pytest_cache"} for part in path.relative_to(DOSSIER).parts):
            continue
        if path.is_symlink():
            raise ValueError("symlink is not permitted in the evidence dossier")
        if path.is_file() and path != target:
            name = str(path.relative_to(ROOT))
            paths.add(name)
            dossier_files.append(name)
    pins = []
    for name in sorted(paths):
        raw = (ROOT / name).read_bytes()
        pins.append({"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    receipt = {"schema": "specorganon.d113.final_local_receipt.v1",
               "classification": "public_fixture_analysis_fake_model_transport_local_evidence",
               "source_freeze_commit": freeze["source_freeze_commit"], "gates": gates,
               "excluded_self_receipt": str(target.relative_to(ROOT)), "files": pins,
               "dossier_files_without_self": len(dossier_files),
               "external_dependency_files": len(paths) - len(dossier_files),
               "protected_baseline_count": len(baseline["files"]),
               "all_protected_baseline_unchanged": True,
               "formal_cells_executed": 0, "real_provider_requests": 0,
               "runtime_image_authenticated": False, "model_identity_authenticated": False,
               "human_normative_approval": False, "criterion_4_assessed": False}
    with target.open("x") as stream:
        stream.write(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"pinned_files": len(pins), "dossier_files": len(dossier_files),
                      "external_dependency_files": len(paths) - len(dossier_files)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
