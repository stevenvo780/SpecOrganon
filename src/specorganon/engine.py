"""Versioned dependency graph and review gates for the SpecOrganon workflow.

All public operations use the same ledger regardless of transport. Signed
approvals are checked against an external public-key trust file; key custody
and field impact still require external evaluation.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
from contextlib import ExitStack
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from pathlib import Path
from typing import Any

from . import approval, field_attestation, review_provenance, test_execution, test_observation
from .ledger import ZERO_HASH, ConflictError, LedgerError, append_event, init_project, read_project
from .workflow import KIND_TO_PHASE, KINDS, PHASES, PHASE_BY_ID


ITEM_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{1,63}$")
_RANGE_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
_CONTEXTUAL_RANGE = re.compile(rf"\s*({_RANGE_NUMBER})\s*[-–]\s*({_RANGE_NUMBER})\s*")
VERDICTS = {"accept", "reject"}
_PUT_MAX_RETRIES = 3
# Keep exact rational comparisons bounded even for compact inputs such as
# "1e1000000000"; accepted values still cover ordinary scientific measurements.
_METRIC_MAX_TEXT = 1024
_METRIC_MAX_DIGITS = 256
_METRIC_MAX_EXPONENT = 512
_PRODUCT_MAX_OPERANDS = 64
_PRODUCT_MAX_SPAN = 2048
_SOURCE_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_LOCAL_ARCHIVE_MAX_BYTES = 32 * 1024 * 1024
_ARCHIVE_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_ARCHIVE_FILE_FLAGS = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC


class MethodError(LedgerError):
    """An action violates a method invariant or a phase gate."""


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _archive_stat_identity(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _local_archive_path_parts(value: Any) -> tuple[str, ...] | None:
    """Require a canonical POSIX relative name before any filesystem lookup."""
    if type(value) is not str or not value:
        return None
    try:
        encoded_length = len(value.encode("utf-8"))
    except UnicodeError:
        return None
    if (encoded_length > 4096
            or value.startswith("/") or "\\" in value or re.match(r"^[A-Za-z]:", value)
            or any(ord(char) < 32 for char in value)):
        return None
    parts = tuple(value.split("/"))
    return parts if all(part not in {"", ".", ".."} for part in parts) else None


def _local_archive_digest(case_path: str, parts: tuple[str, ...]) -> str:
    """Hash a bounded, singly linked regular file through pinned directory fds.

    No path component is followed through a symlink. Recheck every named entry
    after reading to detect ordinary rename, replacement and in-place races.
    This is a live byte check, not an independent source-custody attestation.
    """
    with ExitStack() as stack:
        root_fd = os.open("/", _ARCHIVE_DIR_FLAGS)
        stack.callback(os.close, root_fd)
        parent_fd = root_fd
        opened_dirs: list[tuple[int, str, int]] = []
        for name in Path(case_path).parts[1:] + parts[:-1]:
            directory_fd = os.open(name, _ARCHIVE_DIR_FLAGS, dir_fd=parent_fd)
            stack.callback(os.close, directory_fd)
            opened_dirs.append((parent_fd, name, directory_fd))
            if (_archive_stat_identity(os.fstat(directory_fd)) !=
                    _archive_stat_identity(os.stat(name, dir_fd=parent_fd, follow_symlinks=False))):
                raise ValueError("local archive directory changed while opening")
            parent_fd = directory_fd

        name = parts[-1]
        file_fd = os.open(name, _ARCHIVE_FILE_FLAGS, dir_fd=parent_fd)
        stack.callback(os.close, file_fd)
        before = os.fstat(file_fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError("local archive must be a singly linked regular file")
        if before.st_size > _LOCAL_ARCHIVE_MAX_BYTES:
            raise ValueError("local archive exceeds the 32 MiB size limit")
        digest = hashlib.sha256()
        total = 0
        while chunk := os.read(file_fd, min(1024 * 1024, _LOCAL_ARCHIVE_MAX_BYTES - total + 1)):
            total += len(chunk)
            if total > _LOCAL_ARCHIVE_MAX_BYTES:
                raise ValueError("local archive exceeds the 32 MiB size limit")
            digest.update(chunk)
        after = os.fstat(file_fd)
        named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if (total != before.st_size or _archive_stat_identity(before) != _archive_stat_identity(after)
                or _archive_stat_identity(before) != _archive_stat_identity(named)):
            raise ValueError("local archive changed while hashing")
        for directory_parent, directory_name, directory_fd in reversed(opened_dirs):
            if (_archive_stat_identity(os.fstat(directory_fd)) !=
                    _archive_stat_identity(os.stat(directory_name, dir_fd=directory_parent,
                                                   follow_symlinks=False))):
                raise ValueError("local archive directory changed while hashing")
        return digest.hexdigest()


def _local_archive_issues(case_path: str, data: dict[str, Any], *, check_contents: bool = True) -> list[str]:
    """Evaluate an opted-in source-byte contract in a signed case."""
    archive_present = "archive" in data
    digest_present = "source_sha256" in data
    if not archive_present and not digest_present:
        return []
    if not archive_present or not digest_present:
        return ["local archive requires both archive and source_sha256"]
    parts = _local_archive_path_parts(data["archive"])
    if parts is None:
        return ["local archive path must be canonical and relative to the case"]
    expected = data["source_sha256"]
    if type(expected) is not str or _SOURCE_SHA256.fullmatch(expected) is None:
        return ["local archive source_sha256 must be a lowercase SHA-256 digest"]
    if not check_contents:
        return []
    try:
        actual = _local_archive_digest(case_path, parts)
    except OSError:
        return ["local archive is missing or unsafe to read"]
    except ValueError as exc:
        return [str(exc)]
    if actual != expected:
        return ["local archive bytes differ from source_sha256"]
    return []


def _project(path: str | Path) -> dict[str, Any]:
    ledger = read_project(path)
    project = dict(ledger["project"])
    project.setdefault("approval_policy", "signed")
    observed_tests = project.get("test_gate_policy") == "signed_observed"
    try:
        (approvers, phase_reviewers, test_executors,
         test_observers, trust_status) = approval.trust_contexts_with_observers(project, path)
    except ValueError:
        approvers = {}
        phase_reviewers = {}
        test_executors = {}
        test_observers = {}
        trust_status = "unavailable"
    if project["approval_policy"] == "signed":
        try:
            field_assessors, field_trust_status = field_attestation.trust_context(project, path)
        except ValueError:
            field_assessors = {}
            field_trust_status = "unavailable"
    else:
        field_assessors = {}
        field_trust_status = "not_applicable"
    state: dict[str, Any] = {
        "project": project,
        "case_path": approval.case_path(path),
        "revision": len(ledger["events"]),
        "head_hash": ledger["events"][-1]["hash"] if ledger["events"] else ZERO_HASH,
        "items": {},
        "item_author_history": {},
        "approvals": set(),
        "approval_statuses": {},
        "approval_provenance": {},
        "approval_trust": trust_status,
        "phase_review_trust": (
            "fixture" if trust_status == "fixture" else
            "configured" if trust_status == "configured" and phase_reviewers else "unavailable"
        ),
        "phase_reviewers": phase_reviewers,
        "test_execution_trust": (
            "fixture" if trust_status == "fixture" else
            "configured" if trust_status == "configured" and test_executors else "unavailable"
        ),
        "test_executors": test_executors,
        "test_executions": {},
        "test_execution_reports": {},
        "test_execution_history": [],
        "test_observation_trust": (
            "not_applicable" if not observed_tests else
            "configured" if trust_status == "configured" and test_observers else "unavailable"
        ),
        "test_observers": test_observers,
        "test_observations": {},
        "test_observation_history": [],
        "field_attestation_trust": field_trust_status,
        "field_attestations": [],
        "item_reviews": {},
        "indicator_retirements": [],
        "challenges": {},
        "resolutions": {},
        "phase_reviews": [],
        "advances": [],
    }
    for event in ledger["events"]:
        kind, payload, seq = event["kind"], event["payload"], event["seq"]
        if kind == "item_put":
            item_id = payload.get("id") if isinstance(payload, dict) else None
            prior = state["items"].get(item_id)
            version = payload.get("version") if isinstance(payload, dict) else None
            expected_version = prior["version"] + 1 if prior else 1
            deps = payload.get("deps") if isinstance(payload, dict) else None
            if (not isinstance(item_id, str) or not isinstance(version, int) or isinstance(version, bool)
                    or version != expected_version or not isinstance(deps, dict)
                    or (prior is not None and prior["kind"] != payload.get("kind"))):
                raise MethodError(f"invalid item revision at sequence {seq}")
            for ref, ref_version in deps.items():
                referenced = state["items"].get(ref)
                if (ref == item_id or referenced is None or not isinstance(ref_version, int)
                        or isinstance(ref_version, bool) or referenced["version"] != ref_version):
                    raise MethodError(f"invalid item dependency at sequence {seq}")
            item = dict(payload)
            item["seq"] = seq
            item["author"] = event["actor"]
            state["items"][item["id"]] = item
            state["item_author_history"].setdefault(item["id"], set()).add(event["actor"])
        elif kind == "approval":
            item = state["items"].get(payload.get("id"))
            if item is None or item["version"] != payload.get("version") or item["kind"] not in {"norm", "decision"}:
                continue
            key = (item["id"], item["version"])
            if project["approval_policy"] == "fixture":
                valid = (trust_status == "fixture" and event["actor"] == "human:fixture"
                         and isinstance(payload.get("reason"), str) and bool(payload["reason"].strip()))
                status = "fixture" if valid else "unverified"
            else:
                valid = (trust_status == "configured" and isinstance(payload.get("reason"), str)
                         and isinstance(payload.get("signature"), str)
                         and isinstance(payload.get("key_sha256"), str)
                         and approval.verify(project, item, event["actor"], payload["reason"],
                                             payload["signature"], payload["key_sha256"], approvers,
                                             path, event["prev_hash"]))
                status = "signed_verified" if valid else "unverified"
            if valid:
                state["approval_statuses"][key] = status
                state["approvals"].add(key)
                state["approval_provenance"][key] = (seq, event["hash"])
            elif key not in state["approvals"]:
                state["approval_statuses"][key] = status
        elif kind == "test_execution":
            item = state["items"].get(payload.get("id")) if isinstance(payload, dict) else None
            valid = False
            report = payload.get("report") if isinstance(payload, dict) else None
            if (project["approval_policy"] == "signed" and item is not None
                    and item["kind"] == "test" and type(payload.get("version")) is int
                    and item["version"] == payload["version"]
                    and not test_execution.item_issues(item, observed=observed_tests)
                    and isinstance(event["actor"], str) and isinstance(report, dict)):
                try:
                    test_execution.validate_report(report)
                    valid = bool(
                        report["argv"] == item["data"]["argv"]
                        and test_execution.verify(
                            project, item, report, event["actor"], payload.get("signature"),
                            payload.get("key_sha256"), test_executors, path, event["prev_hash"],
                        )
                    )
                except (KeyError, TypeError, ValueError):
                    valid = False
            record = {
                "seq": seq, "hash": event["hash"], "id": payload.get("id") if isinstance(payload, dict) else None,
                "version": payload.get("version") if isinstance(payload, dict) else None,
                "actor": event["actor"], "signature_verified": valid,
                "passed": bool(valid and report["exit_code"] == 0 and not report["timed_out"]),
            }
            state["test_execution_history"].append(record)
            if valid:
                state["test_executions"][(item["id"], item["version"])] = record
                state["test_execution_reports"][(item["id"], item["version"])] = report
        elif kind == "test_observation":
            item = state["items"].get(payload.get("id")) if isinstance(payload, dict) else None
            receipt = payload.get("receipt") if isinstance(payload, dict) else None
            report_record = (state["test_executions"].get((item["id"], item["version"]))
                             if item is not None and item["kind"] == "test" else None)
            report = (state["test_execution_reports"].get((item["id"], item["version"]))
                      if report_record is not None else None)
            provenance = {"seq": report_record["seq"], "hash": report_record["hash"]} if report_record else None
            authenticated = False
            passed = False
            bundle_verified = False
            if (observed_tests and item is not None and report is not None and type(receipt) is dict
                    and type(payload.get("version")) is int and payload["version"] == item["version"]
                    and payload.get("report_provenance") == provenance
                    and receipt.get("report_provenance") == provenance
                    and event["actor"] not in state["item_author_history"][item["id"]]
                    and event["actor"] != report_record["actor"]):
                try:
                    authenticated = test_observation.verify(
                        project, item, report, provenance, receipt, event["actor"],
                        payload.get("signature"), payload.get("key_sha256"),
                        test_observers, path, event["prev_hash"],
                    )
                    if authenticated:
                        matched = test_observation.validate_receipt(
                            receipt, project, item, report, provenance,
                        )
                        passed = bool(matched and report["exit_code"] == 0 and not report["timed_out"])
                        bundle_verified = True
                except (KeyError, TypeError, ValueError, OSError):
                    bundle_verified = False
            record = {
                "seq": seq, "hash": event["hash"],
                "id": payload.get("id") if isinstance(payload, dict) else None,
                "version": payload.get("version") if isinstance(payload, dict) else None,
                "report_provenance": provenance,
                "actor": event["actor"], "signature_verified": authenticated,
                "bundle_verified": bundle_verified, "passed": bool(bundle_verified and passed),
            }
            state["test_observation_history"].append(record)
            if authenticated:
                state["test_observations"][(item["id"], item["version"],
                                            report_record["seq"], report_record["hash"])] = record
        elif kind == "field_attestation":
            valid = False
            if isinstance(payload, dict) and project["approval_policy"] == "signed":
                try:
                    binding = payload["binding"]
                    materials = payload["materials"]
                    assessment = state["items"].get(binding["assessment_id"])
                    valid = bool(
                        field_trust_status == "configured"
                        and assessment is not None
                        and event["actor"] != assessment["author"]
                        and field_assessors.get(event["actor"]) not in approvers.values()
                        and binding == _field_binding(state["items"], assessment)
                        and field_attestation.verify(
                            project, path, binding, materials, event["actor"],
                            payload["reason"], event["prev_hash"], payload["signature"],
                            payload["key_sha256"], field_assessors,
                        )
                    )
                except (KeyError, TypeError, ValueError):
                    valid = False
            state["field_attestations"].append({
                "seq": seq, "actor": event["actor"], "verified": valid,
                "binding": payload.get("binding") if isinstance(payload, dict) else None,
                "materials": payload.get("materials") if isinstance(payload, dict) else None,
            })
        elif kind == "item_review":
            state["item_reviews"][(payload["id"], payload["version"])] = {
                **payload, "seq": seq, "actor": event["actor"]
            }
        elif kind == "indicator_retire":
            _validate_indicator_retirement(payload, event["actor"])
            # Historical validation must not open an archive whose bytes may
            # have changed since this event. Live validity is evaluated below.
            history_flags = _flags(state, check_archives=False, include_retirements=False)
            if any(entry["id"] == payload["id"]
                   and not _indicator_retirement_issues(state, entry, history_flags)
                   for entry in state["indicator_retirements"]):
                raise MethodError(f"indicator already effectively retired at sequence {seq}")
            issues = _indicator_retirement_issues(state, payload, history_flags)
            if issues:
                raise MethodError(f"invalid indicator retirement at sequence {seq}: {'; '.join(issues)}")
            state["indicator_retirements"].append({"seq": seq, "actor": event["actor"], **payload})
        elif kind == "challenge":
            state["challenges"][seq] = {"seq": seq, "actor": event["actor"], **payload}
        elif kind == "challenge_resolved":
            resolution_item = state["items"][payload["resolution_item"]]
            review = state["item_reviews"].get((resolution_item["id"], resolution_item["version"]))
            state["resolutions"][payload["challenge_seq"]] = {
                "seq": seq,
                "item": resolution_item["id"],
                "version": payload.get("resolution_version", resolution_item["version"]),
                "review_seq": payload.get("review_seq", review["seq"] if review else None),
            }
        elif kind == "phase_review":
            if not isinstance(payload, dict) or payload.get("phase") not in PHASE_BY_ID:
                raise MethodError(f"invalid phase review at sequence {seq}")
            authors = _phase_authors(state, payload["phase"])
            independent = event["actor"] not in authors
            if project["approval_policy"] == "signed":
                has_proof = isinstance(payload.get("signature"), str) and isinstance(payload.get("key_sha256"), str)
                try:
                    current_snapshot = _phase_statuses(state)[payload["phase"]]["snapshot"]
                    verified = bool(
                        has_proof and trust_status == "configured"
                        and payload.get("snapshot") == current_snapshot
                        and review_provenance.verify(
                            project, path, event["prev_hash"], payload["phase"], payload["snapshot"],
                            payload.get("verdict"), payload.get("reason"), event["actor"],
                            payload["signature"], payload["key_sha256"], phase_reviewers,
                        )
                    )
                except (KeyError, TypeError, ValueError):
                    verified = False
                provenance = "signed_verified" if verified else (
                    "legacy_unverified" if not has_proof else "signature_unverified"
                )
            else:
                verified = False
                provenance = "synthetic_fixture" if trust_status == "fixture" else "fixture_unavailable"
            state["phase_reviews"].append({
                "seq": seq, "actor": event["actor"], **payload,
                "independent": independent, "signature_verified": verified,
                "provenance": provenance, "_event": event,
            })
        elif kind == "phase_advance":
            state["advances"].append({"seq": seq, "actor": event["actor"], **payload, "_event": event})
        else:
            raise MethodError(f"unknown event type at sequence {seq}: {kind}")
    return state


def _phase_authors(state: dict[str, Any], phase: str) -> set[str]:
    """Keep earlier item-version authors in signed reviewer independence checks."""
    phase_items = (item for item in state["items"].values() if KIND_TO_PHASE[item["kind"]] == phase)
    if state["project"]["approval_policy"] == "signed":
        authors = set().union(*(state["item_author_history"][item["id"]] for item in phase_items))
        if phase == "study":
            authors.update(entry["actor"] for entry in state["indicator_retirements"])
        return authors
    return {item["author"] for item in phase_items}


def _ancestors(items: dict[str, dict], item_id: str) -> set[str]:
    found: set[str] = set()
    pending = [item_id]
    while pending:
        current = pending.pop()
        if current in found or current not in items:
            continue
        found.add(current)
        pending.extend(items[current]["deps"])
    return found


def _field_binding(items: dict[str, dict], assessment: dict[str, Any]) -> dict[str, Any]:
    """Bind an assessor to every current item revision behind one field verdict."""
    if (assessment["kind"] != "assessment"
            or assessment["data"].get("claim_scope") != "field"
            or assessment["data"].get("verdict") not in {"cumplido", "incumplido"}):
        raise MethodError("attestation requires a decisive field assessment")
    ancestors = _ancestors(items, assessment["id"])
    for kind in ("result", "baseline", "criterion"):
        if sum(items[item_id]["kind"] == kind for item_id in ancestors) != 1:
            raise MethodError(f"field attestation requires exactly one linked {kind}")
    return {
        "assessment_id": assessment["id"],
        "assessment_version": assessment["version"],
        "verdict": assessment["data"]["verdict"],
        "items": [
            {"id": item_id, "kind": items[item_id]["kind"],
             "version": items[item_id]["version"], "sha256": _hash(items[item_id])}
            for item_id in sorted(ancestors)
        ],
    }


def _field_statement_binding_current(state: dict[str, Any], entry: dict[str, Any]) -> bool:
    binding = entry["binding"]
    if not isinstance(binding, dict):
        return False
    assessment_id = binding.get("assessment_id")
    if not isinstance(assessment_id, str):
        return False
    assessment = state["items"].get(assessment_id)
    if assessment is None:
        return False
    try:
        return binding == _field_binding(state["items"], assessment)
    except MethodError:
        return False


def _implementation_requirements(
    items: dict[str, dict], implementation_id: str
) -> set[str]:
    """Follow implementation composition without borrowing requirements from other kinds."""
    requirements: set[str] = set()
    seen: set[str] = set()
    pending = [implementation_id]
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        implementation = items[current]
        if implementation["kind"] != "implementation":
            continue
        for ref in implementation["deps"]:
            kind = items[ref]["kind"]
            if kind == "requirement":
                requirements.add(ref)
            elif kind == "implementation":
                pending.append(ref)
    return requirements


def _dependents(items: dict[str, dict], item_id: str) -> set[str]:
    found = {item_id}
    changed = True
    while changed:
        changed = False
        for candidate, item in items.items():
            if candidate not in found and any(ref in found for ref in item["deps"]):
                found.add(candidate)
                changed = True
    return found


def _active_resolutions(state: dict[str, Any]) -> set[int]:
    """A resolution is valid only while its reviewed item still addresses both sides."""
    active: set[int] = set()
    items = state["items"]
    for challenge_seq, record in state["resolutions"].items():
        item = items.get(record["item"])
        challenge = state["challenges"].get(challenge_seq)
        if item is None or challenge is None or item["version"] != record["version"] or _stale(items, item["id"]):
            continue
        if not {challenge["left"], challenge["right"]}.issubset(_ancestors(items, item["id"])):
            continue
        review = state["item_reviews"].get((item["id"], item["version"]))
        if (review is None or review["seq"] != record["review_seq"] or review["verdict"] != "accept"
                or review["actor"] == item["author"]):
            continue
        active.add(challenge_seq)
    return active


def _stale(items: dict[str, dict], item_id: str, visiting: set[str] | None = None) -> bool:
    visiting = set() if visiting is None else visiting
    if item_id in visiting:
        return True
    item = items[item_id]
    for ref, version in item["deps"].items():
        if ref not in items or items[ref]["version"] != version:
            return True
        if _stale(items, ref, visiting | {item_id}):
            return True
    return False


def _automatic_conflicts(state: dict[str, Any], active_resolutions: set[int]) -> dict[str, list[str]]:
    """Flag each incompatible pair unless that exact pair has an active resolution."""
    resolved_pairs = {
        frozenset((challenge["left"], challenge["right"]))
        for seq, challenge in state["challenges"].items()
        if seq in active_resolutions
    }
    groups: dict[tuple[str, str, str], list[dict]] = {}
    for item in state["items"].values():
        if item["kind"] != "evidence":
            continue
        data = item["data"]
        if all(key in data for key in ("metric_key", "scope", "unit", "value")):
            group = (str(data["metric_key"]), str(data["scope"]), _metric_comparison_unit(data["unit"]))
            groups.setdefault(group, []).append(item)
    issues: dict[str, list[str]] = {}
    for group, members in groups.items():
        for i, left in enumerate(members):
            for right in members[i + 1 :]:
                a, b = _metric_interval(left["data"]), _metric_interval(right["data"])
                left_tolerance = _metric_numeric(left["data"].get("tolerance", 0))
                right_tolerance = _metric_numeric(right["data"].get("tolerance", 0))
                if (any(value is None for value in (a, b, left_tolerance, right_tolerance))
                        or left_tolerance < 0 or right_tolerance < 0):
                    continue
                tolerance = max(left_tolerance, right_tolerance)
                gap = max(Fraction(b[0]) - Fraction(a[1]), Fraction(a[0]) - Fraction(b[1]), Fraction(0))
                if gap > Fraction(tolerance):
                    if frozenset((left["id"], right["id"])) in resolved_pairs:
                        continue
                    label = f"conflicting metric {group[0]} in {group[1]}: {left['id']} vs {right['id']}"
                    issues.setdefault(left["id"], []).append(label)
                    issues.setdefault(right["id"], []).append(label)
    return issues


def _item_issues(item: dict[str, Any]) -> list[str]:
    data, kind = item["data"], item["kind"]
    issues: list[str] = []
    if kind == "evidence":
        if data.get("origin") not in {"published", "observed", "derived", "simulated"}:
            issues.append("evidence origin must be published, observed, derived or simulated")
        for field in ("source", "date", "locator"):
            if not isinstance(data.get(field), str) or not data[field].strip():
                issues.append(f"evidence lacks {field}")
        if data.get("origin") == "observed":
            method = data.get("method")
            if not isinstance(method, str) or not method.strip():
                issues.append("observed evidence lacks collection method")
        if all(field in data for field in ("metric_key", "scope", "unit", "value")):
            if _metric_interval(data) is None:
                issues.append("evidence metric value must be a finite supported number")
            tolerance = _metric_numeric(data.get("tolerance", 0))
            if tolerance is None or tolerance < 0:
                issues.append("evidence metric tolerance must be a nonnegative finite supported number")
        calc = data.get("calculation")
        if calc is not None:
            try:
                if (calc["operator"] != "product" or not isinstance(calc["operands"], list)
                        or not 0 < len(calc["operands"]) <= _PRODUCT_MAX_OPERANDS):
                    raise ValueError("unsupported calculation")
                operands = [_metric_numeric(value) for value in calc["operands"]]
                reported = _metric_numeric(data["value"])
                tolerance = _metric_numeric(calc.get("tolerance", 0))
                if any(value is None for value in operands) or reported is None or tolerance is None or tolerance < 0:
                    raise ValueError("invalid calculation number")
                if sum(len(value.as_tuple().digits) + abs(value.as_tuple().exponent) for value in operands) > _PRODUCT_MAX_SPAN:
                    raise ValueError("calculation exceeds exact arithmetic budget")
                expected = math.prod((Fraction(value) for value in operands), start=Fraction(1))
                if abs(expected - Fraction(reported)) > Fraction(tolerance):
                    issues.append(f"reported calculation {reported} differs from recomputed {expected}")
            except (KeyError, TypeError, ValueError, OverflowError):
                issues.append("malformed or unsupported calculation")
    elif kind == "protocol":
        for field in ("population", "method", "comparison", "uncertainty"):
            if not data.get(field):
                issues.append(f"protocol lacks {field}")
    elif kind == "indicator":
        for field in ("metric", "unit"):
            if not data.get(field):
                issues.append(f"indicator lacks {field}")
    elif kind == "criterion":
        for field in ("metric", "threshold", "reject"):
            if field not in data or data[field] is None or data[field] == "":
                issues.append(f"criterion lacks {field}")
    elif kind == "test":
        if data.get("passed") is not True or not data.get("command"):
            issues.append("test lacks a passing recorded command")
    elif kind in {"baseline", "result"}:
        if data.get("origin") not in {"field", "simulation", "technical", "published"}:
            issues.append(f"{kind} lacks origin classification")
        if not data.get("source") or not data.get("date"):
            issues.append(f"{kind} lacks source or date")
    elif kind == "assessment":
        if data.get("verdict") not in {"cumplido", "incumplido", "no_demostrado"}:
            issues.append("assessment lacks valid verdict")
        if data.get("claim_scope") not in {"field", "simulation", "technical"}:
            issues.append("assessment lacks field, simulation or technical claim_scope")
        for field in ("uncertainty", "adverse_effects", "cost"):
            if field not in data:
                issues.append(f"assessment lacks {field}")
    return issues


def _numeric(value: Any) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def _metric_numeric(value: Any) -> Decimal | None:
    """Accept finite decimal values whose exact fraction is safe to construct."""
    if isinstance(value, str) and len(value) > _METRIC_MAX_TEXT:
        return None
    number = _numeric(value)
    if number is None:
        return None
    parts = number.as_tuple()
    if len(parts.digits) > _METRIC_MAX_DIGITS or abs(parts.exponent) > _METRIC_MAX_EXPONENT:
        return None
    return number


def _metric_interval(data: dict[str, Any]) -> tuple[Decimal, Decimal] | None:
    """Use points for scalars and closed intervals for explicitly declared ranges."""
    unit, value = data.get("unit"), data.get("value")
    number = _metric_numeric(value)
    if number is not None:
        return number, number
    if (not isinstance(unit, str) or not unit.strip().casefold().startswith(("rango ", "range "))
            or not isinstance(value, str) or len(value) > _METRIC_MAX_TEXT):
        return None
    match = _CONTEXTUAL_RANGE.fullmatch(value)
    if match is None:
        return None
    lower, upper = (_metric_numeric(part) for part in match.groups())
    if lower is None or upper is None or lower > upper:
        return None
    return lower, upper


def _metric_comparison_unit(unit: Any) -> str:
    """Remove only the explicit range representation prefix from a unit."""
    rendered = str(unit)
    stripped = rendered.strip()
    for prefix in ("rango ", "range "):
        if stripped.casefold().startswith(prefix):
            return stripped[len(prefix):].strip()
    return rendered


def _structured_field_outcome(value: Any) -> bool:
    """Check a declared measurement record, not source authenticity or actor coverage."""
    if not isinstance(value, dict) or value.get("status") != "measured":
        return False
    if any(not isinstance(value.get(field), str) or not value[field].strip()
           for field in ("source", "date")):
        return False
    measurements = value.get("measurements")
    if not isinstance(measurements, list) or not measurements:
        return False
    for measure in measurements:
        if not isinstance(measure, dict):
            return False
        if any(not isinstance(measure.get(field), str) or not measure[field].strip()
               for field in ("metric", "unit")):
            return False
        number = measure.get("value")
        if (isinstance(number, bool) or not isinstance(number, (int, float))
                or (isinstance(number, float) and not math.isfinite(number))):
            return False
        sample_size = measure.get("sample_size")
        if not isinstance(sample_size, int) or isinstance(sample_size, bool) or sample_size < 1:
            return False
    return True


def _decisive_indicator_has_evidence(items: dict[str, dict], flags: dict[str, dict],
                                     indicator: dict[str, Any]) -> bool:
    """Require a current measurement of this indicator on its own protocol path."""
    metric, unit = indicator["data"].get("metric"), indicator["data"].get("unit")
    if (not isinstance(metric, str) or not metric.strip()
            or not isinstance(unit, str) or not unit.strip()):
        return False
    indicator_id = indicator["id"]
    if any(flags[indicator_id][field] for field in ("stale", "contested", "issues")):
        return False
    normative_problems = _normative_problems(items, indicator_id)
    indicator_ancestors = _ancestors(items, indicator_id)
    for evidence_id in indicator_ancestors:
        evidence = items[evidence_id]
        if evidence["kind"] != "evidence":
            continue
        if any(flags[evidence_id][field] for field in ("stale", "contested", "issues")):
            continue
        data = evidence["data"]
        scope = data.get("scope")
        if (not isinstance(scope, str) or not scope.strip()
                or data.get("metric_key") != metric or data.get("unit") != unit
                or _metric_interval(data) is None):
            continue
        if _has_path(items, evidence_id, {"protocol"}):
            problems = _valid_protocol_problems(items, flags, evidence_id)
        elif data.get("origin") == "published":
            # An independent publication needs an explicit protocol on the
            # indicator or on the inference that interprets that publication.
            problems = set()
            for wrapper_id in indicator_ancestors:
                wrapper = items[wrapper_id]
                if (wrapper["kind"] not in {"indicator", "inference"}
                        or evidence_id not in _ancestors(items, wrapper_id)):
                    continue
                for ref in wrapper["deps"]:
                    if items[ref]["kind"] == "protocol":
                        problems.update(_valid_protocol_problems(items, flags, ref))
        else:
            continue
        if normative_problems & problems:
            return True
    return False


def _success_claim_issues(items: dict[str, dict], assessment: dict[str, Any],
                          approval_policy: str, *,
                          flags: dict[str, dict] | None = None,
                          skip_field_evidence_blocker: bool = False) -> list[str]:
    """Check that a decisive verdict is numerically and procedurally auditable.

    Rejections use the declared reject_test predicate, not the reject prose.
    This does not establish source authenticity or causal identification; an
    independent evaluator must still judge those.
    """
    data = assessment["data"]
    verdict = data.get("verdict")
    if verdict not in {"cumplido", "incumplido"}:
        return []
    claim = "success" if verdict == "cumplido" else "rejection"
    issues: list[str] = []
    scope = data.get("claim_scope")
    if verdict == "cumplido" and scope == "field":
        for field in ("adverse_effects", "cost"):
            if not _structured_field_outcome(data.get(field)):
                issues.append(f"{assessment['id']} field success lacks structured measured {field} evidence")
    if scope == "field" and approval_policy == "signed" and not skip_field_evidence_blocker:
        # A valid assessor signature authenticates a statement and source
        # hashes, but the current bundle does not recompute the protocol's
        # adjusted G/interval or authenticate primary records and margins.
        # Never turn that statement into a decisive field verdict.
        issues.append(
            f"{assessment['id']} decisive field verdict needs verified field effect "
            "analysis and source custody"
        )
    ancestors = [items[key] for key in _ancestors(items, assessment["id"])]
    results = [item for item in ancestors if item["kind"] == "result"]
    baselines = [item for item in ancestors if item["kind"] == "baseline"]
    criteria = [item for item in ancestors if item["kind"] == "criterion"]
    if len(results) != 1 or len(baselines) != 1 or len(criteria) != 1:
        return issues + [f"{assessment['id']} {claim} needs exactly one linked result, baseline and criterion"]
    result, baseline, criterion = results[0], baselines[0], criteria[0]
    if flags is None:
        # Direct structural callers have no challenge ledger. Public gates
        # provide the full current flags, including unresolved challenges.
        flags = {
            item_id: {"stale": _stale(items, item_id), "contested": False,
                      "issues": (
                          test_execution.item_issues(item) + ["signed test needs a current successful signed execution receipt"]
                          if approval_policy == "signed" and item["kind"] == "test" else _item_issues(item)
                      )}
            for item_id, item in items.items()
        }
    for indicator_id in sorted(_ancestors(items, criterion["id"])):
        indicator = items[indicator_id]
        if indicator["kind"] == "indicator" and not _decisive_indicator_has_evidence(items, flags, indicator):
            issues.append(
                f"{assessment['id']} {claim} needs current protocol-valid evidence "
                f"measuring {indicator['data'].get('metric')}/{indicator['data'].get('unit')} "
                f"in indicator {indicator_id}"
            )
    if result["data"].get("origin") != scope or baseline["data"].get("origin") != scope:
        issues.append(f"{assessment['id']} {scope} {claim} cannot use another evidence origin")
    if result["seq"] <= criterion["seq"]:
        issues.append(f"{assessment['id']} {claim} uses a criterion written after the result")
    criterion_requirements = {
        ref for ref in _ancestors(items, criterion["id"])
        if items[ref]["kind"] == "requirement"
    }
    covered_requirements: set[str] = set()
    # A baseline may cite a test without the result using that test.
    for ref in result["deps"]:
        test = items[ref]
        if test["kind"] != "test":
            continue
        if approval_policy == "signed":
            if any(flags[ref][field] for field in ("stale", "contested", "issues")):
                continue
        elif _stale(items, ref) or _item_issues(test):
            continue
        if criterion["id"] not in test["deps"]:
            continue
        # Criterion ancestry cannot certify an implementation. Follow only
        # implementation composition to explicitly linked requirements.
        for implementation_id in test["deps"]:
            implementation = items[implementation_id]
            if implementation["kind"] == "implementation":
                covered_requirements.update(
                    criterion_requirements
                    & _implementation_requirements(items, implementation_id)
                )
    for requirement in sorted(criterion_requirements - covered_requirements):
        issues.append(
            f"{assessment['id']} {claim} needs a current passed test linked to {result['id']} "
            f"for {criterion['id']} and implementation of {requirement}"
        )
    rejection_test = criterion["data"].get("reject_test")
    if verdict == "incumplido":
        rejection_rule = criterion["data"].get("reject")
        if not isinstance(rejection_rule, str) or not rejection_rule.strip():
            issues.append(f"{assessment['id']} rejection lacks a declared rejection rule")
        if rejection_test is None:
            issues.append(f"{assessment['id']} rejection needs a structured preregistered rejection test")
    if rejection_test is not None and not isinstance(rejection_test, dict):
        issues.append(f"{assessment['id']} has an invalid preregistered rejection test")
        rejection_test = None
    threshold = criterion["data"].get("threshold")
    effect = result["data"].get("effect")
    if not isinstance(threshold, dict) or not isinstance(effect, dict):
        return issues + [f"{assessment['id']} {claim} needs structured threshold and measured effect"]
    operator = threshold.get("operator")
    statistic = threshold.get("statistic")
    threshold_value = _numeric(threshold.get("value"))
    estimate = _numeric(effect.get("estimate"))
    interval = effect.get("interval")
    threshold_valid = (operator in (">=", "<=") and statistic in ("estimate", "lower_ci", "upper_ci")
                       and threshold_value is not None)
    if not threshold_valid:
        issues.append(f"{assessment['id']} has an invalid preregistered threshold")
    if effect.get("metric") != criterion["data"].get("metric") or baseline["data"].get("metric") != effect.get("metric"):
        issues.append(f"{assessment['id']} metric differs between baseline, result and criterion")
    effect_unit = effect.get("unit")
    if not isinstance(effect_unit, str) or not effect_unit.strip():
        issues.append(f"{assessment['id']} {claim} lacks a measured effect unit")
    declarations = [("criterion", criterion["data"]), ("threshold", threshold)]
    if rejection_test is not None:
        declarations.append(("reject_test", rejection_test))
    for owner, declaration in declarations:
        if "unit" not in declaration:
            continue
        declared_unit = declaration["unit"]
        if not isinstance(declared_unit, str) or not declared_unit.strip():
            issues.append(f"{assessment['id']} {owner} declares an invalid unit")
        elif declared_unit != effect_unit:
            issues.append(f"{assessment['id']} {owner} unit differs from measured effect")
    linked_indicators = [items[key] for key in _ancestors(items, criterion["id"])
                         if items[key]["kind"] == "indicator"
                         and items[key]["data"].get("metric") == criterion["data"].get("metric")]
    linked_units = [indicator["data"].get("unit") for indicator in linked_indicators]
    if not linked_units or any(not isinstance(unit, str) or not unit.strip() for unit in linked_units):
        issues.append(f"{assessment['id']} {claim} lacks a declared linked indicator unit")
    elif any(unit != linked_units[0] for unit in linked_units[1:]):
        issues.append(f"{assessment['id']} {claim} has ambiguous linked indicator units")
    elif effect_unit != linked_units[0]:
        issues.append(f"{assessment['id']} effect unit differs from linked indicator")
    baseline_unit = baseline["data"].get("unit")
    if not isinstance(baseline_unit, str) or not baseline_unit.strip():
        issues.append(f"{assessment['id']} {claim} lacks a declared baseline unit")
    elif baseline_unit != effect_unit:
        issues.append(f"{assessment['id']} baseline unit differs from measured effect")
    if _numeric(baseline["data"].get("value")) is None or estimate is None:
        issues.append(f"{assessment['id']} lacks numeric baseline or effect estimate")
    if not isinstance(interval, list) or len(interval) != 2 or any(_numeric(value) is None for value in interval):
        issues.append(f"{assessment['id']} lacks a finite two-sided uncertainty interval")
        low = high = None
    else:
        low, high = _numeric(interval[0]), _numeric(interval[1])
        if low > high or (estimate is not None and not low <= estimate <= high):
            issues.append(f"{assessment['id']} has an inconsistent effect interval")
    if scope == "field":
        if not all(effect.get(field) for field in ("design", "comparator", "unit")):
            issues.append(f"{assessment['id']} field {claim} lacks design, comparator or unit")
        sample_size = effect.get("sample_size")
        if not isinstance(sample_size, int) or isinstance(sample_size, bool) or sample_size < 1:
            issues.append(f"{assessment['id']} field {claim} lacks a positive sample size")
    values = {"estimate": estimate, "lower_ci": low, "upper_ci": high}
    chosen = values.get(statistic) if isinstance(statistic, str) else None
    success_passes = None
    if threshold_valid and chosen is not None:
        success_passes = chosen >= threshold_value if operator == ">=" else chosen <= threshold_value
        if verdict == "cumplido" and not success_passes:
            issues.append(f"{assessment['id']} measured {statistic} does not meet the prior threshold")
    if rejection_test is not None:
        reject_operator = rejection_test.get("operator")
        reject_statistic = rejection_test.get("statistic")
        reject_value = _numeric(rejection_test.get("value"))
        allowed_keys = {"operator", "statistic", "value", "unit"}
        required_keys = {"operator", "statistic", "value"}
        if (not required_keys <= rejection_test.keys() or not rejection_test.keys() <= allowed_keys
                or reject_operator not in ("<", "<=", ">", ">=")
                or reject_statistic not in ("estimate", "lower_ci", "upper_ci")
                or reject_value is None):
            issues.append(f"{assessment['id']} has an invalid preregistered rejection test")
        else:
            if scope == "field" and threshold_valid:
                # A crossing interval cannot establish a field rejection: the
                # entire interval must fall on the adverse side of the threshold.
                expected_statistic, expected_operator = (("upper_ci", "<") if operator == ">="
                                                         else ("lower_ci", ">"))
                if (reject_statistic != expected_statistic or reject_operator != expected_operator
                        or reject_value != threshold_value):
                    issues.append(f"{assessment['id']} field rejection test must use {expected_statistic} "
                                  f"{expected_operator} at the success threshold")
            reject_chosen = values[reject_statistic]
            if reject_chosen is not None:
                triggered = {"<": reject_chosen < reject_value, "<=": reject_chosen <= reject_value,
                             ">": reject_chosen > reject_value, ">=": reject_chosen >= reject_value}[reject_operator]
                if verdict == "incumplido" and not triggered:
                    issues.append(f"{assessment['id']} measured {reject_statistic} does not meet the prior rejection test")
                if success_passes and triggered:
                    issues.append(f"{assessment['id']} success and rejection tests both hold for the measured effect")
    return issues


def _flags(state: dict[str, Any], *, check_archives: bool = True,
           include_retirements: bool = True) -> dict[str, dict[str, Any]]:
    items = state["items"]
    contested: set[str] = set()
    active_resolutions = _active_resolutions(state)
    for seq, challenge in state["challenges"].items():
        if seq not in active_resolutions:
            contested |= _dependents(items, challenge["left"])
            contested |= _dependents(items, challenge["right"])
    automatic = _automatic_conflicts(state, active_resolutions)
    for item_id in automatic:
        contested |= _dependents(items, item_id)
    # Rejection concerns the current version and every artifact that relies on it;
    # it does not make unchanged dependency versions "stale".
    review_issues: dict[str, list[str]] = {}
    for item_id, item in items.items():
        review = state["item_reviews"].get((item_id, item["version"]))
        if review is not None and review["verdict"] == "reject":
            for dependent_id in _dependents(items, item_id):
                issue = ("latest item review rejected this version" if dependent_id == item_id
                         else f"depends on rejected item review of {item_id}")
                review_issues.setdefault(dependent_id, []).append(issue)
    archive_issues: dict[str, list[str]] = {}
    archive_dependency_issues: dict[str, list[str]] = {}
    if state["project"]["approval_policy"] == "signed":
        # One named archive cannot substantiate incompatible byte digests in
        # the same case. Reject the declarations before reading a mutable file:
        # separate reads could otherwise each see a different valid version.
        declared: dict[str, set[str]] = {}
        for item in items.values():
            if item["kind"] != "evidence":
                continue
            archive = item["data"].get("archive")
            expected = item["data"].get("source_sha256")
            if (type(archive) is str and _local_archive_path_parts(archive) is not None
                    and type(expected) is str and _SOURCE_SHA256.fullmatch(expected) is not None):
                declared.setdefault(archive, set()).add(expected)
        conflicting_archives = {archive for archive, digests in declared.items() if len(digests) > 1}
        # Many evidence items may cite the same archived source. Cache only
        # within this status calculation so each new read sees live bytes.
        checks: dict[tuple[str, str], list[str]] = {}
        for item_id, item in items.items():
            if item["kind"] != "evidence":
                continue
            data = item["data"]
            archive = data.get("archive")
            expected = data.get("source_sha256")
            if (type(archive) is str and archive in conflicting_archives
                    and type(expected) is str and _SOURCE_SHA256.fullmatch(expected) is not None):
                local_issues = ["local archive has conflicting source_sha256 declarations"]
            elif type(archive) is str and type(expected) is str:
                key = (archive, expected)
                if key not in checks:
                    checks[key] = _local_archive_issues(state["case_path"], data, check_contents=check_archives)
                local_issues = checks[key]
            else:
                local_issues = _local_archive_issues(state["case_path"], data, check_contents=check_archives)
            if local_issues:
                archive_issues[item_id] = local_issues
                for dependent_id in _dependents(items, item_id) - {item_id}:
                    archive_dependency_issues.setdefault(dependent_id, []).append(
                        f"depends on invalid local archive evidence {item_id}"
                    )
    flags: dict[str, dict[str, Any]] = {}
    for item_id, item in items.items():
        issues = (_item_issues(item) if state["project"]["approval_policy"] == "fixture" or item["kind"] != "test"
                  else test_execution.item_issues(
                      item, observed=state["project"].get("test_gate_policy") == "signed_observed",
                  ))
        flag = {
            "stale": _stale(items, item_id),
            "contested": item_id in contested,
            "issues": (issues + automatic.get(item_id, []) + review_issues.get(item_id, [])
                       + archive_issues.get(item_id, []) + archive_dependency_issues.get(item_id, [])),
            "approved": (item_id, item["version"]) in state["approvals"],
            "approval_status": state["approval_statuses"].get((item_id, item["version"]), "missing"),
        }
        if state["project"]["approval_policy"] == "signed" and item["kind"] == "test":
            receipt = state["test_executions"].get((item_id, item["version"]))
            seen_unverified = any(
                entry["id"] == item_id and entry["version"] == item["version"]
                for entry in state["test_execution_history"]
            )
            status = ("signed_passed" if receipt["passed"] else "signed_failed") if receipt else (
                "unverified" if seen_unverified else "missing"
            )
            flag["test_execution_status"] = status
            flag["test_execution_provenance"] = (
                (receipt["seq"], receipt["hash"]) if receipt else None
            )
            flag["test_execution_actor"] = receipt["actor"] if receipt else None
            if status != "signed_passed":
                flag["issues"].append(
                    "latest signed test execution failed or timed out" if status == "signed_failed"
                    else "signed test needs a current successful signed execution receipt"
                )
            if state["project"].get("test_gate_policy") == "signed_observed":
                provenance = flag["test_execution_provenance"]
                observed = (state["test_observations"].get((item_id, item["version"], *provenance))
                            if provenance else None)
                seen = any(entry["id"] == item_id and entry["version"] == item["version"]
                           for entry in state["test_observation_history"])
                observation_status = (
                    "observed_passed" if observed["passed"] else
                    "observed_failed" if observed["bundle_verified"] else "unverified"
                ) if observed else ("unverified" if seen else "missing")
                flag["test_observation_status"] = observation_status
                flag["test_observation_provenance"] = (
                    (observed["seq"], observed["hash"]) if observed else None
                )
                flag["test_observation_actor"] = observed["actor"] if observed else None
                if observation_status != "observed_passed":
                    flag["issues"].append(
                        "latest signed observed repeat failed or its bundle is unavailable"
                        if observation_status in {"observed_failed", "unverified"}
                        else "signed test needs a current successful observed repeat receipt"
                    )
        flags[item_id] = flag
    if include_retirements:
        _annotate_indicator_retirements(state, flags)
    return flags


def _validate_indicator_retirement(payload: Any, actor: Any) -> None:
    if (type(payload) is not dict
            or set(payload) != {"id", "version", "replacements", "review_seq", "reason"}
            or type(payload["id"]) is not str or ITEM_ID.fullmatch(payload["id"]) is None
            or type(payload["version"]) is not int or payload["version"] < 1
            or type(payload["review_seq"]) is not int or payload["review_seq"] < 1
            or type(payload["reason"]) is not str or not payload["reason"].strip()
            or payload["reason"] != payload["reason"].strip()
            or type(actor) is not str or not actor.strip()):
        raise MethodError("indicator retirement needs valid id, positive version/review guards, reason and actor")
    replacements = payload["replacements"]
    if (type(replacements) is not dict or not 1 <= len(replacements) <= 32
            or any(type(key) is not str or ITEM_ID.fullmatch(key) is None
                   or type(version) is not int or version < 1 for key, version in replacements.items())):
        raise MethodError("indicator replacements must map 1–32 IDs to positive integer versions")


def _indicator_retirement_issues(state: dict, record: dict, flags: dict) -> list[str]:
    """Evaluate one declaration without recursing through retirement validity.

    A replacement with any retirement declared on its current version cannot
    support another retirement, even if that earlier declaration is invalid.
    This conservative policy prevents circular lifecycle support.
    """
    items = state["items"]
    source = items.get(record["id"])
    if source is None or source["kind"] != "indicator":
        return ["only an existing indicator can be retired"]
    if source["version"] != record["version"]:
        return ["source indicator version changed"]
    issues = []
    review = state["item_reviews"].get((source["id"], source["version"]))
    source_authors = (state["item_author_history"][source["id"]]
                      if state["project"]["approval_policy"] == "signed" else {source["author"]})
    if (review is None or review["verdict"] != "reject" or review["seq"] != record["review_seq"]
            or type(review["version"]) is not int or review["version"] != source["version"]
            or type(review["actor"]) is not str or not review["actor"].strip()
            or review["actor"] in source_authors):
        issues.append("source needs its current independent negative review at the expected sequence")
    source_flag = flags[source["id"]]
    if source_flag["stale"] or source_flag["contested"]:
        issues.append("source indicator is stale or contested")
    if source_flag["issues"] != ["latest item review rejected this version"]:
        issues.append("source indicator must have only its current review rejection issue")
    if any(source["id"] in item["deps"] for item in items.values()):
        issues.append("source indicator has current consumers, including outdated references")
    source_ancestors = _ancestors(items, source["id"]) - {source["id"]}
    if any(flags[key]["stale"] or flags[key]["contested"] or flags[key]["issues"] for key in source_ancestors):
        issues.append("source indicator ancestors are not current and sound")
    roots = {key for key in source_ancestors if items[key]["kind"] in {"problem", "norm"}}
    if not any(items[key]["kind"] == "problem" for key in roots) or not any(items[key]["kind"] == "norm" for key in roots):
        issues.append("source indicator needs problem and normative roots")
    covered = set()
    for key, version in record["replacements"].items():
        replacement = items.get(key)
        if replacement is None or replacement["kind"] != "indicator" or replacement["version"] != version:
            issues.append(f"replacement {key} is not an indicator at its declared current version")
            continue
        ancestors = _ancestors(items, key)
        covered.update(ancestor for ancestor in ancestors if items[ancestor]["kind"] in {"problem", "norm"})
        if source["id"] in ancestors:
            issues.append(f"replacement {key} depends on the source or is the source")
        if any(entry["id"] == key and entry["version"] == replacement["version"]
               for entry in state["indicator_retirements"]):
            issues.append(f"replacement {key} has a retirement declared on its current version")
        if any(flags[ancestor]["stale"] or flags[ancestor]["contested"] or flags[ancestor]["issues"]
               for ancestor in ancestors):
            issues.append(f"replacement {key} or its ancestors are not current and sound")
        if not _decisive_indicator_has_evidence(items, flags, replacement):
            issues.append(f"replacement {key} lacks current typed numeric evidence on its normative protocol path")
    if not roots <= covered:
        issues.append("replacement union does not preserve every source problem and normative root")
    return sorted(set(issues))


def _annotate_indicator_retirements(state: dict, flags: dict) -> None:
    latest = {entry["id"]: entry["seq"] for entry in state["indicator_retirements"]}
    for flag in flags.values():
        flag.update(retired=False, retirement_status="none", retirement_issues=[], retirement_history=[])
    for entry in state["indicator_retirements"]:
        issues = _indicator_retirement_issues(state, entry, flags)
        if latest[entry["id"]] != entry["seq"]:
            issues.append("superseded by a later retirement declaration")
        public = {**entry, "effective": not issues, "issues": issues}
        flag = flags[entry["id"]]
        flag["retirement_history"].append(public)
        if latest[entry["id"]] == entry["seq"]:
            flag["retired"] = not issues
            flag["retirement_issues"] = issues
            flag["retirement_status"] = (
                "superseded" if state["items"][entry["id"]]["version"] != entry["version"]
                else "invalidated" if issues else "effective"
            )


def _has_path(items: dict[str, dict], item_id: str, kinds: set[str]) -> bool:
    return any(items[ancestor]["kind"] in kinds for ancestor in _ancestors(items, item_id))


def _valid_protocol_problems(items: dict[str, dict], flags: dict[str, dict], item_id: str) -> set[str]:
    """Find valid protocol → hypothesis → question → problem lineages."""
    def usable(candidate: str) -> bool:
        flag = flags[candidate]
        return not (flag["stale"] or flag["contested"] or flag["issues"])

    problems: set[str] = set()
    for protocol_id in _ancestors(items, item_id):
        if items[protocol_id]["kind"] != "protocol" or not usable(protocol_id):
            continue
        protocol_ancestors = _ancestors(items, protocol_id)
        questions = [question_id for question_id in protocol_ancestors
                     if items[question_id]["kind"] == "question" and usable(question_id)]
        hypotheses = [hypothesis_id for hypothesis_id in protocol_ancestors
                      if items[hypothesis_id]["kind"] == "hypothesis" and usable(hypothesis_id)]
        for hypothesis_id in hypotheses:
            hypothesis_ancestors = _ancestors(items, hypothesis_id)
            for question_id in questions:
                if question_id not in hypothesis_ancestors:
                    continue
                problems.update(
                    ancestor for ancestor in _ancestors(items, question_id)
                    if items[ancestor]["kind"] == "problem" and usable(ancestor)
                )
    return problems


def _evidence_matches_indicator(evidence: dict, metric: Any | None, unit: Any | None) -> bool:
    """Explicit metric/unit conflicts exclude support; absent fields stay provisional."""
    data = evidence["data"]
    return all(
        expected is None or data.get(field) is None or data[field] == expected
        for field, expected in (("metric_key", metric), ("unit", unit))
    )


def _linked_evidence_problems(items: dict[str, dict], flags: dict[str, dict],
                              item_id: str, metric: Any | None = None,
                              unit: Any | None = None) -> tuple[set[str], bool]:
    """Attribute protocols to actual evidence, never to an unrelated sibling branch.

    An independent published source can be interpreted under a protocol named
    directly by the inference or indicator. Evidence already linked to a protocol retains
    its own problem lineage regardless of origin; a sibling cannot relabel it.
    """
    item = items[item_id]
    direct_protocol_problems: set[str] = set()
    for ref in item["deps"]:
        if items[ref]["kind"] == "protocol":
            direct_protocol_problems.update(_valid_protocol_problems(items, flags, ref))
    problems: set[str] = set()
    mismatch = False
    for evidence_id in _ancestors(items, item_id):
        evidence = items[evidence_id]
        if evidence["kind"] != "evidence" or not _evidence_matches_indicator(evidence, metric, unit):
            continue
        own_problems = _valid_protocol_problems(items, flags, evidence_id)
        if _has_path(items, evidence_id, {"protocol"}):
            problems.update(own_problems)
            if direct_protocol_problems and not own_problems & direct_protocol_problems:
                mismatch = True
        elif evidence["data"].get("origin") == "published":
            problems.update(direct_protocol_problems)
    return problems, mismatch


def _evidence_based_problems(items: dict[str, dict], flags: dict[str, dict],
                             item_id: str, metric: Any | None = None, unit: Any | None = None) -> set[str]:
    """Problem lineages supported by evidence under a coherent protocol path."""
    problems: set[str] = set()
    for ancestor in _ancestors(items, item_id):
        kind = items[ancestor]["kind"]
        if kind == "evidence" and _evidence_matches_indicator(items[ancestor], metric, unit):
            problems.update(_valid_protocol_problems(items, flags, ancestor))
        elif kind in {"inference", "indicator"}:
            inference_problems, mismatch = _linked_evidence_problems(items, flags, ancestor, metric, unit)
            if not mismatch:
                problems.update(inference_problems)
    return problems


def _normative_problems(items: dict[str, dict], item_id: str) -> set[str]:
    problems: set[str] = set()
    for ancestor in _ancestors(items, item_id):
        if items[ancestor]["kind"] == "norm":
            problems.update(ref for ref in _ancestors(items, ancestor) if items[ref]["kind"] == "problem")
    return problems


def _normative_evidence_problems(items: dict[str, dict], flags: dict[str, dict], item_id: str,
                                 metric: Any | None = None, unit: Any | None = None) -> set[str]:
    """Problem lineages shared by normative and relevant protocol-grounded evidence."""
    return (_normative_problems(items, item_id)
            & _evidence_based_problems(items, flags, item_id, metric, unit))


def _shares_normative_evidence_problem(items: dict[str, dict], flags: dict[str, dict], item_id: str) -> bool:
    item = items[item_id]
    metric = item["data"].get("metric") if item["kind"] == "indicator" else None
    unit = item["data"].get("unit") if item["kind"] == "indicator" else None
    return bool(_normative_evidence_problems(items, flags, item_id, metric, unit))


def _phase_blockers(state: dict[str, Any], phase_id: str, previous_accepted: bool, flags: dict[str, dict]) -> list[str]:
    phase = PHASE_BY_ID[phase_id]
    items = state["items"]
    blockers: list[str] = []
    if not previous_accepted:
        blockers.append("previous phase is not currently accepted")
    in_phase = [item for item in items.values() if KIND_TO_PHASE[item["kind"]] == phase_id
                and not flags[item["id"]].get("retired", False)]
    for item in in_phase:
        item_id, flag = item["id"], flags[item["id"]]
        if flag["stale"]:
            blockers.append(f"{item_id} depends on an older revision")
        if flag["contested"]:
            blockers.append(f"{item_id} has an unresolved contradiction")
        blockers.extend(f"{item_id}: {issue}" for issue in flag["issues"])
        if item["kind"] in {"norm", "decision"} and not flag["approved"]:
            blockers.append(f"{item_id} requires {'a fixture' if state['project']['approval_policy'] == 'fixture' else 'a verified human'} approval")
    for kind, minimum in phase.required:
        count = sum(item["kind"] == kind and not flags[item["id"]]["stale"] and not flags[item["id"]]["contested"] and not flags[item["id"]]["issues"] for item in in_phase)
        if count < minimum:
            blockers.append(f"needs {minimum} valid {kind}; has {count}")

    def refs_of(item: dict, required: set[str]) -> bool:
        return all(_has_path(items, item["id"], {kind}) for kind in required)

    if phase_id == "critique":
        for item in in_phase:
            if item["kind"] == "norm" and not refs_of(item, {"problem", "actor"}):
                blockers.append(f"{item['id']} must link problem and actor")
        frames = [item["text"].strip().casefold() for item in in_phase if item["kind"] == "frame_option"]
        if len(frames) >= 2 and len(set(frames)) < 2:
            blockers.append("frame options must differ")
    elif phase_id == "study":
        for item in in_phase:
            if item["kind"] == "protocol" and not refs_of(item, {"question", "hypothesis"}):
                blockers.append(f"{item['id']} must link question and hypothesis")
            if item["kind"] == "protocol" and not _valid_protocol_problems(items, flags, item["id"]):
                blockers.append(f"{item['id']} needs a valid hypothesis → question → problem chain")
            if item["kind"] == "indicator" and not refs_of(item, {"problem", "norm"}):
                blockers.append(f"{item['id']} must link problem and normative commitment")
    elif phase_id == "observe":
        for item in in_phase:
            if (item["kind"] == "evidence" and item["data"].get("origin") != "published"
                    and not _valid_protocol_problems(items, flags, item["id"])):
                blockers.append(f"{item['id']} must link a valid protocol with hypothesis, question and problem")
            if item["kind"] == "inference" and not refs_of(item, {"evidence"}):
                blockers.append(f"{item['id']} must link evidence")
            if item["kind"] == "inference":
                evidence_problems, mismatch = _linked_evidence_problems(items, flags, item["id"])
                if not evidence_problems:
                    blockers.append(f"{item['id']} must link evidence to a valid protocol and problem chain")
                if mismatch:
                    blockers.append(f"{item['id']} applies protocol-bound evidence to an unrelated protocol problem")
    elif phase_id == "explain":
        for item in in_phase:
            if item["kind"] == "synthesis" and not refs_of(item, {"inference", "evidence"}):
                blockers.append(f"{item['id']} must link inference and evidence")
            if item["kind"] == "uncertainty" and not refs_of(item, {"synthesis"}):
                blockers.append(f"{item['id']} must link synthesis")
    elif phase_id == "compare":
        for item in in_phase:
            if item["kind"] == "option" and not refs_of(item, {"synthesis", "norm"}):
                blockers.append(f"{item['id']} must link synthesis and norm")
            if item["kind"] == "comparison":
                direct_options = [ref for ref in item["deps"] if items[ref]["kind"] == "option"]
                if len(direct_options) < 2:
                    blockers.append(f"{item['id']} must directly compare two options")
            if item["kind"] == "risk" and not refs_of(item, {"option"}):
                blockers.append(f"{item['id']} must link an option")
    elif phase_id == "specify":
        for indicator in items.values():
            if indicator["kind"] != "indicator" or flags[indicator["id"]].get("retired", False):
                continue
            if not _has_path(items, indicator["id"], {"evidence"}):
                blockers.append(f"{indicator['id']} lacks a path to evidence before specification")
                continue
            if not _shares_normative_evidence_problem(items, flags, indicator["id"]):
                blockers.append(f"{indicator['id']} lacks a shared problem between norm and protocol-grounded evidence")
            if _linked_evidence_problems(items, flags, indicator["id"], indicator["data"].get("metric"),
                                         indicator["data"].get("unit"))[1]:
                blockers.append(f"{indicator['id']} applies protocol-bound evidence to an unrelated protocol problem")
        for item in in_phase:
            if item["kind"] == "decision" and not refs_of(item, {"comparison", "norm", "evidence"}):
                blockers.append(f"{item['id']} must link comparison, norm and evidence")
            if item["kind"] in {"requirement", "criterion"} and not refs_of(item, {"problem", "norm", "evidence", "decision"}):
                blockers.append(f"{item['id']} lacks a path to problem, norm, evidence or decision")
            if item["kind"] in {"requirement", "criterion"}:
                if not _shares_normative_evidence_problem(items, flags, item["id"]):
                    blockers.append(f"{item['id']} lacks a shared problem between norm and protocol-grounded evidence")
            if item["kind"] == "criterion":
                ancestors = _ancestors(items, item["id"])
                metric = item["data"].get("metric")
                indicators = [items[ref] for ref in ancestors
                              if items[ref]["kind"] == "indicator" and items[ref]["data"].get("metric") == metric]
                requirements = [items[ref] for ref in ancestors if items[ref]["kind"] == "requirement"]
                if not indicators:
                    blockers.append(f"{item['id']} needs a linked indicator with the same success metric")
                if not requirements:
                    blockers.append(f"{item['id']} needs a linked requirement")
                for requirement in requirements:
                    # A requirement may be justified by evidence measuring a different
                    # property; the success indicator must support its own metric/unit.
                    requirement_problems = _normative_evidence_problems(
                        items, flags, requirement["id"]
                    )
                    if not any(
                        requirement_problems & _normative_evidence_problems(
                            items, flags, indicator["id"], metric, indicator["data"].get("unit")
                        )
                        for indicator in indicators
                    ):
                        blockers.append(
                            f"{item['id']} needs a same-problem link from {requirement['id']} "
                            "to a same-metric indicator"
                        )
    elif phase_id == "build":
        for item in in_phase:
            if item["kind"] == "implementation" and not refs_of(item, {"requirement"}):
                blockers.append(f"{item['id']} must link requirement")
            if item["kind"] == "test" and not refs_of(item, {"implementation", "criterion"}):
                blockers.append(f"{item['id']} must link implementation and criterion")
    elif phase_id == "validate":
        for item in in_phase:
            if item["kind"] == "result":
                if not refs_of(item, {"baseline", "criterion"}):
                    blockers.append(f"{item['id']} must link baseline and criterion")
                linked_criteria = [items[ref] for ref in _ancestors(items, item["id"]) if items[ref]["kind"] == "criterion"]
                if any(criterion["seq"] >= item["seq"] for criterion in linked_criteria):
                    blockers.append(f"{item['id']} precedes a current criterion revision")
            if item["kind"] == "assessment":
                if not refs_of(item, {"result", "risk"}):
                    blockers.append(f"{item['id']} must link result and risk")
                blockers.extend(_success_claim_issues(
                    items, item, state["project"]["approval_policy"], flags=flags,
                ))
    return sorted(set(blockers))


def _phase_statuses(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    flags = _flags(state)
    active_resolutions = _active_resolutions(state)
    statuses: dict[str, dict[str, Any]] = {}
    previous_accepted = True
    previous_marker = 0
    for phase in PHASES:
        phase_item_ids = {item["id"] for item in state["items"].values() if KIND_TO_PHASE[item["kind"]] == phase.id}
        relevant_ids = set().union(*(_ancestors(state["items"], item_id) for item_id in phase_item_ids)) if phase_item_ids else set()
        challenge_history = sorted(
            (seq, seq in active_resolutions, state["resolutions"].get(seq, {}).get("seq"))
            for seq, entry in state["challenges"].items()
            if entry["left"] in relevant_ids or entry["right"] in relevant_ids
        )
        items = sorted(
            (item["id"], item["version"], flags[item["id"]]["stale"], flags[item["id"]]["contested"], flags[item["id"]]["issues"])
            for item in state["items"].values() if KIND_TO_PHASE[item["kind"]] == phase.id
        )
        # A new item verdict needs a new phase review and advance, even when an
        # accepted verdict removes the rejection issue from an unchanged item.
        item_reviews = sorted(
            (item_id, review["seq"], review["verdict"])
            for item_id in relevant_ids
            if (review := state["item_reviews"].get((item_id, state["items"][item_id]["version"]))) is not None
        )
        snapshot_data = {"phase": phase.id, "items": items,
                         "previous_marker": previous_marker, "challenges": challenge_history}
        if phase.id == "study" and state["indicator_retirements"]:
            snapshot_data["indicator_retirements"] = sorted(
                (entry for flag in flags.values() for entry in flag["retirement_history"]),
                key=lambda entry: entry["seq"],
            )
        if state["project"]["approval_policy"] == "signed":
            normative_ids = sorted(item_id for item_id in relevant_ids
                                   if state["items"][item_id]["kind"] in {"norm", "decision"})
            if normative_ids:
                snapshot_data["normative_approvals"] = [
                    (item_id, state["items"][item_id]["version"],
                     state["approval_provenance"].get((item_id, state["items"][item_id]["version"])))
                    for item_id in normative_ids
                ]
            test_ids = sorted(item_id for item_id in relevant_ids
                              if state["items"][item_id]["kind"] == "test")
            if test_ids:
                snapshot_data["test_executions"] = [
                    (item_id, state["items"][item_id]["version"],
                     flags[item_id]["test_execution_provenance"])
                    for item_id in test_ids
                ]
                if state["project"].get("test_gate_policy") == "signed_observed":
                    snapshot_data["test_observations"] = [
                        (item_id, state["items"][item_id]["version"],
                         flags[item_id]["test_observation_provenance"])
                        for item_id in test_ids
                    ]
        # Existing ledgers recorded this payload without an item_reviews key.
        if item_reviews:
            snapshot_data["item_reviews"] = item_reviews
        if phase.id == "validate" and state["field_attestations"]:
            snapshot_data["field_attestations"] = [
                (entry["seq"], entry["verified"])
                for entry in state["field_attestations"]
            ]
        snapshot = _hash(snapshot_data)
        blockers = _phase_blockers(state, phase.id, previous_accepted, flags)
        if (state["project"]["approval_policy"] == "fixture"
                and state["phase_review_trust"] != "fixture"):
            blockers.insert(0, "fixture policy is unavailable or conflicts with a registered signed case")
        reviews = [review for review in state["phase_reviews"] if review["phase"] == phase.id and review["snapshot"] == snapshot]
        review = reviews[-1] if reviews else None
        if state["project"]["approval_policy"] == "signed":
            review_effective = bool(
                review and review["verdict"] == "accept"
                and review["signature_verified"] and review["independent"]
            )
        else:
            review_effective = bool(
                state["phase_review_trust"] == "fixture"
                and review and review["verdict"] == "accept"
            )
        advances = [marker for marker in state["advances"] if marker["phase"] == phase.id and marker["snapshot"] == snapshot and review_effective and marker["review_seq"] == review["seq"] and marker["seq"] > review["seq"]]
        marker = advances[-1] if advances else None
        accepted = not blockers and marker is not None and (
            state["project"]["approval_policy"] == "signed"
            or phase.id != "validate" or bool(review and review["independent"])
        )
        statuses[phase.id] = {
            "phase": phase.id,
            "front": phase.front,
            "ready": not blockers,
            "accepted": accepted,
            "reviewed": review_effective,
            "independent_review": bool(review and review["independent"] and (
                (state["project"]["approval_policy"] == "fixture"
                 and state["phase_review_trust"] == "fixture")
                or review["signature_verified"]
            )),
            "review_signature_verified": bool(review and review["signature_verified"]),
            "review_provenance": review["provenance"] if review else "none",
            "blockers": blockers,
            "snapshot": snapshot,
            "advance_seq": marker["seq"] if marker else None,
        }
        previous_accepted = accepted
        previous_marker = marker["seq"] if accepted else 0
    return statuses


def create_case(path: str | Path, title: str, domain: str, actor: str,
                approval_policy: str = "signed", test_gate_policy: str = "signed_report") -> dict[str, Any]:
    if "ORGANON_LEDGER_ANCHORS_FILE" in os.environ:
        raise MethodError("initialize a case before enabling ORGANON_LEDGER_ANCHORS_FILE; then register its sequence-zero head")
    init_project(path, title, domain, actor, approval_policy, test_gate_policy)
    return get_state(path)


def put_item(path: str | Path, id: str, kind: str, text: str, refs: list[str], data: dict, actor: str, *,
             expected_version: int | None = None, expected_deps: dict[str, int] | None = None) -> dict[str, Any]:
    if not isinstance(id, str) or not ITEM_ID.fullmatch(id):
        raise MethodError("item id must start with a letter and contain 2–64 letters, digits, _ or -")
    if kind not in KINDS:
        raise MethodError(f"unknown item kind: {kind}")
    if not isinstance(text, str) or not text.strip():
        raise MethodError("item text must be nonempty")
    if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs) or len(refs) != len(set(refs)):
        raise MethodError("refs must be a list of distinct item ids")
    if not isinstance(data, dict):
        raise MethodError("data must be an object")
    if (expected_version is not None and (not isinstance(expected_version, int) or isinstance(expected_version, bool)
                                          or expected_version < 0)):
        raise MethodError("expected_version must be a nonnegative integer")
    if (expected_deps is not None and (not isinstance(expected_deps, dict) or set(expected_deps) != set(refs)
                                      or any(not isinstance(version, int) or isinstance(version, bool) or version < 1
                                             for version in expected_deps.values()))):
        raise MethodError("expected_deps must map exactly the refs to positive integer versions")
    state = _project(path)
    items = state["items"]
    if any(ref not in items for ref in refs):
        raise MethodError(f"unknown references: {sorted(set(refs) - set(items))}")
    observed_version = items[id]["version"] if id in items else 0
    observed_deps = {ref: items[ref]["version"] for ref in refs}
    if expected_version is not None and expected_version != observed_version:
        raise ConflictError(f"item version conflict: expected {expected_version}, current {observed_version}")
    if expected_deps is not None and expected_deps != observed_deps:
        raise ConflictError("item dependency version conflict")
    if id in refs or any(id in _ancestors(items, ref) for ref in refs):
        raise MethodError("dependency cycle")
    if id in items and items[id]["kind"] != kind:
        raise MethodError("an item's kind cannot change across revisions")
    case_id = state["project"].get("case_id")
    item = {
        "id": id,
        "kind": kind,
        "version": observed_version + 1,
        "text": text.strip(),
        "deps": observed_deps,
        "data": data,
    }
    guarded = expected_version is not None and (not refs or expected_deps is not None)
    for attempt in range(_PUT_MAX_RETRIES + 1):
        if attempt:
            state = _project(path)
            items = state["items"]
            if state["project"].get("case_id") != case_id:
                raise ConflictError("case changed during item put")
            current = items.get(id)
            if (current["version"] if current else 0) != observed_version:
                raise ConflictError("item changed during item put")
            if any(ref not in items or items[ref]["version"] != version for ref, version in observed_deps.items()):
                raise ConflictError("item dependency changed during item put")
            if id in refs or any(id in _ancestors(items, ref) for ref in refs):
                raise MethodError("dependency cycle")
        try:
            event = append_event(path, "item_put", item, actor, expected_seq=state["revision"])
        except ConflictError:
            if not guarded or attempt == _PUT_MAX_RETRIES:
                raise
        else:
            return {**item, "seq": event["seq"], "author": actor}
    raise AssertionError("unreachable item put retry state")


def review_item(path: str | Path, id: str, verdict: str, reason: str, actor: str) -> dict[str, Any]:
    state = _project(path)
    item = state["items"].get(id)
    if item is None:
        raise MethodError(f"unknown item: {id}")
    if verdict not in VERDICTS or not reason.strip():
        raise MethodError("review needs accept/reject and reason")
    if actor == item["author"]:
        raise MethodError("item reviewer must differ from its author")
    return append_event(path, "item_review", {"id": id, "version": item["version"], "verdict": verdict, "reason": reason.strip()}, actor, expected_seq=state["revision"])


def retire_indicator(path: str | Path, id: str, replacements: dict[str, int], reason: str, actor: str,
                     expected_version: int, expected_review_seq: int) -> dict[str, Any]:
    """Retire one rejected indicator version without deleting it or approving norms.

    Replacement versions and the negative review are mandatory concurrency
    guards. Lifecycle validity is re-evaluated on every read; consumers are never
    rewritten, and the original rejection remains visible in item issues.
    """
    if type(reason) is not str or type(actor) is not str:
        raise MethodError("indicator retirement needs an explicit reason and actor")
    payload = {"id": id, "version": expected_version, "replacements": replacements,
               "review_seq": expected_review_seq, "reason": reason.strip()}
    _validate_indicator_retirement(payload, actor)
    state = _project(path)
    flags = _flags(state)
    if flags.get(id, {}).get("retired", False):
        raise MethodError("indicator is already effectively retired")
    issues = _indicator_retirement_issues(state, payload, flags)
    if issues:
        raise MethodError("indicator retirement is blocked: " + "; ".join(issues))
    return append_event(path, "indicator_retire", payload, actor.strip(), expected_seq=state["revision"])


def _approval_target(state: dict[str, Any], id: str, reason: str, actor: str) -> dict[str, Any]:
    item = state["items"].get(id)
    if item is None or item["kind"] not in {"norm", "decision"}:
        raise MethodError("only a current norm or decision can receive approval")
    if not isinstance(actor, str) or not actor.startswith("human:") or len(actor) <= len("human:"):
        raise MethodError("approval actor must be human:<name>")
    if not isinstance(reason, str) or not reason.strip():
        raise MethodError("approval requires an explicit reason or record locator")
    return item


def approval_challenge(path: str | Path, id: str, reason: str, actor: str) -> dict[str, Any]:
    state = _project(path)
    item = _approval_target(state, id, reason, actor)
    if state["project"]["approval_policy"] != "signed":
        raise MethodError("fixture cases do not need signed approval challenges")
    return approval.challenge(state["project"], item, actor, reason.strip(), path, state["head_hash"])


def approve(path: str | Path, id: str, reason: str, actor: str, signature: str | None = None) -> dict[str, Any]:
    state = _project(path)
    item = _approval_target(state, id, reason, actor)
    payload = {"id": id, "version": item["version"], "reason": reason.strip()}
    if state["project"]["approval_policy"] == "fixture":
        if state["approval_trust"] != "fixture":
            raise MethodError("fixture approval is disabled or conflicts with a registered signed case")
        if actor != "human:fixture" or signature is not None:
            raise MethodError("fixture approval requires human:fixture and no signature")
    else:
        if not isinstance(signature, str) or not signature:
            raise MethodError("signed approval requires an Ed25519 signature")
        try:
            approvers, _ = approval.trust_context(state["project"], path)
        except ValueError as exc:
            raise MethodError(str(exc)) from exc
        key = approvers.get(actor)
        if key is None:
            raise MethodError("approval actor has no trusted public key")
        fingerprint = approval.key_fingerprint(key)
        if not approval.verify(state["project"], item, actor, reason.strip(), signature, fingerprint, approvers,
                               path, state["head_hash"]):
            raise MethodError("approval signature is invalid for this case, item, actor or reason")
        payload.update({"signature": signature, "key_sha256": fingerprint})
    return append_event(path, "approval", payload, actor, expected_seq=state["revision"])


def _test_execution_target(
    state: dict[str, Any], id: str, report: dict[str, Any], actor: str,
) -> dict[str, Any]:
    if state["project"]["approval_policy"] != "signed":
        raise MethodError("test execution receipts are available only for signed cases")
    item = state["items"].get(id)
    if item is None or item["kind"] != "test":
        raise MethodError("test execution requires a current test item")
    problems = test_execution.item_issues(
        item, observed=state["project"].get("test_gate_policy") == "signed_observed",
    )
    if problems:
        raise MethodError("; ".join(problems))
    if not isinstance(actor, str) or not actor.startswith("executor:") or actor != actor.strip():
        raise MethodError("test executor actor must be executor:<name>")
    if state["test_execution_trust"] != "configured" or actor not in state["test_executors"]:
        raise MethodError("test executor actor has no trusted public key")
    try:
        test_execution.validate_report(report)
    except ValueError as exc:
        raise MethodError(str(exc)) from exc
    if report["argv"] != item["data"]["argv"]:
        raise MethodError("test execution report argv differs from the current test declaration")
    return item


def test_execution_challenge(
    path: str | Path, id: str, report: dict[str, Any], actor: str,
) -> dict[str, Any]:
    state = _project(path)
    item = _test_execution_target(state, id, report, actor)
    return test_execution.challenge(state["project"], item, report, actor, path, state["head_hash"])


def record_test_execution(
    path: str | Path, id: str, report: dict[str, Any], actor: str, signature: str,
) -> dict[str, Any]:
    state = _project(path)
    item = _test_execution_target(state, id, report, actor)
    if not isinstance(signature, str) or not signature:
        raise MethodError("test execution requires an Ed25519 signature")
    key = state["test_executors"][actor]
    fingerprint = approval.key_fingerprint(key)
    if not test_execution.verify(
        state["project"], item, report, actor, signature, fingerprint,
        state["test_executors"], path, state["head_hash"],
    ):
        raise MethodError("test execution signature is invalid or stale for this case, test or report")
    payload = {
        "id": id, "version": item["version"], "report": report,
        "signature": signature, "key_sha256": fingerprint,
    }
    return append_event(path, "test_execution", payload, actor, expected_seq=state["revision"])


def _test_observation_target(
    state: dict[str, Any], id: str, receipt: dict[str, Any], actor: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if state["project"].get("test_gate_policy") != "signed_observed":
        raise MethodError("test observations require signed_observed test gate policy")
    item = state["items"].get(id)
    if item is None or item["kind"] != "test":
        raise MethodError("test observation requires a current test item")
    problems = test_execution.item_issues(item, observed=True)
    if problems:
        raise MethodError("; ".join(problems))
    report_record = state["test_executions"].get((id, item["version"]))
    if report_record is None:
        raise MethodError("test observation requires a current signed execution report")
    report = state["test_execution_reports"][(id, item["version"])]
    provenance = {"seq": report_record["seq"], "hash": report_record["hash"]}
    if (not isinstance(actor, str) or not actor.startswith("observer:") or actor != actor.strip()
            or actor == report_record["actor"]
            or actor in state["item_author_history"][id]):
        raise MethodError("test observer must be a distinct registered observer actor")
    if state["test_observation_trust"] != "configured" or actor not in state["test_observers"]:
        raise MethodError("test observer actor has no trusted public key")
    try:
        test_observation.validate_receipt(receipt, state["project"], item, report, provenance)
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise MethodError(f"test observation receipt is invalid or its bundle changed: {exc}") from exc
    return item, report, provenance


def test_observation_challenge(
    path: str | Path, id: str, receipt: dict[str, Any], actor: str,
) -> dict[str, Any]:
    state = _project(path)
    item, report, provenance = _test_observation_target(state, id, receipt, actor)
    return test_observation.challenge(
        state["project"], item, report, provenance, receipt, actor, path, state["head_hash"],
    )


def record_test_observation(
    path: str | Path, id: str, receipt: dict[str, Any], actor: str, signature: str,
) -> dict[str, Any]:
    state = _project(path)
    item, report, provenance = _test_observation_target(state, id, receipt, actor)
    if not isinstance(signature, str) or not signature:
        raise MethodError("test observation requires an Ed25519 signature")
    key = state["test_observers"][actor]
    fingerprint = approval.key_fingerprint(key)
    if not test_observation.verify(
        state["project"], item, report, provenance, receipt, actor, signature,
        fingerprint, state["test_observers"], path, state["head_hash"],
    ):
        raise MethodError("test observation signature is invalid or stale for this case, test or report")
    payload = {
        "id": id, "version": item["version"], "report_provenance": provenance,
        "receipt": receipt, "signature": signature, "key_sha256": fingerprint,
    }
    return append_event(path, "test_observation", payload, actor, expected_seq=state["revision"])


def _field_attestation_target(state: dict[str, Any], id: str, reason: str,
                              actor: str) -> tuple[dict[str, Any], dict[str, Any], bytes]:
    if state["project"]["approval_policy"] != "signed":
        raise MethodError("field attestation is available only for signed cases")
    item = state["items"].get(id)
    if item is None:
        raise MethodError("field attestation needs a current assessment")
    binding = _field_binding(state["items"], item)
    if (not isinstance(actor, str) or not actor.startswith("assessor:")
            or len(actor) <= len("assessor:") or actor == item["author"]):
        raise MethodError("field assessor must be distinct from the assessment author")
    if not isinstance(reason, str) or not reason.strip():
        raise MethodError("field attestation needs an explicit assessor reason")
    if state["field_attestation_trust"] != "configured":
        raise MethodError("field assessor trust registry is unavailable")
    assessors, _ = field_attestation.trust_context(state["project"], state["case_path"])
    key = assessors.get(actor)
    if key is None:
        raise MethodError("field assessor has no trusted public key")
    approvers, _ = approval.trust_context(state["project"], state["case_path"])
    if key in approvers.values():
        raise MethodError("field assessor key must differ from normative approver keys")
    problems = _success_claim_issues(
        state["items"], item, "signed", flags=_flags(state), skip_field_evidence_blocker=True,
    )
    if problems:
        raise MethodError("field assessment fails prior structural checks: " + "; ".join(problems))
    return item, binding, key


def field_attestation_challenge(
    path: str | Path, id: str, reason: str, actor: str,
    source_manifest_path: str, report_path: str,
) -> dict[str, Any]:
    """Return exact bytes for a separately trusted evaluator to sign offline."""
    state = _project(path)
    item, binding, _ = _field_attestation_target(state, id, reason, actor)
    materials = field_attestation.inspect_materials(
        state["project"], id, item["version"], item["data"]["verdict"],
        source_manifest_path, report_path,
    )
    return field_attestation.challenge(
        state["project"], path, binding, materials, actor, reason.strip(), state["head_hash"],
    )


def attest_field(
    path: str | Path, id: str, reason: str, actor: str,
    source_manifest_path: str, report_path: str, signature: str,
) -> dict[str, Any]:
    """Record an independently signed field assessment without copying source data."""
    if not isinstance(signature, str) or not signature:
        raise MethodError("field attestation requires an Ed25519 signature")
    state = _project(path)
    item, binding, key = _field_attestation_target(state, id, reason, actor)
    materials = field_attestation.inspect_materials(
        state["project"], id, item["version"], item["data"]["verdict"],
        source_manifest_path, report_path,
    )
    fingerprint = approval.key_fingerprint(key)
    if not field_attestation.verify(
        state["project"], path, binding, materials, actor, reason.strip(), state["head_hash"],
        signature, fingerprint, {actor: key},
    ):
        raise MethodError("field attestation signature is invalid for current case, evidence or assessor")
    payload = {
        "binding": binding, "materials": materials, "reason": reason.strip(),
        "signature": signature, "key_sha256": fingerprint,
    }
    return append_event(path, "field_attestation", payload, actor, expected_seq=state["revision"])


def challenge(path: str | Path, left: str, right: str, reason: str, actor: str) -> dict[str, Any]:
    state = _project(path)
    if left == right or left not in state["items"] or right not in state["items"]:
        raise MethodError("challenge requires two distinct existing items")
    if not isinstance(reason, str) or not reason.strip():
        raise MethodError("challenge requires a reason")
    return append_event(path, "challenge", {"left": left, "right": right, "reason": reason.strip()}, actor, expected_seq=state["revision"])


def resolve_challenge(path: str | Path, challenge_seq: int, resolution_item: str, actor: str) -> dict[str, Any]:
    state = _project(path)
    contested = state["challenges"].get(challenge_seq)
    if contested is None or challenge_seq in _active_resolutions(state):
        raise MethodError("unknown or already resolved challenge")
    item = state["items"].get(resolution_item)
    if item is None or item["kind"] not in {"synthesis", "assessment"} or item["seq"] <= challenge_seq:
        raise MethodError("resolution needs a later synthesis or assessment item")
    if not {contested["left"], contested["right"]}.issubset(_ancestors(state["items"], resolution_item)):
        raise MethodError("resolution must address both challenged items")
    review = state["item_reviews"].get((resolution_item, item["version"]))
    if review is None or review["verdict"] != "accept" or review["actor"] == item["author"]:
        raise MethodError("resolution needs an independent accepted item review")
    return append_event(path, "challenge_resolved", {
        "challenge_seq": challenge_seq, "resolution_item": resolution_item,
        "resolution_version": item["version"], "review_seq": review["seq"],
    }, actor, expected_seq=state["revision"])


def get_state(path: str | Path) -> dict[str, Any]:
    state = _project(path)
    flags = _flags(state)
    items = {item_id: {**item, **flags[item_id]} for item_id, item in state["items"].items()}
    phases = _phase_statuses(state)
    active_resolutions = _active_resolutions(state)
    open_challenges = [challenge for seq, challenge in state["challenges"].items() if seq not in active_resolutions]
    return {"project": state["project"], "project_sha256": approval.project_fingerprint(state["project"]),
            "revision": state["revision"], "approval_trust": state["approval_trust"],
            "phase_review_trust": state["phase_review_trust"],
            "test_execution_trust": state["test_execution_trust"],
            "test_execution_history": state["test_execution_history"],
            "test_observation_trust": state["test_observation_trust"],
            "test_observation_history": state["test_observation_history"],
            "phase_review_history": [
                {"seq": entry["seq"], "phase": entry["phase"],
                 "verdict": entry.get("verdict"), "actor": entry["actor"],
                 "snapshot": entry.get("snapshot"), "provenance": entry["provenance"],
                 "signature_verified": entry["signature_verified"],
                 "independent": entry["independent"]}
                for entry in state["phase_reviews"]
            ],
            "field_attestation_trust": state["field_attestation_trust"],
            "field_attestations": [
                {"seq": entry["seq"], "actor": entry["actor"],
                 "signature_verified": entry["verified"],
                 "baseline_volume_input_byte_bound": (
                     entry["verified"] is True
                     and isinstance(entry["materials"], dict)
                     and entry["materials"].get("baseline_volume_input_byte_bound") is True
                 ),
                 "binding_current": _field_statement_binding_current(state, entry),
                 "assessment_id": entry["binding"].get("assessment_id")
                 if isinstance(entry["binding"], dict) else None}
                for entry in state["field_attestations"]
            ],
            "indicator_retirement_history": sorted(
                (entry for flag in flags.values() for entry in flag["retirement_history"]),
                key=lambda entry: entry["seq"],
            ),
            "items": items, "phases": phases, "open_challenges": open_challenges}


def gate(path: str | Path, phase: str) -> dict[str, Any]:
    if phase not in PHASE_BY_ID:
        raise MethodError(f"unknown phase: {phase}")
    return _phase_statuses(_project(path))[phase]


def _matching_phase_review(state: dict[str, Any], payload: dict[str, Any], actor: str) -> dict[str, Any] | None:
    for review in reversed(state["phase_reviews"]):
        if review["phase"] == payload["phase"] and review["snapshot"] == payload["snapshot"]:
            if (review["actor"] == actor
                    and (state["project"]["approval_policy"] == "fixture" or review["signature_verified"])
                    and all(review.get(key) == value for key, value in payload.items())):
                return review["_event"]
            break
    return None


def _active_phase_advance(state: dict[str, Any], advance_seq: int) -> dict[str, Any]:
    return next(marker for marker in state["advances"] if marker["seq"] == advance_seq)


def _phase_review_target(
    state: dict[str, Any], phase: str, verdict: str, reason: str, actor: str,
) -> tuple[dict[str, Any], str]:
    if phase not in PHASE_BY_ID or verdict not in VERDICTS or not isinstance(reason, str) or not reason.strip():
        raise MethodError("phase review needs a known phase, accept/reject and reason")
    if not isinstance(actor, str) or not actor.strip():
        raise MethodError("phase review needs a nonempty actor")
    status = _phase_statuses(state)[phase]
    if verdict == "accept" and not status["ready"]:
        raise MethodError("phase cannot be accepted: " + "; ".join(status["blockers"]))
    normalized_actor = actor.strip()
    authors = _phase_authors(state, phase)
    if state["project"]["approval_policy"] == "fixture" and state["phase_review_trust"] != "fixture":
        raise MethodError("fixture phase reviews are disabled or conflict with a registered signed case")
    if state["project"]["approval_policy"] == "signed":
        if normalized_actor != actor:
            raise MethodError("signed phase reviewer actor must not contain surrounding whitespace")
        if state["phase_review_trust"] != "configured":
            raise MethodError("signed phase review requires a trusted reviewer registry")
        if normalized_actor not in state["phase_reviewers"]:
            raise MethodError("phase reviewer actor has no trusted public key")
        if verdict == "accept" and normalized_actor in authors:
            raise MethodError("accepted phase review must be independent of phase authors")
    return status, normalized_actor


def phase_review_challenge(
    path: str | Path, phase: str, verdict: str, reason: str, actor: str,
) -> dict[str, Any]:
    state = _project(path)
    if state["project"]["approval_policy"] != "signed":
        raise MethodError("fixture cases do not need signed phase review challenges")
    status, normalized_actor = _phase_review_target(state, phase, verdict, reason, actor)
    return review_provenance.challenge(
        state["project"], path, state["head_hash"], phase, status["snapshot"],
        verdict, reason.strip(), normalized_actor,
    )


def review_phase(
    path: str | Path, phase: str, verdict: str, reason: str, actor: str,
    signature: str | None = None,
) -> dict[str, Any]:
    state = _project(path)
    status, normalized_actor = _phase_review_target(state, phase, verdict, reason, actor)
    authors = _phase_authors(state, phase)
    payload = {"phase": phase, "verdict": verdict, "reason": reason.strip(), "snapshot": status["snapshot"], "independent": normalized_actor not in authors}
    if state["project"]["approval_policy"] == "fixture":
        if signature is not None:
            raise MethodError("fixture phase review must not have a signature")
    else:
        if not isinstance(signature, str) or not signature:
            raise MethodError("signed phase review requires an Ed25519 signature")
        key = state["phase_reviewers"][normalized_actor]
        fingerprint = approval.key_fingerprint(key)
        payload.update({"signature": signature, "key_sha256": fingerprint})
    if existing := _matching_phase_review(state, payload, normalized_actor):
        return existing
    if state["project"]["approval_policy"] == "signed" and not review_provenance.verify(
        state["project"], path, state["head_hash"], phase, status["snapshot"], verdict,
        reason.strip(), normalized_actor, signature, fingerprint, state["phase_reviewers"],
    ):
        raise MethodError("phase review signature is invalid or stale for this case, snapshot or actor")
    try:
        return append_event(path, "phase_review", payload, normalized_actor, expected_seq=state["revision"])
    except ConflictError:
        current = _project(path)
        current_status = _phase_statuses(current)[phase]
        if current_status["snapshot"] == status["snapshot"] and (verdict != "accept" or current_status["ready"]):
            if existing := _matching_phase_review(current, payload, normalized_actor):
                return existing
        raise


def advance(path: str | Path, phase: str, actor: str) -> dict[str, Any]:
    if not isinstance(actor, str) or not actor.strip():
        raise MethodError("phase advance needs a nonempty actor")
    normalized_actor = actor.strip()
    state = _project(path)
    if phase not in PHASE_BY_ID:
        raise MethodError(f"unknown phase: {phase}")
    status = _phase_statuses(state)[phase]
    if not status["ready"]:
        raise MethodError("phase cannot advance: " + "; ".join(status["blockers"]))
    reviews = [review for review in state["phase_reviews"] if review["phase"] == phase and review["snapshot"] == status["snapshot"]]
    if not reviews or not status["reviewed"]:
        raise MethodError("phase needs an accepted review of its current snapshot")
    if phase == "validate" and not reviews[-1]["independent"]:
        raise MethodError("validation needs an independent review of its current snapshot")
    if status["accepted"]:
        marker = _active_phase_advance(state, status["advance_seq"])
        if marker["actor"] != normalized_actor:
            raise MethodError("phase already advanced by another actor")
        return marker["_event"]
    payload = {"phase": phase, "snapshot": status["snapshot"], "review_seq": reviews[-1]["seq"]}
    try:
        return append_event(path, "phase_advance", payload, actor, expected_seq=state["revision"])
    except ConflictError:
        current = _project(path)
        current_status = _phase_statuses(current)[phase]
        if current_status["accepted"] and current_status["snapshot"] == status["snapshot"]:
            marker = _active_phase_advance(current, current_status["advance_seq"])
            if marker["actor"] == normalized_actor and all(marker[key] == value for key, value in payload.items()):
                return marker["_event"]
        raise


def trace(path: str | Path, id: str) -> dict[str, Any]:
    state = get_state(path)
    if id not in state["items"]:
        raise MethodError(f"unknown item: {id}")
    ancestors = _ancestors(state["items"], id)
    dependents = _dependents(state["items"], id)
    return {
        "item": state["items"][id],
        "ancestors": [state["items"][key] for key in sorted(ancestors - {id})],
        "dependents": [state["items"][key] for key in sorted(dependents - {id})],
    }
