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
    "challenge": "challenge",
    "resolve_challenge": "resolve_challenge",
    "gate": "gate",
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


def _json_object(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(f"invalid JSON object: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise argparse.ArgumentTypeError("--data must be a JSON object")
    return value


def _json_roles(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(f"invalid --roles JSON object: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise argparse.ArgumentTypeError("--roles must be a JSON object")
    return value


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

    put = commands.add_parser("put", help="Add or revise a case item")
    put.add_argument("path")
    put.add_argument("id")
    put.add_argument("--kind", required=True)
    put.add_argument("--text", required=True)
    put.add_argument("--ref", action="append", dest="refs", default=[], help="Referenced item ID; repeatable")
    put.add_argument("--data", type=_json_object, default={}, help="JSON object with structured fields")
    put.add_argument("--actor", required=True)

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
            with args.pop("manifest").open(encoding="utf-8") as source:
                args["manifest"] = json.load(source)
        result = invoke(command, **args)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    except (ValueError, OSError, TypeError, json.JSONDecodeError) as exc:
        print(f"organon: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
