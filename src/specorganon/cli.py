"""Command-line interface and shared dispatch to the Organon engine."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


# The CLI names and MCP tool names map to one set of engine operations. Importing
# the engine at call time keeps --help available even in an incomplete checkout.
ENGINE_OPERATIONS = {
    "init": "create_case",
    "put": "put_item",
    "status": "get_state",
    "review": "review_item",
    "approve": "approve",
    "approval_challenge": "approval_challenge",
    "test_execution_challenge": "test_execution_challenge",
    "record_test_execution": "record_test_execution",
    "test_observation_challenge": "test_observation_challenge",
    "record_test_observation": "record_test_observation",
    "field_attestation_challenge": "field_attestation_challenge",
    "attest_field": "attest_field",
    "challenge": "challenge",
    "resolve_challenge": "resolve_challenge",
    "gate": "gate",
    "phase_review_challenge": "phase_review_challenge",
    "review_phase": "review_phase",
    "advance": "advance",
    "trace": "trace",
}
RUNNER_OPERATIONS = {"next_task": "next_task", "run": "run_manifest"}


def invoke(operation: str, **kwargs: Any) -> Any:
    """Call the same engine or runner operation for both public interfaces."""
    if operation in ENGINE_OPERATIONS:
        from specorganon import engine

        return getattr(engine, ENGINE_OPERATIONS[operation])(**kwargs)
    if operation in RUNNER_OPERATIONS:
        from specorganon import runner

        return getattr(runner, RUNNER_OPERATIONS[operation])(**kwargs)
    raise ValueError(f"unknown operation: {operation}")


def _strict_object(raw: str, name: str) -> dict[str, Any]:
    from specorganon.ledger import strict_json_loads

    try:
        value = strict_json_loads(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid {name} JSON object: {exc}") from exc
    if not isinstance(value, dict):
        raise argparse.ArgumentTypeError(f"{name} must be a JSON object")
    return value


def _json_object(raw: str) -> dict[str, Any]:
    return _strict_object(raw, "--data")


def _json_roles(raw: str) -> dict[str, Any]:
    return _strict_object(raw, "--roles")


def _json_expected_deps(raw: str) -> dict[str, Any]:
    return _strict_object(raw, "--expected-deps")


def _json_report(raw: str) -> dict[str, Any]:
    return _strict_object(raw, "--report")


def _json_receipt(raw: str) -> dict[str, Any]:
    return _strict_object(raw, "--receipt")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="organon",
        description="Evidence-linked case workflow. All results are JSON.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="Create a case")
    init.add_argument("path", help="Case directory")
    init.add_argument("--title", required=True)
    init.add_argument("--domain", required=True)
    init.add_argument("--actor", required=True)
    init.add_argument("--approval-policy", choices=("signed", "fixture"), default="signed",
                      help="signed for real cases; fixture for explicitly synthetic tests")
    init.add_argument("--test-gate-policy", choices=("signed_report", "signed_observed"),
                      default="signed_report", help="Require a signed report or a signed report plus observation")

    put = commands.add_parser("put", help="Add or revise a case item")
    put.add_argument("path")
    put.add_argument("id")
    put.add_argument("--kind", required=True)
    put.add_argument("--text", required=True)
    put.add_argument("--ref", action="append", dest="refs", default=[], help="Referenced item ID; repeatable")
    put.add_argument("--data", type=_json_object, default={}, help="JSON object with structured fields")
    put.add_argument("--actor", required=True)
    put.add_argument("--expected-version", type=int, help="Current item version; 0 requires an absent item")
    put.add_argument("--expected-deps", type=_json_expected_deps,
                     help="JSON object mapping every referenced item ID to its expected version")

    status = commands.add_parser("status", help="Read the current case state")
    status.add_argument("path")

    review = commands.add_parser("review", help="Review an item")
    review.add_argument("path")
    review.add_argument("id")
    review.add_argument("--verdict", required=True)
    review.add_argument("--reason", required=True)
    review.add_argument("--actor", required=True)

    approve = commands.add_parser("approve", help="Record human approval of an item")
    approve.add_argument("path")
    approve.add_argument("id")
    approve.add_argument("--reason", required=True)
    approve.add_argument("--actor", required=True)
    approve.add_argument("--signature", help="Base64 Ed25519 signature of approval-challenge message")

    approval_challenge = commands.add_parser("approval-challenge", help="Prepare exact bytes for offline human signing")
    approval_challenge.add_argument("path")
    approval_challenge.add_argument("id")
    approval_challenge.add_argument("--reason", required=True)
    approval_challenge.add_argument("--actor", required=True)

    test_execution_challenge = commands.add_parser(
        "test-execution-challenge", help="Prepare exact bytes for offline signing of an external test report"
    )
    test_execution_challenge.add_argument("path")
    test_execution_challenge.add_argument("id")
    test_execution_challenge.add_argument("--report", type=_json_report, required=True)
    test_execution_challenge.add_argument("--actor", required=True)

    record_test_execution = commands.add_parser(
        "record-test-execution", help="Record a signed external test execution report"
    )
    record_test_execution.add_argument("path")
    record_test_execution.add_argument("id")
    record_test_execution.add_argument("--report", type=_json_report, required=True)
    record_test_execution.add_argument("--actor", required=True)
    record_test_execution.add_argument("--signature", required=True)

    test_observation_challenge = commands.add_parser(
        "test-observation-challenge", help="Prepare exact bytes for offline signing of a test observation receipt"
    )
    test_observation_challenge.add_argument("path")
    test_observation_challenge.add_argument("id")
    test_observation_challenge.add_argument("--receipt", type=_json_receipt, required=True)
    test_observation_challenge.add_argument("--actor", required=True)

    record_test_observation = commands.add_parser(
        "record-test-observation", help="Record a signed observation of an external test execution"
    )
    record_test_observation.add_argument("path")
    record_test_observation.add_argument("id")
    record_test_observation.add_argument("--receipt", type=_json_receipt, required=True)
    record_test_observation.add_argument("--actor", required=True)
    record_test_observation.add_argument("--signature", required=True)

    field_attestation_challenge = commands.add_parser(
        "field-attestation-challenge", help="Prepare case and source hashes for an assessor signature"
    )
    field_attestation_challenge.add_argument("path")
    field_attestation_challenge.add_argument("id")
    field_attestation_challenge.add_argument("--reason", required=True)
    field_attestation_challenge.add_argument("--actor", required=True)
    field_attestation_challenge.add_argument("--source-manifest-path", required=True)
    field_attestation_challenge.add_argument("--report-path", required=True)

    attest_field = commands.add_parser("attest-field", help="Record a signed assessor statement; field verdict stays blocked")
    attest_field.add_argument("path")
    attest_field.add_argument("id")
    attest_field.add_argument("--reason", required=True)
    attest_field.add_argument("--actor", required=True)
    attest_field.add_argument("--source-manifest-path", required=True)
    attest_field.add_argument("--report-path", required=True)
    attest_field.add_argument("--signature", required=True)

    challenge = commands.add_parser("challenge", help="Record a contradiction between items")
    challenge.add_argument("path")
    challenge.add_argument("left")
    challenge.add_argument("right")
    challenge.add_argument("--reason", required=True)
    challenge.add_argument("--actor", required=True)

    resolve = commands.add_parser("resolve-challenge", help="Resolve a recorded contradiction")
    resolve.add_argument("path")
    resolve.add_argument("challenge_seq", type=int)
    resolve.add_argument("resolution_item")
    resolve.add_argument("--actor", required=True)

    gate = commands.add_parser("gate", help="Evaluate a phase gate without advancing")
    gate.add_argument("path")
    gate.add_argument("phase")

    review_phase = commands.add_parser("review-phase", help="Review a phase")
    review_phase.add_argument("path")
    review_phase.add_argument("phase")
    review_phase.add_argument("--verdict", required=True)
    review_phase.add_argument("--reason", required=True)
    review_phase.add_argument("--actor", required=True)
    review_phase.add_argument("--signature", help="Base64 Ed25519 signature of phase-review-challenge message")

    phase_review_challenge = commands.add_parser(
        "phase-review-challenge", help="Prepare exact phase snapshot bytes for offline reviewer signing"
    )
    phase_review_challenge.add_argument("path")
    phase_review_challenge.add_argument("phase")
    phase_review_challenge.add_argument("--verdict", required=True)
    phase_review_challenge.add_argument("--reason", required=True)
    phase_review_challenge.add_argument("--actor", required=True)

    advance = commands.add_parser("advance", help="Advance a phase after its gate passes")
    advance.add_argument("path")
    advance.add_argument("phase")
    advance.add_argument("--actor", required=True)

    trace = commands.add_parser("trace", help="Show an item's dependency trail")
    trace.add_argument("path")
    trace.add_argument("id")

    next_task = commands.add_parser("next-task", help="Get bounded instructions for the next phase task")
    next_task.add_argument("path")
    next_task.add_argument("--roles", type=_json_roles, help="JSON object mapping roles to actor labels")

    run = commands.add_parser("run", help="Apply a resumable workflow manifest until a gate needs a decision")
    run.add_argument("path")
    run.add_argument("--manifest", type=Path, required=True, help="Path to a schema 1 JSON manifest")
    run.add_argument("--actor", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = vars(parser.parse_args(argv))
    command = args.pop("command").replace("-", "_")
    try:
        if command == "run":
            from specorganon.ledger import strict_json_loads

            with args.pop("manifest").open(encoding="utf-8") as source:
                args["manifest"] = strict_json_loads(source.read())
        result = invoke(command, **args)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
    except (ValueError, OSError, TypeError, json.JSONDecodeError) as exc:
        print(f"organon: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
