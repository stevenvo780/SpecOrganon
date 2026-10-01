"""Seal local public D112 artifacts after independent review, excluding self receipt."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DOSSIER = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))
import run_managed_team as team  # noqa: E402


def main() -> int:
    target = DOSSIER / "receipt.json"
    if target.exists():
        raise FileExistsError("final receipt must be newly created")
    if not (DOSSIER / "review.md").is_file():
        raise ValueError("independent review must precede final receipt")
    baseline = json.loads((DOSSIER / "baseline_pins.json").read_text())
    for pin in baseline["files"]:
        if hashlib.sha256((ROOT / pin["path"]).read_bytes()).hexdigest() != pin["sha256"]:
            raise ValueError("protected baseline changed")
    freeze = json.loads((DOSSIER / "source_freeze.json").read_text())
    paths = {pin["path"] for pin in baseline["files"] + freeze["files"]}
    paths.update(team._source_closure())
    paths.update({"docs/estado.md", "docs/presupuesto_solicitudes_modelo.md"})
    dossier_files = []
    for path in DOSSIER.rglob("*"):
        relative = path.relative_to(DOSSIER)
        if any(part in ("__pycache__", ".pytest_cache") for part in relative.parts):
            continue
        if path.is_symlink():
            raise ValueError("dossier contains a symlink")
        if path.is_file() and path != target:
            name = path.relative_to(ROOT).as_posix()
            paths.add(name)
            dossier_files.append(name)
    pins = []
    for name in sorted(paths):
        raw = (ROOT / name).read_bytes()
        pins.append({"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    receipt = {"schema": "specorganon.d112.final_local_receipt.v1",
               "classification": "public_cases_synthetic_workflow_fake_provider",
               "source_freeze_commit": freeze["source_freeze_commit"],
               "excluded_self_receipt": target.relative_to(ROOT).as_posix(),
               "dossier_files_without_self": len(dossier_files),
               "external_dependency_files": len(paths) - len(dossier_files),
               "protected_baseline_count": len(baseline["files"]),
               "all_protected_baseline_unchanged": True, "files": pins,
               "formal_cells_executed": 0, "real_provider_requests": 0,
               "runtime_image_authenticated": False, "model_identity_authenticated": False,
               "human_normative_approval": False, "criterion_4_assessed": False}
    with target.open("x") as stream:
        stream.write(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"pinned_files": len(pins), "dossier_files": len(dossier_files),
                      "external_dependencies": len(paths) - len(dossier_files)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
