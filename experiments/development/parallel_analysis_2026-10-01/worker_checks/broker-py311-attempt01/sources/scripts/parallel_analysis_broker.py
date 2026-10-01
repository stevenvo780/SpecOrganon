"""Opt-in D113 host analysis for private D115 branches under one parent claim.

The original broker and launcher remain unchanged. A v2 overlay pins the original
v1 branch manifest, the exact fixed launcher, and this extension's source closure.
This remains a reviewed same-UID development primitive, not a hostile-code boundary.
"""

from __future__ import annotations

import ast
import math
import os
import re
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import development_analysis_tool as launcher
import parallel_tool_broker as legacy
from local_replay_sandbox import default_python_runtime_roots, run_sandboxed
from staged_tool_session import (
    SessionError,
    _analysis_output,
    _analysis_source,
    _publish_analysis_metrics,
)
from tool_policy import _read_bounded_file


BrokerError = legacy.BrokerError
CONTRACT = "development_readonly_analysis_d113_v1"
CLASSIFICATION = "development_parallel_analysis_branches_unsealed"
MANIFEST_NAME = "analysis_branch_manifest.json"
MAX_ANALYSIS_STREAM_BYTES = 8 * 1024 * 1024
RESERVATION_FIELDS = {
    "schema", "manifest_sha256", "claim_sha256", "task_id", "request_id", "call_id",
    "function_name", "profile", "arguments", "arguments_sha256", "global_ordinal",
    "local_ordinal", "work_before_sha256",
}
RECEIPT_FIELDS = {
    "schema", "reservation_sha256", "manifest_sha256", "claim_sha256", "task_id",
    "request_id", "call_id", "function_name", "profile", "global_ordinal",
    "local_ordinal", "stdout_sha256", "stderr_sha256", "stdout_bytes", "stderr_bytes",
    "sandbox", "status", "output", "output_json", "work_after", "work_after_sha256",
}
ANALYSIS_RESERVATION_FIELDS = {"analysis_contract", "analysis_script_sha256",
                               "old_metrics_sha256", "executable_sha256"}
ANALYSIS_RECEIPT_FIELDS = ANALYSIS_RESERVATION_FIELDS | {
    "analysis_status", "analysis_diagnostic", "analysis_metrics_sha256",
    "analysis_work_before", "analysis_work_after_child", "analysis_work_after_child_sha256",
}


def _sources() -> dict[str, str]:
    """Freeze local transitive imports, including the D113 host and launcher."""
    root = Path(__file__).resolve().parent
    pending, seen, captured = [Path(__file__).stem], set(), {}
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        path = root / f"{name}.py"
        raw = _read_bounded_file(path, "analysis source closure", legacy.MAX_EXECUTABLE_BYTES)
        captured[f"scripts/{name}.py"] = legacy._sha(raw)
        seen.add(name)
        for node in ast.walk(ast.parse(raw)):
            names = ([item.name.split(".")[0] for item in node.names]
                     if isinstance(node, ast.Import) else
                     [node.module.split(".")[0]]
                     if isinstance(node, ast.ImportFrom) and node.module else [])
            pending.extend(item for item in names if (root / f"{item}.py").is_file())
    if any(legacy._sha(_read_bounded_file(root / Path(name).name, "analysis source closure",
                                        legacy.MAX_EXECUTABLE_BYTES)) != digest
           for name, digest in captured.items()):
        raise BrokerError("analysis source closure changed during capture")
    return dict(sorted(captured.items()))


def _launcher_bytes() -> bytes:
    return (f"#!{sys.executable}\n" + launcher._RUNTIME).encode("utf-8")


