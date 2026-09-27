"""Exercise the exposed T runner with an offline installed wheel and a fake model CLI.

Usage: python scripts/probe_installed_t_runner.py [--output evidence.json]

The model process is synthetic. Its tools are real installed Organon CLI and
stdio MCP executables. All run directories are private temporary local data;
the JSON output keeps their byte digests and the observed negative control.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_development_arm.py"
OBSERVER = ROOT / "scripts" / "observe_development_run.py"
MODEL = "local-fake-model-no-provider"
ANALYSIS = (
    "import csv\n"
    "from pathlib import Path\n"
    "with Path('sample_first_complete_week.csv').open(newline='', encoding='utf-8-sig') as source:\n"
    "    rows = list(csv.DictReader(source))\n"
    "print(f\"rows={len(rows)} appliances_total={sum(int(row['Appliances']) for row in rows)}\")\n"
)
REPORT = (
    "Synthetic installed-wheel T transport probe. The source sample was read; "
    "no intervention, human approval, or field outcome was observed.\n"
)
EXPECTED_REPLAY = "rows=1008 appliances_total=118280\n"
PRE_FIX_COUNTEREXAMPLE = {
    "date_utc": "2026-09-27",
    "runner_sha256": "9f8dd637e26bda82d516a31e21b6064bba5782b18d34dd3653a980eaac9bb58f",
    "observer_sha256": "047343c1c534a8a9411650ca6c7eaa1af5bfcfa042b541901b6a0260ac47d533",
    "control": "valid signed ledger copied from a prior run; fake model called no Organon CLI or MCP executable",
    "runner_exit_code": 0,
    "runner_status": "artifacts_ready_for_inspection",
    "observer_status": "artifacts_ready_for_inspection",
    "conclusion": "false acceptance before the local process-trace gate",
}

FAKE_MODEL_CLI = r'''#!/usr/bin/env python3
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

mode = os.environ.get("SPEC_PROBE_MODE", "use_installed_tools")
work = Path.cwd()
assert Path(".venv/bin/organon").is_file()
assert Path(".venv/bin/organon-mcp").is_file()
assert "exec" in sys.argv and "--json" in sys.argv
prompt = sys.stdin.read()
assert "# Assigned arm" in prompt and "The installed SpecOrganon CLI" in prompt

analysis = (
    "import csv\n"
    "from pathlib import Path\n"
    "with Path('sample_first_complete_week.csv').open(newline='', encoding='utf-8-sig') as source:\n"
    "    rows = list(csv.DictReader(source))\n"
    "print(f\"rows={len(rows)} appliances_total={sum(int(row['Appliances']) for row in rows)}\")\n"
)
report = (
    "Synthetic installed-wheel T transport probe. The source sample was read; "
    "no intervention, human approval, or field outcome was observed.\n"
)
Path("analysis.py").write_text(analysis, encoding="utf-8")
Path("report.md").write_text(report, encoding="utf-8")

if mode == "use_installed_tools":
    cli = work / ".venv/bin/organon"
    case = work / "case"
    def command(*args):
        result = subprocess.run([str(cli), *args], cwd=work, text=True,
                                capture_output=True, check=True, timeout=15)
        return json.loads(result.stdout)
    initialized = command("init", str(case), "--title", "Installed T probe",
                          "--domain", "building-energy", "--actor", "agent:probe",
                          "--approval-policy", "signed")
    first_put = command("put", str(case), "p1", "--kind", "problem",
                        "--text", "Energy use in the provided week requires interpretation.",
                        "--actor", "agent:probe", "--expected-version", "0")
    mcp_code = """
import asyncio
import json
import os
import sys
from pathlib import Path
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

