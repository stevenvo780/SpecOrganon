"""Inspect a common tool policy's declared format and limits without executing it.

The caller must supply either a release manifest or independently expected
limits. A successful inspection does not enforce any declared runtime policy.

Usage::

    python scripts/tool_policy.py POLICY --release-manifest MANIFEST
    python scripts/tool_policy.py POLICY --expected-limits '{"measured_tokens":80000,"active_seconds":5400,"tool_calls":120}'
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
import sys
from contextlib import ExitStack
from pathlib import Path
from typing import Any


MAX_POLICY_BYTES = 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
CHUNK_SIZE = 64 * 1024
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
POLICY_FIELDS = frozenset(
    {
        "schema",
        "classification",
        "runtime_image_sha256",
        "network",
        "read_roots",
        "write_roots",
        "generic_tools",
        "limits",
    }
)
TOOL_FIELDS = frozenset({"id", "version", "executable_sha256"})
TOOL_FIELDS_V2 = TOOL_FIELDS | {"profile"}
EXECUTION_PROFILES = frozenset({"workspace", "analysis_readonly"})
LIMIT_FIELDS = frozenset({"measured_tokens", "active_seconds", "tool_calls"})
POLICY_CLASSIFICATION = "common_tool_policy_development_unenforced"
INSPECTION_CLASSIFICATION = "development_tool_policy_inspection_unenforced"
INSPECTION_NOTICE = (
    "Format and declared limits were checked against caller-supplied limits; "
    "this inspection does not enforce sandbox, network, tool access, or runtime caps."
)
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
TOOL_ID_RE = re.compile(r"[a-z][a-z0-9_-]*\Z")


class ToolPolicyError(ValueError):
    """The policy or its expected limits failed strict inspection."""


def _exact_object(value: Any, label: str, fields: frozenset[str]) -> dict[str, Any]:
    if type(value) is not dict or set(value) != fields:
        raise ToolPolicyError(f"{label} must contain exactly {sorted(fields)}")
    return value


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ToolPolicyError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise ToolPolicyError("non-JSON numeric constant")


def _finite_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ToolPolicyError("nonfinite JSON number")
    return result


def _parse_json(data: bytes | str, label: str) -> Any:
    try:
        source = data.decode("utf-8") if isinstance(data, bytes) else data
        return json.loads(
            source,
            object_pairs_hook=_unique_pairs,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
        )
    except ToolPolicyError:
        raise
    except (UnicodeError, ValueError, OverflowError, RecursionError) as exc:
        raise ToolPolicyError(f"{label} is not valid strict JSON") from exc


def _same_file_state(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev == right.st_dev
        and left.st_ino == right.st_ino
        and left.st_mode == right.st_mode
        and left.st_uid == right.st_uid
        and left.st_nlink == right.st_nlink
        and left.st_size == right.st_size
        and left.st_mtime_ns == right.st_mtime_ns
        and left.st_ctime_ns == right.st_ctime_ns
    )


def _same_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def _open_directory_chain(
    path: Path | str, label: str, stack: ExitStack
) -> tuple[int, str, list[tuple[int, str, int]]]:
    raw = os.fspath(path)
    if type(raw) is not str or "\x00" in raw:
        raise ToolPolicyError(f"{label} path is invalid")
    if raw.endswith("/"):
        raise ToolPolicyError(f"{label} path must name a file without a trailing slash")
    components = [part for part in raw.split("/") if part]
    if not components:
        raise ToolPolicyError(f"{label} path has no file name")
    directory_fd = os.open("/" if raw.startswith("/") else ".", DIRECTORY_FLAGS)
    stack.callback(os.close, directory_fd)
    chain: list[tuple[int, str, int]] = []
    for component in components[:-1]:
        child_fd = os.open(component, DIRECTORY_FLAGS, dir_fd=directory_fd)
        stack.callback(os.close, child_fd)
        chain.append((directory_fd, component, child_fd))
        directory_fd = child_fd
    return directory_fd, components[-1], chain


def _check_directory_chain(chain: list[tuple[int, str, int]], label: str) -> None:
    for parent_fd, name, opened_fd in chain:
        opened = os.fstat(opened_fd)
        named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if (
            not stat.S_ISDIR(opened.st_mode)
            or not stat.S_ISDIR(named.st_mode)
            or not _same_identity(opened, named)
        ):
            raise ToolPolicyError(f"{label} parent directory changed while being read")


def _read_bounded_file(path: Path | str, label: str, maximum: int) -> bytes:
    """Read a regular file through a no-follow path and recheck every component."""
    try:
        with ExitStack() as stack:
            parent_fd, name, chain = _open_directory_chain(path, label, stack)
            fd = os.open(name, FILE_FLAGS, dir_fd=parent_fd)
            stack.callback(os.close, fd)
            _check_directory_chain(chain, label)
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
                raise ToolPolicyError(f"{label} must be a bounded regular file")
            chunks: list[bytes] = []
            total = 0
            while chunk := os.read(fd, min(CHUNK_SIZE, maximum - total + 1)):
                total += len(chunk)
                if total > maximum:
                    raise ToolPolicyError(f"{label} is too large")
                chunks.append(chunk)
            after = os.fstat(fd)
            named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if (
                total != before.st_size
                or not _same_file_state(before, after)
                or not _same_file_state(before, named)
            ):
                raise ToolPolicyError(f"{label} changed while being read")
            _check_directory_chain(chain, label)
            return b"".join(chunks)
    except (OSError, TypeError, ValueError) as exc:
        if isinstance(exc, ToolPolicyError):
            raise
        raise ToolPolicyError(f"{label} cannot be read securely") from exc


def _sha256(value: Any, label: str) -> None:
    if type(value) is not str or SHA256_RE.fullmatch(value) is None:
        raise ToolPolicyError(f"{label} must be lowercase SHA-256 hex")


def _limits(value: Any, label: str) -> dict[str, int]:
    limits = _exact_object(value, label, LIMIT_FIELDS)
    for field in LIMIT_FIELDS:
        if type(limits[field]) is not int or limits[field] <= 0:
            raise ToolPolicyError(f"{label}.{field} must be a positive integer")
    return limits


def _validate_policy(raw: Any) -> dict[str, Any]:
    policy = _exact_object(raw, "tool policy", POLICY_FIELDS)
    if type(policy["schema"]) is not int or policy["schema"] not in (1, 2):
        raise ToolPolicyError("tool policy schema must be integer 1 or 2")
    if (
        type(policy["classification"]) is not str
        or policy["classification"] != POLICY_CLASSIFICATION
    ):
        raise ToolPolicyError("tool policy classification is invalid")
    _sha256(policy["runtime_image_sha256"], "runtime_image_sha256")
    if type(policy["network"]) is not str or policy["network"] != "disabled":
        raise ToolPolicyError("tool policy network must be disabled")
    if type(policy["read_roots"]) is not list or policy["read_roots"] != ["/case"]:
        raise ToolPolicyError("tool policy read_roots must be exactly ['/case']")
    if type(policy["write_roots"]) is not list or policy["write_roots"] != ["/work"]:
        raise ToolPolicyError("tool policy write_roots must be exactly ['/work']")

    tools = policy["generic_tools"]
    if type(tools) is not list:
        raise ToolPolicyError("tool policy generic_tools must be a list")
    seen: set[str] = set()
    for index, raw_tool in enumerate(tools):
        label = f"generic_tools[{index}]"
        tool = _exact_object(raw_tool, label,
                             TOOL_FIELDS_V2 if policy["schema"] == 2 else TOOL_FIELDS)
        tool_id = tool["id"]
        if type(tool_id) is not str or TOOL_ID_RE.fullmatch(tool_id) is None:
            raise ToolPolicyError(f"{label}.id must be a simple lowercase ID")
        if tool_id in seen:
            raise ToolPolicyError(f"duplicate generic tool id: {tool_id}")
        seen.add(tool_id)
        version = tool["version"]
        if type(version) is not str or not version.strip():
            raise ToolPolicyError(f"{label}.version must be nonempty")
        _sha256(tool["executable_sha256"], f"{label}.executable_sha256")
        if policy["schema"] == 2 and tool["profile"] not in EXECUTION_PROFILES:
            raise ToolPolicyError(f"{label}.profile is not a fixed execution profile")
    _limits(policy["limits"], "tool policy limits")
    return policy


def execution_profile(selected: dict[str, Any]) -> str:
    """Resolve a validated tool's fixed host capability, retaining v1 behavior."""
    if type(selected) is not dict or set(selected) not in (TOOL_FIELDS, TOOL_FIELDS_V2):
        raise ToolPolicyError("selected tool fields are invalid")
    profile = selected.get("profile", "workspace")
    if type(profile) is not str or profile not in EXECUTION_PROFILES:
        raise ToolPolicyError("selected tool profile is invalid")
    return profile


