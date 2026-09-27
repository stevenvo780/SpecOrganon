"""Run one exposed D-E development arm with local Codex or agy telemetry.

This is an unsealed feasibility runner, not a confirmatory matrix executor or
an authenticated provider receipt. Each invocation creates a private directory
and never reuses another arm's workspace. Raw CLI streams stay there for audit.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "cases" / "building_energy"
PROMPTS = ROOT / "experiments" / "development" / "energy_pilot"
PUBLIC_FILES = ("task.md", "source_manifest.json", "sample_first_complete_week.csv")
USAGE_FIELDS = {
    "codex": ("input_tokens", "cached_input_tokens", "cache_write_input_tokens",
              "output_tokens", "reasoning_output_tokens"),
    "agy": ("input_tokens", "output_tokens", "thinking_tokens", "cache_read_tokens",
            "total_tokens"),
}
# The exposed Agy pilot asks for file writes only. This is a local JSONL
# allowlist, not a provider-side or operating-system command prohibition.
AGY_NO_COMMAND_ALLOWED_TOOLS = frozenset({"write_to_file"})


class RunError(ValueError):
    """A run cannot be prepared without violating its recorded contract."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _regular_file(path: Path) -> bool:
    try:
        return stat.S_ISREG(path.lstat().st_mode)
    except FileNotFoundError:
        return False


def _file_record(path: Path) -> dict[str, Any] | None:
    if not _regular_file(path):
        return None
    return {"sha256": _sha256(path), "bytes": path.stat().st_size}


def _toolkit_fingerprint(work: Path) -> str | None:
    """Hash only the console entrypoint and installed SpecOrganon Python sources."""
    installed = work / ".venv"
    files = [installed / "bin" / "organon"]
    files.extend(sorted(installed.glob("lib/python*/site-packages/specorganon/**/*.py")))
    if len(files) < 2 or any(not _regular_file(path) for path in files):
        return None
    digest = hashlib.sha256()
    for path in files:
        digest.update(str(path.relative_to(installed)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(_sha256(path)))
    return digest.hexdigest()


def _write_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                         encoding="utf-8")
    temporary.replace(path)


def _private_run_dir(output_root: Path) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    for _ in range(5):
        name = f"de-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:12]}"
        result = output_root / name
        try:
            result.mkdir(mode=0o700)
        except FileExistsError:
            continue
        result.chmod(0o700)
        return result
    raise RunError("could not allocate a unique run directory")


