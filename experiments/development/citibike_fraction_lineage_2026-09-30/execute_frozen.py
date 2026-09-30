"""Run one frozen public D105 probe once and retain its exact input and streams."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


def pin(raw: bytes) -> dict:
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def verify(repo: Path, files: dict) -> None:
    for name, expected in files.items():
        path = repo / name
        if not path.is_file() or path.is_symlink() or pin(path.read_bytes()) != expected:
            raise ValueError(f"frozen input differs: {name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    parser.add_argument("env", choices=("311", "312"))
    parser.add_argument("--freeze", choices=("source_freeze.json", "source_freeze_amendment.json"),
                        default="source_freeze.json")
    args = parser.parse_args()
    repo = args.repo.resolve(strict=True)
    dossier = repo / "experiments/development/citibike_fraction_lineage_2026-09-30"
    freeze_raw = (dossier / args.freeze).read_bytes()
    frozen = json.loads(freeze_raw)
    runtime = Path(frozen["runtime"]).resolve(strict=True)
    if runtime.is_relative_to(repo):
        raise ValueError("runtime must be outside repository")
    verify(repo, frozen["files"])
    output = runtime / args.env
    marker = runtime / f"{args.env}.started.json"
    if output.exists() or marker.exists():
        raise ValueError("execution already started; do not rerun or overwrite")
    source = repo / frozen["probe"]
    raw = source.read_bytes()
    if pin(raw) != frozen["files"][frozen["probe"]]:
        raise ValueError("probe bytes changed after verification")
    snapshot = runtime / f"{args.env}.probe.py"
    with snapshot.open("xb") as stream:
        stream.write(raw)
    python = frozen["pythons"][args.env]
    code = (
        "import sys; raw=sys.stdin.buffer.read(); name=sys.argv[1]; "
        "sys.argv=sys.argv[1:]; "
        "exec(compile(raw,name,'exec'),"
        "{'__name__':'__main__','__file__':name,'__package__':None})"
    )
    argv = [python, "-I", "-c", code, str(snapshot), str(repo), str(output)]
    record = {
        "schema": 1, "env": args.env, "argv": argv,
        "freeze_pin": pin(freeze_raw), "executed_source_pin": pin(raw),
        "freeze_file": args.freeze,
        "execution_mode": "compile already verified probe bytes supplied through stdin",
        "git_head_before": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
        "started_at_utc": dt.datetime.now(dt.UTC).isoformat(),
        "timeout_seconds": 600, "no_automatic_retry": True,
        "auth_copied": False, "exit_code": None,
    }
    with marker.open("x") as stream:
        json.dump(record, stream, indent=2, sort_keys=True)
        stream.write("\n")
    env = {
        "PATH": str(Path(python).parent) + ":/usr/local/bin:/usr/bin:/bin",
        "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "TZ": "UTC",
        "TMPDIR": str(runtime), "PYTHONDONTWRITEBYTECODE": "1",
    }
    if "HOME" in os.environ:
        env["HOME"] = os.environ["HOME"]
    began = time.monotonic()
    try:
        with (runtime / f"{args.env}.stdout.log").open("xb") as stdout, \
                (runtime / f"{args.env}.stderr.log").open("xb") as stderr:
            result = subprocess.run(argv, input=raw, cwd=runtime, env=env,
                                    stdout=stdout, stderr=stderr, timeout=600, check=False)
        record["exit_code"] = result.returncode
        verify(repo, frozen["files"])
        record["frozen_inputs_unchanged_after"] = True
    except Exception as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        record["finished_at_utc"] = dt.datetime.now(dt.UTC).isoformat()
        record["wall_seconds"] = time.monotonic() - began
        for suffix in ("stdout.log", "stderr.log"):
            path = runtime / f"{args.env}.{suffix}"
            if path.exists():
                record[suffix] = pin(path.read_bytes())
        with (runtime / f"{args.env}.execution.json").open("x") as stream:
            json.dump(record, stream, indent=2, sort_keys=True)
            stream.write("\n")
    print(json.dumps({key: record.get(key) for key in
                      ("env", "exit_code", "wall_seconds", "error", "frozen_inputs_unchanged_after")}))
    return 0 if record["exit_code"] == 0 and "error" not in record else 2


if __name__ == "__main__":
    raise SystemExit(main())
