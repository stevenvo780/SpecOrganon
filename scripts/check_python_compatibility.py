"""Check one available Python using a fresh wheel and real CLI/MCP stdio.

Only package dependencies may be downloaded; Python downloads are disabled.
Every case, approval, and reviewer used by these checks is synthetic. Passing
does not establish native-agent review, model/API compatibility, or field impact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TESTS = (
    "test_local_workflow.py", "test_local_interfaces.py", "test_case_report.py",
    "test_ledger.py", "test_runner.py",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default=sys.executable,
                        help="Path or executable name of an already installed Python")
    parser.add_argument("--output", required=True, type=Path,
                        help="New directory outside the source tree for environments and evidence")
    parser.add_argument("--offline", action="store_true",
                        help="Use only dependencies already in the uv cache")
    args = parser.parse_args()
    interpreter = shutil.which(args.python)
    uv = shutil.which("uv")
    if interpreter is None or uv is None:
        parser.error("the requested Python and uv must already be installed; nothing was downloaded")
    # Anchor relative paths without resolving away a virtualenv symlink.
    interpreter = os.path.abspath(interpreter)
    uv = os.path.abspath(uv)
    output = args.output.resolve()
    if output.is_relative_to(ROOT):
        parser.error("--output must be outside the source tree")
    output.mkdir(parents=True, exist_ok=False)
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("ORGANON_")
           and key not in {"PYTHONPATH", "PYTHONHOME", "PYTHONUSERBASE", "VIRTUAL_ENV",
                           "PYTHONOPTIMIZE", "PYTEST_ADDOPTS", "PYTEST_PLUGINS"}}
    env.update({"PYTHONNOUSERSITE": "1", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                "UV_PYTHON_DOWNLOADS": "never", "UV_NO_CONFIG": "1"})
    if args.offline:
        env["UV_OFFLINE"] = "1"
    if "UV_CACHE_DIR" in env:
        env["UV_CACHE_DIR"] = str(Path(env["UV_CACHE_DIR"]).absolute())
    elif env.get("UV_OFFLINE", "").lower() not in {"1", "true", "yes", "on"}:
        env["UV_CACHE_DIR"] = str(output / "uv-cache")
    sources = [ROOT / "README.md", ROOT / "pyproject.toml", ROOT / "uv.lock", Path(__file__),
               ROOT / "scripts/clean_smoke.py", ROOT / "workflows/synthetic_full.json",
               ROOT / "tests/conftest.py", *(ROOT / "tests" / name for name in TESTS),
               *sorted((ROOT / "src/specorganon").glob("*.py"))]
    summary = {
        "schema": 1, "status": "running", "requested_python": interpreter,
        "source_sha256": {str(path.relative_to(ROOT)): sha256(path) for path in sources},
        "checks": [],
        "limits": ["Linux runtime observed only; no promise for all Python >=3.11",
                   "Synthetic cases and declared approvals/reviews; no native-agent review",
                   "No model/provider API calls, scientific efficacy, or field validation",
                   "Selected tests only; full repository suite is a separate check"],
    }

    def save() -> None:
        (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    def run(name: str, argv: list[str], *, cwd: Path = output, timeout: int = 180) -> str:
        print(name, flush=True)
        started = time.monotonic()
        timed_out = False
        try:
            result = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, timeout=timeout)
            stdout, stderr, code = result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired as exc:
            stdout, stderr, code = exc.stdout or b"", exc.stderr or b"", None
            timed_out = True
        (output / f"{name}.stdout").write_bytes(stdout)
        (output / f"{name}.stderr").write_bytes(stderr)
        summary["checks"].append({
            "name": name, "argv": argv, "cwd": str(cwd), "exit_code": code,
            "timed_out": timed_out, "timeout_seconds": timeout,
            "duration_seconds": round(time.monotonic() - started, 3),
            "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
            "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        })
        save()
        if timed_out or code != 0:
            raise RuntimeError(f"{name} failed; inspect {output / (name + '.stderr')}")
        return stdout.decode("utf-8")

    try:
        run("build", [uv, "build", "--wheel", "--python", interpreter,
                      "--out-dir", str(output / "dist"), str(ROOT)])
        wheels = list((output / "dist").glob("specorganon-*.whl"))
        if len(wheels) != 1:
            raise RuntimeError("expected exactly one freshly built wheel")
        wheel = wheels[0]
        summary["wheel_sha256"] = sha256(wheel)
        requirements = output / "requirements.txt"
        run("export", [uv, "export", "--locked", "--extra", "dev", "--no-emit-project",
                       "--format", "requirements.txt", "--output-file", str(requirements)], cwd=ROOT)
        venv = output / "venv"
        run("venv", [uv, "venv", "--no-project", "--python", interpreter, str(venv)])
        python = str(venv / "bin/python")
        run("dependencies", [uv, "pip", "install", "--python", python,
                             "--require-hashes", "-r", str(requirements)])
        run("install", [uv, "pip", "install", "--python", python, "--no-deps", str(wheel)])
        run("dependency-check", [uv, "pip", "check", "--python", python])
        run("installed-packages", [uv, "pip", "freeze", "--python", python])
        summary["runtime"] = json.loads(run("origin", [python, "-I", "-c", """
import json, platform, sys, sysconfig
from pathlib import Path
import specorganon
origin = Path(specorganon.__file__).resolve()
assert origin.is_relative_to(Path(sysconfig.get_paths()['purelib']).resolve())
assert origin.is_relative_to(Path(sys.prefix).resolve())
print(json.dumps({'python': sys.version, 'executable': sys.executable,
                  'platform': platform.platform(), 'module': str(origin)}))
"""]))
        summary["smoke"] = json.loads(run("clean-smoke", [python, str(ROOT / "scripts/clean_smoke.py"),
                                                        str(ROOT)], timeout=300))
        run("local-ledger-tests", [python, "-m", "pytest", "-q", "-ra",
                                  "-o", "cache_dir=" + str(output / "pytest-cache"),
                                  "--junitxml=" + str(output / "tests.xml"),
                                  *(str(ROOT / "tests" / name) for name in TESTS)], timeout=300)
        summary["status"] = "passed"
    except (OSError, RuntimeError, ValueError) as exc:
        summary["status"] = "failed"
        summary["error"] = str(exc)
        print(str(exc), file=sys.stderr)
    save()
    print(output / "summary.json")
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
