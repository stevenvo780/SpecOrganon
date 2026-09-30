"""Repeat reviewed native analysis scripts offline in new bounded processes.

Usage: python replay_trials.py REPOSITORY NEW_OUTPUT_DIRECTORY
Run only after reviewing preserved runs/*/analysis.py. This does not launch
agents, change their outputs, measure native budgets or attest historical runs.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from inspect_trial import inspect
from stage_trials import stage


def strict_json(raw: str):
    def reject(value: str):
        raise ValueError(f"nonfinite JSON: {value}")

    return json.loads(raw, parse_constant=reject)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", type=Path)
    parser.add_argument("new_output_directory", type=Path)
    parser.add_argument("--reviewed-subprocess-replay", action="store_true",
                        help="Explicit extra replay for reviewed pdftotext scripts; no filesystem/network sandbox")
    args = parser.parse_args()
    repo = args.repository.resolve(strict=True)
    destination = args.new_output_directory.absolute()
    location = repo / "experiments/development/bread_prototype_feasibility_2026-09-30"
    original = json.loads((location / "staging_receipt.json").read_text())
    fresh = stage(repo, destination)
    if fresh["frozen_git_files"] != original["frozen_git_files"]:
        raise ValueError("current inputs differ from original frozen bytes; partial replay is untrusted")
    sys.path.insert(0, str(repo / "scripts"))
    from local_replay_sandbox import default_python_runtime_roots, run_sandboxed

    observations = []
    for trial in fresh["trials"]:
        work = Path(trial["directory"])
        preserved = location / "runs" / trial["trial_id"]
        for name in ["analysis.py", "metrics.json", "sources.json", "report.md",
                     "prototype_case.json", "state.json", "prototype_calls.jsonl"]:
            if (preserved / name).is_file():
                shutil.copyfile(preserved / name, work / name)
        observation = inspect(location / "staging_receipt.json", trial["trial_id"], work)
        observation["historical_execution_attested"] = False
        observation["replay_command"] = ["python3", "-I", "analysis.py", "input"]
        if (work / "analysis.py").is_file():
            audit = destination / (trial["trial_id"] + "-replay")
            audit.mkdir(mode=0o700)
            expected = hashlib.sha256((work / "analysis.py").read_bytes()).hexdigest()
            try:
                result = run_sandboxed(
                    argv=[sys.executable, "-I", "analysis.py", "input"], cwd=work,
                    read_roots=[work], write_roots=[],
                    runtime_roots=default_python_runtime_roots(),
                    stdout_path=audit / "stdout.json", stderr_path=audit / "stderr.txt",
                    timeout_seconds=30, cpu_seconds=10,
                )
                observation["replay"] = dataclasses.asdict(result)
                observation["replay"]["script_sha256_before"] = expected
                observation["replay"]["script_bytes_unchanged"] = (
                    hashlib.sha256((work / "analysis.py").read_bytes()).hexdigest() == expected)
                observation["replay"]["output_json_equal_preserved_metrics"] = None
                if result.exit_code == 0:
                    try:
                        actual = strict_json((audit / "stdout.json").read_text())
                        prior = strict_json((work / "metrics.json").read_text())
                        observation["replay"]["output_json_equal_preserved_metrics"] = actual == prior
                    except (OSError, ValueError) as exc:
                        observation["replay"]["json_comparison_error"] = str(exc)
                observation["replay"]["streams"] = {
                    name: {"sha256": hashlib.sha256((audit / name).read_bytes()).hexdigest(),
                           "bytes": (audit / name).stat().st_size}
                    for name in ["stdout.json", "stderr.txt"] if (audit / name).is_file()}
            except Exception as exc:
                observation["replay_error"] = {"type": type(exc).__name__, "message": str(exc)}
            if args.reviewed_subprocess_replay:
                started = time.monotonic()
                environment = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
                               "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"}
                timed_out = False
                with (audit / "reviewed.stdout.json").open("xb") as stdout, (audit / "reviewed.stderr.txt").open("xb") as stderr:
                    process = subprocess.Popen([sys.executable, "-I", "analysis.py", "input"],
                                               cwd=work, env=environment, stdout=stdout,
                                               stderr=stderr, start_new_session=True)
                    try:
                        code = process.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        timed_out = True
                        if process.poll() is None:
                            os.killpg(process.pid, signal.SIGKILL)
                        code = process.wait()
                extra = {"backend": "reviewed_local_subprocess_with_clean_environment",
                         "filesystem_network_sandbox_enforced": False,
                         "timeout_seconds": 30, "timed_out": timed_out, "exit_code": code,
                         "duration_seconds_local": time.monotonic() - started,
                         "output_json_equal_preserved_metrics": None}
                try:
                    actual = strict_json((audit / "reviewed.stdout.json").read_text())
                    prior = strict_json((work / "metrics.json").read_text())
                    extra["output_json_equal_preserved_metrics"] = actual == prior
                except (OSError, ValueError) as exc:
                    extra["json_comparison_error"] = str(exc)
                extra["streams"] = {
                    name: {"sha256": hashlib.sha256((audit / name).read_bytes()).hexdigest(),
                           "bytes": (audit / name).stat().st_size}
                    for name in ["reviewed.stdout.json", "reviewed.stderr.txt"]}
                observation["reviewed_subprocess_replay"] = extra
            after = inspect(location / "staging_receipt.json", trial["trial_id"], work)
            observation["all_deliverable_bytes_unchanged_after_replays"] = after["artifacts"] == observation["artifacts"]
            observation["fixed_file_mismatches_after_replays"] = after["fixed_file_mismatches"]
        observations.append(observation)
    result = {"schema": 1, "classification": "local_offline_native_artifact_replay",
              "original_frozen_commit": original["frozen_commit"],
              "current_replay_input_commit": fresh["frozen_commit"],
              "input_bytes_equal_original_frozen_files": True,
              "trials": observations, "native_limits_enforced": False,
              "native_tokens": None, "native_cost": None,
              "custody_independent": False, "counts_toward_required_24_runs": False}
    (destination / "replay_receipt.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
