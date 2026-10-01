"""Synthetic role responses around real D118 sources and D119 tools.

This fixture controls responses and declared usage. It measures local HTTP
intervals, never authenticates provider activity or evaluates scientific quality.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import coordinated_prototype_runtime as runtime  # noqa: E402
import coordinated_prototype_kernel as kernel  # noqa: E402


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def configuration():
    return {"schema": 1, "role_config": {
        role: {"max_output_tokens": 128, "max_model_turns": 1 if role == "reviewer" else 32}
        for role in runtime.ROLES}, "max_epochs": 8, "tool_wall_seconds": 5}


def bundle_configuration():
    value = json.loads((runtime.SPEC / "fixture_configuration.json").read_bytes())
    value["seed"] = 119
    value["per_run_limits"]["active_seconds"] = 600
    return value


def nodes():
    return [{"id": key, "kind": kind, "phase": phase, "depends_on": deps,
             "status": "pending", "claim": "Synthetic mechanics control; not evidence for the case: " + key}
            for key, kind, phase, deps in (
                ("P1", "problem", "philosophy", []), ("P2", "assumption", "philosophy", []),
                ("N", "normative", "philosophy", ["P1"]), ("E", "evidence", "science", ["P1"]),
                ("R", "requirement", "engineering", ["E", "N"]), ("V", "test_result", "validation", ["R"]))]


def pending_metrics(case_id):
    quantity = {"value": None, "unit": "not evaluated", "base": "original public case",
                "reason": "Synthetic runtime control; scientific calculation and independent review pending."}
    audit = ["Actual readonly script verifies every listed file size and digest. Passage interpretation remains unverified."]
    if case_id == "D-E":
        return {"intervals": {"count": 0, "continuity_checked": False,
                              "issues": ["Interval calculations deliberately pending in the synthetic runtime control."]},
                "appliances_weekly": quantity, "appliances_daily": {"2016-12-17": quantity},
                "additional_observation": "No scientific observation is claimed by this synthetic mechanism control.",
                "source_audit": audit}
    result = {section: {key: copy.deepcopy(quantity) for key in fields}
              for section, fields in runtime.delivery.QUANTITY_FIELDS.items()}
    result["milling"].update(mass_fractions={"pending": quantity}, economic_allocation={"pending": quantity},
                             original_electricity_base="Original base conversion remains pending.")
    result["baking_energy"]["conversion"] = "No evaluated conversion in this synthetic control."
    result["survey"].update(closed_mean_interval={key: quantity for key in ("lower", "upper", "denominator")},
        finite_upper_all={"finite": False, "reason": "Bound interpretation pending."},
        finite_upper_known={"finite": False, "reason": "Bound interpretation pending."},
        category_and_missing_rules="Category and missing-data interpretation pending independent calculation.")
    result["source_audit"] = audit
    return result


def analysis_source(case_id):
    # Output is finite public structure plus actual original byte inventory.
    # No participant writes, subprocesses or network calls are used.
    return ("import hashlib,json,sys\nfrom pathlib import Path\n"
            "p=Path(sys.argv[1]); c=json.loads((p/'case.json').read_bytes())\n"
            "observed=[]\nfor row in c['files']:\n"
            " raw=(p/row['path']).read_bytes()\n"
            " assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256']\n"
            " observed.append({'path':row['path'],'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})\n"
            "m=json.loads(" + repr(json.dumps(pending_metrics(case_id), sort_keys=True)) + ")\n"
            "m['observed_source_inventory']=observed\n"
            "m['classification']='synthetic_delivery_structure_not_scientific_results'\n"
            "print(json.dumps(m,sort_keys=True,allow_nan=False))\n")


def source_claims():
    return json.dumps({"schema": 1, "claims": [{"id": "pending-calculation", "claim": "Case calculations await independent execution.",
        "classification": "pending", "sources": [], "unit": "not evaluated", "base": "original public case",
        "formula": "", "inputs": [], "author": "synthetic fixture", "reason": "No scientific result claimed."}]})


REPORT = "# Synthetic runtime control\n\nOriginal sources and host controls are exercised. Quantities, source interpretation, intervention quality and causal effects remain pending. Normative approval requires the competent human.\n"


def method(request):
    return {"name": "development_method", "arguments": {"request": json.dumps(request)}}


def write(path, content):
    return method({"op": "write", "path": path, "offset": 0, "content": content})


class SyntheticRoles:
    """Fixture-side host inspection selects deterministic public responses."""
    def __init__(self, run):
        self.run = Path(run)
        self.plan = json.loads((self.run / "plan.json").read_bytes())
        self.binding = json.loads((self.run / "run.json").read_bytes())["broker_binding"]
        self.case_id = self.plan["descriptor"]["coordinates"]["case_id"]
        self.source = analysis_source(self.case_id)
        self.trace, self.payloads = [], {role: [] for role in runtime.ROLES}
        self.turns = dict.fromkeys(runtime.ROLES, 0)
        self._lock = threading.RLock()

    def _work(self, role):
        return self.run / "broker_stages" / role / "work"

    def _operation(self, role):
        from coordinated_prototype_broker import CoordinatedPrototypeBroker
        broker = CoordinatedPrototypeBroker(self.run, self.binding)
        if role == "reviewer":
            return "Public synthetic review: structure exercised, no independent quality or normative verdict."
        work = self._work(role)
        if role == "leader":
            if not (work / "method_state.json").exists():
                if self.turns[role] == 1:
                    return method({"op": "read", "path": "task.md", "offset": 0, "length": 8192})
                return method({"op": "init", "nodes": nodes()})
            state = json.loads((work / "method_state.json").read_bytes())
            if kernel.select_work(state):
                return json.dumps({"action": "delegate", "public_text": "Delegate the next original-mode ready nodes; all conclusions synthetic."})
            for path, content in (("analysis.py", self.source), ("report.md", REPORT),
                                  *(([("sources.json", source_claims())]) if self.case_id == "D-F" else [])):
                if not (work / path).exists():
                    return write(path, content)
            if broker.current_metrics("leader") is None:
                return {"name": "development_analysis", "arguments": {"script_sha256": sha(self.source.encode())}}
            return json.dumps({"action": "deliver", "public_text": "Deliver synthetic structural artifacts with current final host metrics; science and normative acceptance pending."})
        branch = broker.branch(role)
        state = json.loads((work / "method_state.json").read_bytes())
        for key in branch["owned_node_ids"]:
            node = state["nodes"][key]
            if node["status"] != "supported":
                return method({"op": "revise", "id": key, "status": "supported",
                               "reason": "Synthetic control of native revision, not empirical support for the public case."})
            if node["stale"]:
                return method({"op": "review", "id": key})
        owned = [("analysis.py", self.source)] if role == "worker-1" else [("report.md", REPORT)]
        if role == "worker-2" and self.case_id == "D-F":
            owned.append(("sources.json", source_claims()))
        for path, content in owned:
            if not (work / path).exists():
                return write(path, content)
        if role == "worker-1" and broker.current_metrics(role) is None:
            return {"name": "development_analysis", "arguments": {"script_sha256": sha(self.source.encode())}}
        return "Public synthetic worker artifact; graph work is mechanical and norms remain pending."

    def count(self, role, payload):
        with self._lock:
            self.trace.append({"operation": "count", "role": role, "request": copy.deepcopy(payload), "declared_input_tokens": 5})
        return 5

    def send(self, role, payload):
        started = time.monotonic_ns()
        with self._lock:
            self.turns[role] += 1
            turn = self.turns[role]
            self.payloads[role].append(copy.deepcopy(payload))
        operation = self._operation(role)
        time.sleep(0.04)
        output = [{"type": "reasoning", "encrypted_content": f"SYNTHETIC-PRIVATE:{role}:{turn}", "summary": []}]
        if isinstance(operation, str):
            output.append({"type": "message", "role": "assistant", "status": "completed",
                           "content": [{"type": "output_text", "text": operation}]})
        else:
            output.append({"type": "function_call", "status": "completed", "name": operation["name"],
                           "call_id": f"call-{role}-{turn}", "arguments": json.dumps(operation["arguments"])})
        response = {"id": f"fixture-{role}-{turn}", "model": self.plan["model"], "service_tier": "default",
                    "status": "completed", "output": output,
                    "usage": {"input_tokens": 5, "output_tokens": 2, "total_tokens": 7}}
        with self._lock:
            self.trace.append({"operation": "send", "role": role, "turn": turn, "request": copy.deepcopy(payload),
                               "response": response, "started_ns": started, "ended_ns": time.monotonic_ns()})
        return response

    def transports(self):
        fixture = self
        class Transport:
            def __init__(self, role):
                self.role = role
            def count_input(self, payload, *, timeout_seconds):
                assert timeout_seconds > 0
                return fixture.count(self.role, payload)
            def send(self, payload, *, timeout_seconds):
                assert timeout_seconds > 0
                return fixture.send(self.role, payload)
        return {role: Transport(role) for role in runtime.ROLES}

    @contextmanager
    def http_server(self):
        fixture = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass
            def do_POST(self):
                try:
                    size = int(self.headers["Content-Length"])
                    if not 0 < size <= 4 * 1024 * 1024:
                        raise ValueError("fixture payload bound exceeded")
                    payload = json.loads(self.rfile.read(size))
                    # Initial user JSON publicly identifies the actual role.
                    selected = []
                    for row in payload.get("input", []):
                        if row.get("role") != "user" or not isinstance(row.get("content"), str):
                            continue
                        try:
                            content = json.loads(row["content"])
                        except ValueError:
                            continue
                        if isinstance(content, dict):
                            role = content.get("task_id", content.get("role", content.get("assignment", {}).get("task_id")))
                            if role in runtime.ROLES:
                                selected.append(role)
                    if not selected or len(set(selected)) != 1:
                        raise ValueError("fixture needs one explicit public role identity")
                    role = selected[0]
                    if self.path == "/v1/responses/input_tokens":
                        response = {"object": "response.input_tokens", "input_tokens": fixture.count(role, payload)}
                    elif self.path == "/v1/responses":
                        response = fixture.send(role, payload)
                    else:
                        raise ValueError("unexpected fixture endpoint")
                    raw = json.dumps(response, allow_nan=False).encode()
                    self.send_response(200)
                except Exception as exc:
                    raw = json.dumps({"synthetic_fixture_error": f"{type(exc).__name__}: {exc}"}).encode()
                    self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}/v1"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(5)
