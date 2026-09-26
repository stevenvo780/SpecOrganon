"""Verify local matrix assets and release one unsealed, executor-visible run.

Usage::

    python scripts/preflight_assets.py schedule.json assets.json --check
    python scripts/preflight_assets.py schedule.json assets.json \
        --run-id conf-... --output-dir /absolute/new/directory

The schema-1 asset map has exact keys ``schema``, ``schedule_sha256``,
``input_sha256``, ``cases``, and ``inputs``. ``cases`` maps R-F/R-M/R-S to
objects with absolute ``package`` and ``reference`` file paths. ``inputs``
maps task_contract, common_prompt, rubric, tool_policy, sdd_guide, and
toolkit to absolute file paths, plus ``arm_prompts`` with N/S/T paths.

All 15 files, including hidden references and the rubric, are checked against
the candidate schedule before any destination is created. Only assets needed
for the selected run are copied. A manifest is written last. This is an
offline development aid: it does not establish external custody, a sealed
registry, the authority of reference answers, provider access, or the absence
of hidden answers embedded inside otherwise visible source files. It requires
a parent directory owned by the current UID and not writable by group/others;
a hostile process with the same UID can still replace it. Hidden assets are
rechecked at manifest time, which is a point-in-time check, not immutable
custody. Independent human content review is required before case reservation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from analyze_confirmatory import AnalysisError, _validate_schedule
from plan_confirmatory import ManifestError, validate_manifest


CASES = ("R-F", "R-M", "R-S")
ARMS = ("N", "S", "T")
INPUTS = ("task_contract", "common_prompt", "rubric", "tool_policy", "sdd_guide", "toolkit")
CHUNK_SIZE = 1024 * 1024


class PreflightError(ValueError):
    """An input is invalid or a verified release cannot be created."""


def _object(raw: Any, label: str, keys: set[str]) -> dict[str, Any]:
    if type(raw) is not dict or set(raw) != keys:
        raise PreflightError(f"{label} must have exactly {sorted(keys)}")
    return raw


def _absolute_file_path(raw: Any, label: str) -> Path:
    if type(raw) is not str or not raw or "\x00" in raw or not Path(raw).is_absolute():
        raise PreflightError(f"{label} must be an absolute file path")
    return Path(raw)


def _candidate_schedule(raw: Any) -> dict[str, Any]:
    try:
        schedule, _, _ = _validate_schedule(raw)
        # The analysis validator checks all run coordinates and hashes. The
        # planner validator also checks every input reference's exact schema.
        validate_manifest({
            "schema": 1,
            "seed": schedule["seed"],
            "protocol_sha256": schedule["protocol_sha256"],
            "tool_call_cap": schedule["per_run_limits"]["tool_calls"],
            "models": schedule["models"],
            "cases": schedule["cases"],
            "inputs": schedule["inputs"],
        })
    except (AnalysisError, ManifestError, KeyError, TypeError, ValueError) as exc:
        raise PreflightError("invalid candidate schedule") from exc
    return schedule


def _asset_paths(schedule: dict[str, Any], raw: Any) -> tuple[dict[str, Path], dict[str, str]]:
    asset_map = _object(raw, "asset map", {
        "schema", "schedule_sha256", "input_sha256", "cases", "inputs"
    })
    if type(asset_map["schema"]) is not int or asset_map["schema"] != 1:
        raise PreflightError("asset map schema must be integer 1")
    if (
        asset_map["schedule_sha256"] != schedule["schedule_sha256"]
        or type(asset_map["schedule_sha256"]) is not str
        or asset_map["input_sha256"] != schedule["input_sha256"]
        or type(asset_map["input_sha256"]) is not str
    ):
        raise PreflightError("asset map digest binding differs from schedule")

    cases = _object(asset_map["cases"], "asset map cases", set(CASES))
    inputs = _object(asset_map["inputs"], "asset map inputs", set(INPUTS) | {"arm_prompts"})
    prompts = _object(inputs["arm_prompts"], "asset map arm_prompts", set(ARMS))
    expected_cases = {case["case_id"]: case for case in schedule["cases"]}
    paths: dict[str, Path] = {}
    digests: dict[str, str] = {}
    for case_id in CASES:
        item = _object(cases[case_id], f"asset map case {case_id}", {"package", "reference"})
        for role, digest_role in (("package", "package_sha256"), ("reference", "reference_sha256")):
            label = f"case:{case_id}:{role}"
            paths[label] = _absolute_file_path(item[role], label)
            digests[label] = expected_cases[case_id][digest_role]
    for role in INPUTS:
        label = f"input:{role}"
        paths[label] = _absolute_file_path(inputs[role], label)
        digests[label] = schedule["inputs"][role]["sha256"]
    for arm in ARMS:
        label = f"prompt:{arm}"
        paths[label] = _absolute_file_path(prompts[arm], label)
        digests[label] = schedule["inputs"]["arm_prompts"][arm]["sha256"]
    return paths, digests


def _hash_fd(fd: int) -> str:
    os.lseek(fd, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    while chunk := os.read(fd, CHUNK_SIZE):
        digest.update(chunk)
    return digest.hexdigest()


def _open_verified_assets(
    paths: dict[str, Path], digests: dict[str, str], stack: ExitStack
) -> dict[str, int]:
    opened: dict[str, int] = {}
    for label, path in paths.items():
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
            stack.callback(os.close, fd)
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise PreflightError(f"{label} is not a regular file")
            if _hash_fd(fd) != digests[label]:
                raise PreflightError(f"{label} byte digest differs from schedule")
        except OSError as exc:
            raise PreflightError(f"{label} cannot be read") from exc
        opened[label] = fd
    return opened


def _selected_assets(run: dict[str, Any]) -> dict[str, str]:
    selected = {
        "case_package": f"case:{run['case_id']}:package",
        "task_contract": "input:task_contract",
        "common_prompt": "input:common_prompt",
        "arm_prompt": f"prompt:{run['arm']}",
        "tool_policy": "input:tool_policy",
    }
    if run["arm"] == "S":
        selected["sdd_guide"] = "input:sdd_guide"
    elif run["arm"] == "T":
        selected["toolkit"] = "input:toolkit"
    return selected


def _copy_verified_asset(source_fd: int, directory_fd: int, name: str, expected: str) -> dict[str, Any]:
    os.lseek(source_fd, 0, os.SEEK_SET)
    output_fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd)
    written = 0
    copied_digest = hashlib.sha256()
    with os.fdopen(output_fd, "wb") as destination:
        os.fchmod(destination.fileno(), 0o600)
        while chunk := os.read(source_fd, CHUNK_SIZE):
            destination.write(chunk)
            copied_digest.update(chunk)
            written += len(chunk)
        destination.flush()
        os.fsync(destination.fileno())
    if copied_digest.hexdigest() != expected:
        raise PreflightError(f"{name} changed after preflight")
    verification_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
    try:
        if _hash_fd(verification_fd) != expected:
            raise PreflightError(f"{name} copy verification failed")
    finally:
        os.close(verification_fd)
    return {"file": name, "sha256": expected, "bytes": written}


def _write_manifest(directory_fd: int, manifest: dict[str, Any]) -> None:
    encoded = json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8") + b"\n"
    output_fd = os.open("manifest.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd)
    with os.fdopen(output_fd, "wb") as destination:
        os.fchmod(destination.fileno(), 0o600)
        destination.write(encoded)
        destination.flush()
        os.fsync(destination.fileno())
    os.fsync(directory_fd)


def _directory_matches_name(directory_fd: int, parent_fd: int, name: str) -> bool:
    try:
        opened = os.fstat(directory_fd)
        named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError:
        return False
    return stat.S_ISDIR(named.st_mode) and (opened.st_dev, opened.st_ino) == (named.st_dev, named.st_ino)


def _reverify_hidden_assets(paths: dict[str, Path], digests: dict[str, str], opened: dict[str, int]) -> None:
    for label in (f"case:{case_id}:reference" for case_id in CASES):
        _reverify_hidden_asset(label, paths, digests, opened)
    _reverify_hidden_asset("input:rubric", paths, digests, opened)


def _reverify_hidden_asset(
    label: str, paths: dict[str, Path], digests: dict[str, str], opened: dict[str, int]
) -> None:
    try:
        current_fd = os.open(paths[label], os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        try:
            original = os.fstat(opened[label])
            current = os.fstat(current_fd)
            if (
                not stat.S_ISREG(current.st_mode)
                or (original.st_dev, original.st_ino) != (current.st_dev, current.st_ino)
                or _hash_fd(opened[label]) != digests[label]
                or _hash_fd(current_fd) != digests[label]
            ):
                raise PreflightError(f"{label} changed during release")
        finally:
            os.close(current_fd)
    except OSError as exc:
        raise PreflightError(f"{label} cannot be reverified") from exc


def preflight(schedule_raw: Any, assets_raw: Any, *, run_id: str | None = None, output_dir: Path | None = None) -> dict[str, Any]:
    """Check all bound bytes; optionally create one new, narrowly scoped release."""
    schedule = _candidate_schedule(schedule_raw)
    paths, digests = _asset_paths(schedule, assets_raw)
    if (run_id is None) != (output_dir is None):
        raise PreflightError("run_id and output_dir must be supplied together")
    run = None
    if run_id is not None:
        if type(run_id) is not str:
            raise PreflightError("run_id must be a string")
        run = next((item for item in schedule["runs"] if item["run_id"] == run_id), None)
        if run is None:
            raise PreflightError("run_id is absent from schedule")
        if not Path(output_dir).is_absolute():
            raise PreflightError("output_dir must be absolute")

    with ExitStack() as stack:
        opened = _open_verified_assets(paths, digests, stack)
        hidden_digests = {digests[f"case:{case_id}:reference"] for case_id in CASES}
        hidden_digests.add(digests["input:rubric"])
        if hidden_digests.intersection(
            digest for label, digest in digests.items()
            if not label.endswith(":reference") and label != "input:rubric"
        ):
            raise PreflightError("hidden and executor-visible assets have identical bytes")

        summary = {
            "schema": 1,
            "classification": "development_asset_preflight_unsealed",
            "notice": "Independent human content review and external custody are required before case reservation.",
            "schedule_sha256": schedule["schedule_sha256"],
            "input_sha256": schedule["input_sha256"],
            "scheduled_runs": schedule["run_count"],
            "verified_assets": len(opened),
            "verified_case_packages": len(CASES),
            "verified_hidden_references": len(CASES),
            "asset_digest_binding_sha256": hashlib.sha256(json.dumps(
                digests, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")).hexdigest(),
        }
        if run is None:
            return summary

        output = Path(output_dir)
        name = output.name
        if name in ("", ".", ".."):
            raise PreflightError("output_dir must name a new directory")
        try:
            parent_fd = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            stack.callback(os.close, parent_fd)
            parent = os.fstat(parent_fd)
            if parent.st_uid != os.geteuid() or parent.st_mode & 0o022:
                raise PreflightError("output_dir parent must be owned by current UID and not group/other writable")
        except OSError as exc:
            raise PreflightError("output_dir parent cannot be opened securely") from exc
        try:
            os.mkdir(name, 0o700, dir_fd=parent_fd)
        except FileExistsError as exc:
            raise PreflightError("output_dir already exists") from exc
        except OSError as exc:
            raise PreflightError("output_dir cannot be created") from exc

        # The directory is new. If a later copy fails, leave it without a
        # manifest; never remove or overwrite any path during recovery.
        try:
            created = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            directory_fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
            try:
                opened_directory = os.fstat(directory_fd)
                named_directory = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                if (
                    not stat.S_ISDIR(created.st_mode)
                    or (created.st_dev, created.st_ino) != (opened_directory.st_dev, opened_directory.st_ino)
                    or (created.st_dev, created.st_ino) != (named_directory.st_dev, named_directory.st_ino)
                ):
                    raise PreflightError("output_dir identity changed before release")
                os.fchmod(directory_fd, 0o700)
                files = {
                    name: _copy_verified_asset(opened[label], directory_fd, name, digests[label])
                    for name, label in _selected_assets(run).items()
                }
                coordinate_fields = (
                    "stratum_id", "block_id", "family", "tier", "model_id", "model_version",
                    "effort", "effort_provider_value", "agents", "case_id", "replica",
                    "order_position", "release_block_order", "arm",
                )
                manifest = {
                    "schema": 1,
                    "classification": "development_release_unsealed",
                    "notice": "Independent human content review and external custody are required before case reservation.",
                    "run_id": run["run_id"],
                    "run_sha256": run["run_sha256"],
                    "schedule_sha256": schedule["schedule_sha256"],
                    "coordinates": {field: run[field] for field in coordinate_fields},
                    "limits": schedule["per_run_limits"],
                    "files": files,
                }
                _reverify_hidden_assets(paths, digests, opened)
                if not _directory_matches_name(directory_fd, parent_fd, name):
                    raise PreflightError("output_dir identity changed during release")
                _write_manifest(directory_fd, manifest)
                if not _directory_matches_name(directory_fd, parent_fd, name):
                    raise PreflightError("output_dir identity changed after manifest")
            finally:
                os.close(directory_fd)
        except (OSError, PreflightError) as exc:
            raise PreflightError("release could not be verified; partial directory and any manifest are untrusted") from exc
        return manifest


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise PreflightError("duplicate JSON object key")
        value[key] = item
    return value


def _reject_constant(value: str) -> None:
    raise PreflightError("non-JSON numeric constant")


def _read_json(path: str) -> Any:
    try:
        return json.loads(
            Path(path).read_text(encoding="utf-8"),
            object_pairs_hook=_unique_pairs,
            parse_constant=_reject_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PreflightError("input JSON cannot be read or parsed") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("schedule", help="candidate schedule JSON")
    parser.add_argument("asset_map", help="schema-1 absolute path map JSON")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="verify without writing")
    mode.add_argument("--run-id", help="release exactly one scheduled run")
    parser.add_argument("--output-dir", help="new absolute release directory; required with --run-id")
    args = parser.parse_args(argv)
    if (args.check and args.output_dir) or (args.run_id and not args.output_dir):
        parser.error("--output-dir is required only with --run-id")
    try:
        result = preflight(
            _read_json(args.schedule), _read_json(args.asset_map),
            run_id=args.run_id,
            output_dir=Path(args.output_dir) if args.output_dir else None,
        )
    except PreflightError as exc:
        print(f"Asset preflight failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
