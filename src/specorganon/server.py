"""MCP 2.x stdio server exposing the Organon engine."""

from __future__ import annotations

import ctypes
import json
import os
import platform
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Iterator

import anyio
from mcp.shared.message import SessionMessage
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.stdio import (
    _claim_fd,
    _open_stdin_diversion,
    stdio_server,
)
from mcp_types import (
    INVALID_PARAMS,
    INVALID_REQUEST,
    PARSE_ERROR,
    ErrorData,
    JSONRPCError,
)
from pydantic import StrictInt

from specorganon.cli import invoke
from specorganon.ledger import strict_json_loads


_DIR_FLAGS = os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_MAX_MCP_LINE_BYTES = 8 * 1024 * 1024
_LANDLOCK_SYSCALLS = {"x86_64": (444, 445, 446), "aarch64": (444, 445, 446)}
_LANDLOCK_MIN_ABI = 5  # ABI 3 adds truncate; ABI 5 adds device ioctl.
_LANDLOCK_WRITE_ACCESS = sum(1 << bit for bit in (1, *range(4, 16)))


class _LandlockRulesetAttr(ctypes.Structure):
    _fields_ = [("handled_access_fs", ctypes.c_uint64)]


class _LandlockPathBeneathAttr(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32)]


def _landlock_syscall(libc: ctypes.CDLL, number: int, *args: object) -> int:
    ctypes.set_errno(0)
    result = libc.syscall(number, *args)
    if result == -1:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code))
    return int(result)


def _confine_root_writes() -> None:
    """Restrict new path-based writes by this MCP thread to ORGANON_ROOT.

    The rule is installed before serving and inherited by the worker threads
    the stdio transport creates. It does not revoke existing writable FDs or
    confine same-UID peers; root moves and in-root hardlinks remain outside a
    complete same-UID filesystem integrity boundary.
    """
    if "ORGANON_ROOT" not in os.environ:
        return  # Keep the historical development mode when no root is set.
    architecture = platform.machine()
    if sys.platform != "linux" or architecture not in _LANDLOCK_SYSCALLS:
        raise RuntimeError("ORGANON_ROOT requires Linux Landlock support")

    root, root_fd = _root_directory()
    try:
        # _root_directory resolves aliases, then walks canonical components.
        # Reject a root replaced during that walk before granting its inode.
        pinned = os.fstat(root_fd)
        current = os.stat(root, follow_symlinks=False)
        if (pinned.st_dev, pinned.st_ino) != (current.st_dev, current.st_ino):
            raise RuntimeError("ORGANON_ROOT changed during Landlock setup")

        libc = ctypes.CDLL(None, use_errno=True)
        libc.syscall.restype = ctypes.c_long
        libc.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong,
                               ctypes.c_ulong, ctypes.c_ulong]
        libc.prctl.restype = ctypes.c_int
        create, add_rule, restrict = _LANDLOCK_SYSCALLS[architecture]
        abi = _landlock_syscall(libc, create, 0, 0, 1)
        if abi < _LANDLOCK_MIN_ABI:
            raise RuntimeError(f"ORGANON_ROOT requires Landlock ABI {_LANDLOCK_MIN_ABI}+")

        ruleset_attr = _LandlockRulesetAttr(_LANDLOCK_WRITE_ACCESS)
        ruleset_fd = _landlock_syscall(
            libc, create, ctypes.byref(ruleset_attr), ctypes.sizeof(ruleset_attr), 0
        )
        try:
            root_rule = _LandlockPathBeneathAttr(_LANDLOCK_WRITE_ACCESS, root_fd)
            _landlock_syscall(libc, add_rule, ruleset_fd, 1, ctypes.byref(root_rule), 0)
            if libc.prctl(38, 1, 0, 0, 0) != 0:  # PR_SET_NO_NEW_PRIVS
                code = ctypes.get_errno()
                raise OSError(code, os.strerror(code))
            _landlock_syscall(libc, restrict, ruleset_fd, 0)
        finally:
            os.close(ruleset_fd)
    except OSError as exc:
        raise RuntimeError(f"cannot confine ORGANON_ROOT with Landlock: {exc}") from exc
    finally:
        os.close(root_fd)


