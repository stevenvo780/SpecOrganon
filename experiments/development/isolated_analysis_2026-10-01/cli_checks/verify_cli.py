"""Read retained public D113 CLI artifacts; never execute prepared workloads."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
ORIGINALS = {
    "D-F": {
        "task.md": ("cases/bread_development/task.md", "ab73075db2b4ee8c5e58dfc873ef14b75276dbcc0ba7afc9685c5b72b72add51"),
        "source_claims.json": ("cases/bread_development/source_claims.json", "63ce5419981c0a3f7d7ba83218cac2dbb528f061b313cfdf4655400ac2e86abc"),
        "source_manifest.json": ("cases/bread_development/source_manifest.json", "83bdf5e7bc584971ca2446cf0fe6bd83dd4b9ea624a433fc54c5e5b3f89c4f3a"),
        "source_lca.pdf": ("cases/bread_norway/source_lca.pdf", "9d64c0538b76ebaa19af86fb7ec231243cb5e1272316105ad979cfb9b6de3a32"),
        "source_survey.pdf": ("cases/bread_norway/source_survey.pdf", "61b3b63cc7b5748138335fa2eaebde2f4ab0e454750e4592582fb80a5043dcee"),
        "survey_table1.json": ("cases/bread_norway/survey_table1.json", "50361b4803226a6a387fb39f0289c0e708679f348b5081ccb0034242155a064f"),
    },
    "D-E": {
        "task.md": ("cases/building_energy/task.md", "f6fed29bc6ce18631cff30710b25f30b9662e04f889f336cccda2869f0789b64"),
        "source_manifest.json": ("cases/building_energy/source_manifest.json", "0e18340d130c495201e68c1c869bc2c6f49b35663176040aebb0d0d7d7bd1ee1"),
        "sample_first_complete_week.csv": ("cases/building_energy/sample_first_complete_week.csv", "c7f66ffaadc4e38375a7edf03091bae4fc861880510867903487eec83f05e6ba"),
    },
}
FULL_TEXT_PINS = {
    "source_lca.txt": "e65be3ae44b90aa7a78eabde032d874d97897db0ba458e8015e7c8f6d8c10582",
    "source_survey.txt": "1ee82f5fe6c51981b640995d9ddcaebd1077cf0315f45744f5ffdd1981b514f3",
}


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_bytes())


def verify(version: str) -> dict:
    runtime = load(OUT / f"runtime_{version}.json")
    bundle, prepared = Path(runtime["bundle"]), Path(runtime["prepared"])
    parent = Path(runtime["parent"])
    for path in (parent, bundle, prepared, prepared / "managed"):
        assert path.stat().st_uid == os.getuid()
        assert stat.S_IMODE(path.stat().st_mode) == 0o700
    schedule = load(bundle / "schedule.json")
    metadata = load(bundle / "preparation.json")
    result = load(OUT / f"{version}_prepare/stdout")
    run = load(prepared / "managed/run.json")
    context = load(prepared / "managed/context/run.json")
    plan = load(prepared / "managed/plan.json")
    policy = load(bundle / "assets/tool_policy")
    assert result["state"] == context["state"] == "prepared"
    assert context["revision"] == context["cursor"] == 0
    assert context["active_seconds"] == context["paused_seconds"] == 0
    assert result["remaining_active_seconds"] == 120
    assert result["model_requests_completed"] == result["tool_calls_completed"] == 0
    assert run["segments_completed"] == 0
    assert metadata["prepared_cell_count"] == schedule["run_count"] == 12
    assert schedule["block_count"] == 4
    assert schedule["per_run_limits"] == {"measured_tokens": 1000, "active_seconds": 120, "tool_calls": 64}
    assert schedule["max_model_requests"] == 128
    assert metadata["analysis_profile"] == "read_only_v1"
    assert metadata["formal_cells_executed"] == metadata["real_provider_requests"] == 0
    assert metadata["execution_authorized"] is False
    assert result["budget"]["request_count"] == result["budget"]["committed_tokens"] == 0
    assert result["budget"]["committed_cost_micro_usd"] == 0
    assert result["budget"]["blocked"] is False
    for name in ("requests", "responses", "receipts", "tool_reservations", "tool_receipts", "histories", "artifacts"):
        assert not list((prepared / "managed" / name).iterdir())
    assert not list((prepared / "managed/tool_session/calls").iterdir())
    assert load(prepared / "managed/ledger/ledger.json")["requests"] == {}
    assert load(prepared / "preparation.json")["formal_cell_executed"] is False
    expected = {"development_method": ("method", "workspace"),
                "development_analysis": ("analysis", "analysis_readonly")}
    assert {item["name"] for item in plan["functions"]} == set(expected)
    bindings = run["tool_binding"]["functions"]
    assert set(bindings) == set(expected)
    assert policy["schema"] == 2
    shebangs = {}
    for name, (tool_id, profile) in expected.items():
        binding = bindings[name]
        entry = next(item for item in policy["generic_tools"] if item["id"] == tool_id)
        assert binding["tool_id"] == tool_id
        assert binding["execution_profile"] == entry["profile"] == profile
        raw = Path(binding["executable"]).read_bytes()
        assert sha(raw) == binding["executable_sha256"] == entry["executable_sha256"]
        shebang = raw.splitlines()[0].decode()
        assert shebang == "#!" + runtime["python"]
        shebangs[name] = {"shebang": shebang, "sha256": sha(raw), "profile": profile}
    originals_checked = []
    for case_id, files in ORIGINALS.items():
        capsule = bundle / "assets" / case_id
        with zipfile.ZipFile(bundle / "assets" / f"{case_id}.zip") as package:
            for name, (source_path, expected_sha) in files.items():
                original = (ROOT / source_path).read_bytes()
                assert sha(original) == expected_sha
                assert (capsule / name).read_bytes() == package.read(name) == original
                if case_id == "D-F":
                    assert (prepared / "stage/case" / name).read_bytes() == original
                originals_checked.append({"case_id": case_id, "name": name, "sha256": expected_sha})
            manifest = load(capsule / "case.json")
            assert {item["path"] for item in manifest["files"]} == set(package.namelist()) - {"case.json"}
            for item in manifest["files"]:
                raw = (capsule / item["path"]).read_bytes()
                assert len(raw) == item["bytes"] and sha(raw) == item["sha256"]
                assert package.read(item["path"]) == raw
    extraction = bundle / "assets/text_extracts"
    manifest = load(extraction / "text_extract_manifest.json")
    assert manifest["no_analysis_answers_added"] is True
    pages_checked = 0
    records = [{"path": "text_extract_manifest.json",
                "sha256": sha((extraction / "text_extract_manifest.json").read_bytes())}]
    for doc in manifest["documents"]:
        full = doc["full_text"]
        raw = (extraction / full["path"]).read_bytes()
        assert sha(raw) == full["sha256"] == FULL_TEXT_PINS[full["path"]]
        pages = raw.decode("utf-8").split("\f")
        if not pages[-1].strip():
            pages.pop()
        assert len(pages) == len(doc["pages"])
        for index, item in enumerate(doc["pages"]):
            page = (extraction / item["path"]).read_bytes()
            assert page == pages[index].encode("utf-8")
            assert item["page"] == index + 1 and len(page) == item["bytes"]
            assert sha(page) == item["sha256"]
            records.append(item)
            pages_checked += 1
        records.append(full)
    with zipfile.ZipFile(bundle / "assets/D-F.zip") as package:
        for item in records:
            raw = (extraction / item["path"]).read_bytes()
            assert (bundle / "assets/D-F" / item["path"]).read_bytes() == raw
            assert (prepared / "stage/case" / item["path"]).read_bytes() == package.read(item["path"]) == raw
    assert pages_checked == 35 and len(records) == 38
    return {"python": runtime["python"], "run_id": run["run_id"], "state": result["state"],
            "schedule_sha256": schedule["schedule_sha256"], "checkpoint_sha256": result["checkpoint_sha256"],
            "prepared_schedule_cells": 12, "staged_case": "D-F", "arm": "A",
            "originals": originals_checked, "original_count": len(originals_checked),
            "derived_text_file_count": len(records), "page_count": pages_checked,
            "text_manifest_sha256": records[0]["sha256"], "function_bindings": shebangs,
            "provider_requests": 0, "tool_invocations": 0, "committed_cost_micro_usd": 0,
            "private_owned_parents": True, "passed": True}


def main() -> int:
    os.umask(0o077)
    report = {"classification": "read_only_artifact_verification_of_real_cli_preparation",
              "versions": {version: verify(version) for version in ("311", "312")},
              "formal_cells_executed": 0, "execution_authorized": False,
              "scope": "Build both domains and prepare one D-F/A cell per Python; no model or tool execution."}
    with (OUT / "artifact_verification.json").open("x") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
