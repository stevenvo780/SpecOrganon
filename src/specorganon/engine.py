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
from pathlib import Path
from typing import Any

from . import approval
from .ledger import ZERO_HASH, ConflictError, LedgerError, append_event, init_project, read_project
from .workflow import KIND_TO_PHASE, KINDS, PHASES, PHASE_BY_ID


ITEM_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{1,63}$")
VERDICTS = {"accept", "reject"}
_PUT_MAX_RETRIES = 3


class MethodError(LedgerError):
    """An action violates a method invariant or a phase gate."""


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _project(path: str | Path) -> dict[str, Any]:
    ledger = read_project(path)
    project = dict(ledger["project"])
    project.setdefault("approval_policy", "signed")
    try:
        approvers, trust_status = approval.trust_context(project, path)
    except ValueError:
        approvers = {}
        trust_status = "unavailable"
    state: dict[str, Any] = {
        "project": project,
        "revision": len(ledger["events"]),
        "head_hash": ledger["events"][-1]["hash"] if ledger["events"] else ZERO_HASH,
        "items": {},
        "approvals": set(),
        "approval_statuses": {},
        "approval_trust": trust_status,
        "item_reviews": {},
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
            elif key not in state["approvals"]:
                state["approval_statuses"][key] = status
        elif kind == "item_review":
            state["item_reviews"][(payload["id"], payload["version"])] = {
                "seq": seq, "actor": event["actor"], **payload
            }
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
            state["phase_reviews"].append({"seq": seq, "actor": event["actor"], **payload})
        elif kind == "phase_advance":
            state["advances"].append({"seq": seq, "actor": event["actor"], **payload})
        else:
            raise MethodError(f"unknown event type at sequence {seq}: {kind}")
    return state


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
            groups.setdefault((str(data["metric_key"]), str(data["scope"]), str(data["unit"])), []).append(item)
    issues: dict[str, list[str]] = {}
    for group, members in groups.items():
        for i, left in enumerate(members):
            for right in members[i + 1 :]:
                try:
                    a, b = float(left["data"]["value"]), float(right["data"]["value"])
                    tolerance = max(float(left["data"].get("tolerance", 0)), float(right["data"].get("tolerance", 0)))
                except (TypeError, ValueError):
                    continue
                if math.isfinite(a) and math.isfinite(b) and abs(a - b) > tolerance:
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
        if data.get("origin") == "observed" and not data.get("method"):
            issues.append("observed evidence lacks collection method")
        calc = data.get("calculation")
        if calc is not None:
            try:
                if calc["operator"] != "product" or not isinstance(calc["operands"], list) or not calc["operands"]:
                    raise ValueError("unsupported calculation")
                expected = math.prod(float(value) for value in calc["operands"])
                reported = float(data["value"])
                tolerance = float(calc.get("tolerance", 0))
                if not all(math.isfinite(v) for v in (expected, reported, tolerance)) or tolerance < 0:
                    raise ValueError("non-finite calculation")
                if abs(expected - reported) > tolerance:
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


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _success_claim_issues(items: dict[str, dict], assessment: dict[str, Any]) -> list[str]:
    """Check that a fulfilled claim is at least numerically and procedurally auditable.

    This does not establish source authenticity or causal identification; an
    independent evaluator must still judge those.
    """
    if assessment["data"].get("verdict") != "cumplido":
        return []
    issues: list[str] = []
    ancestors = [items[key] for key in _ancestors(items, assessment["id"])]
    results = [item for item in ancestors if item["kind"] == "result"]
    baselines = [item for item in ancestors if item["kind"] == "baseline"]
    criteria = [item for item in ancestors if item["kind"] == "criterion"]
    if len(results) != 1 or len(baselines) != 1 or len(criteria) != 1:
        return [f"{assessment['id']} success needs exactly one linked result, baseline and criterion"]
    result, baseline, criterion = results[0], baselines[0], criteria[0]
    scope = assessment["data"].get("claim_scope")
    if result["data"].get("origin") != scope or baseline["data"].get("origin") != scope:
        issues.append(f"{assessment['id']} {scope} success cannot use another evidence origin")
    if result["seq"] <= criterion["seq"]:
        issues.append(f"{assessment['id']} success uses a criterion written after the result")
    threshold = criterion["data"].get("threshold")
    effect = result["data"].get("effect")
    if not isinstance(threshold, dict) or not isinstance(effect, dict):
        return issues + [f"{assessment['id']} success needs structured threshold and measured effect"]
    operator = threshold.get("operator")
    statistic = threshold.get("statistic")
    threshold_value = _numeric(threshold.get("value"))
    estimate = _numeric(effect.get("estimate"))
    interval = effect.get("interval")
    if operator not in {">=", "<="} or statistic not in {"estimate", "lower_ci", "upper_ci"} or threshold_value is None:
        issues.append(f"{assessment['id']} has an invalid preregistered threshold")
    if effect.get("metric") != criterion["data"].get("metric") or baseline["data"].get("metric") != effect.get("metric"):
        issues.append(f"{assessment['id']} metric differs between baseline, result and criterion")
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
            issues.append(f"{assessment['id']} field success lacks design, comparator or unit")
        sample_size = effect.get("sample_size")
        if not isinstance(sample_size, int) or isinstance(sample_size, bool) or sample_size < 1:
            issues.append(f"{assessment['id']} field success lacks a positive sample size")
    values = {"estimate": estimate, "lower_ci": low, "upper_ci": high}
    chosen = values.get(statistic)
    if threshold_value is not None and chosen is not None and operator in {">=", "<="}:
        passes = chosen >= threshold_value if operator == ">=" else chosen <= threshold_value
        if not passes:
            issues.append(f"{assessment['id']} measured {statistic} does not meet the prior threshold")
    return issues


def _flags(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
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
    return {
        item_id: {
            "stale": _stale(items, item_id),
            "contested": item_id in contested,
            "issues": _item_issues(item) + automatic.get(item_id, []) + review_issues.get(item_id, []),
            "approved": (item_id, item["version"]) in state["approvals"],
            "approval_status": state["approval_statuses"].get((item_id, item["version"]), "missing"),
        }
        for item_id, item in items.items()
    }


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


def _shares_normative_evidence_problem(items: dict[str, dict], flags: dict[str, dict], item_id: str) -> bool:
    item = items[item_id]
    metric = item["data"].get("metric") if item["kind"] == "indicator" else None
    unit = item["data"].get("unit") if item["kind"] == "indicator" else None
    return bool(_normative_problems(items, item_id) & _evidence_based_problems(items, flags, item_id, metric, unit))


def _phase_blockers(state: dict[str, Any], phase_id: str, previous_accepted: bool, flags: dict[str, dict]) -> list[str]:
    phase = PHASE_BY_ID[phase_id]
    items = state["items"]
    blockers: list[str] = []
    if not previous_accepted:
        blockers.append("previous phase is not currently accepted")
    in_phase = [item for item in items.values() if KIND_TO_PHASE[item["kind"]] == phase_id]
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
            if indicator["kind"] != "indicator":
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
                indicators = [items[ref] for ref in _ancestors(items, item["id"]) if items[ref]["kind"] == "indicator"]
                if not any(indicator["data"].get("metric") == item["data"].get("metric") for indicator in indicators):
                    blockers.append(f"{item['id']} needs a linked indicator with the same success metric")
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
                blockers.extend(_success_claim_issues(items, item))
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
        # Existing ledgers recorded this payload without an item_reviews key.
        if item_reviews:
            snapshot_data["item_reviews"] = item_reviews
        snapshot = _hash(snapshot_data)
        blockers = _phase_blockers(state, phase.id, previous_accepted, flags)
        reviews = [review for review in state["phase_reviews"] if review["phase"] == phase.id and review["snapshot"] == snapshot]
        review = reviews[-1] if reviews else None
        advances = [marker for marker in state["advances"] if marker["phase"] == phase.id and marker["snapshot"] == snapshot and review and review["verdict"] == "accept" and marker["review_seq"] == review["seq"] and marker["seq"] > review["seq"]]
        marker = advances[-1] if advances else None
        accepted = not blockers and marker is not None and (phase.id != "validate" or bool(review and review["independent"]))
        statuses[phase.id] = {
            "phase": phase.id,
            "front": phase.front,
            "ready": not blockers,
            "accepted": accepted,
            "reviewed": review is not None and review["verdict"] == "accept",
            "independent_review": bool(review and review["independent"]),
            "blockers": blockers,
            "snapshot": snapshot,
            "advance_seq": marker["seq"] if marker else None,
        }
        previous_accepted = accepted
        previous_marker = marker["seq"] if accepted else 0
    return statuses


def create_case(path: str | Path, title: str, domain: str, actor: str, approval_policy: str = "signed") -> dict[str, Any]:
    if "ORGANON_LEDGER_ANCHORS_FILE" in os.environ:
        raise MethodError("initialize a case before enabling ORGANON_LEDGER_ANCHORS_FILE; then register its sequence-zero head")
    init_project(path, title, domain, actor, approval_policy)
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
            "items": items, "phases": phases, "open_challenges": open_challenges}


def gate(path: str | Path, phase: str) -> dict[str, Any]:
    if phase not in PHASE_BY_ID:
        raise MethodError(f"unknown phase: {phase}")
    return _phase_statuses(_project(path))[phase]


def review_phase(path: str | Path, phase: str, verdict: str, reason: str, actor: str) -> dict[str, Any]:
    state = _project(path)
    if phase not in PHASE_BY_ID or verdict not in VERDICTS or not isinstance(reason, str) or not reason.strip():
        raise MethodError("phase review needs a known phase, accept/reject and reason")
    status = _phase_statuses(state)[phase]
    if verdict == "accept" and not status["ready"]:
        raise MethodError("phase cannot be accepted: " + "; ".join(status["blockers"]))
    authors = {item["author"] for item in state["items"].values() if KIND_TO_PHASE[item["kind"]] == phase}
    payload = {"phase": phase, "verdict": verdict, "reason": reason.strip(), "snapshot": status["snapshot"], "independent": actor not in authors}
    return append_event(path, "phase_review", payload, actor, expected_seq=state["revision"])


def advance(path: str | Path, phase: str, actor: str) -> dict[str, Any]:
    state = _project(path)
    if phase not in PHASE_BY_ID:
        raise MethodError(f"unknown phase: {phase}")
    status = _phase_statuses(state)[phase]
    if not status["ready"]:
        raise MethodError("phase cannot advance: " + "; ".join(status["blockers"]))
    reviews = [review for review in state["phase_reviews"] if review["phase"] == phase and review["snapshot"] == status["snapshot"]]
    if not reviews or reviews[-1]["verdict"] != "accept":
        raise MethodError("phase needs an accepted review of its current snapshot")
    if phase == "validate" and not reviews[-1]["independent"]:
        raise MethodError("validation needs an independent review of its current snapshot")
    return append_event(path, "phase_advance", {"phase": phase, "snapshot": status["snapshot"], "review_seq": reviews[-1]["seq"]}, actor, expected_seq=state["revision"])


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
