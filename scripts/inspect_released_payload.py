"""Inspect one unsealed release's visible content without running its payload.

Usage: ``python scripts/inspect_released_payload.py schedule.json /absolute/release``.

The candidate schedule is supplied by the caller and is not authenticated.
The result is a point-in-time development inspection, not execution approval.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from case_package import CasePackageError, MAX_ARCHIVE_BYTES, inspect_package
from inspect_toolkit_wheel import ToolkitWheelError, inspect_toolkit_wheel
from toolkit_bundle import ToolkitBundleError, inspect_toolkit_bundle
from tool_policy import ToolPolicyError, inspect_tool_policy
from verify_released_run import (
    ReleaseVerificationError,
    _check_directory_chain,
    _check_release_file,
    _open_directory_chain,
    _open_release_file,
    _read_schedule,
    verify_release,
)


CHUNK_SIZE = 1024 * 1024
MAX_TEXT_BYTES = 1024 * 1024
CLASSIFICATION = "development_released_payload_inspection_unsealed"
NOTICE = (
    "Offline inspection against an unauthenticated caller-supplied schedule; "
    "no execution readiness, approval, or custody is established."
)
LIMITATIONS = [
    "Caller-supplied schedule is unauthenticated.",
    "Runtime isolation and actual tool enforcement were not checked.",
    "Provider telemetry and execution receipts were not checked.",
    "Independent human content review and external custody were not established.",
    "A hostile process with the same UID can race these point-in-time reads.",
]


class PayloadInspectionError(ValueError):
    """The released visible payload failed read-only content inspection."""


def _scan_role(
    release_dir: Path | str,
    role: str,
    maximum: int,
    *,
    collect: bool,
) -> tuple[str, bytes | None]:
    """Hash a private release file, optionally retaining bounded text bytes."""
    try:
        with ExitStack() as stack:
            release_fd, _parent_fd, _name, chain, directory_info = (
                _open_directory_chain(release_dir, stack)
            )
            _check_directory_chain(chain, directory_info)
            fd, original = _open_release_file(release_fd, role, stack)
            if original.st_size == 0 or original.st_size > maximum:
                raise PayloadInspectionError(
                    f"{role} is empty or exceeds its size limit"
                )
            digest = hashlib.sha256()
            total = 0
            chunks: list[bytes] = []
            while chunk := os.read(fd, min(CHUNK_SIZE, maximum - total + 1)):
                total += len(chunk)
                if total > maximum:
                    raise PayloadInspectionError(f"{role} exceeds its size limit")
                digest.update(chunk)
                if collect:
                    chunks.append(chunk)
            if total != original.st_size:
                raise PayloadInspectionError(f"{role} changed while being read")
            _check_release_file(release_fd, role, fd, original)
            _check_directory_chain(chain, directory_info)
            return digest.hexdigest(), b"".join(chunks) if collect else None
    except (OSError, ReleaseVerificationError) as exc:
        raise PayloadInspectionError(f"{role} cannot be read securely") from exc


def _inspect_text(release_dir: Path | str, role: str, expected_sha256: str) -> None:
    digest, data = _scan_role(release_dir, role, MAX_TEXT_BYTES, collect=True)
    if digest != expected_sha256:
        raise PayloadInspectionError(f"{role} bytes differ from schedule")
    if data is None:
        raise PayloadInspectionError(f"{role} bytes could not be retained")
    try:
        decoded = data.decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise PayloadInspectionError(f"{role} is not strict UTF-8") from exc
    if "\x00" in decoded or not decoded.strip():
        raise PayloadInspectionError(f"{role} must be nonempty UTF-8 without NUL")


def inspect_released_payload(
    schedule_raw: Any, release_dir: Path | str
) -> dict[str, Any]:
    """Check the selected visible case, policy, and arm text for one run.

    Both release verifications validate the schedule and all selected outer
    hashes. The intervening inspections add format and text checks. A hostile
    process with the same UID can still race these point-in-time reads.
    """
    try:
        release = verify_release(schedule_raw, release_dir)
    except ReleaseVerificationError as exc:
        raise PayloadInspectionError("release verification failed") from exc

    run = next(
        item for item in schedule_raw["runs"] if item["run_id"] == release["run_id"]
    )
    arm = run["arm"]
    case_id = run["case_id"]

    package_sha256, _ = _scan_role(
        release_dir, "case_package", MAX_ARCHIVE_BYTES, collect=False
    )
    if package_sha256 != run["case_package_sha256"]:
        raise PayloadInspectionError("case_package bytes differ from schedule")
    try:
        case_manifest = inspect_package(
            Path(release_dir) / "case_package", expected_case_id=case_id
        )
    except CasePackageError as exc:
        raise PayloadInspectionError("case_package inspection failed") from exc

    try:
        policy = inspect_tool_policy(
            Path(release_dir) / "tool_policy",
            expected_limits=schedule_raw["per_run_limits"],
        )
    except ToolPolicyError as exc:
        raise PayloadInspectionError("tool_policy inspection failed") from exc
    policy_sha256 = schedule_raw["inputs"]["tool_policy"]["sha256"]
    if policy["sha256"] != policy_sha256:
        raise PayloadInspectionError("tool_policy bytes differ from schedule")

    text_roles = {
        "task_contract": schedule_raw["inputs"]["task_contract"]["sha256"],
        "common_prompt": schedule_raw["inputs"]["common_prompt"]["sha256"],
        "arm_prompt": schedule_raw["inputs"]["arm_prompts"][arm]["sha256"],
    }
    if arm == "S":
        text_roles["sdd_guide"] = schedule_raw["inputs"]["sdd_guide"]["sha256"]
    for role, expected_sha256 in text_roles.items():
        _inspect_text(release_dir, role, expected_sha256)

    toolkit_inspection = None
    toolkit_format = None
    if arm == "T":
        try:
            toolkit_inspection = inspect_toolkit_wheel(Path(release_dir) / "toolkit")
            toolkit_format = "wheel"
        except ToolkitWheelError:
            try:
                toolkit_inspection = inspect_toolkit_bundle(
                    Path(release_dir) / "toolkit"
                )
                toolkit_format = "bundle"
            except ToolkitBundleError as exc:
                raise PayloadInspectionError(
                    "toolkit content inspection failed"
                ) from exc
        if toolkit_inspection["sha256"] != schedule_raw["inputs"]["toolkit"]["sha256"]:
            raise PayloadInspectionError("toolkit bytes differ from schedule")

    try:
        final_release = verify_release(schedule_raw, release_dir)
    except ReleaseVerificationError as exc:
        raise PayloadInspectionError("release changed during inspection") from exc
    if final_release != release:
        raise PayloadInspectionError("release changed during inspection")

    return {
        "schema": 1,
        "classification": CLASSIFICATION,
        "notice": NOTICE,
        "run_id": run["run_id"],
        "run_sha256": run["run_sha256"],
        "schedule_sha256": final_release["schedule_sha256"],
        "arm": arm,
        "case_id": case_id,
        "case_package_sha256": package_sha256,
        "tool_policy_sha256": policy["sha256"],
        "case_manifest_summary": {
            "classification": case_manifest["classification"],
            "case_id": case_manifest["case_id"],
            "file_count": len(case_manifest["files"]),
            "source_bytes": sum(item["bytes"] for item in case_manifest["files"]),
            "deliverable_count": len(case_manifest["deliverables"]),
        },
        "validated_roles": [
            "case_package",
            "tool_policy",
            *text_roles,
            *(["toolkit"] if toolkit_inspection is not None else []),
        ],
        "outer_hash_verified_roles": sorted(
            [
                "case_package",
                "tool_policy",
                *text_roles,
                *(["toolkit"] if arm == "T" else []),
            ]
        ),
        "toolkit_format_checked": (
            toolkit_inspection["static_format_checked"]
            if toolkit_inspection is not None
            else False
        ),
        "toolkit_format": toolkit_format,
        "toolkit_bundle_checked": toolkit_format == "bundle",
        "toolkit_container_format_checked": (
            toolkit_inspection.get("container_format_checked", False)
            if toolkit_inspection is not None
            else False
        ),
        "toolkit_root_wheel_format_checked": toolkit_inspection is not None,
        "toolkit_dependency_wheel_format_checked": (
            toolkit_inspection.get("dependency_wheel_format_checked", False)
            if toolkit_inspection is not None
            else False
        ),
        "toolkit_wheel_count": (
            toolkit_inspection.get("wheel_count", 1)
            if toolkit_inspection is not None
            else None
        ),
        "toolkit_target": (
            toolkit_inspection.get("target") if toolkit_inspection is not None else None
        ),
        "toolkit_version": (
            toolkit_inspection["version"] if toolkit_inspection is not None else None
        ),
        "toolkit_dependencies_checked": False,
        "toolkit_install_checked": False,
        "execution_ready": False,
        "limitations": LIMITATIONS
        + (
            [
                "Toolkit dependency wheel internals, dependency closure, installation, CLI and MCP were not checked."
            ]
            if arm == "T"
            else []
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "schedule", help="independently supplied candidate schedule JSON"
    )
    parser.add_argument("release_dir", help="absolute path to one unsealed release")
    args = parser.parse_args(argv)
    try:
        result = inspect_released_payload(
            _read_schedule(args.schedule), args.release_dir
        )
    except (PayloadInspectionError, ReleaseVerificationError) as exc:
        print(f"Released payload inspection failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
