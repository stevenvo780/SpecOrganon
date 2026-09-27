"""Prepare one unsealed release's visible bytes without executing a model.

Usage: ``python scripts/stage_released_run.py schedule.json /absolute/release /absolute/new-stage --gate-dir /absolute/gate``.

For local development without block sequencing, use
``--development-unsequenced`` explicitly instead of ``--gate-dir``.

The stage is a private, new directory containing only the selected run's
visible case, policy, arm inputs, and an empty work directory. It is not a
runtime sandbox or a confirmatory execution receipt.
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
    MAX_CASE_JSON_BYTES,
    _check_destination_path,
    _check_parent_chain,
    _open_parent_chain,
    extract_package,
    inspect_package,
)
from inspect_released_payload import PayloadInspectionError, inspect_released_payload
from local_block_release_gate import BlockReleaseError, verify_claim
from preflight_assets import _selected_assets
from verify_released_run import (
    DIRECTORY_FLAGS,
    ReleaseVerificationError,
    _check_directory_chain,
    _check_release_file,
    _open_directory_chain,
    _open_release_file,
    _read_schedule,
    verify_release,
)


CLASSIFICATION = "development_run_stage_unsealed"
NOTICE = (
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
CHUNK_SIZE = 1024 * 1024


class StageError(ValueError):
    """The visible run could not be staged securely or completely."""


def _named_dir_matches(parent_fd: int, name: str, opened_fd: int) -> bool:
    named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    opened = os.fstat(opened_fd)
    return (
        stat.S_ISDIR(named.st_mode)
        and (named.st_dev, named.st_ino) == (opened.st_dev, opened.st_ino)
        and named.st_uid == os.geteuid()
        and stat.S_IMODE(named.st_mode) == 0o700
    )


def _new_private_dir(parent_fd: int, name: str, stack: ExitStack) -> int:
    os.mkdir(name, 0o700, dir_fd=parent_fd)
    directory_fd = os.open(name, DIRECTORY_FLAGS, dir_fd=parent_fd)
    stack.callback(os.close, directory_fd)
    os.fchmod(directory_fd, 0o700)
    if not _named_dir_matches(parent_fd, name, directory_fd):
        raise StageError(f"{name} directory identity changed")
    os.fsync(parent_fd)
    return directory_fd


def _write_pending_manifest(root_fd: int, manifest: dict[str, Any]) -> None:
    data = (
        json.dumps(
            manifest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )
    fd = os.open(
        ".stage.json.pending",
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
        dir_fd=root_fd,
    )
    with os.fdopen(fd, "wb") as output:
        os.fchmod(output.fileno(), 0o600)
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
    os.fsync(root_fd)


def _read_staged_digest(directory_fd: int, role: str, expected_size: int) -> str:
    fd = os.open(role, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=directory_fd)
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_size != expected_size
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o600
        ):
            raise StageError(f"{role} staged size or file type changed")
        digest = hashlib.sha256()
        remaining = expected_size
        while remaining:
            chunk = os.read(fd, min(CHUNK_SIZE, remaining))
            if not chunk:
                raise StageError(f"{role} staged bytes were truncated")
            digest.update(chunk)
            remaining -= len(chunk)
        if os.read(fd, 1):
            raise StageError(f"{role} staged bytes grew")
        named = os.stat(role, dir_fd=directory_fd, follow_symlinks=False)
        if (info.st_dev, info.st_ino) != (named.st_dev, named.st_ino):
            raise StageError(f"{role} staged file identity changed")
        return digest.hexdigest()
    finally:
        os.close(fd)


def _copy_role(
    source_fd: int,
    directory_fd: int,
    role: str,
    expected_size: int,
    expected_sha256: str,
) -> dict[str, Any]:
    os.lseek(source_fd, 0, os.SEEK_SET)
    output_fd = os.open(
        role,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
        dir_fd=directory_fd,
    )
    digest = hashlib.sha256()
    with os.fdopen(output_fd, "wb") as output:
        os.fchmod(output.fileno(), 0o600)
        remaining = expected_size
        while remaining:
            chunk = os.read(source_fd, min(CHUNK_SIZE, remaining))
            if not chunk:
                raise StageError(f"{role} source was truncated")
            output.write(chunk)
            digest.update(chunk)
            remaining -= len(chunk)
        if os.read(source_fd, 1):
            raise StageError(f"{role} source grew")
        output.flush()
        os.fsync(output.fileno())
    if digest.hexdigest() != expected_sha256:
        raise StageError(f"{role} source bytes differ from schedule")
    if _read_staged_digest(directory_fd, role, expected_size) != expected_sha256:
        raise StageError(f"{role} staged bytes differ from schedule")
    return {"file": role, "sha256": expected_sha256, "bytes": expected_size}


def _case_json_from_archive(inputs_fd: int) -> bytes:
    fd = os.open(
        "case_package",
        os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW,
        dir_fd=inputs_fd,
    )
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise StageError("staged case_package is not a regular file")
        with os.fdopen(os.dup(fd), "rb") as file, zipfile.ZipFile(file) as archive:
            with archive.open("case.json", "r") as member:
                data = member.read(MAX_CASE_JSON_BYTES + 1)
            if len(data) > MAX_CASE_JSON_BYTES:
                raise StageError("case.json exceeds its source limit")
            return data
    finally:
        os.close(fd)


def _verify_case_tree(
    case_fd: int, case_manifest: dict[str, Any], case_json: bytes
) -> None:
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
        for length, part in enumerate(parts):
            parent = parts[:length]
            expected_entries.setdefault(parent, set()).add(part)
            if length < len(parts) - 1:
                expected_entries.setdefault(parts[: length + 1], set())

    def walk(directory_fd: int, prefix: tuple[str, ...]) -> None:
        if set(os.listdir(directory_fd)) != expected_entries[prefix]:
            raise StageError("extracted case has missing or extra entries")
        for name in sorted(expected_entries[prefix]):
            child = (*prefix, name)
            if child in expected_entries:
                fd = os.open(name, DIRECTORY_FLAGS, dir_fd=directory_fd)
                try:
                    if not _named_dir_matches(directory_fd, name, fd):
                        raise StageError("extracted case directory identity changed")
                    walk(fd, child)
                finally:
                    os.close(fd)
            else:
                size, expected_sha256 = expected_files[child]
                if _read_staged_digest(directory_fd, name, size) != expected_sha256:
                    raise StageError("extracted case bytes differ from bound package")

    walk(case_fd, ())


def stage_released_run(
    schedule_raw: Any,
    release_dir: Path | str,
    output_dir: Path | str,
    *,
    gate_root: Path | str | None = None,
    development_unsequenced: bool = False,
    attempt_number: int = 1,
) -> dict[str, Any]:
    """Copy one verified visible release into a new private stage.

    A failure after creating the stage leaves a partial directory without
    ``stage.json``. Its bytes are untrusted and must never be executed.
    """
    if type(development_unsequenced) is not bool:
        raise StageError("development_unsequenced must be a boolean")
    if (gate_root is None and not development_unsequenced) or (
        gate_root is not None and development_unsequenced
    ):
        raise StageError("staging requires exactly one of gate_root or development_unsequenced")
    if type(attempt_number) is not int or attempt_number < 1:
        raise StageError("attempt_number must be a positive integer")
    if attempt_number > 1 and gate_root is None:
        raise StageError("retry staging requires gate_root")
    try:
        # API callers may retain and mutate their input while this function
        # runs. Every check and the published manifest must use one snapshot.
        schedule_raw = copy.deepcopy(schedule_raw)
    except (TypeError, ValueError, RuntimeError, RecursionError) as exc:
        raise StageError("candidate schedule cannot be snapshotted") from exc
    try:
        first = verify_release(schedule_raw, release_dir)
        inspection = inspect_released_payload(schedule_raw, release_dir)
    except (ReleaseVerificationError, PayloadInspectionError) as exc:
        raise StageError("release verification or visible inspection failed") from exc
    if first["run_id"] != inspection["run_id"]:
        raise StageError("release changed between checks")
    if (
        first["attempt_number"] != attempt_number
        or inspection["attempt_number"] != attempt_number
    ):
        raise StageError("release attempt differs from requested attempt")
    run = next(
        item for item in schedule_raw["runs"] if item["run_id"] == first["run_id"]
    )
    if inspection["execution_ready"] is not False:
        raise StageError("visible inspection unexpectedly claimed execution readiness")
    if not Path(output_dir).is_absolute():
        raise StageError("output_dir must be absolute")
    claim = None
    if gate_root is not None:
        try:
            claim = verify_claim(
                schedule_raw,
                run["run_id"],
                gate_root,
                release_dir,
                attempt_number=attempt_number,
            )
        except BlockReleaseError as exc:
            raise StageError(f"release gate rejected stage: {exc}") from exc

    created = False
    try:
        with ExitStack() as stack:
            release_fd, _release_parent, _release_name, release_chain, release_info = (
                _open_directory_chain(release_dir, stack)
            )
            _check_directory_chain(release_chain, release_info)
            roles = tuple(_selected_assets(run))
            opened: dict[str, tuple[int, os.stat_result]] = {}
            for role in roles:
                opened[role] = _open_release_file(release_fd, role, stack)
            _check_directory_chain(release_chain, release_info)

            parent_chain: list[tuple[int, str, int]] = []
            parent_fd, name = _open_parent_chain(output_dir, stack, parent_chain)
            _check_parent_chain(parent_chain)
            parent = os.fstat(parent_fd)
            if parent.st_uid != os.geteuid() or parent.st_mode & 0o022:
                raise StageError(
                    "output parent must be private and owned by current UID"
                )
            os.mkdir(name, 0o700, dir_fd=parent_fd)
            created = True
            root_fd = os.open(name, DIRECTORY_FLAGS, dir_fd=parent_fd)
            stack.callback(os.close, root_fd)
            os.fchmod(root_fd, 0o700)
            if not _named_dir_matches(parent_fd, name, root_fd):
                raise StageError("stage directory identity changed")
            os.fsync(parent_fd)
            created_info = os.fstat(root_fd)
            root_identity = (created_info.st_dev, created_info.st_ino)
            _check_destination_path(
                parent_chain, root_fd, parent_fd, name, root_identity
            )
            inputs_fd = _new_private_dir(root_fd, "inputs", stack)
            work_fd = _new_private_dir(root_fd, "work", stack)

            copied: dict[str, dict[str, Any]] = {}
            for role in roles:
                fd, source_info = opened[role]
                _check_release_file(release_fd, role, fd, source_info)
                expected = (
                    schedule_raw["inputs"]["arm_prompts"][run["arm"]]["sha256"]
                    if role == "arm_prompt"
                    else None
                )
                if role == "case_package":
                    expected = run["case_package_sha256"]
                elif role != "arm_prompt":
                    expected = schedule_raw["inputs"][role]["sha256"]
                copied[role] = _copy_role(
                    fd, inputs_fd, role, source_info.st_size, expected
                )
                _check_release_file(release_fd, role, fd, source_info)
                _check_destination_path(
                    parent_chain, root_fd, parent_fd, name, root_identity
                )
                if not _named_dir_matches(root_fd, "inputs", inputs_fd):
                    raise StageError("inputs directory identity changed")

            case_manifest = extract_package(
                Path(output_dir) / "inputs" / "case_package",
                Path(output_dir) / "case",
                expected_case_id=run["case_id"],
            )
            bound_case_manifest = inspect_package(
                Path(output_dir) / "inputs" / "case_package",
                expected_case_id=run["case_id"],
            )
            if case_manifest != bound_case_manifest:
                raise StageError("extracted case manifest differs from bound package")
            case_json = _case_json_from_archive(inputs_fd)
            case_fd = os.open("case", DIRECTORY_FLAGS, dir_fd=root_fd)
            stack.callback(os.close, case_fd)
            if not _named_dir_matches(root_fd, "case", case_fd):
                raise StageError("case directory identity changed")
            _verify_case_tree(case_fd, bound_case_manifest, case_json)
            _check_destination_path(
                parent_chain, root_fd, parent_fd, name, root_identity
            )
            if not _named_dir_matches(root_fd, "inputs", inputs_fd):
                raise StageError("inputs directory identity changed")
            if not _named_dir_matches(root_fd, "work", work_fd):
                raise StageError("work directory identity changed")
            if os.listdir(work_fd):
                raise StageError("work directory is not empty")
            if set(os.listdir(inputs_fd)) != set(roles):
                raise StageError("staged inputs have missing or extra entries")
            for role, record in copied.items():
                if (
                    _read_staged_digest(inputs_fd, role, record["bytes"])
                    != record["sha256"]
                ):
                    raise StageError(f"{role} changed before stage manifest")
            if set(os.listdir(root_fd)) != {"case", "inputs", "work"}:
                raise StageError("stage has missing or extra entries")
            for role, (fd, source_info) in opened.items():
                _check_release_file(release_fd, role, fd, source_info)
            _check_directory_chain(release_chain, release_info)
            final = verify_release(schedule_raw, release_dir)
            if final != first:
                raise StageError("release changed during staging")

            manifest = {
                "schema": 1,
                "classification": CLASSIFICATION,
                "notice": NOTICE,
                "run_id": run["run_id"],
                "run_sha256": run["run_sha256"],
                "schedule_sha256": final["schedule_sha256"],
                "coordinates": {key: run[key] for key in COORDINATE_FIELDS},
                "limits": schedule_raw["per_run_limits"],
                "case_task_file": case_manifest["task_file"],
                "deliverables": case_manifest["deliverables"],
                "visible_files": copied,
                "toolkit_format": inspection["toolkit_format"],
                "toolkit_target": inspection["toolkit_target"],
                "toolkit_install_checked": False,
                "execution_ready": False,
                "runtime_enforced": False,
                "provider_receipts_checked": False,
                "custody_verified": False,
            }
            if attempt_number > 1:
                if claim is None:
                    raise StageError("retry stage lacks a verified release claim")
                manifest.update(
                    schema=2,
                    attempt_number=attempt_number,
                    release_dir=claim["release_dir"],
                    claim_sha256=claim["claim_sha256"],
                    publication_sha256=claim["publication_sha256"],
                )
            os.fsync(inputs_fd)
            os.fsync(case_fd)
            os.fsync(work_fd)
            if not _named_dir_matches(root_fd, "case", case_fd):
                raise StageError("case directory identity changed")
            _verify_case_tree(case_fd, bound_case_manifest, case_json)
            if not _named_dir_matches(root_fd, "work", work_fd) or os.listdir(work_fd):
                raise StageError("work directory changed before stage manifest")
            _check_destination_path(
                parent_chain, root_fd, parent_fd, name, root_identity
            )
            _write_pending_manifest(root_fd, manifest)
            _check_destination_path(
                parent_chain, root_fd, parent_fd, name, root_identity
            )
            if not _named_dir_matches(root_fd, "inputs", inputs_fd):
                raise StageError("inputs changed before manifest publication")
            if not _named_dir_matches(root_fd, "case", case_fd):
                raise StageError("case changed before manifest publication")
            if not _named_dir_matches(root_fd, "work", work_fd) or os.listdir(work_fd):
                raise StageError("work changed before manifest publication")
            _verify_case_tree(case_fd, bound_case_manifest, case_json)
            for role, record in copied.items():
                if (
                    _read_staged_digest(inputs_fd, role, record["bytes"])
                    != record["sha256"]
                ):
                    raise StageError(f"{role} changed before manifest publication")
            if set(os.listdir(root_fd)) != {
                "case",
                "inputs",
                "work",
                ".stage.json.pending",
            }:
                raise StageError("stage changed before manifest publication")
            os.fsync(parent_fd)
            os.rename(
                ".stage.json.pending",
                "stage.json",
                src_dir_fd=root_fd,
                dst_dir_fd=root_fd,
            )
            return manifest
    except (
        OSError,
        CasePackageError,
        ReleaseVerificationError,
        StageError,
        zipfile.BadZipFile,
        KeyError,
    ) as exc:
        suffix = "; partial stage is untrusted" if created else ""
        raise StageError(f"staging failed{suffix}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "schedule", help="independently supplied candidate schedule JSON"
    )
    parser.add_argument("release_dir", help="absolute path to one released run")
    parser.add_argument("output_dir", help="absolute path for a new private stage")
    parser.add_argument(
        "--attempt-number", type=int, default=1,
        help="release attempt number (default: 1; retries require --gate-dir)",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--gate-dir", help="absolute durable block release gate directory")
    mode.add_argument(
        "--development-unsequenced",
        action="store_true",
        help="explicitly stage without block sequencing for local development",
    )
    args = parser.parse_args(argv)
    try:
        result = stage_released_run(
            _read_schedule(args.schedule),
            args.release_dir,
            args.output_dir,
            gate_root=args.gate_dir,
            development_unsequenced=args.development_unsequenced,
            attempt_number=args.attempt_number,
        )
    except (ReleaseVerificationError, StageError) as exc:
        print(f"Run staging failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