def _capture(
    argv: list[str], *, cwd: Path, timeout_seconds: int, stdout_path: Path,
    stderr_path: Path, stdin_text: str | None = None, env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Save raw streams and terminate the entire child group at a wall deadline."""
    started = _utc_now()
    before = time.monotonic()
    result: dict[str, Any] = {"started_at_utc": started, "exit_code": None,
                              "timed_out": False, "launch_error": None}
    with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
        try:
            process = subprocess.Popen(
                argv, cwd=cwd, stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
                stdout=stdout, stderr=stderr, start_new_session=True, env=env,
            )
        except OSError as exc:
            result["launch_error"] = f"{type(exc).__name__}: {exc}"
        else:
            try:
                process.communicate(input=stdin_text.encode("utf-8") if stdin_text is not None else None,
                                    timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                result["timed_out"] = True
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.communicate(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.communicate()
            result["exit_code"] = process.returncode
    result["ended_at_utc"] = _utc_now()
    result["wall_seconds"] = round(time.monotonic() - before, 3)
    result["stdout"] = _file_record(stdout_path)
    result["stderr"] = _file_record(stderr_path)
    return result


def _clean_environment() -> dict[str, str]:
    env = os.environ.copy()
    for name in tuple(env):
        if name.startswith("ORGANON_") or name in {"PYTHONPATH", "PYTHONHOME"}:
            env.pop(name, None)
    return env


def _replay_environment(run_dir: Path) -> dict[str, str]:
    """Offer no inherited credentials to generated code; this is not OS isolation."""
    home = run_dir / "replay_home"
    temporary = run_dir / "replay_tmp"
    home.mkdir(mode=0o700)
    temporary.mkdir(mode=0o700)
    return {"HOME": str(home), "TMPDIR": str(temporary), "PATH": "/usr/bin:/bin",
            "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"}


def _usage_subset_errors(
    provider: str, usage: dict[str, int | None], source: str
) -> list[str]:
    """Check counters that must be subsets of input or output tokens."""
    cached_field, reasoning_field = (
        ("cached_input_tokens", "reasoning_output_tokens")
        if provider == "codex"
        else ("cache_read_tokens", "thinking_tokens")
    )
    errors: list[str] = []
    if (
        usage["input_tokens"] is not None
        and usage[cached_field] is not None
        and usage[cached_field] > usage["input_tokens"]
    ):
        errors.append(f"{source}.{cached_field} exceeds {source}.input_tokens")
    if (
        usage["output_tokens"] is not None
        and usage[reasoning_field] is not None
        and usage[reasoning_field] > usage["output_tokens"]
    ):
        errors.append(f"{source}.{reasoning_field} exceeds {source}.output_tokens")
    return errors


def _parse_usage(provider: str, stdout_path: Path, requested_model: str,
                 *, agy_no_command_tool: bool = False) -> dict[str, Any]:
    """Separate terminal execution evidence from optional token-field completeness."""
    if agy_no_command_tool and provider != "agy":
        raise ValueError("no-command trace check requires Agy")
    final_events: list[tuple[int, dict[str, Any]]] = []
    init_models: list[str] = []
    terminal_errors: list[str] = []
    usage_errors: list[str] = []
    event_count = 0
    last_type: str | None = None
    completed_tool_steps: set[int] = set()
    observed_tool_steps: set[int] = set()
    no_command_allowed_steps: set[int] = set()
    no_command_violating_steps: set[int] = set()
    failed_codex_items = 0
    failed_agy_steps: set[int] = set()
    agy_step_types: dict[int, str] = {}
    agy_colliding_indices: set[int] = set()
    agy_malformed_step_events = 0
    agy_unknown_step_events = 0
    agy_agent_observed_steps: set[int] = set()
    agy_agent_done_steps: set[int] = set()
    agy_agent_usage: dict[int, dict[str, int]] = {}
    agy_agent_done_events = 0
    agy_agent_duplicate_events = 0
    agy_agent_invalid_events = 0
    agy_agent_conflicting_events = 0
    agy_agent_subset_errors: set[str] = set()
    with stdout_path.open("r", encoding="utf-8", errors="replace") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                terminal_errors.append(f"line {line_number}: blank JSONL line")
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                terminal_errors.append(f"line {line_number}: invalid JSON")
                continue
            kind_key = "type" if provider == "codex" else "event"
            if type(event) is not dict or type(event.get(kind_key)) is not str:
                terminal_errors.append(f"line {line_number}: event/{kind_key} missing")
                continue
            event_count += 1
            kind = event[kind_key]
            last_type = kind
            if provider == "codex" and kind == "turn.completed":
                final_events.append((line_number, event))
            elif provider == "codex" and kind in {"item.failed", "turn.failed"}:
                failed_codex_items += 1
            elif provider == "codex" and kind == "item.completed":
                item = event.get("item")
                if type(item) is dict:
                    exit_code = item.get("exit_code")
                    if (item.get("status") in {"failed", "error"}
                            or (item.get("type") == "command_execution" and type(exit_code) is int
                                and exit_code != 0)):
                        failed_codex_items += 1
            elif provider == "agy" and kind == "result":
                final_events.append((line_number, event))
            elif provider == "agy" and kind == "init":
                initialization = event.get("init")
                if type(initialization) is dict and type(initialization.get("model")) is str:
                    init_models.append(initialization["model"])
            elif provider == "agy" and kind == "step_update":
                update = event.get("step_update")
                if type(update) is not dict:
                    agy_malformed_step_events += 1
                    continue
                index = update.get("step_index")
                step_type = update.get("step_type")
                state = update.get("state")
                if (type(index) is not int or index < 0 or type(step_type) is not str
                        or type(state) is not str
                        or state not in {"ACTIVE", "DONE", "FAILED", "ERROR", "PENDING", "CANCELLED"}):
                    agy_malformed_step_events += 1
                    continue
                prior_type = agy_step_types.get(index)
                if prior_type is None:
                    agy_step_types[index] = step_type
                elif prior_type != step_type:
                    agy_colliding_indices.add(index)
                if agy_no_command_tool and step_type not in {"tool", "agent_response"}:
                    agy_unknown_step_events += 1
                if step_type == "tool":
                    observed_tool_steps.add(index)
                    if agy_no_command_tool:
                        tool_name = update.get("tool_name")
                        if type(tool_name) is str and tool_name in AGY_NO_COMMAND_ALLOWED_TOOLS:
                            no_command_allowed_steps.add(index)
                        else:
                            no_command_violating_steps.add(index)
                    if state == "DONE":
                        completed_tool_steps.add(index)
                    elif state in {"FAILED", "ERROR"}:
                        failed_agy_steps.add(index)
                elif step_type == "agent_response":
                    agy_agent_observed_steps.add(index)
                    if state != "DONE":
                        continue
                    agy_agent_done_steps.add(index)
                    agy_agent_done_events += 1
                    raw_step_usage = update.get("usage")
                    if (type(raw_step_usage) is not dict
                            or any(type(raw_step_usage.get(field)) is not int
                                   or raw_step_usage[field] < 0 for field in USAGE_FIELDS["agy"])):
                        agy_agent_invalid_events += 1
                        continue
                    parsed = {field: raw_step_usage[field] for field in USAGE_FIELDS["agy"]}
                    if parsed["total_tokens"] != parsed["input_tokens"] + parsed["output_tokens"]:
                        agy_agent_invalid_events += 1
                        continue
                    subset_errors = _usage_subset_errors("agy", parsed, "agy agent_response usage")
                    if subset_errors:
                        agy_agent_invalid_events += 1
                        agy_agent_subset_errors.update(subset_errors)
                        continue
                    prior = agy_agent_usage.get(index)
                    if prior is None:
                        agy_agent_usage[index] = parsed
                    elif prior == parsed:
                        agy_agent_duplicate_events += 1
                    else:
                        agy_agent_conflicting_events += 1
    expected_type = "turn.completed" if provider == "codex" else "result"
    if len(final_events) != 1:
        terminal_errors.append(f"expected exactly one {expected_type}; found {len(final_events)}")
    if last_type != expected_type:
        terminal_errors.append(f"last parsed event is {last_type!r}, expected {expected_type!r}")
    if provider == "agy" and (len(init_models) != 1 or init_models[0] != requested_model):
        terminal_errors.append("agy init.model missing, duplicated or different from requested model")
    if failed_codex_items:
        terminal_errors.append(f"Codex stream contains {failed_codex_items} failed item/turn events")
    if failed_agy_steps:
        terminal_errors.append(f"agy stream contains {len(failed_agy_steps)} failed tool steps")
    no_command_uninspectable = (agy_malformed_step_events + len(agy_colliding_indices)
                                + len(observed_tool_steps - completed_tool_steps)
                                + agy_unknown_step_events)
    if agy_no_command_tool:
        if not observed_tool_steps:
            terminal_errors.append("agy no-command trace has no observable file-writing tool step")
        if no_command_violating_steps:
            terminal_errors.append(
                f"agy no-command trace has {len(no_command_violating_steps)} tool steps outside the file-write allowlist")
        if no_command_uninspectable:
            terminal_errors.append(
                f"agy no-command trace has {no_command_uninspectable} uninspectable step events")
    fields = USAGE_FIELDS[provider]
    values: dict[str, int | None] = {field: None for field in fields}
    final_status: str | None = None
    denied_action_count: int | None = None
    if len(final_events) == 1:
        final = final_events[0][1]
        if provider == "agy":
            final = final.get("result")
            if type(final) is not dict:
                final = {}
                terminal_errors.append("agy final result object missing")
            status = final.get("status")
            final_status = status if type(status) is str else None
            if final_status != "SUCCESS":
                terminal_errors.append(f"agy final status is {final_status!r}, expected 'SUCCESS'")
            denied = final.get("denied_actions")
            if type(denied) is list:
                denied_action_count = len(denied)
                if denied_action_count:
                    terminal_errors.append(f"agy final result reports {denied_action_count} denied actions")
            elif denied is not None:
                terminal_errors.append("agy final denied_actions is malformed")
        raw = final.get("usage")
        if type(raw) is not dict:
            usage_errors.append("final usage object missing")
        else:
            for field in fields:
                value = raw.get(field)
                if type(value) is int and value >= 0:
                    values[field] = value
                else:
                    usage_errors.append(f"final usage.{field} missing or invalid")
            usage_errors.extend(_usage_subset_errors(provider, values, "final usage"))
    preterminal: dict[str, Any] | None = None
    if provider == "agy":
        unfinished_tools = len(observed_tool_steps - completed_tool_steps)
        unfinished_agents = len(agy_agent_observed_steps - agy_agent_done_steps)
        if agy_malformed_step_events:
            usage_errors.append(f"agy has {agy_malformed_step_events} malformed step_update events")
        if agy_colliding_indices:
            usage_errors.append(f"agy has {len(agy_colliding_indices)} step_index collisions across step types")
        if unfinished_tools:
            usage_errors.append(f"agy has {unfinished_tools} tool steps without DONE")
        if unfinished_agents:
            usage_errors.append(f"agy has {unfinished_agents} agent_response steps without DONE")
        final_arithmetic_valid: bool | None = None
        if all(value is not None for value in values.values()):
            final_arithmetic_valid = (
                values["total_tokens"] == values["input_tokens"] + values["output_tokens"])
            if not final_arithmetic_valid:
                usage_errors.append("agy final total_tokens differs from input_tokens + output_tokens")
        step_sum = ({field: sum(step[field] for step in agy_agent_usage.values())
                     for field in USAGE_FIELDS["agy"]} if agy_agent_usage else None)
        step_complete = (bool(agy_agent_usage) and agy_agent_invalid_events == 0
                         and agy_agent_conflicting_events == 0 and agy_malformed_step_events == 0
                         and not agy_colliding_indices and unfinished_tools == 0
                         and unfinished_agents == 0)
        reconciles: bool | None = None
        if not agy_agent_usage:
            usage_errors.append("agy preterminal agent_response usage unavailable")
        if agy_agent_invalid_events:
            usage_errors.append(f"agy has {agy_agent_invalid_events} invalid agent_response usage events")
        usage_errors.extend(sorted(agy_agent_subset_errors))
        if agy_agent_conflicting_events:
            usage_errors.append(
                f"agy has {agy_agent_conflicting_events} contradictory duplicate agent_response usage events")
        if step_complete and final_arithmetic_valid:
            reconciles = step_sum == values
            if not reconciles:
                usage_errors.append("agy preterminal step usage differs from final usage")
        preterminal = {
            "origin": "local_cli_agent_response_done_steps_not_authenticated_provider_receipts",
            "done_events": agy_agent_done_events,
            "unique_steps_with_valid_usage": len(agy_agent_usage),
            "duplicate_identical_events_deduplicated": agy_agent_duplicate_events,
            "invalid_events": agy_agent_invalid_events,
            "contradictory_duplicate_events": agy_agent_conflicting_events,
            "malformed_step_update_events": agy_malformed_step_events,
            "cross_type_index_collisions": len(agy_colliding_indices),
            "unfinished_agent_response_steps": unfinished_agents,
            "final_arithmetic_valid": final_arithmetic_valid,
            "observed_unique_step_sum": step_sum,
            "step_usage_complete": step_complete,
            "reconciles_with_final": reconciles,
        }
    return {
        "origin": "local_cli_jsonl_not_authenticated_provider_receipt",
        "observed_model": init_models[0] if provider == "agy" and len(init_models) == 1 else None,
        "final_status": final_status,
        "denied_action_count": denied_action_count,
        "event_count": event_count,
        "observed_completed_tool_steps": (len(completed_tool_steps) if provider == "agy" else None),
        "observed_unfinished_tool_steps": (len(observed_tool_steps - completed_tool_steps)
                                           if provider == "agy" else None),
        "observed_failed_agy_steps": len(failed_agy_steps) if provider == "agy" else None,
        **({"no_command_tool_trace": {
            "origin": "local_cli_jsonl_observed_steps_only_not_enforced",
            "allowed_tool_steps": len(no_command_allowed_steps - no_command_violating_steps),
            "violating_tool_steps": len(no_command_violating_steps),
            "uninspectable_step_events": no_command_uninspectable,
        }} if agy_no_command_tool else {}),
        "observed_failed_codex_items_partial": failed_codex_items if provider == "codex" else None,
        "final_usage": values,
        "preterminal_step_usage": preterminal,
        "terminal_success": not terminal_errors,
        "terminal_errors": terminal_errors,
        "complete": not terminal_errors and not usage_errors
                    and all(value is not None for value in values.values()),
        "errors": terminal_errors + usage_errors,
    }


def _assembled_prompt(arm: str, common_bytes: bytes, treatment_bytes: bytes,
                      *, agy_no_command_tool: bool = False) -> str:
    """Rebuild the exact prompt so a later observer can bind its policy to bytes."""
    wrapper = (
        "Development-only D-E execution. Work in the current directory. Read only the local "
        "task.md, source_manifest.json and sample_first_complete_week.csv as case inputs. "
        "Do not inspect parent directories, other arms, evaluation rubric, private files or "
        "credentials. Create analysis.py and report.md here, run any checks you actually use, "
        "and state failures honestly. No field action or causal impact is authorized.\n\n"
    )
    treatment_note = (
        "\nThe installed SpecOrganon CLI is .venv/bin/organon in this directory. "
        "Create the case under case/; use signed policy and do not simulate human approval.\n"
        if arm == "T" else ""
    )
    no_command_note = (
        "\nTool policy for this Agy development run: do not call run_command, RunCommand, "
        "a terminal, a shell, or any other code-execution tool. Create analysis.py and "
        "report.md with file-writing tools only. An independent replay may check numbers "
        "after a reviewer inspects analysis.py. If a numerical result cannot be computed "
        "without command tools, leave it unavailable and do not guess. Do not claim that "
        "you executed analysis.py or its tests.\n"
        if agy_no_command_tool else ""
    )
    text = (wrapper + "# Common contract\n" + common_bytes.decode("utf-8")
            + "\n# Assigned arm\n" + treatment_bytes.decode("utf-8")
            + treatment_note + no_command_note)
    # This is an execution instruction, not a cryptographic confinement boundary.
    return text


def _prompt(arm: str, work: Path, *, agy_no_command_tool: bool = False) -> tuple[str, dict[str, str]]:
    common = PROMPTS / "common.md"
    treatment = PROMPTS / f"arm_{arm.lower()}.md"
    if not _regular_file(common) or not _regular_file(treatment):
        raise RunError("common or arm prompt is absent or not a regular file")
    common_bytes = common.read_bytes()
    treatment_bytes = treatment.read_bytes()
    text = _assembled_prompt(arm, common_bytes, treatment_bytes,
                             agy_no_command_tool=agy_no_command_tool)
    return text, {"common_sha256": hashlib.sha256(common_bytes).hexdigest(),
                  "arm_sha256": hashlib.sha256(treatment_bytes).hexdigest(),
                  "assembled_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}


def _prepare_packet(work: Path) -> dict[str, dict[str, Any]]:
    manifest_path = PACKET / "source_manifest.json"
    if not all(_regular_file(PACKET / name) for name in PUBLIC_FILES):
        raise RunError("public case packet has a missing or nonregular file")
    source_records = {name: _file_record(PACKET / name) for name in PUBLIC_FILES}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        pinned = manifest["selection"]["sample_sha256"]
        expected_rows = manifest["selection"]["rows"]
        expected_columns = manifest["selection"]["columns"]
    except (ValueError, KeyError, TypeError) as exc:
        raise RunError("source manifest lacks usable sample metadata") from exc
    if (type(pinned) is not str or type(expected_rows) is not int or expected_rows < 1
            or type(expected_columns) is not list or not all(type(column) is str for column in expected_columns)
            or source_records["sample_first_complete_week.csv"]["sha256"] != pinned):
        raise RunError("source sample differs from manifest digest or metadata is invalid")
    records: dict[str, dict[str, Any]] = {}
    for name in PUBLIC_FILES:
        destination = work / name
        shutil.copyfile(PACKET / name, destination)
        record = _file_record(destination)
        assert record is not None
        records[name] = record
    if records != source_records or any(_file_record(PACKET / name) != source_records[name]
                                        for name in PUBLIC_FILES):
        raise RunError("public packet changed during copy")
    try:
        copied_manifest = json.loads((work / "source_manifest.json").read_text(encoding="utf-8"))
        copied_selection = copied_manifest["selection"]
        with (work / "sample_first_complete_week.csv").open(
            "r", encoding="utf-8-sig", newline=""
        ) as source:
            reader = csv.reader(source, strict=True)
            header = next(reader, None)
            rows = 0
            for row in reader:
                if len(row) != len(header):
                    raise RunError("copied CSV has a malformed row")
                rows += 1
    except (OSError, ValueError, KeyError, TypeError, csv.Error) as exc:
        raise RunError("copied public packet cannot be parsed") from exc
    if (copied_selection.get("sample_sha256") != records["sample_first_complete_week.csv"]["sha256"]
            or copied_selection.get("rows") != rows or copied_selection.get("columns") != header
            or rows != expected_rows or header != expected_columns):
        raise RunError("copied public packet does not match its manifest hash, rows or columns")
    return records


def _setup_toolkit(work: Path, run_dir: Path, wheel: Path | None, timeout_seconds: int,
                   env: dict[str, str]) -> dict[str, Any]:
    if wheel is None or not _regular_file(wheel) or wheel.suffix != ".whl":
        raise RunError("T requires --toolkit-wheel pointing to a regular .whl file")
    uv = shutil.which("uv")
    if uv is None:
        raise RunError("T requires uv for offline installation with dependencies")
    copied = work / wheel.name
    shutil.copyfile(wheel, copied)
    venv = work / ".venv"
    commands = [
        ("toolkit_venv", [sys.executable, "-m", "venv", str(venv)]),
        ("toolkit_install", [uv, "pip", "install", "--offline", "--python", str(venv / "bin/python"),
                             str(copied)]),
    ]
    result: dict[str, Any] = {"wheel": _file_record(copied), "steps": {}}
    for name, argv in commands:
        step = _capture(argv, cwd=work, timeout_seconds=timeout_seconds,
                        stdout_path=run_dir / f"{name}.stdout",
                        stderr_path=run_dir / f"{name}.stderr", env=env)
        result["steps"][name] = step
        if step["timed_out"] or step["exit_code"] != 0:
            raise RunError(f"T toolkit {name} failed; see private raw streams")
    cli = venv / "bin" / "organon"
    if not _regular_file(cli):
        raise RunError("T toolkit install did not create .venv/bin/organon")
    probe = run_dir / "toolkit_probe"
    for name, argv in (
        ("toolkit_init", [str(cli), "init", str(probe), "--title", "D-E installation probe",
                          "--domain", "building-energy", "--actor", "agent:preflight",
                          "--approval-policy", "signed"]),
        ("toolkit_status", [str(cli), "status", str(probe)]),
    ):
        step = _capture(argv, cwd=work, timeout_seconds=timeout_seconds,
                        stdout_path=run_dir / f"{name}.stdout",
                        stderr_path=run_dir / f"{name}.stderr", env=env)
        result["steps"][name] = step
        if step["timed_out"] or step["exit_code"] != 0:
            raise RunError(f"T toolkit {name} failed; see private raw streams")
    try:
        status = json.loads((run_dir / "toolkit_status.stdout").read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise RunError("T toolkit status did not return JSON") from exc
    if (type(status) is not dict or type(status.get("project")) is not dict
            or status["project"].get("approval_policy") != "signed"):
        raise RunError("T toolkit preflight did not prove signed policy")
    result["signed_policy_verified_in_local_probe"] = True
    result["toolkit_files_fingerprint_sha256"] = _toolkit_fingerprint(work)
    if result["toolkit_files_fingerprint_sha256"] is None:
        raise RunError("T toolkit installation files could not be fingerprinted")
    return result


def _inspect_t_ledger(work: Path, run_dir: Path, timeout_seconds: int,
                      env: dict[str, str], expected_toolkit_fingerprint: str) -> dict[str, Any]:
    case = work / "case"
    ledger = case / "organon.json"
    result: dict[str, Any] = {"present": False, "signed_policy": False,
                              "event_count": None, "sha256": None,
                              "independent_cli_status": None,
                              "toolkit_files_unchanged": False,
                              "model_cli_invocations_proven": False}
    result["toolkit_files_unchanged"] = (
        _toolkit_fingerprint(work) == expected_toolkit_fingerprint)
    if not result["toolkit_files_unchanged"]:
        return result
    if case.is_symlink() or not case.is_dir() or not _regular_file(ledger):
        return result
    result["present"] = True
    result["sha256"] = _sha256(ledger)
    try:
        data = json.loads(ledger.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return result
    if type(data) is not dict:
        return result
    project = data.get("project")
    events = data.get("events")
    result["signed_policy"] = (type(project) is dict
                               and project.get("approval_policy") == "signed")
    if type(events) is list:
        result["event_count"] = len(events)
    cli = work / ".venv" / "bin" / "organon"
    status = _capture([str(cli), "status", str(case)], cwd=work,
                      timeout_seconds=timeout_seconds,
                      stdout_path=run_dir / "toolkit_after_status.stdout",
                      stderr_path=run_dir / "toolkit_after_status.stderr", env=env)
    result["independent_cli_status"] = status
    if status["exit_code"] == 0 and not status["timed_out"]:
        try:
            observed = json.loads((run_dir / "toolkit_after_status.stdout").read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
        else:
            result["signed_policy"] = (result["signed_policy"]
                                       and type(observed) is dict
                                       and type(observed.get("project")) is dict
                                       and observed["project"].get("approval_policy") == "signed")
    else:
        result["signed_policy"] = False
    return result


def run_development_arm(
    *, arm: str, provider: str, model: str, effort: str, output_root: Path,
    timeout_seconds: int = 600, replay_timeout_seconds: int = 90,
    setup_timeout_seconds: int = 180, toolkit_wheel: Path | None = None,
    agy_no_command_tool: bool = False,
) -> tuple[Path, dict[str, Any]]:
    """Execute exactly one arm and return its private run path and sanitized summary."""
    if arm not in {"N", "S", "T"} or provider not in {"codex", "agy"}:
        raise RunError("arm must be N/S/T and provider must be codex/agy")
    if agy_no_command_tool and (provider != "agy" or arm == "T"):
        raise RunError("--agy-no-command-tool requires Agy N/S")
    if not model.strip() or not effort.strip():
        raise RunError("model and effort must both be explicit nonempty values")
    if re.fullmatch(r"[A-Za-z0-9._:/-]+", model) is None:
        raise RunError("model must be a simple CLI model identifier")
    valid_efforts = ({"low", "medium", "high", "xhigh", "max", "ultra"}
                     if provider == "codex" else {"low", "medium", "high", "max"})
    if effort not in valid_efforts:
        raise RunError(f"effort must be one of {sorted(valid_efforts)} for {provider}")
    if any(type(value) is not int or value < 1 for value in
           (timeout_seconds, replay_timeout_seconds, setup_timeout_seconds)):
        raise RunError("all timeout values must be positive integer seconds")
    executable = shutil.which("codex" if provider == "codex" else "agy")
    if executable is None:
        raise RunError(f"{provider} executable is unavailable")
    if arm == "T" and (toolkit_wheel is None or not _regular_file(toolkit_wheel)):
        raise RunError("T requires a real toolkit wheel; no model call was made")
    output_root = output_root.expanduser().resolve()
    if toolkit_wheel is not None:
        toolkit_wheel = toolkit_wheel.expanduser().resolve()
    previous_umask = os.umask(0o077)
    try:
        run_dir = _private_run_dir(output_root)
        work = run_dir / "work"
        work.mkdir(mode=0o700)
        packet = _prepare_packet(work)
        prompt, prompt_hashes = _prompt(arm, work, agy_no_command_tool=agy_no_command_tool)
        (run_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
        env = _clean_environment()
        summary: dict[str, Any] = {
            "schema": 1, "classification": "exposed_development_unsealed",
            "arm": arm, "provider_cli": provider, "requested_model": model,
            "requested_effort": effort, "packet": packet, "prompt": prompt_hashes,
            "tool_policy": "no_command_tool" if agy_no_command_tool else "default",
            "timeout_seconds": timeout_seconds, "replay_timeout_seconds": replay_timeout_seconds,
            "packet_after": None, "packet_unchanged": None,
            "toolkit": None, "cli": None, "cli_usage": None,
            "artifacts": {}, "analysis_replay": None, "t_ledger": None,
            "execution_status": "preparing",
            "controlled_comparison_eligible": False,
            "limitations": ["development case and prompts are exposed; no sealed assignment",
                            "local CLI telemetry is not an authenticated provider receipt",
                            "no OS file-access isolation or global tool/token budget is proven",
                            "generated analysis replay requires a later hash-bound opt-in; default replay is not filesystem/network isolated"],
            "provider_request_id": None, "price": None, "cost": None,
        }
        _write_json(run_dir / "run.json", summary)
        if arm == "T":
            summary["limitations"].append(
                "T toolkit fingerprint covers only the Organon entrypoint and package Python sources, not dependencies")
        if agy_no_command_tool:
            summary["limitations"].append(
                "No-command Agy pilot checks reported tool steps only; it does not enforce a provider or OS prohibition or detect unreported calls, and is not comparable with T CLI execution")
        try:
            # The prompt hashes describe the bytes actually delivered to the model.
            # Copies must match them before any CLI or toolkit preparation starts.
            try:
                shutil.copyfile(PROMPTS / "common.md", work / "common.md")
                shutil.copyfile(PROMPTS / f"arm_{arm.lower()}.md", work / "arm.md")
            except OSError as exc:
                raise RunError("assigned prompt files could not be copied") from exc
            if (_sha256(work / "common.md") != prompt_hashes["common_sha256"]
                    or _sha256(work / "arm.md") != prompt_hashes["arm_sha256"]):
                raise RunError("assigned prompt copies differ from the bytes used to build the prompt")
            if arm == "T":
                summary["toolkit"] = _setup_toolkit(work, run_dir, toolkit_wheel,
                                                    setup_timeout_seconds, env)
                _write_json(run_dir / "run.json", summary)
            if provider == "codex":
                argv = [executable, "exec", "--json", "--ephemeral", "--ignore-user-config",
                        "--skip-git-repo-check", "-C", str(work), "-s", "workspace-write",
                        "-m", model, "-c", f'model_reasoning_effort="{effort}"', "-"]
                stdin_text = prompt
            else:
                argv = [executable, "--print", prompt, "--output-format", "stream-json",
                        "--model", model, "--effort", effort, "--print-timeout",
                        f"{timeout_seconds}s", "--new-project", "--sandbox", "--mode",
                        "accept-edits", "--disable-slash-commands"]
                stdin_text = None
            summary["cli_mode"] = ({"codex_sandbox": "workspace-write"} if provider == "codex"
                                   else {"agy_sandbox": True, "agy_mode": "accept-edits"})
            _write_json(run_dir / "run.json", summary)
            result = _capture(argv, cwd=work, timeout_seconds=timeout_seconds,
                              stdout_path=run_dir / "cli.stdout.jsonl",
                              stderr_path=run_dir / "cli.stderr", stdin_text=stdin_text, env=env)
            summary["cli"] = result
            summary["cli_usage"] = _parse_usage(
                provider, run_dir / "cli.stdout.jsonl", model,
                agy_no_command_tool=agy_no_command_tool,
            )
            summary["packet_after"] = {
                name: _file_record(work / name) for name in PUBLIC_FILES
            }
            summary["packet_unchanged"] = summary["packet_after"] == packet
            for name in ("analysis.py", "report.md"):
                summary["artifacts"][name] = _file_record(work / name)
            if arm == "T":
                summary["t_ledger"] = _inspect_t_ledger(
                    work, run_dir, setup_timeout_seconds, env,
                    summary["toolkit"]["toolkit_files_fingerprint_sha256"])
            if result["timed_out"]:
                summary["execution_status"] = "cli_timeout"
            elif result["exit_code"] != 0:
                summary["execution_status"] = "cli_failure"
            elif not summary["cli_usage"]["terminal_success"]:
                summary["execution_status"] = "cli_internal_failure"
            elif not summary["packet_unchanged"]:
                summary["execution_status"] = "public_packet_mutated"
            elif any(value is None for value in summary["artifacts"].values()):
                summary["execution_status"] = "required_artifact_missing"
            elif arm == "T" and (not summary["t_ledger"]["present"]
                                 or not summary["t_ledger"]["signed_policy"]
                                 or not isinstance(summary["t_ledger"]["event_count"], int)
                                 or summary["t_ledger"]["event_count"] < 1
                                 or not summary["t_ledger"]["toolkit_files_unchanged"]):
                summary["execution_status"] = "t_signed_ledger_missing_or_invalid"
            else:
                summary["execution_status"] = "artifacts_ready_for_inspection"
            if not summary["cli_usage"]["complete"]:
                summary["limitations"].append("final local CLI usage is missing or malformed")
            if summary["cli_usage"]["observed_failed_codex_items_partial"]:
                summary["limitations"].append("local Codex stream contains failed items")
        except RunError as exc:
            summary["execution_status"] = "preflight_failure"
            summary["preflight_error"] = str(exc)
        finally:
            _write_json(run_dir / "run.json", summary)
        return run_dir, summary
    finally:
        os.umask(previous_umask)


def _material_mismatches(run_dir: Path, summary: dict[str, Any]) -> list[str]:
    """Compare the byte commitments of every fixed input and produced artifact."""
    work = run_dir / "work"
    mismatches: list[str] = []
    for name in ("analysis.py", "report.md"):
        if _file_record(work / name) != summary.get("artifacts", {}).get(name):
            mismatches.append(name)
    for name in PUBLIC_FILES:
        if _file_record(work / name) != summary.get("packet", {}).get(name):
            mismatches.append(name)
    prompt = summary.get("prompt", {})
    for path, expected in (
        (run_dir / "prompt.txt", prompt.get("assembled_sha256")),
        (work / "common.md", prompt.get("common_sha256")),
        (work / "arm.md", prompt.get("arm_sha256")),
    ):
        if not _regular_file(path) or _sha256(path) != expected:
            mismatches.append(path.name)
    cli = summary.get("cli", {})
    for name, key in (("cli.stdout.jsonl", "stdout"), ("cli.stderr", "stderr")):
        if _file_record(run_dir / name) != cli.get(key):
            mismatches.append(name)
    if summary.get("arm") == "T":
        ledger = summary.get("t_ledger", {})
        case = work / "case"
        ledger_path = case / "organon.json"
        if (case.is_symlink() or not _regular_file(ledger_path)
                or _sha256(ledger_path) != ledger.get("sha256")):
            mismatches.append("case/organon.json")
        toolkit = summary.get("toolkit", {})
        if _toolkit_fingerprint(work) != toolkit.get("toolkit_files_fingerprint_sha256"):
            mismatches.append("toolkit_files")
        wheel_name = next(work.glob("*.whl"), None)
        if wheel_name is None or _file_record(wheel_name) != toolkit.get("wheel"):
            mismatches.append("toolkit_wheel")
    return mismatches


def replay_run_dir(
    run_dir: Path, expected_analysis_sha256: str, *, sandboxed: bool = False
) -> dict[str, Any]:
    """Replay a reviewed script only if its bytes and the packet still match the run.

    The caller must inspect analysis.py before supplying its digest. The
    optional Linux sandbox is a local replay safeguard, not provider isolation.
    Without it, Python -I and a clean environment do not restrict file/network
    access by generated code.
    """
    if re.fullmatch(r"[0-9a-f]{64}", expected_analysis_sha256) is None:
        raise RunError("--expected-analysis-sha256 must be a lowercase SHA-256 hex digest")
    run_dir = run_dir.expanduser().resolve()
    work = run_dir / "work"
    record = run_dir / "run.json"
    if not _regular_file(record) or work.is_symlink() or not work.is_dir():
        raise RunError("run directory, summary or work directory is missing or unsafe")
    try:
        summary = json.loads(record.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RunError("run summary is not valid JSON") from exc
    if type(summary) is not dict or summary.get("classification") != "exposed_development_unsealed":
        raise RunError("run summary is not a D-E exposed development record")
    if summary.get("execution_status") != "artifacts_ready_for_inspection":
        raise RunError("run is not in artifacts_ready_for_inspection state")
    artifacts = summary.get("artifacts")
    if type(artifacts) is not dict or type(artifacts.get("analysis.py")) is not dict:
        raise RunError("analysis.py is not recorded as a regular artifact")
    if artifacts["analysis.py"].get("sha256") != expected_analysis_sha256:
        raise RunError("reviewed analysis digest differs from the recorded artifact")
    if summary.get("arm") == "T":
        ledger = summary.get("t_ledger")
        if type(ledger) is not dict or not ledger.get("signed_policy"):
            raise RunError("T signed ledger was not verified in the model run")
    mismatches = _material_mismatches(run_dir, summary)
    if mismatches:
        raise RunError(f"{mismatches[0]} changed after the model run")
    if (run_dir / "analysis_replay.stdout").exists() or (run_dir / "analysis_replay.stderr").exists():
        raise RunError("replay streams already exist; no overwrite or implicit retry")
    timeout = summary.get("replay_timeout_seconds")
    if type(timeout) is not int or timeout < 1:
        raise RunError("recorded replay wall timeout is invalid")
    previous_umask = os.umask(0o077)
    try:
        summary_before = _file_record(record)
        stdout_path = run_dir / "analysis_replay.stdout"
        stderr_path = run_dir / "analysis_replay.stderr"
        if sandboxed:
            from local_replay_sandbox import (
                SandboxError, SandboxUnavailable, default_python_runtime_roots,
                run_sandboxed,
            )

            started = _utc_now()
            try:
                restricted = run_sandboxed(
                    argv=[sys.executable, "-I", "analysis.py"], cwd=work,
                    read_roots=[work], runtime_roots=default_python_runtime_roots(),
                    write_roots=[],
                    stdout_path=stdout_path, stderr_path=stderr_path,
                    timeout_seconds=timeout, cpu_seconds=timeout,
                    address_space_bytes=512 * 1024 * 1024,
                    file_bytes_per_file=16 * 1024 * 1024,
                    env={"HOME": str(work), "TMPDIR": str(work)},
                )
            except (SandboxError, SandboxUnavailable) as exc:
                raise RunError(f"sandboxed replay cannot start: {exc}") from exc
            replay = {
                "started_at_utc": started, "ended_at_utc": _utc_now(),
                "wall_seconds": round(restricted.duration_seconds, 3),
                "exit_code": restricted.exit_code,
                "timed_out": restricted.timed_out,
                "launch_error": restricted.launch_error,
                "stdout": _file_record(stdout_path), "stderr": _file_record(stderr_path),
                "sandbox": {
                    "backend": "linux_landlock_seccomp_rlimit_single_process",
                    "enforced": restricted.launch_error is None,
                    "landlock_abi": restricted.landlock_abi,
                    "cpu_seconds": timeout,
                    "address_space_bytes": 512 * 1024 * 1024,
                    "aggregate_memory_enforced": False,
                    "file_bytes_per_file": 16 * 1024 * 1024,
                    "aggregate_file_bytes_enforced": False,
                    "path_opened_writes_allowed": False,
                },
            }
        else:
            replay = _capture([sys.executable, "-I", "analysis.py"], cwd=work,
                              timeout_seconds=timeout, stdout_path=stdout_path,
                              stderr_path=stderr_path,
                              env=_replay_environment(run_dir))
            replay["sandbox"] = {"backend": "none", "enforced": False}
        summary["analysis_replay"] = replay
        summary["reviewed_analysis_sha256"] = expected_analysis_sha256
        mismatches = _material_mismatches(run_dir, summary)
        if _file_record(record) != summary_before:
            mismatches.append("run.json")
        summary["replay_material_mismatches"] = mismatches
        if mismatches:
            summary["execution_status"] = "replay_artifacts_mutated"
        elif replay["launch_error"] is not None:
            summary["execution_status"] = "analysis_replay_launch_failure"
        elif replay["timed_out"]:
            summary["execution_status"] = "analysis_replay_timeout"
        elif replay["exit_code"] != 0:
            summary["execution_status"] = "analysis_replay_failure"
        else:
            summary["execution_status"] = "output_replayed"
        _write_json(record, summary)
        return summary
    finally:
        os.umask(previous_umask)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", choices=("N", "S", "T"))
    parser.add_argument("--provider", choices=("codex", "agy"))
    parser.add_argument("--model")
    parser.add_argument("--effort")
    parser.add_argument("--output-root", type=Path,
                        help="operator-selected private directory; raw CLI traces are written here")
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--replay-timeout-seconds", type=int, default=90)
    parser.add_argument("--setup-timeout-seconds", type=int, default=180)
    parser.add_argument("--toolkit-wheel", type=Path, help="required for T; installed offline with dependencies")
    parser.add_argument("--agy-no-command-tool", action="store_true",
                        help="opt in to an N/S Agy prompt that forbids shell/command tools")
    parser.add_argument("--replay-run-dir", type=Path,
                        help="second step, after reviewing analysis.py; makes no model call")
    parser.add_argument("--expected-analysis-sha256",
                        help="digest of the exact analysis.py bytes inspected before replay")
    parser.add_argument("--sandboxed-replay", action="store_true",
                        help="enforce local Linux Landlock/seccomp/rlimit limits on replay")
    args = parser.parse_args(argv)
    try:
        if args.replay_run_dir is not None:
            if not args.expected_analysis_sha256:
                raise RunError("replay requires --expected-analysis-sha256")
            if any(value is not None for value in
                   (args.arm, args.provider, args.model, args.effort, args.output_root, args.toolkit_wheel)) \
                    or args.agy_no_command_tool:
                raise RunError("replay accepts only run directory and reviewed analysis digest")
            run_dir = args.replay_run_dir
            summary = replay_run_dir(
                run_dir, args.expected_analysis_sha256,
                sandboxed=args.sandboxed_replay,
            )
        else:
            if args.expected_analysis_sha256 is not None or args.sandboxed_replay:
                raise RunError("replay options require --replay-run-dir")
            if any(value is None for value in
                   (args.arm, args.provider, args.model, args.effort, args.output_root)):
                raise RunError("a model run requires arm, provider, model, effort and output-root")
            run_dir, summary = run_development_arm(
                arm=args.arm, provider=args.provider, model=args.model, effort=args.effort,
                output_root=args.output_root, timeout_seconds=args.timeout_seconds,
                replay_timeout_seconds=args.replay_timeout_seconds,
                setup_timeout_seconds=args.setup_timeout_seconds,
                toolkit_wheel=args.toolkit_wheel,
                agy_no_command_tool=args.agy_no_command_tool,
            )
    except (RunError, OSError) as exc:
        parser.exit(2, f"run_development_arm: {exc}\n")
    print(json.dumps({"run_dir": str(run_dir), "status": summary["execution_status"],
                      "usage_complete": summary["cli_usage"]["complete"] if summary["cli_usage"] else False},
                     ensure_ascii=False, sort_keys=True))
    return 0 if summary["execution_status"] in {
        "artifacts_ready_for_inspection", "output_replayed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