def _analysis_functions(branch: dict) -> list[dict]:
    functions = branch["functions"]
    selected = [fn for fn in functions if fn["profile"] == "analysis_readonly"]
    if len(selected) != 1 or not any(fn["profile"] == "workspace" for fn in functions):
        raise BrokerError("analysis branches require workspace and one fixed analysis function")
    for fn in selected:
        raw, current = legacy._executable(Path(fn["path"]))
        if raw != _launcher_bytes() or current != {
            key: fn[key] for key in ("path", "sha256", "bytes", "identity")
        }:
            raise BrokerError("analysis function differs from the exact D113 launcher")
    if any(item["path"] == "metrics.json" for item in branch["initial_work"]["files"]):
        raise BrokerError("initial metrics.json has no host analysis provenance")
    return selected


def _legacy_manifest(binding: dict) -> dict:
    if type(binding) is not dict or set(binding) != {"path", "sha256"}:
        raise BrokerError("legacy manifest binding is invalid")
    # The existing closed validator reads only these two attributes; no globals
    # or live broker state are changed when reusing it for the pinned v1 file.
    reader = SimpleNamespace(path=legacy._absolute(binding["path"], "legacy manifest"),
                             sha256=legacy._digest(binding["sha256"], "legacy manifest digest"))
    return legacy.ParallelToolBroker._manifest(reader)


def prepare_analysis_branch_manifest(root: Path, specifications: list[dict]) -> dict:
    """Create an explicit v2 overlay; v1 specifications and bytes stay intact."""
    sources = _sources()
    if type(specifications) is not list:
        raise BrokerError("analysis specifications must be a list")
    # Validate the opted-in launcher before publishing the underlying manifest.
    for spec in specifications:
        if type(spec) is not dict or type(spec.get("functions")) is not list:
            raise BrokerError("analysis branch specification is invalid")
        functions = spec["functions"]
        if any(type(fn) is not dict for fn in functions):
            raise BrokerError("analysis function specification is invalid")
        selected = [fn for fn in functions if fn.get("profile") == "analysis_readonly"]
        if len(selected) != 1 or not any(fn.get("profile") == "workspace" for fn in functions):
            raise BrokerError("analysis branches require workspace and one fixed analysis function")
        tool = legacy._absolute(selected[0].get("executable"), "analysis executable")
        if legacy._executable(tool)[0] != _launcher_bytes():
            raise BrokerError("analysis function differs from the exact D113 launcher")
        if any(item["path"] == "metrics.json" for item in
               legacy._work(legacy._absolute(spec.get("stage_dir"), "analysis stage"))["files"]):
            raise BrokerError("initial metrics.json has no host analysis provenance")
    binding = legacy.prepare_branch_manifest(root, specifications)
    original = _legacy_manifest(binding)
    for branch in original["branches"]:
        _analysis_functions(branch)
    if sources != _sources():
        raise BrokerError("analysis source closure changed before publication")
    manifest = {**original, "schema": 2, "classification": CLASSIFICATION,
                "analysis_contract": CONTRACT, "legacy_manifest": binding,
                "source_bindings": sources}
    path = Path(root) / MANIFEST_NAME
    return {"path": str(path), "sha256": legacy._new_file(path, legacy._canonical(manifest))}


def _file(work: dict, name: str) -> dict | None:
    return next((item for item in work["files"] if item["path"] == name), None)


def _metrics_transition(before: dict, after: dict, parsed: dict | None) -> None:
    """Check the actual inventory delta produced solely by host metrics writes."""
    if (not before["complete"] or not after["complete"]
            or {item["path"]: item for item in before["files"] if item["path"] != "metrics.json"}
            != {item["path"]: item for item in after["files"] if item["path"] != "metrics.json"}
            or set(before["directories"]) != set(after["directories"])):
        raise BrokerError("host changed work outside metrics.json")
    for name, state in before["directories"].items():
        current = after["directories"][name]
        if (state != current if name else state[:5] != current[:5]):
            raise BrokerError("host changed work directory identity")
    metrics = _file(after, "metrics.json")
    if parsed is None:
        if metrics is not None:
            raise BrokerError("invalid analysis retained stale metrics.json")
    else:
        raw = legacy._canonical(parsed)
        if (metrics is None or metrics["bytes"] != len(raw)
                or metrics["sha256"] != legacy._sha(raw)
                or type(metrics.get("state")) is not list or len(metrics["state"]) != 8
                or metrics["state"][2] & 0o7777 != 0o600
                or metrics["state"][3] != os.geteuid() or metrics["state"][4] != 1
                or metrics["state"][5] != len(raw)):
            raise BrokerError("host metrics inventory differs from validated analysis")


