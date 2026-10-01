"""Explicit operator gate for observed OpenAI Responses steps of DEV prototypes.

Preflight does not read credentials. Local fixture steps never use a real key.
Operator declarations are cooperative local policy, not authenticated authority.
No command establishes experimental acceptance, invoices or remote cancellation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import stat
import sys
import threading
import time
import urllib.request

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import observed_coordinated_runtime as observed  # noqa: E402
import provider_outcome_accounting as accounting  # noqa: E402
from coordinated_observation_journal import ObservationJournal  # noqa: E402
from run_managed_conversation import _canonical, _private_dir, _private_file  # noqa: E402
from run_managed_response import OpenAIResponsesHTTP, _json_bytes  # noqa: E402

runtime = observed.runtime
OFFICIAL_ORIGIN = "https://api.openai.com/v1"
OPENAI_ROUTE = {"provider": "openai", "api": "responses", "version": "v1", "service_tier": "default"}
DECLARATION_CLASS = "coordinated_operator_declaration_not_authenticated_authority"
DECLARATION_NAME = "operator-declaration.json"
MAX_DECLARATION_BYTES = 256 * 1024
MAX_WAIT_SECONDS = 90


class AuthorizedRouteError(ValueError):
    """A bounded local route gate failed; messages contain fixed codes only."""


def _require(condition, code):
    if not condition:
        raise AuthorizedRouteError(code)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _controller_sources():
    rows = {**runtime._runtime_sources(), **observed._source_digests()}
    for name in ("authorized_coordinated_runtime.py", "provider_outcome_accounting.py"):
        rows["scripts/" + name] = _sha(runtime.preparation._read(SCRIPTS / name))
    return dict(sorted(rows.items()))


def _paths(run_dir, directory):
    run_dir = runtime.preparation._chain(Path(run_dir), directory=True)
    directory = runtime.preparation._chain(Path(directory), directory=True)
    _private_dir(directory)
    _private_dir(directory / "events")
    for name in ("binding.json", ".events.lock", ".driver.lock"):
        _private_file(directory / name)
    return run_dir, directory


def _binding(plan, status, report, run_dir, directory):
    return {"run_dir": str(run_dir), "observation_dir": str(directory), "run_id": plan["run_id"],
            "plan_sha256": _sha(_canonical(plan)), "schedule_sha256": status["schedule_sha256"],
            "observation_binding_sha256": _sha(_canonical(report["binding"])),
            "provider_route": plan["descriptor"]["provider_route"], "model": plan["descriptor"]["model"],
            "limits": plan["limits"], "role_config": plan["role_config"], "max_epochs": plan["max_epochs"],
            "controller_source_digests": _controller_sources()}


def preflight(run_dir, directory, *, expected_checkpoint):
    """Read the original guard and observation under their established locks."""
    run_dir, directory = _paths(run_dir, directory)
    journal = ObservationJournal(directory)
    with journal.driver_lock():
        report = journal.report()
        plan, _state, status, calls = observed._native_snapshot(run_dir, expected_checkpoint=expected_checkpoint)
        observed._check_binding(report, plan, status, run_dir)
        _require(status["state"] in {"prepared", "paused"} and report["state"] == "ready", "not_startable")
        binding = _binding(plan, status, report, run_dir, directory)
        return {"schema": 1, "classification": "offline_coordinated_route_preflight",
                "binding": binding, "checkpoint_sha256": status["checkpoint_sha256"],
                "next_roles": [row["role"] for row in calls], "next_call_digests": calls,
                "native_guard_verified": True, "provider_requests": 0, "credentials_read": False,
                "operator_template": {"schema": 1, "classification": DECLARATION_CLASS,
                                      "decision": "not_approved", "valid_until_unix": None, "binding": binding},
                "formal_cell_executed": False, "quality_assessed": False,
                "human_identity_authenticated": False}


def _declaration_bytes(path):
    path = Path(path)
    _require(path.name == DECLARATION_NAME, "declaration_filename")
    runtime.preparation._chain(path)
    _private_dir(path.parent)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        raise AuthorizedRouteError("private_declaration_required") from None
    try:
        before = os.fstat(fd)
        _require(stat.S_ISREG(before.st_mode) and stat.S_IMODE(before.st_mode) == 0o600
                 and before.st_uid == os.getuid() and before.st_nlink == 1
                 and 0 < before.st_size <= MAX_DECLARATION_BYTES, "private_declaration_required")
        pieces, size = [], 0
        while piece := os.read(fd, min(65536, MAX_DECLARATION_BYTES + 1 - size)):
            size += len(piece)
            _require(size <= MAX_DECLARATION_BYTES, "declaration_size")
            pieces.append(piece)
        after, named = os.fstat(fd), path.lstat()
        def identity(item):
            return (item.st_dev, item.st_ino, item.st_mode, item.st_uid, item.st_nlink,
                    item.st_size, item.st_mtime_ns, item.st_ctime_ns)
        _require(identity(before) == identity(after) == identity(named), "declaration_changed")
        return b"".join(pieces)
    finally:
        os.close(fd)


def _validate_declaration(raw, binding):
    value = runtime.delivery.parse_json(raw)
    _require(type(value) is dict and set(value) == {"schema", "classification", "decision", "valid_until_unix", "binding"},
             "declaration_schema")
    _require(type(value["schema"]) is int and value["schema"] == 1
             and value["classification"] == DECLARATION_CLASS and value["decision"] == "approved",
             "operator_approval_required")
    expiry = value["valid_until_unix"]
    _require(type(expiry) is int and time.time() < expiry <= time.time() + 86400, "declaration_expired_or_unbounded")
    _require(_canonical(value["binding"]) == _canonical(binding), "declaration_binding")
    return value


def _declaration_guard(path, raw, binding):
    def guard():
        current = _declaration_bytes(path)
        _require(current == raw, "declaration_changed")
        _validate_declaration(current, binding)
        _require(_controller_sources() == binding["controller_source_digests"], "controller_sources_changed")
        plan = runtime.preparation._read(Path(binding["run_dir"]) / "plan.json")
        _require(_sha(plan) == binding["plan_sha256"], "plan_changed")
    return guard


class BoundedResponsesTransport:
    """Bound the local wait, not the remote execution or socket lifetime.

    The native HTTP implementation has an I/O timeout. A separate local wait
    deadline also handles a response arriving in slow fragments. Timed-out
    daemon workers may finish remotely; their late results cannot be published.
    """
    def __init__(self, http, guard, *, max_wait_seconds=MAX_WAIT_SECONDS):
        _require(type(max_wait_seconds) in (int, float) and math.isfinite(max_wait_seconds)
                 and 0 < max_wait_seconds <= MAX_WAIT_SECONDS, "wait_bound")
        self.http, self.guard, self.max_wait_seconds = http, guard, max_wait_seconds

    def _operation(self, kind, payload, timeout_seconds):
        _require(type(timeout_seconds) in (int, float) and math.isfinite(timeout_seconds) and timeout_seconds > 0,
                 "operation_timeout")
        deadline = time.monotonic() + min(timeout_seconds, self.max_wait_seconds)
        self.guard()
        raw = _json_bytes(payload)
        result_queue = queue.Queue(maxsize=1)
        closed = threading.Event()
        def operation():
            result, error = None, None
            try:
                result = observed.wave._RemainingTransport(self.http, deadline).operation(kind, json.loads(raw))
                self.guard()
            except BaseException:
                error = "provider_operation_failed"
            if not closed.is_set() and time.monotonic() < deadline:
                result_queue.put_nowait((result, error))
        threading.Thread(target=operation, daemon=True).start()
        try:
            remaining = deadline - time.monotonic()
            _require(remaining > 0, "local_wait_deadline")
            result, error = result_queue.get(timeout=remaining)
            _require(time.monotonic() < deadline, "local_wait_deadline")
            _require(error is None, "provider_operation_failed")
            self.guard()
            _require(_json_bytes(payload) == raw, "caller_payload_changed")
            return result
        except queue.Empty:
            raise AuthorizedRouteError("local_wait_deadline") from None
        finally:
            closed.set()

    def count_input(self, payload, *, timeout_seconds):
        return self._operation("count_input", payload, timeout_seconds)

    def send(self, payload, *, timeout_seconds):
        return self._operation("send", payload, timeout_seconds)


def _execute(run_dir, directory, transports, checkpoint, *, operator_bound):
    try:
        result = observed.execute_observed_step(run_dir, directory, transports, expected_checkpoint=checkpoint)
        return {"classification": "guarded_coordinated_route_step_not_acceptance", "result": result,
                "operator_declaration_bound": operator_bound, "formal_cell_executed": False,
                "quality_assessed": False, "human_identity_authenticated": False,
                "remote_cancellation_guaranteed": False, "step_failed": False}
    except (ValueError, OSError, RuntimeError):
        try:
            outcome = accounting.read_provider_outcomes(Path(run_dir))
        except (ValueError, OSError, RuntimeError):
            outcome = None
        return {"classification": "guarded_step_rejected_or_indeterminate", "provider_outcomes": outcome,
                "step_failed": True, "reexecution_authorized": False, "operator_declaration_bound": operator_bound,
                "formal_cell_executed": False, "quality_assessed": False,
                "human_identity_authenticated": False, "remote_cancellation_guaranteed": False}


def execute_authorized_step(run_dir, directory, declaration_path, *, expected_checkpoint, allow_paid_request=False):
    _require(allow_paid_request is True, "explicit_paid_flag_required")
    preview = preflight(run_dir, directory, expected_checkpoint=expected_checkpoint)
    binding = preview["binding"]
    _require(binding["provider_route"] == OPENAI_ROUTE, "openai_route_required")
    path = Path(declaration_path)
    for root in (Path(run_dir), Path(directory), runtime.ROOT):
        _require(path != root and root not in path.parents and path not in root.parents, "declaration_overlap")
    raw = _declaration_bytes(path)
    _validate_declaration(raw, binding)
    guard = _declaration_guard(path, raw, binding)
    guard()
    key = os.environ.get("OPENAI_API_KEY")
    _require(type(key) is str and bool(key), "api_key_unavailable")
    transports = {role: BoundedResponsesTransport(OpenAIResponsesHTTP(key, base_url=OFFICIAL_ORIGIN), guard)
                  for role in runtime.ROLES}
    return _execute(run_dir, directory, transports, expected_checkpoint, operator_bound=True)


def execute_fixture_step(run_dir, directory, endpoint, *, expected_checkpoint):
    endpoint = runtime._fixture_endpoint(endpoint)
    preview = preflight(run_dir, directory, expected_checkpoint=expected_checkpoint)
    _require(preview["binding"]["provider_route"]["provider"] == "fixture", "fixture_route_required")
    transports = {}
    for role in runtime.ROLES:
        http = OpenAIResponsesHTTP("public-synthetic-no-credential", base_url=endpoint)
        http._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), OpenAIResponsesHTTP._NoRedirect())
        transports[role] = BoundedResponsesTransport(http, lambda: None)
    return _execute(run_dir, directory, transports, expected_checkpoint, operator_bound=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("preflight", "step", "step-fixture", "outcomes"):
        command = sub.add_parser(name)
        command.add_argument("--run-dir", type=Path, required=True)
        if name != "outcomes":
            command.add_argument("--observation-dir", type=Path, required=True)
            command.add_argument("--expected-checkpoint", required=True)
        if name == "step":
            command.add_argument("--operator-declaration", type=Path, required=True)
            command.add_argument("--allow-paid-request", action="store_true")
        elif name == "step-fixture":
            command.add_argument("--local-http-fixture", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "outcomes":
            result = accounting.read_provider_outcomes(args.run_dir)
        elif args.command == "preflight":
            result = preflight(args.run_dir, args.observation_dir, expected_checkpoint=args.expected_checkpoint)
        elif args.command == "step":
            result = execute_authorized_step(args.run_dir, args.observation_dir, args.operator_declaration,
                                            expected_checkpoint=args.expected_checkpoint, allow_paid_request=args.allow_paid_request)
        else:
            result = execute_fixture_step(args.run_dir, args.observation_dir, args.local_http_fixture,
                                          expected_checkpoint=args.expected_checkpoint)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 2 if result.get("step_failed") else 0
    except (ValueError, OSError, KeyError, TypeError, RuntimeError):
        print(json.dumps({"error": "authorization_or_runtime_gate_rejected", "formal_cell_executed": False,
                          "quality_assessed": False, "human_identity_authenticated": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