def _validate_raw_envelope(message: Any) -> None:
    """Accept only one JSON-RPC message with an unambiguous root shape."""
    if type(message) is not dict:
        raise ValueError("JSON-RPC message must be an object, not a batch or scalar")
    if message.get("jsonrpc") != "2.0":
        raise ValueError("JSON-RPC version must be 2.0")

    if "method" in message:
        if "result" in message or "error" in message:
            raise ValueError("JSON-RPC request cannot include response fields")
        allowed = {"jsonrpc", "id", "method", "params"}
        if type(message["method"]) is not str or not message["method"]:
            raise ValueError("JSON-RPC method must be a nonempty string")
        if "id" in message and type(message["id"]) not in (int, str):
            raise ValueError("JSON-RPC request id must be a string or integer")
        if (
            "params" in message
            and message["params"] is not None
            and type(message["params"]) is not dict
        ):
            raise ValueError("JSON-RPC params must be an object or null")
    else:
        # Responses to server-initiated requests are valid input to the SDK.
        if ("result" in message) == ("error" in message):
            raise ValueError("JSON-RPC response requires exactly one result or error")
        allowed = {"jsonrpc", "id", "result", "error"}
        if "id" not in message or (
            type(message["id"]) not in (int, str)
            and not ("error" in message and message["id"] is None)
        ):
            raise ValueError("JSON-RPC response id is invalid")
        field = "result" if "result" in message else "error"
        if type(message[field]) is not dict:
            raise ValueError(f"JSON-RPC {field} must be an object")

    unexpected = message.keys() - allowed
    if unexpected:
        raise ValueError(
            "unexpected JSON-RPC envelope fields: " + ", ".join(sorted(unexpected))
        )


def _validate_raw_tool_arguments(message: Any) -> None:
    """Reject ambiguous shapes before SDK metadata parsing or integer coercion."""
    if not isinstance(message, dict) or message.get("method") != "tools/call":
        return
    params = message.get("params")
    if not isinstance(params, dict) or not isinstance(params.get("arguments"), dict):
        return
    arguments = params["arguments"]
    if params.get("name") == "put":
        for field, expected_type in (
            ("data", dict),
            ("expected_deps", dict),
            ("refs", list),
        ):
            if (
                field in arguments
                and arguments[field] is not None
                and type(arguments[field]) is not expected_type
            ):
                kind = "object" if expected_type is dict else "array"
                raise ValueError(f"put.{field} must be a JSON {kind}")
        if type(arguments.get("expected_version")) is bool:
            raise ValueError("expected_version must be an integer, not a boolean")
        dependencies = arguments.get("expected_deps")
        if isinstance(dependencies, dict) and any(
            type(value) is bool for value in dependencies.values()
        ):
            raise ValueError("expected_deps values must be integers, not booleans")
    elif params.get("name") == "retire_indicator":
        replacements = arguments.get("replacements")
        if type(replacements) is not dict:
            raise ValueError("retire_indicator.replacements must be a JSON object")
        if any(type(version) is not int for version in replacements.values()):
            raise ValueError("retire_indicator.replacements values must be integers, without coercion")
        for field in ("expected_version", "expected_review_seq"):
            if type(arguments.get(field)) is not int:
                raise ValueError(f"retire_indicator.{field} must be an integer, without coercion")
    elif (
        params.get("name") in {"test_execution_challenge", "record_test_execution"}
        and "report" in arguments
        and type(arguments["report"]) is not dict
    ):
        raise ValueError("test execution report must be a JSON object")
    elif (
        params.get("name") in {"test_observation_challenge", "record_test_observation"}
        and "receipt" in arguments
        and type(arguments["receipt"]) is not dict
    ):
        raise ValueError("test observation receipt must be a JSON object")
    elif (
        params.get("name") == "resolve_challenge"
        and type(arguments.get("challenge_seq")) is bool
    ):
        raise ValueError("challenge_seq must be an integer, not a boolean")
    elif (
        params.get("name") == "run"
        and "manifest" in arguments
        and type(arguments["manifest"]) is not dict
    ):
        raise ValueError("run.manifest must be a JSON object")
    elif (
        params.get("name") == "next_task"
        and "roles" in arguments
        and arguments["roles"] is not None
        and type(arguments["roles"]) is not dict
    ):
        raise ValueError("next_task.roles must be a JSON object")