def validate_tool_policy_bytes(
    data: bytes, *, expected_limits: dict[str, Any]
) -> dict[str, Any]:
    """Return strict policy declarations after matching independently known caps.

    The returned tool IDs and digests are declarations. A caller that executes
    a tool must separately bind an executable path to its bytes and enforce
    the runtime restrictions; this function does neither.
    """
    expected = _limits(expected_limits, "expected limits")
    if type(data) is not bytes or len(data) > MAX_POLICY_BYTES:
        raise ToolPolicyError("tool policy bytes must be bounded bytes")
    policy = _validate_policy(_parse_json(data, "tool policy"))
    if policy["limits"] != expected:
        raise ToolPolicyError(
            "tool policy limits differ from release or expected limits"
        )
    return policy


def _inspect_policy_data(data: bytes, expected: dict[str, int]) -> dict[str, Any]:
    policy = validate_tool_policy_bytes(data, expected_limits=expected)
    return {
        "schema": 1,
        "classification": INSPECTION_CLASSIFICATION,
        "notice": INSPECTION_NOTICE,
        "sha256": hashlib.sha256(data).hexdigest(),
        "limits": dict(policy["limits"]),
    }


def inspect_tool_policy_bytes(
    data: bytes, *, expected_limits: dict[str, Any]
) -> dict[str, Any]:
    """Inspect already pinned policy bytes against independently known caps."""
    return _inspect_policy_data(data, _limits(expected_limits, "expected limits"))


