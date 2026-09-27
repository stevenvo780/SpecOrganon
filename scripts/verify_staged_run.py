"""Verify an existing development stage against a caller-supplied schedule.

Usage: ``python scripts/verify_staged_run.py SCHEDULE.json RUN_ID /absolute/STAGE``.

This is a read-only, point-in-time check of visible bytes and metadata. The
schedule is unauthenticated, and a same-UID process can change the stage after
this function returns. The result is not an execution authorization.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import stat
import sys
import zipfile
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from case_package import (
    CasePackageError,
    MAX_ARCHIVE_BYTES,
    MAX_CASE_JSON_BYTES,
    MAX_ENTRY_BYTES,
    inspect_package_fd,
)
from inspect_toolkit_wheel import (
    MAX_WHEEL_BYTES,
    ToolkitWheelError,
    inspect_toolkit_wheel_bytes,
)
from preflight_assets import PreflightError, _candidate_schedule, _selected_assets
from tool_policy import MAX_POLICY_BYTES, ToolPolicyError, inspect_tool_policy_bytes
from toolkit_bundle import (
    MAX_BUNDLE_BYTES,
    ToolkitBundleError,
    inspect_toolkit_bundle_bytes,
)
from verify_released_run import (
    CHUNK_SIZE,
    DIRECTORY_FLAGS,
    ReleaseVerificationError,
    _canonical,
    _check_directory_chain,
    _check_release_file,
    _open_directory_chain,
    _open_release_file,
    _parse_json,
    _read_manifest,
    _read_schedule,
    _same_file_state,
    verify_release,
)


CLASSIFICATION = "development_stage_verification_unsealed"
NOTICE = (
    "Point-in-time consistency against an unauthenticated caller-supplied "
    "schedule; no seal, custody, runtime enforcement, or execution readiness "
    "is established. Recheck before any later use."
)
STAGE_CLASSIFICATION = "development_run_stage_unsealed"
STAGE_NOTICE = (
    "Visible bytes only; the caller-supplied schedule is unauthenticated. "
    "No runtime isolation, policy enforcement, provider receipt, human approval, "
    "or external custody is established."
)
COORDINATE_FIELDS = (
    "model_id",
    "model_version",
    "effort",
    "effort_provider_value",
    "agents",
    "arm",
    "case_id",
)
STAGE_FIELDS = frozenset(
    {
        "schema",
        "classification",
        "notice",
        "run_id",
        "run_sha256",
        "schedule_sha256",
        "coordinates",
        "limits",
        "case_task_file",
        "deliverables",
        "visible_files",
        "toolkit_format",
        "toolkit_target",
        "toolkit_install_checked",
        "execution_ready",
        "runtime_enforced",
        "provider_receipts_checked",
        "custody_verified",
    }
)
GATED_STAGE_FIELDS = STAGE_FIELDS | frozenset(
    {"attempt_number", "release_dir", "claim_sha256", "publication_sha256"}
)
TEXT_ROLES = frozenset({"task_contract", "common_prompt", "arm_prompt", "sdd_guide"})


class StageVerificationError(ValueError):
    """A published stage failed a read-only consistency check."""


def _exact_object(
    value: Any, fields: set[str] | frozenset[str], label: str
) -> dict[str, Any]:
    if type(value) is not dict or set(value) != set(fields):
        raise StageVerificationError(f"{label} has missing or extra fields")
    return value


def _expected_digest(schedule: dict[str, Any], run: dict[str, Any], role: str) -> str:
    if role == "case_package":
        return run["case_package_sha256"]
    if role == "arm_prompt":
        return schedule["inputs"]["arm_prompts"][run["arm"]]["sha256"]
    return schedule["inputs"][role]["sha256"]


def _role_limit(role: str) -> int:
    if role == "case_package":
        return MAX_ARCHIVE_BYTES
    if role == "tool_policy":
        return MAX_POLICY_BYTES
    if role == "toolkit":
        return max(MAX_WHEEL_BYTES, MAX_BUNDLE_BYTES)
    return 1024 * 1024


def _validate_manifest(
    raw: Any, schedule: dict[str, Any], run: dict[str, Any]
) -> dict[str, Any]:
    if type(raw) is not dict or type(raw.get("schema")) is not int:
        raise StageVerificationError("stage.json schema is invalid")
    schema = raw["schema"]
    if schema not in (1, 2):
        raise StageVerificationError("stage.json schema is invalid")
    manifest = _exact_object(
        raw, STAGE_FIELDS if schema == 1 else GATED_STAGE_FIELDS, "stage.json"
    )
    if schema == 2:
        attempt_number = manifest["attempt_number"]
        release_dir = manifest["release_dir"]
        if type(attempt_number) is not int or attempt_number < 1:
            raise StageVerificationError("gated stage attempt_number is invalid")
        if type(release_dir) is not str or not release_dir.startswith("/"):
            raise StageVerificationError("gated stage release_dir must be absolute")
        for field in ("claim_sha256", "publication_sha256"):
            digest = manifest[field]
            if (
                type(digest) is not str
                or len(digest) != 64
                or any(character not in "0123456789abcdef" for character in digest)
            ):
                raise StageVerificationError(f"gated stage {field} is invalid")
    if (
        type(manifest["classification"]) is not str
        or manifest["classification"] != STAGE_CLASSIFICATION
        or type(manifest["notice"]) is not str
        or manifest["notice"] != STAGE_NOTICE
    ):
        raise StageVerificationError("stage.json classification or notice is invalid")
    for field, expected in (
        ("run_id", run["run_id"]),
        ("run_sha256", run["run_sha256"]),
        ("schedule_sha256", schedule["schedule_sha256"]),
    ):
        if type(manifest[field]) is not str or manifest[field] != expected:
            raise StageVerificationError(f"stage.json {field} differs from schedule")
    coordinates = _exact_object(
        manifest["coordinates"], set(COORDINATE_FIELDS), "stage coordinates"
    )
    if _canonical(coordinates) != _canonical(
        {field: run[field] for field in COORDINATE_FIELDS}
    ):
        raise StageVerificationError("stage coordinates differ from schedule")
    limits = _exact_object(
        manifest["limits"], set(schedule["per_run_limits"]), "stage limits"
    )
    if _canonical(limits) != _canonical(schedule["per_run_limits"]):
        raise StageVerificationError("stage limits differ from schedule")
    for field in (
        "toolkit_install_checked",
        "execution_ready",
        "runtime_enforced",
        "provider_receipts_checked",
        "custody_verified",
    ):
        if manifest[field] is not False:
            raise StageVerificationError(f"stage.json {field} must be false")
    if type(manifest["case_task_file"]) is not str:
        raise StageVerificationError("stage task file is invalid")
    if type(manifest["deliverables"]) is not list:
        raise StageVerificationError("stage deliverables are invalid")
    if run["arm"] == "T":
        if manifest["toolkit_format"] not in ("wheel", "bundle"):
            raise StageVerificationError("stage toolkit format is invalid")
    elif (
        manifest["toolkit_format"] is not None or manifest["toolkit_target"] is not None
    ):
        raise StageVerificationError("stage has unexpected toolkit claims")

    roles = set(_selected_assets(run))
    entries = _exact_object(manifest["visible_files"], roles, "stage visible files")
    for role in roles:
        record = _exact_object(
            entries[role], {"file", "sha256", "bytes"}, "stage file record"
        )
        if type(record["file"]) is not str or record["file"] != role:
            raise StageVerificationError("stage file record name is invalid")
        if type(record["sha256"]) is not str or record["sha256"] != _expected_digest(
            schedule, run, role
        ):
            raise StageVerificationError("stage file digest differs from schedule")
        if type(record["bytes"]) is not int or not 0 < record["bytes"] <= _role_limit(
            role
        ):
            raise StageVerificationError("stage file byte count is invalid")
    return manifest


def _read_stage_manifest(
    root_fd: int, stack: ExitStack
) -> tuple[Any, int, os.stat_result]:
    fd, info = _open_release_file(root_fd, "stage.json", stack)
    data = _read_manifest(fd, info.st_size)
    raw = _parse_json(data, "stage.json")
    if data != _canonical(raw) + b"\n":
        raise StageVerificationError(
            "stage.json is not the published canonical JSON form"
        )
    _check_release_file(root_fd, "stage.json", fd, info)
    return raw, fd, info


def _check_directory(
    parent_fd: int, name: str, fd: int, before: os.stat_result
) -> None:
    opened = os.fstat(fd)
    named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if (
        not stat.S_ISDIR(opened.st_mode)
        or not stat.S_ISDIR(named.st_mode)
        or opened.st_uid != os.geteuid()
        or stat.S_IMODE(opened.st_mode) != 0o700
        or not _same_file_state(before, opened)
        or not _same_file_state(before, named)
    ):
        raise StageVerificationError("stage directory changed or is not private")


def _open_private_directory(
    parent_fd: int, name: str, stack: ExitStack
) -> tuple[int, os.stat_result]:
    fd = os.open(name, DIRECTORY_FLAGS, dir_fd=parent_fd)
    stack.callback(os.close, fd)
    before = os.fstat(fd)
    _check_directory(parent_fd, name, fd, before)
    return fd, before


def _hash_open_file(
    directory_fd: int,
    name: str,
    fd: int,
    before: os.stat_result,
    expected_size: int,
    *,
    collect: bool = False,
) -> tuple[str, bytes | None]:
    if before.st_size != expected_size:
        raise StageVerificationError("stage file size differs from manifest")
    os.lseek(fd, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    chunks: list[bytes] = []
    remaining = expected_size
    while remaining:
        chunk = os.read(fd, min(CHUNK_SIZE, remaining))
        if not chunk:
            raise StageVerificationError("stage file was truncated")
        digest.update(chunk)
        if collect:
            chunks.append(chunk)
        remaining -= len(chunk)
    if os.read(fd, 1):
        raise StageVerificationError("stage file grew during verification")
    _check_release_file(directory_fd, name, fd, before)
    return digest.hexdigest(), b"".join(chunks) if collect else None


def _case_json(archive_fd: int) -> bytes:
    os.lseek(archive_fd, 0, os.SEEK_SET)
    with (
        os.fdopen(os.dup(archive_fd), "rb") as source,
        zipfile.ZipFile(source) as archive,
    ):
        with archive.open("case.json") as member:
            data = member.read(MAX_CASE_JSON_BYTES + 1)
            if len(data) > MAX_CASE_JSON_BYTES or member.read(1):
                raise StageVerificationError("case.json exceeds its size bound")
            return data


def _verify_case_tree(
    case_fd: int,
    case_manifest: dict[str, Any],
    case_json: bytes,
    previous_states: dict[tuple[str, ...], os.stat_result] | None = None,
) -> tuple[int, dict[tuple[str, ...], os.stat_result]]:
    expected_files = {
        tuple(item["path"].split("/")): (item["bytes"], item["sha256"])
        for item in case_manifest["files"]
    }
    expected_files[("case.json",)] = (
        len(case_json),
        hashlib.sha256(case_json).hexdigest(),
    )
    expected_entries: dict[tuple[str, ...], set[str]] = {(): set()}
    for parts in expected_files:
        for index, component in enumerate(parts):
            parent = parts[:index]
            expected_entries.setdefault(parent, set()).add(component)
            if index < len(parts) - 1:
                expected_entries.setdefault(parts[: index + 1], set())

    states: dict[tuple[str, ...], os.stat_result] = {}

    def remember(path: tuple[str, ...], before: os.stat_result) -> None:
        if previous_states is not None:
            original = previous_states.get(path)
            if original is None or not _same_file_state(original, before):
                raise StageVerificationError("extracted case changed between reads")
        states[path] = before

    def walk(directory_fd: int, prefix: tuple[str, ...]) -> None:
        if set(os.listdir(directory_fd)) != expected_entries[prefix]:
            raise StageVerificationError("extracted case has missing or extra entries")
        for name in sorted(expected_entries[prefix]):
            child = (*prefix, name)
            if child in expected_entries:
                with ExitStack() as stack:
                    fd, before = _open_private_directory(directory_fd, name, stack)
                    remember(child, before)
                    walk(fd, child)
                    _check_directory(directory_fd, name, fd, before)
            else:
                size, expected_sha256 = expected_files[child]
                if size > MAX_ENTRY_BYTES and child != ("case.json",):
                    raise StageVerificationError("case file exceeds its size bound")
                with ExitStack() as stack:
                    fd, before = _open_release_file(directory_fd, name, stack)
                    remember(child, before)
                    actual_sha256, _ = _hash_open_file(
                        directory_fd, name, fd, before, size
                    )
                    if actual_sha256 != expected_sha256:
                        raise StageVerificationError(
                            "extracted case differs from archive"
                        )
        if set(os.listdir(directory_fd)) != expected_entries[prefix]:
            raise StageVerificationError("extracted case changed during verification")

    walk(case_fd, ())
    if previous_states is not None and set(states) != set(previous_states):
        raise StageVerificationError("extracted case entries changed between reads")
    return len(expected_files), states


def _inspect_visible_content(
    schedule: dict[str, Any],
    run: dict[str, Any],
    manifest: dict[str, Any],
    opened: dict[str, tuple[int, os.stat_result]],
    captured: dict[str, bytes],
    inputs_fd: int,
    case_fd: int,
) -> tuple[int, dict[tuple[str, ...], os.stat_result]]:
    case_manifest = inspect_package_fd(
        opened["case_package"][0], expected_case_id=run["case_id"]
    )
    package_json = _case_json(opened["case_package"][0])
    case_files, case_states = _verify_case_tree(case_fd, case_manifest, package_json)
    if manifest["case_task_file"] != case_manifest["task_file"] or _canonical(
        manifest["deliverables"]
    ) != _canonical(case_manifest["deliverables"]):
        raise StageVerificationError("stage case summary differs from archive")

    policy = inspect_tool_policy_bytes(
        captured["tool_policy"], expected_limits=schedule["per_run_limits"]
    )
    if policy["sha256"] != manifest["visible_files"]["tool_policy"]["sha256"]:
        raise StageVerificationError("stage policy differs from schedule")

    if run["arm"] == "T":
        try:
            toolkit = inspect_toolkit_wheel_bytes(captured["toolkit"])
            toolkit_format = "wheel"
        except ToolkitWheelError:
            toolkit = inspect_toolkit_bundle_bytes(captured["toolkit"])
            toolkit_format = "bundle"
        if (
            toolkit["sha256"] != manifest["visible_files"]["toolkit"]["sha256"]
            or toolkit_format != manifest["toolkit_format"]
            or _canonical(toolkit.get("target"))
            != _canonical(manifest["toolkit_target"])
        ):
            raise StageVerificationError(
                "stage toolkit claims differ from static inspection"
            )
    elif (
        manifest["toolkit_format"] is not None or manifest["toolkit_target"] is not None
    ):
        raise StageVerificationError("stage has unexpected toolkit claims")

    # Rehash all opened roles after structural inspection. Descriptor metadata
    # and named entries must still match the states seen on opening.
    for role, (fd, before) in opened.items():
        expected = manifest["visible_files"][role]
        digest, _ = _hash_open_file(inputs_fd, role, fd, before, expected["bytes"])
        if digest != expected["sha256"]:
            raise StageVerificationError("stage inputs changed during inspection")
    return case_files, case_states


def verify_stage(
    schedule_raw: Any, run_id: str, stage_dir: Path | str
) -> dict[str, Any]:
    """Inspect one published stage without writing, executing, or authorizing it."""
    try:
        frozen = copy.deepcopy(schedule_raw)
    except (TypeError, ValueError, RuntimeError, RecursionError) as exc:
        raise StageVerificationError(
            "candidate schedule cannot be snapshotted"
        ) from exc
    try:
        schedule = _candidate_schedule(frozen)
    except PreflightError as exc:
        raise StageVerificationError("invalid candidate schedule") from exc
    if type(run_id) is not str:
        raise StageVerificationError("run_id must be a scheduled string")
    run = next((item for item in schedule["runs"] if item["run_id"] == run_id), None)
    if run is None:
        raise StageVerificationError("run_id is absent from schedule")

    try:
        with ExitStack() as stack:
            root_fd, _parent_fd, _name, chain, root_before = _open_directory_chain(
                stage_dir, stack
            )
            _check_directory_chain(chain, root_before)
            raw, manifest_fd, manifest_before = _read_stage_manifest(root_fd, stack)
            manifest = _validate_manifest(raw, schedule, run)
            if manifest["schema"] == 2:
                release = verify_release(schedule, manifest["release_dir"])
                if (
                    release["run_id"] != run_id
                    or release["run_sha256"] != run["run_sha256"]
                    or release["attempt_number"] != manifest["attempt_number"]
                ):
                    raise StageVerificationError(
                        "gated stage release identity differs from stage manifest"
                    )
            expected_root = {"case", "inputs", "work", "stage.json"}
            if set(os.listdir(root_fd)) != expected_root:
                raise StageVerificationError("stage root has missing or extra entries")

            inputs_fd, inputs_before = _open_private_directory(root_fd, "inputs", stack)
            case_fd, case_before = _open_private_directory(root_fd, "case", stack)
            work_fd, work_before = _open_private_directory(root_fd, "work", stack)
            if os.listdir(work_fd):
                raise StageVerificationError("stage work directory is not empty")
            roles = set(_selected_assets(run))
            if set(os.listdir(inputs_fd)) != roles:
                raise StageVerificationError(
                    "stage inputs have missing or extra entries"
                )
            opened: dict[str, tuple[int, os.stat_result]] = {}
            captured: dict[str, bytes] = {}
            verified_bytes = 0
            for role in sorted(roles):
                fd, before = _open_release_file(inputs_fd, role, stack)
                opened[role] = (fd, before)
                record = manifest["visible_files"][role]
                digest, data = _hash_open_file(
                    inputs_fd,
                    role,
                    fd,
                    before,
                    record["bytes"],
                    collect=role in TEXT_ROLES or role in {"tool_policy", "toolkit"},
                )
                if digest != record["sha256"]:
                    raise StageVerificationError("stage input differs from schedule")
                if data is not None:
                    if role in TEXT_ROLES:
                        try:
                            decoded = data.decode("utf-8", errors="strict")
                        except UnicodeError as exc:
                            raise StageVerificationError(
                                "stage text is not UTF-8"
                            ) from exc
                        if "\x00" in decoded or not decoded.strip():
                            raise StageVerificationError(
                                "stage text is empty or contains NUL"
                            )
                    else:
                        captured[role] = data
                verified_bytes += record["bytes"]

            case_files, case_states = _inspect_visible_content(
                schedule, run, manifest, opened, captured, inputs_fd, case_fd
            )
            package_json = _case_json(opened["case_package"][0])
            case_manifest = inspect_package_fd(
                opened["case_package"][0], expected_case_id=run["case_id"]
            )
            final_case_files, _ = _verify_case_tree(
                case_fd, case_manifest, package_json, case_states
            )
            if final_case_files != case_files:
                raise StageVerificationError("stage case changed during verification")
            for role, (fd, before) in opened.items():
                record = manifest["visible_files"][role]
                digest, _ = _hash_open_file(
                    inputs_fd, role, fd, before, record["bytes"]
                )
                if digest != record["sha256"]:
                    raise StageVerificationError(
                        "stage inputs changed during verification"
                    )
            if os.listdir(work_fd):
                raise StageVerificationError("stage work directory changed")
            if (
                set(os.listdir(inputs_fd)) != roles
                or set(os.listdir(root_fd)) != expected_root
            ):
                raise StageVerificationError(
                    "stage entries changed during verification"
                )
            for parent, name, fd, before in (
                (root_fd, "inputs", inputs_fd, inputs_before),
                (root_fd, "case", case_fd, case_before),
                (root_fd, "work", work_fd, work_before),
            ):
                _check_directory(parent, name, fd, before)
            _check_release_file(root_fd, "stage.json", manifest_fd, manifest_before)
            _check_directory_chain(chain, root_before)
    except StageVerificationError:
        raise
    except (
        OSError,
        ReleaseVerificationError,
        CasePackageError,
        ToolPolicyError,
        ToolkitWheelError,
        ToolkitBundleError,
        zipfile.BadZipFile,
        KeyError,
        RecursionError,
        TypeError,
        ValueError,
    ) as exc:
        raise StageVerificationError("stage could not be verified securely") from exc

    return {
        "schema": 1,
        "classification": CLASSIFICATION,
        "notice": NOTICE,
        "run_id": run_id,
        "run_sha256": run["run_sha256"],
        "schedule_sha256": schedule["schedule_sha256"],
        "attempt_number": (
            manifest["attempt_number"] if manifest["schema"] == 2 else 1
        ),
        "release_dir": manifest["release_dir"] if manifest["schema"] == 2 else None,
        "claim_sha256": manifest["claim_sha256"] if manifest["schema"] == 2 else None,
        "publication_sha256": (
            manifest["publication_sha256"] if manifest["schema"] == 2 else None
        ),
        "verified_files": len(roles),
        "verified_bytes": verified_bytes,
        "verified_case_files": case_files,
        "stage_verified_at_read": True,
        "execution_ready": False,
        "runtime_enforced": False,
        "custody_verified": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "schedule", help="independently supplied candidate schedule JSON"
    )
    parser.add_argument("run_id", help="scheduled run_id to bind to this stage")
    parser.add_argument("stage_dir", help="absolute path to an existing stage")
    args = parser.parse_args(argv)
    try:
        result = verify_stage(
            _read_schedule(args.schedule), args.run_id, args.stage_dir
        )
    except (ReleaseVerificationError, StageVerificationError) as exc:
        print(f"Stage verification failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
