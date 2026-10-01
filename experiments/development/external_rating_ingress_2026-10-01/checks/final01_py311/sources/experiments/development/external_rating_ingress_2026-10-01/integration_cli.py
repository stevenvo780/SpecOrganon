"""Finite real CLI controls on synthetic originals; no human scores supplied."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

DOSSIER = Path(__file__).resolve().parent
ROOT = DOSSIER.parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import development_rating_ingress as ingress  # noqa: E402

ENV = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "TZ": "UTC", "PYTHONDONTWRITEBYTECODE": "1"}
SENTINEL = "PUBLIC-SYNTHETIC-SENTINEL"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def snapshot(root):
    rows = {}
    for path in sorted(root.rglob("*")):
        info = path.lstat()
        assert stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)
        row = {"mode": stat.S_IMODE(info.st_mode), "identity": [info.st_dev, info.st_ino, info.st_uid,
               info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns]}
        if path.is_file():
            raw = path.read_bytes()
            row.update(bytes=len(raw), sha256=sha(raw))
        rows[path.relative_to(root).as_posix()] = row
    return rows


def run_controls(output):
    output.mkdir(parents=True)
    original_root = Path(tempfile.mkdtemp(prefix="specorganon-D124-cli-originals-"))
    delivery = b"PUBLIC SYNTHETIC DELIVERY; NOT A HUMAN OR FIELD CASE\n"
    base = {"schema": 1, "classification": ingress.CLASSIFICATION,
            "blinded_delivery_sha256": sha(delivery), "rubric_sha256": ingress.RUBRIC_SHA256,
            "delivery_contract_sha256": ingress.DELIVERY_CONTRACT_SHA256,
            "reviewer_reference_sha256": None, "scores": dict.fromkeys(ingress.DIMENSIONS, 20),
            "declarations": dict.fromkeys(ingress.DECLARATION_FIELDS, True),
            "critical_incidents": [{"incident_id": SENTINEL, "type": "false_test_result",
                                    "evidence_sha256": sha(b"PUBLIC SYNTHETIC EVIDENCE"),
                                    "description": SENTINEL}]}
    unknown = copy.deepcopy(base)
    unknown.update(scores=dict.fromkeys(ingress.DIMENSIONS, 9), critical_incidents=[],
                   declarations=dict.fromkeys(ingress.DECLARATION_FIELDS, None))
    pretty = json.dumps(base, indent=2).encode() + b"\n"
    compact = json.dumps(base, separators=(",", ":")).encode()
    controls = [("high_critical_pretty", pretty, 0), ("high_critical_compact", compact, 0),
                ("unknown_declarations", json.dumps(unknown).encode(), 0),
                ("wrong_digest", pretty, 2), ("public_mode", pretty, 2),
                ("duplicate_field", b'{"schema":1,"schema":1}', 2), ("unknown_argument", pretty, 2)]
    records = []
    for index, (name, raw, expected) in enumerate(controls):
        case = original_root / name
        case.mkdir(mode=0o700)
        rating_path, delivery_path = case / "rating.json", case / "blinded-delivery.bin"
        for path, content in ((rating_path, raw), (delivery_path, delivery)):
            path.write_bytes(content)
            path.chmod(0o600)
        if name == "public_mode":
            rating_path.chmod(0o644)
        command = [sys.executable, "-I", "-B", str(ROOT / "scripts/read_development_rating.py"),
                   "--rating", str(rating_path), "--rating-sha256", "0" * 64 if name == "wrong_digest" else sha(raw),
                   "--blinded-delivery", str(delivery_path), "--blinded-delivery-sha256", sha(delivery)]
        if name == "unknown_argument":
            command += ["--" + SENTINEL, SENTINEL]
        before = snapshot(case)
        result = subprocess.run(command, cwd=ROOT, env=ENV, capture_output=True, timeout=30)
        (output / f"{index}.stdout").write_bytes(result.stdout)
        (output / f"{index}.stderr").write_bytes(result.stderr)
        assert result.returncode == expected and result.stderr == b""
        assert SENTINEL.encode() not in result.stdout + result.stderr
        assert before == snapshot(case)
        report = json.loads(result.stdout)
        assert report["Q_demonstrated"] is False and report["quality_verified"] is False
        assert report["acceptance_assessed"] is False
        if expected == 0:
            assert all(report[key] is False for key in (
                "human_judgment_verified", "reviewer_identity_verified", "reviewer_independence_verified",
                "blinding_verified", "chronology_verified", "custody_verified", "incident_evidence_verified",
                "critical_review_complete_verified", "formal_cell_executed", "confirmatory_rating_rules_applied"))
            assert report["binding"]["raw_rating_sha256"] == sha(raw)
            assert report["reader"] == {"classification": "readonly_local_original_rating_reader",
                                       "original_files_rechecked": True, "originals_written": False,
                                       "fixed_public_byte_pins_verified": True}
            if name.startswith("high_"):
                assert report["declared_component_total"] == 100 and report["declared_incident_count"] == 1
                assert report["has_declared_critical_incidents"] is True
            else:
                assert report["declared_component_total"] == 45 and report["declared_incident_count"] == 0
                assert all(value is None for value in report["declarations"].values())
        else:
            assert report == {"error": "rating_arguments_or_originals_rejected", "Q_demonstrated": False,
                              "quality_verified": False, "acceptance_assessed": False}
        records.append({"name": name, "argv": command, "expected_exit": expected, "exit_code": result.returncode,
                        "stdout_sha256": sha(result.stdout), "stderr_sha256": sha(result.stderr),
                        "original_files_unchanged": True, "raw_rating_sha256": sha(raw), "report": report})
    assert sha(pretty) != sha(compact) and json.loads(pretty) == json.loads(compact)
    value = {"classification": "synthetic_real_CLI_only_not_human_judgment", "python": sys.executable,
             "original_root": str(original_root), "commands": records, "actual_cli_calls": len(records),
             "accepted_controls": 3, "rejected_controls": 4, "all_expected": True,
             "equal_values_different_original_byte_hashes": True, "actual_human_evaluations": 0,
             "formal_cells_executed": 0, "paid_api_requests": 0, "key_environment_inherited": False}
    (output / "integration_result.json").write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    return value


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run_controls(args.output)
    print(json.dumps({"all_expected": report["all_expected"], "actual_cli_calls": report["actual_cli_calls"],
                      "original_root": report["original_root"]}))