def _feedback(status: str, diagnostic: str, stdout: bytes, parsed: dict | None) -> str:
    return legacy._canonical(parsed if parsed is not None else {
        "ok": False, "analysis_status": status, "diagnostic": diagnostic,
        "raw_stdout_bytes": len(stdout), "raw_stdout_sha256": legacy._sha(stdout),
    }).decode().strip()


class AnalysisParallelToolBroker(legacy.ParallelToolBroker):
    """D113 host metrics with D115 global reservations and private ownership."""

    def _manifest(self) -> dict:
        raw = _read_bounded_file(self.path, "analysis branch manifest", legacy.MAX_MANIFEST_BYTES)
        if legacy._sha(raw) != self.sha256:
            raise BrokerError("analysis branch manifest digest changed")
        manifest = legacy._parse(raw, "analysis branch manifest", legacy.MAX_MANIFEST_BYTES)
        if (type(manifest) is not dict or legacy._canonical(manifest) != raw
                or set(manifest) != {"schema", "classification", "root", "root_identity", "branches",
                                     "analysis_contract", "legacy_manifest", "source_bindings"}
                or type(manifest["schema"]) is not int or manifest["schema"] != 2
                or manifest["classification"] != CLASSIFICATION
                or manifest["analysis_contract"] != CONTRACT
                or manifest["source_bindings"] != _sources()):
            raise BrokerError("analysis manifest contract or source closure changed")
        original = _legacy_manifest(manifest["legacy_manifest"])
        if (Path(manifest["legacy_manifest"]["path"]) != Path(original["root"]) / legacy.MANIFEST_NAME
                or any(manifest[key] != original[key] for key in ("root", "root_identity", "branches"))):
            raise BrokerError("analysis overlay differs from frozen legacy branches")
        for branch in manifest["branches"]:
            _analysis_functions(branch)
        return manifest

    def journal_roots(self) -> list[Path]:
        return super().journal_roots() + [Path(self.manifest["legacy_manifest"]["path"])]

    def _records(self) -> tuple[list[tuple[int, dict, dict | None]], dict[str, dict]]:
        reservations = sorted(path.name for path in self.reservations.iterdir())
        receipts = sorted(path.name for path in self.receipts.iterdir())
        if (any(re.fullmatch(r"[0-9]{4}\.json", name) is None for name in reservations + receipts)
                or not set(receipts) <= set(reservations)
                or reservations != [f"{number:04d}.json" for number in range(1, len(reservations) + 1)]):
            raise BrokerError("global analysis journal ordinals or files changed")
        branches = {item["task_id"]: item for item in self.manifest["branches"]}
        last_work = {task: item["initial_work"] for task, item in branches.items()}
        counts, calls, records, pending = dict.fromkeys(branches, 0), set(), [], set()
        valid_metrics: dict[str, str | None] = dict.fromkeys(branches)
        for ordinal, name in enumerate(reservations, 1):
            reservation = legacy._read_json(self.reservations / name)
            analysis = reservation.get("profile") == "analysis_readonly"
            fields = RESERVATION_FIELDS | (ANALYSIS_RESERVATION_FIELDS if analysis else set())
            if (set(reservation) != fields or type(reservation["schema"]) is not int
                    or reservation["schema"] != (2 if analysis else 1)
                    or reservation["manifest_sha256"] != self.sha256
                    or type(reservation["global_ordinal"]) is not int
                    or reservation["global_ordinal"] != ordinal):
                raise BrokerError("analysis tool reservation is malformed")
            task = reservation["task_id"]
            if task not in branches or task in pending:
                raise BrokerError("tool reservation has unknown or pending branch")
            for field in ("request_id", "call_id", "function_name"):
                legacy._identifier(reservation[field], field)
            if not reservation["request_id"].startswith(task + "-turn-") or reservation["call_id"] in calls:
                raise BrokerError("tool request ownership or unique call ID changed")
            calls.add(reservation["call_id"])
            counts[task] += 1
            before = last_work[task]
            if (type(reservation["local_ordinal"]) is not int
                    or reservation["local_ordinal"] != counts[task]
                    or reservation["work_before_sha256"] != legacy._sha(legacy._canonical(before))):
                raise BrokerError("branch work sequence changed")
            selected = next((fn for fn in branches[task]["functions"]
                             if fn["name"] == reservation["function_name"]), None)
            if selected is None or selected["profile"] != reservation["profile"]:
                raise BrokerError("reservation function was not delegated")
            args = reservation["arguments"]
            parsed_args = legacy._parse(args, "reserved arguments", legacy.MAX_ARGUMENT_BYTES)
            if (type(args) is not str or type(parsed_args) is not dict
                    or legacy._canonical(parsed_args).decode().strip() != args
                    or legacy._sha(args.encode()) != reservation["arguments_sha256"]):
                raise BrokerError("reserved arguments changed")
            if analysis:
                source, previous = _file(before, "analysis.py"), _file(before, "metrics.json")
                if (reservation["analysis_contract"] != CONTRACT
                        or reservation["executable_sha256"] != selected["sha256"]
                        or set(parsed_args) != {"script_sha256"}
                        or parsed_args["script_sha256"] != reservation["analysis_script_sha256"]
                        or source is None or source["sha256"] != parsed_args["script_sha256"]
                        or not 0 < source["bytes"] <= 256 * 1024
                        or reservation["old_metrics_sha256"] != (previous["sha256"] if previous else None)
                        or (previous is not None and previous["sha256"] != valid_metrics[task])):
                    raise BrokerError("analysis source or prior metrics provenance changed")
            receipt = None
            if name in receipts:
                receipt = legacy._read_json(self.receipts / name)
                fields = RECEIPT_FIELDS | (ANALYSIS_RECEIPT_FIELDS if analysis else set())
                common = ("manifest_sha256", "claim_sha256", "task_id", "request_id", "call_id",
                          "function_name", "profile", "global_ordinal", "local_ordinal")
                if (set(receipt) != fields or type(receipt["schema"]) is not int
                        or receipt["schema"] != (2 if analysis else 1)
                        or receipt["reservation_sha256"] != legacy._sha(legacy._canonical(reservation))
                        or any(receipt[field] != reservation[field] for field in common)
                        or receipt["work_after_sha256"] != legacy._sha(legacy._canonical(receipt["work_after"]))):
                    raise BrokerError("tool receipt differs from reservation or work inventory")
                stream_dir = self.broker_dir / f"{ordinal:04d}"
                maximum = MAX_ANALYSIS_STREAM_BYTES if analysis else legacy.MAX_STREAM_BYTES
                streams = {stream: _read_bounded_file(stream_dir / stream, f"analysis {stream}", maximum)
                           for stream in ("stdout", "stderr")}
                if any(type(receipt[f"{stream}_bytes"]) is not int
                       or receipt[f"{stream}_bytes"] != len(raw)
                       or receipt[f"{stream}_sha256"] != legacy._sha(raw)
                       for stream, raw in streams.items()):
                    raise BrokerError("tool stream changed")
                sandbox = receipt["sandbox"]
                if (type(sandbox) is not dict or set(sandbox) != {
                        "exit_code", "timed_out", "launch_error", "landlock_abi", "duration_seconds",
                        "sealed_executable_sha256", "host_elapsed_seconds"}
                        or sandbox["timed_out"] is not False or sandbox["launch_error"] is not None
                        or sandbox["sealed_executable_sha256"] != selected["sha256"]):
                    raise BrokerError("tool terminal sandbox seal changed")
                if analysis:
                    if (type(sandbox["exit_code"]) is not int or sandbox["exit_code"] < 0
                            or any(receipt[field] != reservation[field] for field in ANALYSIS_RESERVATION_FIELDS)
                            or receipt["analysis_work_before"] != before
                            or receipt["analysis_work_after_child"] != before
                            or receipt["analysis_work_after_child_sha256"] != reservation["work_before_sha256"]):
                        raise BrokerError("analysis participant inventory or binding changed")
                    status, diagnostic, _, _, parsed = _analysis_output(
                        stream_dir / "stdout", sandbox["exit_code"], MAX_ANALYSIS_STREAM_BYTES)
                    metrics_sha = legacy._sha(legacy._canonical(parsed)) if parsed is not None else None
                    if (receipt["analysis_status"] != status or receipt["analysis_diagnostic"] != diagnostic
                            or receipt["analysis_metrics_sha256"] != metrics_sha
                            or receipt["status"] != "success" or receipt["output_json"] != parsed
                            or receipt["output"] != _feedback(status, diagnostic, streams["stdout"], parsed)):
                        raise BrokerError("analysis feedback or metrics provenance changed")
                    _metrics_transition(before, receipt["work_after"], parsed)
                    valid_metrics[task] = metrics_sha
                else:
                    parsed = None
                    try:
                        candidate = legacy._parse(streams["stdout"], "tool stdout", legacy.MAX_OUTPUT_BYTES)
                        if type(candidate) is dict:
                            parsed = candidate
                    except BrokerError:
                        pass
                    status = "success" if sandbox["exit_code"] == 0 else "tool_failure"
                    output = (legacy._canonical(parsed).decode().strip() if parsed is not None else
                              legacy._canonical({"ok": False, "broker_status": status,
                                                 "stdout_sha256": legacy._sha(streams["stdout"]),
                                                 "stdout_bytes": len(streams["stdout"])}).decode().strip())
                    if (receipt["status"] != status or receipt["output_json"] != parsed
                            or receipt["output"] != output
                            or _file(before, "metrics.json") != _file(receipt["work_after"], "metrics.json")):
                        raise BrokerError("workspace feedback or host-owned metrics changed")
                last_work[task] = receipt["work_after"]
            else:
                pending.add(task)
            records.append((ordinal, reservation, receipt))
        for task, branch in branches.items():
            stage = self._stage(branch)
            if task not in pending and legacy._work(stage) != last_work[task]:
                raise BrokerError("branch work differs from last terminal receipt")
        return records, last_work

    def invoke(self, task_id: str, request_id: str, call: dict, context: Any,
               guard: Callable[[], None]) -> dict:
        branch = next((item for item in self.manifest["branches"] if item["task_id"] == task_id), None)
        function = next((item for item in branch["functions"] if item["name"] == call.get("name")), None) \
            if branch is not None and type(call) is dict else None
        if function is not None and function["profile"] == "workspace":
            return super().invoke(task_id, request_id, call, context, guard)
        if self._unusable:
            raise BrokerError("broker already has an uncertain local effect")
        legacy._identifier(task_id, "task ID")
        legacy._identifier(request_id, "request ID")
        if (not request_id.startswith(task_id + "-turn-") or type(call) is not dict
                or set(call) != {"name", "call_id", "arguments"} or function is None):
            raise BrokerError("analysis call ownership or fields are invalid")
        name, call_id = legacy._identifier(call["name"], "function name"), legacy._identifier(call["call_id"], "call ID")
        if type(call["arguments"]) is not str or not callable(guard):
            raise BrokerError("analysis arguments and effect guard are required")
        arguments = legacy._parse(call["arguments"], "analysis arguments", legacy.MAX_ARGUMENT_BYTES)
        canonical = legacy._canonical(arguments).decode().strip()
        stage = Path(branch["stage_dir"])
        with self._locked():
            self._guard(context, guard)
            report = self.verify()
            if any(number not in self._active for number in report["pending"]):
                raise BrokerError("unreconciled tool reservation blocks new effects")
            records, _ = self._records()
            if any(record["task_id"] == task_id and receipt is None for _, record, receipt in records):
                raise BrokerError("branch already has an active tool")
            status = context.status()
            if (status["state"] != "active" or status["tools_reserved"] >= status["max_tool_calls"]
                    or report["reservations"] != status["tools_reserved"]):
                raise BrokerError("shared tool cap or count changed")
            if any(record["call_id"] == call_id for _, record, _ in records):
                raise BrokerError("function call ID was already reserved")
            work_before = legacy._work(stage)
            try:
                source_sha, old_sha = _analysis_source(stage, work_before, arguments,
                    [(None, receipt) for _, record, receipt in records if record["task_id"] == task_id])
            except SessionError as exc:
                raise BrokerError(str(exc)) from exc
            ordinal = report["reservations"] + 1
            local = sum(record["task_id"] == task_id for _, record, _ in records) + 1
            claimed = self._guard(context, guard)
            reservation = {
                "schema": 2, "manifest_sha256": self.sha256, "claim_sha256": claimed,
                "task_id": task_id, "request_id": request_id, "call_id": call_id,
                "function_name": name, "profile": "analysis_readonly", "arguments": canonical,
                "arguments_sha256": legacy._sha(canonical.encode()), "global_ordinal": ordinal,
                "local_ordinal": local, "work_before_sha256": legacy._sha(legacy._canonical(work_before)),
                "analysis_contract": CONTRACT, "analysis_script_sha256": source_sha,
                "old_metrics_sha256": old_sha, "executable_sha256": function["sha256"],
            }
            legacy._publish_file(self.reservations / f"{ordinal:04d}.json",
                                 legacy._canonical(reservation), self.broker_dir)
            self._active.add(ordinal)
        try:
            self._guard(context, guard)
            stream_dir = self.broker_dir / f"{ordinal:04d}"
            stream_dir.mkdir(mode=0o700)
            legacy._fsync_dir(self.broker_dir)
            tool_bytes, current = legacy._executable(Path(function["path"]))
            if current != {key: function[key] for key in ("path", "sha256", "bytes", "identity")}:
                raise BrokerError("analysis launcher changed before launch")
            self._stage(branch)
            remaining = context.deadline - time.monotonic()
            wall = legacy._read_json(self.run_dir / "plan.json").get("tool_wall_seconds")
            if (not math.isfinite(remaining) or remaining <= 0 or type(wall) not in (int, float)
                    or not math.isfinite(wall) or wall <= 0):
                raise BrokerError("shared analysis deadline or wall cap is invalid")
            timeout = min(float(wall), remaining)
            self._guard(context, guard)
            started = time.monotonic()
            result = run_sandboxed(
                argv=[function["path"], str(stage / "case"), str(stage / "inputs"), str(stage / "work"), canonical],
                cwd=stage / "case", read_roots=[stage / "case", stage / "inputs", stage / "work"],
                write_roots=[], runtime_roots=default_python_runtime_roots(),
                stdout_path=stream_dir / "stdout", stderr_path=stream_dir / "stderr",
                timeout_seconds=timeout, cpu_seconds=max(1, min(60, math.ceil(timeout))),
                file_bytes_per_file=MAX_ANALYSIS_STREAM_BYTES,
                sealed_executable_bytes=tool_bytes, sealed_executable_sha256=function["sha256"],
            )
            elapsed = time.monotonic() - started
            self._guard(context, guard)
            child_work = legacy._work(stage)
            self._stage(branch)
            if child_work != work_before:
                raise BrokerError("readonly analysis mutated branch work")
            if (result.sealed_executable_sha256 != function["sha256"] or result.launch_error is not None
                    or result.timed_out or type(result.exit_code) is not int or result.exit_code < 0):
                raise BrokerError("analysis launch, seal, or deadline is uncertain")
            stdout = _read_bounded_file(stream_dir / "stdout", "analysis stdout", MAX_ANALYSIS_STREAM_BYTES)
            stderr = _read_bounded_file(stream_dir / "stderr", "analysis stderr", MAX_ANALYSIS_STREAM_BYTES)
            analysis_status, diagnostic, _, _, parsed = _analysis_output(
                stream_dir / "stdout", result.exit_code, MAX_ANALYSIS_STREAM_BYTES)
            self._guard(context, guard)
            if legacy._work(stage) != child_work:
                raise BrokerError("analysis work changed before host publication")
            metrics_sha = _publish_analysis_metrics(stage / "work", parsed, old_sha)
            work_after = legacy._work(stage)
            _metrics_transition(child_work, work_after, parsed)
            output = _feedback(analysis_status, diagnostic, stdout, parsed)
            receipt = {
                **{key: reservation[key] for key in ANALYSIS_RESERVATION_FIELDS},
                "schema": 2, "reservation_sha256": legacy._sha(legacy._canonical(reservation)),
                **{key: reservation[key] for key in ("manifest_sha256", "claim_sha256", "task_id", "request_id",
                    "call_id", "function_name", "profile", "global_ordinal", "local_ordinal")},
                "stdout_sha256": legacy._sha(stdout), "stderr_sha256": legacy._sha(stderr),
                "stdout_bytes": len(stdout), "stderr_bytes": len(stderr), "sandbox": {
                    "exit_code": result.exit_code, "timed_out": result.timed_out, "launch_error": result.launch_error,
                    "landlock_abi": result.landlock_abi, "duration_seconds": result.duration_seconds,
                    "sealed_executable_sha256": result.sealed_executable_sha256, "host_elapsed_seconds": elapsed},
                "status": "success", "analysis_status": analysis_status, "analysis_diagnostic": diagnostic,
                "analysis_metrics_sha256": metrics_sha, "analysis_work_before": work_before,
                "analysis_work_after_child": child_work,
                "analysis_work_after_child_sha256": legacy._sha(legacy._canonical(child_work)),
                "output": output, "output_json": parsed, "work_after": work_after,
                "work_after_sha256": legacy._sha(legacy._canonical(work_after)),
            }
            self._guard(context, guard)
            legacy._publish_file(self.receipts / f"{ordinal:04d}.json", legacy._canonical(receipt), self.broker_dir)
            self._guard(context, guard)
            return {"type": "function_call_output", "call_id": call_id, "output": output}
        except BaseException:
            self._unusable = True
            raise
        finally:
            with self._process_lock:
                self._active.discard(ordinal)

    def current_metrics(self, task_id: str) -> dict | None:
        """Return fresh host metrics only when the current script still matches."""
        self.branch(task_id)
        report = self.verify()
        if report["pending"] or report["blocked"]:
            raise BrokerError("unreconciled analysis prevents metrics publication")
        records, last_work = self._records()
        metrics, source = _file(last_work[task_id], "metrics.json"), _file(last_work[task_id], "analysis.py")
        if metrics is None or source is None:
            return None
        selected = next(((ordinal, receipt) for ordinal, reservation, receipt in reversed(records)
                         if reservation["task_id"] == task_id and receipt is not None
                         and receipt.get("analysis_status") == "valid"), None)
        if (selected is None or selected[1]["analysis_script_sha256"] != source["sha256"]
                or selected[1]["analysis_metrics_sha256"] != metrics["sha256"]):
            return None
        ordinal, receipt = selected
        return {"task_id": task_id, "function_name": receipt["function_name"], "global_ordinal": ordinal,
                "local_ordinal": receipt["local_ordinal"], "analysis_script_sha256": source["sha256"],
                "analysis_metrics_sha256": metrics["sha256"], "metrics_bytes": metrics["bytes"],
                "metrics_path": str(Path(self.branch(task_id)["stage_dir"]) / "work" / "metrics.json"),
                "metrics": receipt["output_json"], "receipt_sha256": legacy._sha(legacy._canonical(receipt))}
