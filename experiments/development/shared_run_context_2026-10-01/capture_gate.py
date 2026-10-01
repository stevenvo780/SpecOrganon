"""Capture one public, offline gate without logging process environment."""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
DOSSIER = Path(__file__).resolve().parent
SOURCES = (
    "scripts/managed_run_context.py",
    "scripts/run_managed_team.py",
    "scripts/run_managed_tool_conversation.py",
    "tests/test_managed_run_context.py",
    "tests/test_run_managed_team.py",
    "tests/test_run_managed_tool_conversation.py",
    "tests/test_managed_token_ledger.py",
    "tests/test_staged_tool_session.py",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("label")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9_]{1,64}", args.label) or not args.command:
        parser.error("bounded label and explicit public offline command required")
    command = args.command[1:] if args.command[0] == "--" else args.command
    if not command:
        parser.error("command is empty")
    target = DOSSIER / "gates" / args.label
    target.mkdir(parents=True, exist_ok=False)
    sources = target / "source"
    sources.mkdir()
    pins = []
    for name in SOURCES:
        raw = (REPO / name).read_bytes()
        copied = sources / name
        copied.parent.mkdir(parents=True, exist_ok=True)
        copied.write_bytes(raw)
        pins.append({"path": name, "bytes": len(raw),
                     "sha256": hashlib.sha256(raw).hexdigest()})
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    before = time.monotonic()
    with (target / "stdout").open("wb") as out, (target / "stderr").open("wb") as err:
        result = subprocess.run(command, cwd=REPO, stdout=out, stderr=err, check=False)
    unchanged = all(hashlib.sha256((REPO / pin["path"]).read_bytes()).hexdigest()
                    == pin["sha256"] for pin in pins)
    streams = []
    for name in ("stdout", "stderr"):
        raw = (target / name).read_bytes()
        streams.append({"path": str((target / name).relative_to(REPO)),
                        "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    metadata = {"schema": "specorganon.d111.offline_gate.v1",
                "classification": "public_synthetic_fixtures_fake_provider",
                "command": command, "cwd": str(REPO), "started_at_utc": started,
                "elapsed_seconds": time.monotonic() - before,
                "exit_code": result.returncode, "sources": pins,
                "source_bytes_unchanged_after": unchanged, "streams": streams,
                "real_provider_requests": 0, "real_reserved_inputs": 0}
    (target / "metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"label": args.label, "exit_code": result.returncode,
                      "source_bytes_unchanged_after": unchanged,
                      "elapsed_seconds": metadata["elapsed_seconds"]}, sort_keys=True))
    return result.returncode if unchanged else 2


if __name__ == "__main__":
    raise SystemExit(main())