class _WireObject(dict[str, Any]):
    """Retain only root-key ambiguity needed to route an error safely."""

    def __init__(self, pairs: list[tuple[str, Any]]) -> None:
        super().__init__()
        self.duplicate_keys: set[str] = set()
        for key, value in pairs:
            if key in self:
                self.duplicate_keys.add(key)
            self[key] = value


class _StrictStdin:
    """Feed only strict JSON lines to the SDK's own stdio transport parser."""

    def __init__(self, source: anyio.AsyncFile[bytes]) -> None:
        self._source = source
        self._writer: Any = None
        self._ready = anyio.Event()

    def attach_writer(self, writer: Any) -> None:
        self._writer = writer
        self._ready.set()

    async def _send_error(
        self, request_id: int | str | None, code: int, reason: str
    ) -> None:
        await self._writer.send(
            SessionMessage(
                JSONRPCError(
                    jsonrpc="2.0",
                    id=request_id,
                    error=ErrorData(code=code, message=reason[:256]),
                )
            )
        )

    async def _reject(self, line: str, code: int, reason: str) -> None:
        # A permissive parse is used only to recover the request ID for the
        # error response. The original message is never sent to tool dispatch.
        try:
            envelope = json.loads(line, object_pairs_hook=_WireObject)
        except (ValueError, RecursionError):
            envelope = None
        request_id = (
            envelope.get("id")
            if isinstance(envelope, _WireObject) and not envelope.duplicate_keys
            else None
        )
        if type(request_id) not in (int, str):
            request_id = None
        await self._send_error(request_id, code, reason)

    async def _readline(self, size: int) -> bytes:
        # AsyncFile.readline() has no size argument; call the same wrapped
        # binary reader with a bound in AnyIO's worker thread.
        return await anyio.to_thread.run_sync(
            self._source.wrapped.readline, size, limiter=self._source.limiter
        )

    async def __aiter__(self) -> AsyncIterator[str]:
        await self._ready.wait()
        while raw_line := await self._readline(_MAX_MCP_LINE_BYTES + 1):
            if len(raw_line) > _MAX_MCP_LINE_BYTES:
                # Drain the rest of this frame without retaining it or routing
                # any prefix to the SDK. Its ID cannot safely be recovered.
                while not raw_line.endswith(b"\n"):
                    raw_line = await self._readline(64 * 1024)
                    if not raw_line:
                        break
                await self._send_error(
                    None, INVALID_REQUEST, "JSON-RPC line exceeds the size limit"
                )
                continue
            try:
                line = raw_line.decode("utf-8", errors="strict")
            except UnicodeDecodeError:
                await self._send_error(
                    None, PARSE_ERROR, "invalid UTF-8 in JSON-RPC line"
                )
                continue
            try:
                message = strict_json_loads(line)
            except (ValueError, OverflowError, RecursionError) as exc:
                await self._reject(line, PARSE_ERROR, f"invalid strict JSON: {exc}")
                continue
            try:
                _validate_raw_envelope(message)
            except ValueError as exc:
                await self._reject(line, INVALID_REQUEST, str(exc))
                continue
            try:
                _validate_raw_tool_arguments(message)
            except ValueError as exc:
                await self._reject(line, INVALID_PARAMS, str(exc))
                continue
            yield line


