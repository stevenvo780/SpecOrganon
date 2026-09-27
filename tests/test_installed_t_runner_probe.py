"""The exposed T runner must be exercised through an actual offline wheel install."""

from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from probe_installed_t_runner import run_probe  # noqa: E402


def test_installed_t_runner_accepts_real_tool_use_and_rejects_copied_ledger(
    tmp_path: Path,
) -> None:
    evidence = run_probe(tmp_path)

    assert evidence["positive"]["replay_status"] == "output_replayed"
    assert evidence["positive"]["cli_mcp_final_status_equal"] is True
    assert evidence["positive"]["observer"]["state"] == "recorded_materials_verified"
    assert evidence["positive"]["local_t_process_trace"]["organon_mcp_execs"] >= 1
    assert (
        evidence["negative_omitted_t_tool_use"]["status"]
        == "t_signed_ledger_missing_or_invalid"
    )
    assert (
        evidence["negative_copied_ledger_without_t_tool_use"]["probe_admitted"] is False
    )
    assert (
        evidence["negative_copied_ledger_without_t_tool_use"]["runner_status"]
        == "t_tool_execution_unverified"
    )
    assert (
        evidence["negative_read_only_tool_then_copied_ledger"]["probe_admitted"]
        is False
    )
    assert (
        evidence["negative_read_only_tool_then_copied_ledger"]["runner_status"]
        == "t_tool_execution_unverified"
    )
    assert evidence["runner_provenance_gate_passed"] is True
    assert evidence["criterion_4"] == "not_assessed"
