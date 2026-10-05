"""Actual Docker controls for the draft evaluator; contains no study solutions."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments.software_comparison_v1.reserved.evaluator import encoded, route_suite, tree_suite
from experiments.software_comparison_v1.reserved.docker_evaluator import ReservedDocker, audit_case


def controls():
    route = {c["id"]: c for c in route_suite()}
    tree = {c["id"]: c for c in tree_suite()}
    no_route = route["unreachable"]
    byte_cap = route["byte-cap"]
    probe = audit_case()

    def emit(value):
        return "import sys\nsys.stdout.write(" + repr((encoded(value) + b"\n").decode()) + ")\n"

    wrong_type = {"reachable": True, "cost": True, "path": ["A", "B"]}
    trace_output = emit(probe["expected"])
    isolation = """from pathlib import Path
import os
assert set(os.listdir('/input')) == {'delivery'}
assert not Path('/var/run/docker.sock').exists()
assert not Path('/home/codex/.codex').exists()
assert not Path('/home/stev/.gemini').exists()
assert not Path('/output').exists()
Path('/tmp/private-scratch').write_text('ok')
try:
    Path('/input/delivery/forbidden.py').write_text('bad')
except OSError as exc:
    assert exc.errno == 30
else:
    raise AssertionError('delivery writable')
"""
    error = "import sys\nsys.stderr.write('{\"error\":\"invalid_input\"}\\n')\nraise SystemExit(2)\n"
    return [
        ("correct-output", no_route, emit(no_route["expected"]), "pass"),
        ("boolean-is-not-cost", byte_cap, emit(wrong_type), "fail"),
        ("stdin-inclusive-cap", byte_cap,
         "import sys\nassert len(sys.stdin.buffer.read()) == 65536\n" + emit(byte_cap["expected"]), "pass"),
        ("error-contract", route["empty"], error, "pass"),
        ("extra-json", no_route, emit(no_route["expected"]) + "print('{}')\n", "fail"),
        ("debug-stderr", no_route, emit(no_route["expected"]) + "sys.stderr.write('debug\\n')\n", "fail"),
        ("subject-timeout", no_route, "import time\ntime.sleep(20)\n", "fail"),
        ("physical-isolation", no_route, isolation + emit(no_route["expected"]), "pass"),
        ("metadata-no-open", probe, "import os\nassert os.lstat('/fixture/root/probe.txt').st_size == 3\n" + trace_output, "pass"),
        ("content-open-absolute", probe, "with open('/fixture/root/probe.txt','rb') as f: f.read()\n" + trace_output, "fail"),
        ("content-open-relative", probe, "import os\nos.chdir('/fixture/root')\nwith open('probe.txt','rb') as f: f.read()\n" + trace_output, "fail"),
        ("content-open-symlink", probe, "with open('/fixture/root/link','rb') as f: f.read()\n" + trace_output, "fail"),
        ("readlink-absolute", probe, "import os\nos.readlink('/fixture/root/link')\n" + trace_output, "fail"),
        ("readlink-relative", probe, "import os\nos.chdir('/fixture/root')\nos.readlink('link')\n" + trace_output, "fail"),
        ("denied-directory", tree["unreadable-directory"],
         "import os\ntry: os.listdir('/fixture/root/denied')\nexcept PermissionError:\n    " + error.replace("\n", "\n    ").rstrip() + "\nelse: raise AssertionError('expected denied directory')\n", "pass"),
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--image", required=True)
    args = parser.parse_args()
    executor = ReservedDocker(args.run_root, args.image)
    results = []
    for name, case, source, expected in controls():
        record = executor.run(name, case, {case["task"] + ".py": source})
        actual = record["verdict"]["status"]
        results.append({"control": name, "expected": expected, "actual": actual, "record": record})
        print(json.dumps({"control": name, "expected": expected, "actual": actual}), flush=True)
        if actual != expected:
            raise RuntimeError("evaluator control did not meet expected verdict: " + name)
    # Reusing a closed receipt must not restart its terminated subject.
    name, case, source, _ = controls()[0]
    reused = executor.run(name, case, {case["task"] + ".py": source})
    if not reused["reused_closed_receipt"]:
        raise RuntimeError("closed subject invocation was repeated")
    report = {"schema": 1, "classification": "actual evaluator infrastructure/mutation controls, not study solutions",
              "controls": results, "closed_receipt_reused": True, "native_model_calls": 0,
              "nine_phase_delivery": False, "study_cells_generated": 0, "image": args.image}
    (args.run_root / "controls.json").write_bytes(encoded(report) + b"\n")
    print(json.dumps({"controls_passed": len(results), "native_model_calls": 0,
                      "study_cells_generated": 0, "closed_receipt_reused": True}))


if __name__ == "__main__":
    main()