class _StrictStdioMCPServer(MCPServer):
    async def run_stdio_async(self) -> None:
        """Use SDK stdio framing with validation before its JSON adapter."""
        _confine_root_writes()
        stdin_buffer, restore_stdin = _claim_fd(
            0, sys.stdin, "rb", _open_stdin_diversion
        )
        try:
            stdin = anyio.wrap_file(stdin_buffer)
            strict_stdin = _StrictStdin(stdin)
            async with stdio_server(stdin=strict_stdin) as (read_stream, write_stream):
                strict_stdin.attach_writer(write_stream)
                await self._lowlevel_server.run(
                    read_stream,
                    write_stream,
                    self._lowlevel_server.create_initialization_options(),
                )
        finally:
            if restore_stdin is not None:
                restore_stdin()


def _root_directory() -> tuple[str, int]:
    """Open the configured root one directory at a time, without symlink ancestors."""
    configured_root = os.environ.get("ORGANON_ROOT")
    if configured_root == "":
        raise ValueError("ORGANON_ROOT must name an existing directory")
    root = str(
        Path(configured_root if configured_root is not None else os.getcwd()).resolve(
            strict=True
        )
    )
    fd = os.open("/", _DIR_FLAGS)
    try:
        for component in Path(root).parts[1:]:
            next_fd = os.open(component, _DIR_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = next_fd
    except BaseException:
        os.close(fd)
        raise
    return root, fd


@contextmanager
def _case_path(path: str, *, create: bool = False) -> Iterator[str]:
    """Pin the canonical in-root case inode throughout a single operation.

    An existing symlink alias may resolve to a directory inside the root. The
    canonical components are then opened relative to the pinned root with
    O_NOFOLLOW, so a replacement between resolution and open cannot redirect
    the operation. Linux procfs lets the engine use the pinned directory while
    this context keeps its descriptor alive. A peer with permission to rename
    that inode can still move the pinned directory itself after it is opened.
    """
    root, root_fd = _root_directory()
    case_fd: int | None = None
    try:
        case_fd = os.dup(root_fd)
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = Path(root) / candidate
        resolved = candidate.resolve()
        if not resolved.is_relative_to(root):
            raise ValueError("case path is outside the Organon server root")
        for component in resolved.relative_to(root).parts:
            if create:
                try:
                    os.mkdir(component, dir_fd=case_fd)
                except FileExistsError:
                    pass
            next_fd = os.open(component, _DIR_FLAGS, dir_fd=case_fd)
            os.close(case_fd)
            case_fd = next_fd
        yield f"/proc/self/fd/{case_fd}"
    finally:
        if case_fd is not None:
            os.close(case_fd)
        os.close(root_fd)


def _validate_init(kwargs: dict[str, Any]) -> None:
    if "ORGANON_LEDGER_ANCHORS_FILE" in os.environ:
        raise ValueError(
            "initialize a case before enabling ORGANON_LEDGER_ANCHORS_FILE; "
            "then register its sequence-zero head"
        )
    if not all(
        isinstance(kwargs.get(key), str) and kwargs[key].strip()
        for key in ("title", "domain", "actor")
    ):
        raise ValueError("title, domain and actor must be nonempty strings")
    if kwargs.get("approval_policy", "signed") not in {"signed", "fixture"}:
        raise ValueError("approval_policy must be signed or fixture")
    if kwargs.get("test_gate_policy", "signed_report") not in {"signed_report", "signed_observed"}:
        raise ValueError("test_gate_policy must be signed_report or signed_observed")


def _invoke(operation: str, **kwargs: Any) -> dict[str, Any]:
    try:
        if operation == "init":
            _validate_init(kwargs)
        with _case_path(kwargs["path"], create=operation == "init") as pinned_path:
            kwargs["path"] = pinned_path
            return invoke(operation, **kwargs)
    except (ValueError, OSError, TypeError, RuntimeError) as exc:
        raise ToolError(str(exc)) from exc


server = _StrictStdioMCPServer(
    "organon",
    description="Evidence-linked case workflow with review, contradictions, phase gates and traceability.",
    instructions=(
        "Start with init, add items with put, inspect status and gate before advance. "
        "Record reviews and human decisions explicitly. Signed cases require an offline Ed25519 "
        "signature checked against the operator-controlled ORGANON_APPROVERS_FILE."
    ),
)


@server.tool(description="Create a case at path with a title, domain and actor label.")
def init(
    path: str, title: str, domain: str, actor: str, approval_policy: str = "signed",
    test_gate_policy: str = "signed_report",
) -> dict[str, Any]:
    return _invoke(
        "init",
        path=path,
        title=title,
        domain=domain,
        actor=actor,
        approval_policy=approval_policy,
        test_gate_policy=test_gate_policy,
    )


@server.tool(
    description="Add or revise an evidence-linked case item; supply expected_version and expected_deps for guarded concurrent writes."
)
def put(
    path: str,
    id: str,
    kind: str,
    text: str,
    actor: str,
    refs: list[str] | None = None,
    data: dict[str, Any] | None = None,
    expected_version: StrictInt | None = None,
    expected_deps: dict[str, StrictInt] | None = None,
) -> dict[str, Any]:
    return _invoke(
        "put",
        path=path,
        id=id,
        kind=kind,
        text=text,
        refs=refs or [],
        data=data or {},
        actor=actor,
        expected_version=expected_version,
        expected_deps=expected_deps,
    )


@server.tool(description="Read the current case state.")
def status(path: str) -> dict[str, Any]:
    return _invoke("status", path=path)


@server.tool(description="Record an item review with a verdict and reason.")
def review(path: str, id: str, verdict: str, reason: str, actor: str) -> dict[str, Any]:
    return _invoke(
        "review", path=path, id=id, verdict=verdict, reason=reason, actor=actor
    )


@server.tool(
    description="Retire a rejected unused indicator with pinned replacement versions and review; technical action, not human approval."
)
def retire_indicator(
    path: str, id: str, replacements: dict[str, StrictInt], reason: str, actor: str,
    expected_version: StrictInt, expected_review_seq: StrictInt,
) -> dict[str, Any]:
    return _invoke(
        "retire_indicator", path=path, id=id, replacements=replacements, reason=reason,
        actor=actor, expected_version=expected_version, expected_review_seq=expected_review_seq,
    )


@server.tool(
    description="Return canonical bytes for offline Ed25519 signing of an exact normative item revision."
)
def approval_challenge(path: str, id: str, reason: str, actor: str) -> dict[str, Any]:
    return _invoke("approval_challenge", path=path, id=id, reason=reason, actor=actor)


@server.tool(
    description="Record a normative approval; signed cases require a trusted Ed25519 signature."
)
def approve(
    path: str, id: str, reason: str, actor: str, signature: str | None = None
) -> dict[str, Any]:
    return _invoke(
        "approve", path=path, id=id, reason=reason, actor=actor, signature=signature
    )


@server.tool(
    description="Return canonical bytes for offline Ed25519 signing of an external test execution report. No command is run."
)
def test_execution_challenge(
    path: str, id: str, report: dict[str, Any], actor: str,
) -> dict[str, Any]:
    return _invoke(
        "test_execution_challenge", path=path, id=id, report=report, actor=actor,
    )


@server.tool(
    description="Record a signed external test report for the current test revision. No command is run."
)
def record_test_execution(
    path: str, id: str, report: dict[str, Any], actor: str, signature: str,
) -> dict[str, Any]:
    return _invoke(
        "record_test_execution", path=path, id=id, report=report,
        actor=actor, signature=signature,
    )


@server.tool(
    description="Return canonical bytes for offline Ed25519 signing of an external test observation receipt. No command is run."
)
def test_observation_challenge(
    path: str, id: str, receipt: dict[str, Any], actor: str,
) -> dict[str, Any]:
    return _invoke(
        "test_observation_challenge", path=path, id=id, receipt=receipt, actor=actor,
    )


@server.tool(
    description="Record a signed external observation for the current test execution. No command is run."
)
def record_test_observation(
    path: str, id: str, receipt: dict[str, Any], actor: str, signature: str,
) -> dict[str, Any]:
    return _invoke(
        "record_test_observation", path=path, id=id, receipt=receipt,
        actor=actor, signature=signature,
    )


@server.tool(
    description="Prepare case, item and source hashes for an independent field assessor's Ed25519 signature."
)
def field_attestation_challenge(
    path: str, id: str, reason: str, actor: str,
    source_manifest_path: str, report_path: str,
) -> dict[str, Any]:
    return _invoke(
        "field_attestation_challenge", path=path, id=id, reason=reason, actor=actor,
        source_manifest_path=source_manifest_path, report_path=report_path,
    )


@server.tool(
    description="Record a signed assessor statement. It does not unblock a decisive field verdict."
)
def attest_field(
    path: str, id: str, reason: str, actor: str,
    source_manifest_path: str, report_path: str, signature: str,
) -> dict[str, Any]:
    return _invoke(
        "attest_field", path=path, id=id, reason=reason, actor=actor,
        source_manifest_path=source_manifest_path, report_path=report_path,
        signature=signature,
    )


@server.tool(description="Record a contradiction between two items.")
def challenge(
    path: str, left: str, right: str, reason: str, actor: str
) -> dict[str, Any]:
    return _invoke(
        "challenge", path=path, left=left, right=right, reason=reason, actor=actor
    )


@server.tool(description="Resolve a contradiction using an existing resolution item.")
def resolve_challenge(
    path: str, challenge_seq: StrictInt, resolution_item: str, actor: str
) -> dict[str, Any]:
    return _invoke(
        "resolve_challenge",
        path=path,
        challenge_seq=challenge_seq,
        resolution_item=resolution_item,
        actor=actor,
    )


@server.tool(
    description="Evaluate the requirements for advancing a phase without changing state."
)
def gate(path: str, phase: str) -> dict[str, Any]:
    return _invoke("gate", path=path, phase=phase)


@server.tool(
    description="Return canonical bytes for offline Ed25519 signing of a phase review of the current snapshot."
)
def phase_review_challenge(
    path: str, phase: str, verdict: str, reason: str, actor: str
) -> dict[str, Any]:
    return _invoke(
        "phase_review_challenge",
        path=path,
        phase=phase,
        verdict=verdict,
        reason=reason,
        actor=actor,
    )


@server.tool(description="Record a phase review; signed cases require a trusted Ed25519 reviewer signature.")
def review_phase(
    path: str, phase: str, verdict: str, reason: str, actor: str,
    signature: str | None = None,
) -> dict[str, Any]:
    return _invoke(
        "review_phase",
        path=path,
        phase=phase,
        verdict=verdict,
        reason=reason,
        actor=actor,
        signature=signature,
    )


@server.tool(
    description="Advance the requested phase only when the engine gate permits it."
)
def advance(path: str, phase: str, actor: str) -> dict[str, Any]:
    return _invoke("advance", path=path, phase=phase, actor=actor)


@server.tool(description="Trace an item to its referenced inputs and dependents.")
def trace(path: str, id: str) -> dict[str, Any]:
    return _invoke("trace", path=path, id=id)


@server.tool(
    description="Get bounded, versioned instructions for the next pending workflow task."
)
def next_task(path: str, roles: dict[str, str] | None = None) -> dict[str, Any]:
    return _invoke("next_task", path=path, roles=roles)


@server.tool(
    description="Apply a schema 1 workflow manifest; pause at human approval or independent review."
)
def run(path: str, manifest: dict[str, Any], actor: str) -> dict[str, Any]:
    return _invoke("run", path=path, manifest=manifest, actor=actor)


@server.tool(
    description="Audit declared incremental lot balances and wet/dry mass basis; no field authenticity or acceptance is established. Read-only, no case required."
)
def audit_lot_journal(journal: dict[str, Any]) -> dict[str, Any]:
    try:
        return invoke("audit_lot_journal", journal=journal)
    except (ValueError, TypeError) as exc:
        raise ToolError(str(exc)) from exc


def main() -> None:
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