async def exercise():
    case = sys.argv[1]
    server = Path(sys.executable).parent / 'organon-mcp'
    params = StdioServerParameters(command=str(server), cwd=str(Path.cwd()), env=os.environ.copy())
    async with Client(params, mode='legacy') as client:
        names = sorted(tool.name for tool in (await client.list_tools()).tools)
        assert {'put', 'status'} <= set(names)
        before_result = await client.call_tool('status', {'path': case})
        assert not before_result.is_error, before_result.content
        before = before_result.structured_content or json.loads(before_result.content[0].text)
        put_result = await client.call_tool('put', {
            'path': case, 'id': 'a1', 'kind': 'actor',
            'text': 'A household occupant is affected by energy-use decisions.',
            'refs': ['p1'], 'data': {}, 'actor': 'agent:probe',
            'expected_version': 0, 'expected_deps': {'p1': 1},
        })
        assert not put_result.is_error, put_result.content
        put = put_result.structured_content or json.loads(put_result.content[0].text)
        after_result = await client.call_tool('status', {'path': case})
        assert not after_result.is_error, after_result.content
        after = after_result.structured_content or json.loads(after_result.content[0].text)
        return {'discovered_tools': names, 'status_before': before,
                'put': put, 'status_after': after}

print(json.dumps(asyncio.run(exercise()), sort_keys=True))
"""
    mcp_result = subprocess.run([str(work / ".venv/bin/python"), "-c", mcp_code, str(case)],
                                cwd=work, text=True, capture_output=True, check=True, timeout=20)
    mcp = json.loads(mcp_result.stdout)
    final_status = command("status", str(case))
    assert final_status == mcp["status_after"]
    assert final_status["project"]["approval_policy"] == "signed"
    assert {"p1", "a1"} <= set(final_status["items"])
    Path("probe_tool_trace.json").write_text(json.dumps({
        "schema": 1,
        "cli_executable": str(cli),
        "mcp_executable": str(work / ".venv/bin/organon-mcp"),
        "cli_init": initialized,
        "cli_put": first_put,
        "mcp": mcp,
        "cli_status_after": final_status,
    }, sort_keys=True) + "\n", encoding="utf-8")
elif mode in {"copy_valid_ledger_without_t_tool_use", "read_only_tool_then_copy_valid_ledger"}:
    # Adversarial fake model: copy a valid ledger from the preceding positive
    # run. The second form exercises only CLI --help; it never mutates a case.
    if mode == "read_only_tool_then_copy_valid_ledger":
        help_result = subprocess.run([str(work / ".venv/bin/organon"), "--help"],
                                     cwd=work, text=True, capture_output=True,
                                     check=True, timeout=15)
        assert "usage:" in help_result.stdout
    case = work / "case"
    case.mkdir()
    shutil.copyfile(os.environ["SPEC_PROBE_SOURCE_LEDGER"], case / "organon.json")
elif mode != "omit_t_tool_use":
    raise ValueError("unknown fake model mode")

for event in (
    {"type": "thread.started", "thread_id": "synthetic-local-probe"},
    {"type": "item.completed", "item": (
        {"type": "command_execution", "command": ".venv/bin/organon --help", "exit_code": 0}
        if mode == "read_only_tool_then_copy_valid_ledger"
        else {"type": "command_execution", "exit_code": 0}
        if mode == "use_installed_tools" else {"type": "file_change"}
    )},
    {"type": "turn.completed", "usage": {"input_tokens": 20,
        "cached_input_tokens": 0, "cache_write_input_tokens": 0,
        "output_tokens": 8, "reasoning_output_tokens": 0}},
):
    print(json.dumps(event, sort_keys=True))
'''


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check(condition: bool, reason: str) -> None:
    if not condition:
        raise RuntimeError(reason)


def _run(
    argv: list[str], *, env: dict[str, str] | None = None, timeout: int = 90
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def _invoke_arm(
    wheel: Path,
    run_root: Path,
    fake_bin: Path,
    mode: str,
    *,
    source_ledger: Path | None = None,
) -> tuple[Path, dict[str, Any], int]:
    env = os.environ.copy()
    env["PATH"] = str(fake_bin) + os.pathsep + env.get("PATH", "")
    env["SPEC_PROBE_MODE"] = mode
    if source_ledger is not None:
        env["SPEC_PROBE_SOURCE_LEDGER"] = str(source_ledger)
    command = [
        sys.executable,
        str(RUNNER),
        "--arm",
        "T",
        "--provider",
        "codex",
        "--model",
        MODEL,
        "--effort",
        "low",
        "--output-root",
        str(run_root),
        "--toolkit-wheel",
        str(wheel),
        "--timeout-seconds",
        "45",
        "--setup-timeout-seconds",
        "45",
    ]
    result = _run(command, env=env, timeout=120)
    _check(result.stdout.strip() != "", f"runner produced no receipt: {result.stderr}")
    receipt = json.loads(result.stdout)
    run_dir = Path(receipt["run_dir"])
    _check(run_dir.is_dir(), "runner did not leave its private run directory")
    summary = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    _check(
        receipt["status"] == summary["execution_status"],
        "runner receipt status differs from run.json",
    )
    return run_dir, summary, result.returncode


def _observe(run_dir: Path) -> tuple[dict[str, Any], int]:
    result = _run([sys.executable, str(OBSERVER), str(run_dir)], timeout=30)
    _check(result.returncode == 0, f"observer rejected run: {result.stderr}")
    return json.loads(result.stdout), result.returncode


def run_probe(work_root: Path) -> dict[str, Any]:
    """Build once, run positive and three negative T paths, and check their bytes."""
    work_root.mkdir(parents=True, exist_ok=True)
    wheel_dir = work_root / "wheel"
    build = _run(
        ["uv", "build", "--offline", "--wheel", "--out-dir", str(wheel_dir)], timeout=60
    )
    _check(build.returncode == 0, f"offline wheel build failed: {build.stderr}")
    wheels = list(wheel_dir.glob("specorganon-*.whl"))
    _check(
        len(wheels) == 1, "offline build did not produce exactly one SpecOrganon wheel"
    )
    wheel = wheels[0]
    fake_bin = work_root / "fake-bin"
    fake_bin.mkdir(mode=0o700)
    fake_cli = fake_bin / "codex"
    fake_cli.write_text(FAKE_MODEL_CLI, encoding="utf-8")
    fake_cli.chmod(0o700)

    run_dir, summary, exit_code = _invoke_arm(
        wheel, work_root / "positive-runs", fake_bin, "use_installed_tools"
    )
    _check(
        exit_code == 0
        and summary["execution_status"] == "artifacts_ready_for_inspection",
        f"installed T run failed: {summary['execution_status']}",
    )
    work = run_dir / "work"
    trace_path = work / "probe_tool_trace.json"
    _check(trace_path.is_file(), "fake model did not record the CLI/MCP calls")
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    ledger_path = work / "case" / "organon.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    _check(
        trace["cli_executable"] == str(work / ".venv/bin/organon"),
        "fake model used a different CLI executable",
    )
    _check(
        trace["mcp_executable"] == str(work / ".venv/bin/organon-mcp"),
        "fake model used a different MCP executable",
    )
    _check(
        {"put", "status"} <= set(trace["mcp"]["discovered_tools"]),
        "MCP client did not discover required tools",
    )
    _check(
        trace["mcp"]["status_before"]["project"]["approval_policy"] == "signed",
        "MCP status did not read signed policy",
    )
    _check(
        trace["cli_status_after"] == trace["mcp"]["status_after"],
        "installed CLI and MCP status differ",
    )
    _check(
        {"p1", "a1"} <= set(trace["cli_status_after"]["items"]),
        "CLI/MCP writes are missing from installed status",
    )
    _check(
        ledger["project"]["approval_policy"] == "signed" and len(ledger["events"]) == 2,
        "installed ledger lacks signed policy or two writes",
    )
    _check(
        summary["t_ledger"]["sha256"] == _sha(ledger_path)
        and summary["t_ledger"]["event_count"] == len(ledger["events"]),
        "runner T ledger receipt differs from actual bytes",
    )
    _check(
        summary["toolkit"]["wheel"]
        == {"sha256": _sha(wheel), "bytes": wheel.stat().st_size},
        "installed wheel receipt differs from built wheel",
    )
    _check(
        summary["toolkit"]["signed_policy_verified_in_local_probe"] is True
        and summary["t_ledger"]["toolkit_files_unchanged"] is True,
        "runner did not verify installed T toolkit",
    )
    process_trace = summary["t_process_trace"]
    process_trace_path = run_dir / "t_execve.log"
    _check(
        process_trace["method"] == "linux_strace_execve_case_publish"
        and process_trace["record"]
        == {
            "sha256": _sha(process_trace_path),
            "bytes": process_trace_path.stat().st_size,
        }
        and process_trace["inspectable"] is True
        and process_trace["organon_cli_execs"] >= 2
        and process_trace["organon_mcp_execs"] >= 1
        and process_trace["tool_ledger_publish_count"] >= len(ledger["events"]) + 1
        and process_trace["other_ledger_write_count"] == 0,
        "runner did not observe installed CLI/MCP ledger publications",
    )
    _check(
        all(step["exit_code"] == 0 for step in summary["toolkit"]["steps"].values())
        and summary["t_ledger"]["independent_cli_status"]["exit_code"] == 0,
        "installed setup or final status command failed",
    )
    _check(
        (work / "analysis.py").read_text(encoding="utf-8") == ANALYSIS
        and (work / "report.md").read_text(encoding="utf-8") == REPORT,
        "model artifacts differ from expected bytes",
    )
    _check(
        summary["artifacts"]["analysis.py"]["sha256"] == _sha(work / "analysis.py")
        and summary["artifacts"]["report.md"]["sha256"] == _sha(work / "report.md"),
        "runner artifact receipt differs from actual bytes",
    )
    _check(
        summary["cli_usage"]["complete"] is True
        and summary["cli_usage"]["terminal_success"] is True,
        "fake CLI JSONL did not yield a complete local receipt",
    )
    first_observation, _ = _observe(run_dir)
    _check(
        first_observation["execution_status"] == "artifacts_ready_for_inspection"
        and first_observation["observation_state"] == "recorded_materials_verified",
        "observer did not verify first T receipt",
    )

    replay = _run(
        [
            sys.executable,
            str(RUNNER),
            "--replay-run-dir",
            str(run_dir),
            "--expected-analysis-sha256",
            _sha(work / "analysis.py"),
        ],
        timeout=30,
    )
    _check(replay.returncode == 0, f"reviewed analysis replay failed: {replay.stderr}")
    replay_receipt = json.loads(replay.stdout)
    _check(
        replay_receipt["status"] == "output_replayed",
        "runner replay receipt is not successful",
    )
    final_summary = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    _check(
        (run_dir / "analysis_replay.stdout").read_text(encoding="utf-8")
        == EXPECTED_REPLAY,
        "analysis replay output differs from actual sample calculation",
    )
    _check(
        final_summary["analysis_replay"]["stdout"]["sha256"]
        == _sha(run_dir / "analysis_replay.stdout"),
        "replay stdout receipt differs from actual bytes",
    )
    final_observation, _ = _observe(run_dir)
    _check(
        final_observation["execution_status"] == "output_replayed"
        and final_observation["observation_state"] == "recorded_materials_verified"
        and final_observation["verified_artifacts"]["work/case/organon.json"]["sha256"]
        == _sha(ledger_path),
        "observer did not verify the final ledger and replay",
    )

    negative_dir, negative, negative_exit = _invoke_arm(
        wheel, work_root / "negative-runs", fake_bin, "omit_t_tool_use"
    )
    negative_work = negative_dir / "work"
    _check(
        negative_exit == 1
        and negative["execution_status"] == "t_signed_ledger_missing_or_invalid"
        and negative["t_ledger"]["present"] is False,
        "runner accepted a fake model that omitted T tool use",
    )
    _check(
        (negative_work / "analysis.py").read_text(encoding="utf-8") == ANALYSIS
        and (negative_work / "report.md").read_text(encoding="utf-8") == REPORT,
        "negative model did not produce the same required artifacts",
    )
    _check(
        not (negative_work / "case").exists()
        and not (negative_work / "probe_tool_trace.json").exists(),
        "negative model unexpectedly used T tools or created a ledger",
    )
    negative_observation, _ = _observe(negative_dir)
    _check(
        negative_observation["execution_status"] == "t_signed_ledger_missing_or_invalid"
        and negative_observation["observation_state"] == "recorded_materials_verified",
        "observer did not preserve negative T result",
    )

    copied_dir, copied, copied_exit = _invoke_arm(
        wheel,
        work_root / "copied-ledger-runs",
        fake_bin,
        "copy_valid_ledger_without_t_tool_use",
        source_ledger=ledger_path,
    )
    copied_work = copied_dir / "work"
    copied_ledger = copied_work / "case" / "organon.json"
    _check(
        copied_ledger.read_bytes() == ledger_path.read_bytes(),
        "adversarial fake model did not preserve copied ledger bytes",
    )
    _check(
        (copied_work / "analysis.py").read_text(encoding="utf-8") == ANALYSIS
        and (copied_work / "report.md").read_text(encoding="utf-8") == REPORT
        and not (copied_work / "probe_tool_trace.json").exists(),
        "copied-ledger control changed artifacts or unexpectedly called T tools",
    )
    copied_observation, _ = _observe(copied_dir)
    _check(
        copied_observation["execution_status"] == copied["execution_status"],
        "observer disagrees with copied-ledger runner result",
    )
    copied_accepted = (
        copied_exit == 0
        and copied["execution_status"] == "artifacts_ready_for_inspection"
    )
    copied_rejected_as_expected = (
        copied_exit == 1
        and copied["execution_status"] == "t_tool_execution_unverified"
        and copied_observation["execution_status"] == "t_tool_execution_unverified"
    )
    _check(
        copied_exit in {0, 1}, "copied-ledger runner returned an unexpected exit code"
    )

    read_only_dir, read_only, read_only_exit = _invoke_arm(
        wheel,
        work_root / "read-only-then-copy-runs",
        fake_bin,
        "read_only_tool_then_copy_valid_ledger",
        source_ledger=ledger_path,
    )
    read_only_work = read_only_dir / "work"
    read_only_ledger = read_only_work / "case" / "organon.json"
    _check(
        read_only_ledger.read_bytes() == ledger_path.read_bytes()
        and (read_only_work / "analysis.py").read_text(encoding="utf-8") == ANALYSIS
        and (read_only_work / "report.md").read_text(encoding="utf-8") == REPORT
        and not (read_only_work / "probe_tool_trace.json").exists(),
        "read-only control did not preserve the copied bytes or unexpectedly wrote a tool trace",
    )
    read_only_observation, _ = _observe(read_only_dir)
    _check(
        read_only_observation["execution_status"] == read_only["execution_status"],
        "observer disagrees with read-only-tool copied-ledger result",
    )
    read_only_accepted = (
        read_only_exit == 0
        and read_only["execution_status"] == "artifacts_ready_for_inspection"
    )
    read_only_rejected_as_expected = (
        read_only_exit == 1
        and read_only["execution_status"] == "t_tool_execution_unverified"
        and read_only_observation["execution_status"] == "t_tool_execution_unverified"
    )
    _check(
        read_only_exit in {0, 1},
        "read-only-tool runner returned an unexpected exit code",
    )

    return {
        "schema": 1,
        "classification": "synthetic_installed_t_runner_probe_unsealed_not_provider_evidence",
        "date_utc": datetime.now(timezone.utc).date().isoformat(),
        "goal_sha256": _sha(ROOT / "GOAL.md"),
        "source_sha256": {"runner": _sha(RUNNER), "observer": _sha(OBSERVER)},
        "before_fix_counterexample": PRE_FIX_COUNTEREXAMPLE,
        "environment": {
            "python": sys.version.split()[0],
            "offline_build": True,
            "offline_runner_install": True,
            "temporary_runs_retained": False,
        },
        "commands": [
            "uv build --offline --wheel --out-dir <temporary-wheel-dir>",
            "python scripts/run_development_arm.py --arm T --provider codex --model local-fake-model-no-provider --effort low --toolkit-wheel <built-wheel> --output-root <private-run-root>",
            "python scripts/run_development_arm.py --replay-run-dir <positive-run> --expected-analysis-sha256 <reviewed-digest>",
            "python scripts/observe_development_run.py <each-run>",
        ],
        "built_wheel": {
            "filename": wheel.name,
            "sha256": _sha(wheel),
            "bytes": wheel.stat().st_size,
        },
        "positive": {
            "runner_exit_code": exit_code,
            "initial_status": summary["execution_status"],
            "replay_status": final_summary["execution_status"],
            "toolkit_steps": {
                name: step["exit_code"]
                for name, step in summary["toolkit"]["steps"].items()
            },
            "installed_toolkit_fingerprint_sha256": summary["toolkit"][
                "toolkit_files_fingerprint_sha256"
            ],
            "cli_operations": ["init", "put", "status"],
            "mcp_client_discovered_tools": trace["mcp"]["discovered_tools"],
            "mcp_operations": ["status", "put", "status"],
            "cli_mcp_final_status_equal": True,
            "ledger": {
                "sha256": _sha(ledger_path),
                "bytes": ledger_path.stat().st_size,
                "event_count": len(ledger["events"]),
                "approval_policy": "signed",
            },
            "artifacts": final_summary["artifacts"],
            "replay_stdout": final_summary["analysis_replay"]["stdout"],
            "local_cli_usage_complete": summary["cli_usage"]["complete"],
            "local_t_process_trace": process_trace,
            "observer": {
                "initial_status": first_observation["execution_status"],
                "final_status": final_observation["execution_status"],
                "state": final_observation["observation_state"],
                "verified_ledger_sha256": final_observation["verified_artifacts"][
                    "work/case/organon.json"
                ]["sha256"],
                "criterion_4": final_observation["criterion_4"],
                "controlled_comparison_eligible": final_observation[
                    "controlled_comparison_eligible"
                ],
            },
        },
        "negative_omitted_t_tool_use": {
            "runner_exit_code": negative_exit,
            "status": negative["execution_status"],
            "same_artifact_bytes_as_positive": True,
            "case_ledger_present": False,
            "observer_status": negative_observation["execution_status"],
            "observer_state": negative_observation["observation_state"],
        },
        "negative_copied_ledger_without_t_tool_use": {
            "runner_exit_code": copied_exit,
            "runner_status": copied["execution_status"],
            "observer_status": copied_observation["execution_status"],
            "copied_ledger_sha256": _sha(copied_ledger),
            "same_ledger_bytes_as_positive": True,
            "same_artifact_bytes_as_positive": True,
            "model_invoked_installed_t_tools": False,
            "probe_admitted": False,
            "runner_false_acceptance": copied_accepted,
            "expected_rejection_observed": copied_rejected_as_expected,
            "local_t_process_trace": copied["t_process_trace"],
        },
        "negative_read_only_tool_then_copied_ledger": {
            "runner_exit_code": read_only_exit,
            "runner_status": read_only["execution_status"],
            "observer_status": read_only_observation["execution_status"],
            "same_ledger_bytes_as_positive": True,
            "same_artifact_bytes_as_positive": True,
            "model_invoked_only_installed_cli_help": True,
            "probe_admitted": False,
            "runner_false_acceptance": read_only_accepted,
            "expected_rejection_observed": read_only_rejected_as_expected,
            "local_t_process_trace": read_only["t_process_trace"],
        },
        "runner_provenance_gate_passed": copied_rejected_as_expected
        and read_only_rejected_as_expected,
        "limits": [
            "The model executable and its JSONL usage counters are synthetic; no model provider or authenticated receipt was used.",
            "The positive fake model made real installed CLI and MCP calls; the runner records local process activity, not authenticated provider attribution or cryptographic provenance.",
            "The copied-ledger controls test two provenance forgeries; they do not prove that all possible unreported calls are detected.",
            "The case UUID and timestamps vary, so ledger digests are checked within each run rather than fixed across independent invocations.",
            "The case is exposed development data, the default analysis replay has no OS isolation, and no human approval or field effect was assessed.",
            "No provider, model, effort, agent configuration, or N/S/T outcome comparison was tested; criterion 4 remains not assessed.",
        ],
        "criterion_4": "not_assessed",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="write the checked summary as JSON")
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory(
        prefix="specorganon-installed-t-probe-"
    ) as temporary:
        result = run_probe(Path(temporary))
    encoded = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if result["runner_provenance_gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
