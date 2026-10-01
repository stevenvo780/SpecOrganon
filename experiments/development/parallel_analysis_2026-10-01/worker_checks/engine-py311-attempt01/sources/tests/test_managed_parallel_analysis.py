"""Analysis adapter selects its broker without changing D115 globals or bytes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from test_c_parallel_analysis import adapters, prepare, sandbox, step
import managed_parallel_analysis as adapter
import managed_parallel_tools as engine
from parallel_analysis_broker import AnalysisParallelToolBroker


def test_new_manifest_constructor_and_original_globals_preserved(tmp_path):
    original_constructor = engine.ParallelToolBroker
    originals = [Path(engine.__file__), Path(engine.__file__).with_name("parallel_tool_broker.py"),
                 Path(engine.__file__).with_name("c_parallel_tools.py"),
                 Path(engine.__file__).with_name("development_analysis_tool.py")]
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in originals}
    run, status, _ = prepare(tmp_path)
    plan = json.loads((run / "plan.json").read_bytes())
    manifest = json.loads(Path(plan["branch_manifest"]["path"]).read_bytes())
    assert manifest["schema"] == 2 and status["base_execution_profile"] == "parallel_tool_wave_v2"
    assert status["execution_profile"] == adapter.PROFILE
    assert status["caller_graph_required"] is True and status["comparable_development_cell"] is False
    assert engine.ParallelToolBroker is original_constructor
    assert {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in originals} == before
    broker = AnalysisParallelToolBroker(run, plan["branch_manifest"])
    assert broker.verify()["reservations"] == 0


@pytest.mark.parametrize("point", ["prepared", "paused", "completed"])
def test_new_source_binding_tamper_blocks_status_and_effects(tmp_path, monkeypatch, point):
    sandbox()
    run, status, _ = prepare(tmp_path)
    transports = adapters()
    if point != "prepared":
        status = step(run, status, transports)
        assert status["state"] == "paused", status
    if point == "completed":
        status = step(run, status, transports)
        status = step(run, status, transports)
        assert status["state"] == "completed", status
    source_digests = adapter._source_digests()
    monkeypatch.setattr(adapter, "_source_digests", lambda: {**source_digests, "/changed/source.py": "0" * 64})
    before = sum(t.counts + t.sends for t in transports.values())
    with pytest.raises(adapter.ParallelAnalysisError, match="source closure changed"):
        adapter.read_analysis_wave_status(run)
    with pytest.raises(adapter.ParallelAnalysisError):
        adapter.execute_analysis_wave_step(run, transports, expected_checkpoint=status["checkpoint_sha256"], merge=lambda *args: {})
    assert sum(t.counts + t.sends for t in transports.values()) == before


def test_analysis_binding_rejected_before_new_directory(tmp_path):
    source = {"schema": 2, "execution_profile": "parallel_tool_wave_v2"}
    with pytest.raises(ValueError):
        adapter.prepare_analysis_wave(tmp_path / "run", source, admission_root=tmp_path / "admission")
    assert not (tmp_path / "run").exists()