def inspect_tool_policy(
    policy_path: Path | str,
    *,
    release_manifest: dict[str, Any] | Path | str | None = None,
    expected_limits: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Check policy bytes and compare its caps with one caller-supplied source.

    A manifest supplied as a mapping is assumed to have been read or verified by
    the caller. A path is opened and parsed strictly, but its authenticity is
    not established by this function.
    """
    if (release_manifest is None) == (expected_limits is None):
        raise ToolPolicyError("provide exactly one release manifest or expected limits")
    if release_manifest is not None:
        if isinstance(release_manifest, (str, os.PathLike)):
            release_manifest = _parse_json(
                _read_bounded_file(
                    release_manifest, "release manifest", MAX_MANIFEST_BYTES
                ),
                "release manifest",
            )
        if type(release_manifest) is not dict or "limits" not in release_manifest:
            raise ToolPolicyError("release manifest must contain limits")
        expected = _limits(release_manifest["limits"], "release manifest limits")
    else:
        expected = _limits(expected_limits, "expected limits")

    data = _read_bounded_file(policy_path, "tool policy", MAX_POLICY_BYTES)
    return _inspect_policy_data(data, expected)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("policy", help="path to the common tool policy JSON")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--release-manifest", help="path to a release manifest JSON")
    source.add_argument(
        "--expected-limits", help="JSON object containing expected caps"
    )
    args = parser.parse_args(argv)
    try:
        expected = (
            _parse_json(args.expected_limits, "expected limits")
            if args.expected_limits is not None
            else None
        )
        result = inspect_tool_policy(
            args.policy,
            release_manifest=args.release_manifest,
            expected_limits=expected,
        )
    except ToolPolicyError as exc:
        print(f"Tool policy inspection failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
