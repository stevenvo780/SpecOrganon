"""Execute one committed D108 probe once, preserving terminal failures.

Use only after root freeze, independent review and explicit launch instruction.
Usage: python execute_frozen.py REPO {311,312}
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import time

DOSSIER = "experiments/development/bread_energy_derivation_2026-09-30"
FREEZE = DOSSIER + "/source_freeze.json"
ENV_GIT = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def pin(raw):
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def regular(path):
    require(stat.S_ISREG(path.lstat().st_mode), "nonregular input: " + str(path))
    return path.read_bytes()


def git(repo, *args):
    return subprocess.check_output(["git", "--no-optional-locks", *args], cwd=repo, env=ENV_GIT)


def verify(repo, frozen):
    for name, row in frozen["files"].items():
        require(not Path(name).is_absolute() and ".." not in Path(name).parts, "noncanonical frozen path")
        path = repo / name
        require(path.resolve(strict=True).is_relative_to(repo), "frozen input escapes repository")
        expected = {k: row[k] for k in ("bytes", "sha256")}
        require(pin(regular(path)) == expected, "frozen input differs: " + name)
        require(pin(git(repo, "show", "HEAD:" + name)) == expected, "committed input differs or is missing: " + name)


def exclusive_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def execute(repo, label):
    repo = repo.resolve(strict=True)
    head = git(repo, "rev-parse", "HEAD").decode().strip()
    freeze_raw = git(repo, "show", "HEAD:" + FREEZE)
    require(regular(repo / FREEZE) == freeze_raw, "freeze working bytes differ from committed HEAD")
    frozen = json.loads(freeze_raw)
    verify(repo, frozen)
    own_name = str(Path(__file__).resolve(strict=True).relative_to(repo))
    require(own_name in frozen["files"] and pin(regular(Path(__file__))) ==
            {k: frozen["files"][own_name][k] for k in ("bytes", "sha256")}, "launcher source is not frozen")
    runtime = Path(frozen["runtime"])
    require(runtime.is_absolute(), "runtime must be absolute")
    require(not runtime.resolve().is_relative_to(repo), "runtime must be external")
    if not runtime.exists():
        runtime.mkdir(mode=0o700)
    require(runtime.is_dir() and not runtime.is_symlink(), "runtime must be a real directory")
    runtime = runtime.resolve(strict=True)
    output = runtime / label
    marker = runtime / (label + ".started.json")
    require(not output.exists() and not marker.exists(), "attempt already started; no retry or replacement")
    probe_name = frozen["probe"]
    require(probe_name in frozen["files"], "probe missing from frozen files")
    raw = regular(repo / probe_name)
    require(pin(raw) == {k: frozen["files"][probe_name][k] for k in ("bytes", "sha256")}, "probe source differs")
    snapshot = runtime / (label + ".probe.py")
    with snapshot.open("xb") as stream:
        stream.write(raw)
    python = frozen.get("pythons", {}).get(label, frozen["environments"][label]["python"])
    require(python == frozen["environments"][label]["python"], "launcher interpreter alias differs")
    bootstrap = (
        "import sys; raw=sys.stdin.buffer.read(); name=sys.argv[1]; sys.argv=sys.argv[1:]; "
        "exec(compile(raw,name,'exec'),{'__name__':'__main__','__file__':name,'__package__':None})"
    )
    argv = [python, "-I", "-B", "-c", bootstrap, str(snapshot), str(repo), str(output)]
    env = {"PATH": str(Path(python).parent) + ":/usr/bin:/bin", "LANG": "C.UTF-8", "TZ": "UTC", "PYTHONDONTWRITEBYTECODE": "1"}
    record = {"schema": 1, "study_id": "D108", "env": label, "argv": argv, "cwd": str(runtime),
              "environment_allowlist": env, "freeze_pin": pin(freeze_raw), "git_head_before": head,
              "executed_source_pin": pin(raw), "launcher_source_pin": pin(regular(Path(__file__))),
              "execution_mode": "compile verified committed probe bytes supplied through stdin",
              "started_at_utc": now(), "timeout_seconds": 600, "no_automatic_retry": True,
              "auth_copied": False, "home_inherited_or_remapped": False,
              "exit_code": None, "timed_out": False}
    exclusive_json(marker, record)
    began = time.monotonic()
    process = None
    try:
        with (runtime / (label + ".stdout.log")).open("xb") as stdout, \
                (runtime / (label + ".stderr.log")).open("xb") as stderr:
            process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
                                       cwd=runtime, env=env, start_new_session=True)
            try:
                process.communicate(input=raw, timeout=600)
            except subprocess.TimeoutExpired:
                record["timed_out"] = True
                record["error"] = "600 second terminal timeout; process group killed; no retry"
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.communicate()
            record["exit_code"] = process.returncode
        verify(repo, frozen)
        require(regular(repo / FREEZE) == freeze_raw and git(repo, "show", "HEAD:" + FREEZE) == freeze_raw,
                "freeze changed during execution")
        record["frozen_inputs_unchanged_after"] = True
        record["git_head_after"] = git(repo, "rev-parse", "HEAD").decode().strip()
    except Exception as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
        if process is not None and process.returncode is not None:
            record["exit_code"] = process.returncode
    finally:
        record["finished_at_utc"] = now()
        record["wall_seconds"] = time.monotonic() - began
        for suffix in ("stdout.log", "stderr.log"):
            path = runtime / (label + "." + suffix)
            if path.exists():
                record[suffix] = {"path": str(path), **pin(regular(path))}
        report_path = output / "report.json"
        record["probe_report_present"] = report_path.exists()
        record["probe_report_passed"] = False
        if record["probe_report_present"]:
            try:
                report_raw = regular(report_path)
                record["probe_report"] = {"path": str(report_path), **pin(report_raw)}
                report_value = json.loads(report_raw)
                record["probe_report_passed"] = isinstance(report_value, dict) and report_value.get("passed") is True
            except Exception as exc:
                record["report_error"] = f"{type(exc).__name__}: {exc}"
        if record["exit_code"] == 0 and not record["probe_report_passed"]:
            record.setdefault("error", "exit0 without a present, valid, passed probe report; terminal failure")
        exclusive_json(runtime / (label + ".execution.json"), record)
    print(json.dumps({key: record.get(key) for key in ("env", "exit_code", "timed_out", "wall_seconds", "error", "frozen_inputs_unchanged_after")}))
    return 0 if record["exit_code"] == 0 and "error" not in record else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    parser.add_argument("env", choices=("311", "312"))
    args = parser.parse_args()
    try:
        return execute(args.repo, args.env)
    except Exception as exc:
        print(json.dumps({"env": args.env, "prelaunch_error": f"{type(exc).__name__}: {exc}"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
