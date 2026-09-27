"""MCP 2.x stdio server exposing the Organon engine."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from specorganon.cli import invoke


_DIR_FLAGS = os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


def _root_directory() -> tuple[str, int]:
    """Open the configured root one directory at a time, without symlink ancestors."""
    configured_root = os.environ.get("ORGANON_ROOT")
    if configured_root == "":
        raise ValueError("ORGANON_ROOT must name an existing directory")
    root = str(Path(configured_root if configured_root is not None else os.getcwd()).resolve(strict=True))
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
    if not all(isinstance(kwargs.get(key), str) and kwargs[key].strip() for key in ("title", "domain", "actor")):
        raise ValueError("title, domain and actor must be nonempty strings")
    if kwargs.get("approval_policy", "signed") not in {"signed", "fixture"}:
        raise ValueError("approval_policy must be signed or fixture")


def _invoke(operation: str, **kwargs: Any) -> dict[str, Any]:
    try:
        if operation == "init":
            _validate_init(kwargs)
        with _case_path(kwargs["path"], create=operation == "init") as pinned_path:
            kwargs["path"] = pinned_path
            return invoke(operation, **kwargs)
    except (ValueError, OSError, TypeError, RuntimeError) as exc:
        raise ToolError(str(exc)) from exc


server = MCPServer(
    "organon",
    description="Evidence-linked case workflow with review, contradictions, phase gates and traceability.",
    instructions=(
        "Start with init, add items with put, inspect status and gate before advance. "
        "Record reviews and human decisions explicitly. Signed cases require an offline Ed25519 "
        "signature checked against the operator-controlled ORGANON_APPROVERS_FILE."
    ),
)


@server.tool(description="Create a case at path with a title, domain and actor label.")
def init(path: str, title: str, domain: str, actor: str, approval_policy: str = "signed") -> dict[str, Any]:
    return _invoke("init", path=path, title=title, domain=domain, actor=actor, approval_policy=approval_policy)


@server.tool(description="Add or revise an evidence-linked case item; supply expected_version and expected_deps for guarded concurrent writes.")
def put(
    path: str,
    id: str,
    kind: str,
    text: str,
    actor: str,
    refs: list[str] | None = None,
    data: dict[str, Any] | None = None,
    expected_version: int | None = None,
    expected_deps: dict[str, int] | None = None,
) -> dict[str, Any]:
    return _invoke("put", path=path, id=id, kind=kind, text=text, refs=refs or [], data=data or {}, actor=actor,
                   expected_version=expected_version, expected_deps=expected_deps)


@server.tool(description="Read the current case state.")
def status(path: str) -> dict[str, Any]:
    return _invoke("status", path=path)


@server.tool(description="Record an item review with a verdict and reason.")
def review(path: str, id: str, verdict: str, reason: str, actor: str) -> dict[str, Any]:
    return _invoke("review", path=path, id=id, verdict=verdict, reason=reason, actor=actor)


@server.tool(description="Return canonical bytes for offline Ed25519 signing of an exact normative item revision.")
def approval_challenge(path: str, id: str, reason: str, actor: str) -> dict[str, Any]:
    return _invoke("approval_challenge", path=path, id=id, reason=reason, actor=actor)


@server.tool(description="Record a normative approval; signed cases require a trusted Ed25519 signature.")
def approve(path: str, id: str, reason: str, actor: str, signature: str | None = None) -> dict[str, Any]:
    return _invoke("approve", path=path, id=id, reason=reason, actor=actor, signature=signature)


@server.tool(description="Record a contradiction between two items.")
def challenge(path: str, left: str, right: str, reason: str, actor: str) -> dict[str, Any]:
    return _invoke("challenge", path=path, left=left, right=right, reason=reason, actor=actor)


@server.tool(description="Resolve a contradiction using an existing resolution item.")
def resolve_challenge(path: str, challenge_seq: int, resolution_item: str, actor: str) -> dict[str, Any]:
    return _invoke(
        "resolve_challenge", path=path, challenge_seq=challenge_seq, resolution_item=resolution_item, actor=actor
    )


@server.tool(description="Evaluate the requirements for advancing a phase without changing state.")
def gate(path: str, phase: str) -> dict[str, Any]:
    return _invoke("gate", path=path, phase=phase)


@server.tool(description="Record a phase review with a verdict and reason.")
def review_phase(path: str, phase: str, verdict: str, reason: str, actor: str) -> dict[str, Any]:
    return _invoke("review_phase", path=path, phase=phase, verdict=verdict, reason=reason, actor=actor)


@server.tool(description="Advance the requested phase only when the engine gate permits it.")
def advance(path: str, phase: str, actor: str) -> dict[str, Any]:
    return _invoke("advance", path=path, phase=phase, actor=actor)


@server.tool(description="Trace an item to its referenced inputs and dependents.")
def trace(path: str, id: str) -> dict[str, Any]:
    return _invoke("trace", path=path, id=id)


@server.tool(description="Get bounded, versioned instructions for the next pending workflow task.")
def next_task(path: str, roles: dict[str, str] | None = None) -> dict[str, Any]:
    return _invoke("next_task", path=path, roles=roles)


@server.tool(description="Apply a schema 1 workflow manifest; pause at human approval or independent review.")
def run(path: str, manifest: dict[str, Any], actor: str) -> dict[str, Any]:
    return _invoke("run", path=path, manifest=manifest, actor=actor)


def main() -> None:
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
