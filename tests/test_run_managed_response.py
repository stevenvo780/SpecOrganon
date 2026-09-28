"""Offline tests for the concrete count/reserve/send Responses path."""

from __future__ import annotations

import hashlib
import http.server
import json
import stat
import sys
import threading
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from managed_token_ledger import BudgetError, TokenLedger  # noqa: E402
from run_managed_response import (  # noqa: E402
    DispatchError,
    OpenAIResponsesHTTP,
    dispatch_response,
    main,
)


REQUEST = {"model": "gpt-6-luna", "input": "A short public question.",
           "reasoning": {"effort": "low"}, "max_output_tokens": 10}


class FakeTransport:
    def __init__(self, input_tokens: int = 8, output_tokens: int = 4) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.counts: list[dict] = []
        self.sends: list[dict] = []
        self.response: dict | None = None
        self.send_error: Exception | None = None

    def count_input(self, payload: dict) -> int:
        self.counts.append(payload)
        return self.input_tokens

    def send(self, payload: dict) -> dict:
        self.sends.append(payload)
        if self.send_error is not None:
            raise self.send_error
        return self.response or {
            "id": "resp_local_1", "model": "gpt-6-luna", "status": "completed",
            "usage": {"input_tokens": self.input_tokens,
                      "output_tokens": self.output_tokens,
                      "total_tokens": self.input_tokens + self.output_tokens},
            "output": [],
        }


def _ledger(tmp_path: Path, limit: int = 30) -> TokenLedger:
    return TokenLedger.create(tmp_path / "ledger", limit, 8)


def _output_dir(tmp_path: Path) -> Path:
    path = tmp_path / "responses"
    path.mkdir(mode=0o700)
    return path


def test_count_reserve_send_and_persist_response(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    output = _output_dir(tmp_path) / "one.json"
    transport = FakeTransport()
    receipt = dispatch_response(ledger, request_id="one", role="leader",
                                request=REQUEST, response_path=output,
                                transport=transport)
    assert transport.counts == [{"model": "gpt-6-luna", "input": REQUEST["input"],
                                 "reasoning": REQUEST["reasoning"]}]
    assert transport.sends == [{**REQUEST, "store": False, "stream": False}]
    assert receipt["usage"]["total_tokens"] == 12
    assert receipt["response_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert receipt["criterion_4"] == "not_assessed"


def test_provider_usage_details_are_preserved_without_double_counting(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    output = _output_dir(tmp_path) / "one.json"
    transport = FakeTransport()
    transport.response = {
        "id": "resp_local_1", "model": "gpt-6-luna", "status": "completed",
        "usage": {"input_tokens": 8, "output_tokens": 4, "total_tokens": 12,
                  "input_tokens_details": {"cached_tokens": 3},
                  "output_tokens_details": {"reasoning_tokens": 2}},
        "output": [],
    }
    receipt = dispatch_response(ledger, request_id="one", role="leader",
                                request=REQUEST, response_path=output,
                                transport=transport)
    assert receipt["budget"]["held_tokens"] == 12
    assert json.loads(output.read_text())["usage"]["output_tokens_details"] == {
        "reasoning_tokens": 2}


def test_over_budget_rejects_before_send(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path, limit=17)
    output = _output_dir(tmp_path) / "one.json"
    transport = FakeTransport()
    with pytest.raises(BudgetError):
        dispatch_response(ledger, request_id="one", role="leader", request=REQUEST,
                          response_path=output, transport=transport)
    assert len(transport.counts) == 1
    assert transport.sends == []
    assert not output.exists()


def test_unsupported_tool_route_rejects_before_count(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    output = _output_dir(tmp_path) / "one.json"
    transport = FakeTransport()
    with pytest.raises(DispatchError, match="unsupported"):
        dispatch_response(ledger, request_id="one", role="leader",
                          request={**REQUEST, "tools": [{"type": "web_search"}]},
                          response_path=output, transport=transport)
    assert transport.counts == transport.sends == []


def test_multimodal_message_is_rejected_before_count(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    output = _output_dir(tmp_path) / "one.json"
    transport = FakeTransport()
    with pytest.raises(DispatchError, match="only text"):
        dispatch_response(ledger, request_id="one", role="leader",
                          request={**REQUEST, "input": [{"role": "user", "content": [
                              {"type": "input_image", "image_url": "https://example.com/a.png"}
                          ]}]}, response_path=output, transport=transport)
    assert transport.counts == transport.sends == []


def test_count_transport_cannot_change_payload_before_reservation(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    output = _output_dir(tmp_path) / "one.json"

    class MutatingTransport(FakeTransport):
        def count_input(self, payload: dict) -> int:
            payload["input"] = "different text"
            return 8

    transport = MutatingTransport()
    with pytest.raises(DispatchError, match="changed during token counting"):
        dispatch_response(ledger, request_id="one", role="leader", request=REQUEST,
                          response_path=output, transport=transport)
    assert transport.sends == []
    assert dispatch_response(ledger, request_id="one", role="leader", request=REQUEST,
                             response_path=output,
                             transport=FakeTransport())["usage"]["total_tokens"] == 12


def test_transport_failure_holds_reservation_without_retry(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    output = _output_dir(tmp_path) / "one.json"
    transport = FakeTransport()
    transport.send_error = TimeoutError("timeout")
    with pytest.raises(DispatchError, match="reservation held"):
        dispatch_response(ledger, request_id="one", role="leader", request=REQUEST,
                          response_path=output, transport=transport)
    assert len(transport.sends) == 1
    with pytest.raises(BudgetError):
        dispatch_response(ledger, request_id="one", role="leader", request=REQUEST,
                          response_path=output, transport=FakeTransport())
    assert not output.exists()


def test_bad_usage_preserves_response_and_blocks_next_request(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    output = _output_dir(tmp_path) / "one.json"
    transport = FakeTransport()
    transport.response = {"id": "resp_local_1", "model": "gpt-6-luna",
                          "status": "completed", "usage": None, "output": []}
    with pytest.raises(DispatchError, match="reservation held"):
        dispatch_response(ledger, request_id="one", role="leader", request=REQUEST,
                          response_path=output, transport=transport)
    assert output.exists()
    with pytest.raises(BudgetError):
        dispatch_response(ledger, request_id="two", role="reviewer", request=REQUEST,
                          response_path=output.parent / "two.json", transport=FakeTransport())


def test_reported_model_mismatch_is_indeterminate(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    output = _output_dir(tmp_path) / "one.json"
    transport = FakeTransport()
    transport.response = {"id": "resp_local_1", "model": "different-model",
                          "status": "completed", "usage": {"input_tokens": 8,
                          "output_tokens": 4, "total_tokens": 12}, "output": []}
    with pytest.raises(DispatchError, match="reservation held"):
        dispatch_response(ledger, request_id="one", role="leader", request=REQUEST,
                          response_path=output, transport=transport)
    assert json.loads(output.read_text())["model"] == "different-model"
    with pytest.raises(BudgetError):
        dispatch_response(ledger, request_id="two", role="reviewer", request=REQUEST,
                          response_path=output.parent / "two.json", transport=FakeTransport())


def test_incomplete_response_is_metered_but_run_policy_remains_external(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path, limit=50)
    output_dir = _output_dir(tmp_path)
    transport = FakeTransport(input_tokens=8, output_tokens=10)
    transport.response = {"id": "resp_local_1", "model": "gpt-6-luna",
                          "status": "incomplete", "usage": {"input_tokens": 8,
                          "output_tokens": 10, "total_tokens": 18}, "output": []}
    first = dispatch_response(ledger, request_id="one", role="leader",
                              request=REQUEST, response_path=output_dir / "one.json",
                              transport=transport)
    assert first["provider_status"] == "incomplete"
    assert first["budget"]["held_tokens"] == 18
    second = dispatch_response(ledger, request_id="two", role="leader",
                               request=REQUEST, response_path=output_dir / "two.json",
                               transport=FakeTransport())
    assert second["budget"]["held_tokens"] == 12


def test_cli_init_is_offline_and_send_requires_explicit_flag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ledger_dir = tmp_path / "ledger"
    assert main(["init", str(ledger_dir), "--limit-tokens", "30",
                 "--max-requests", "2"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["provider_calls"] == 0
    assert main(["send", str(ledger_dir), str(tmp_path / "missing.json"),
                 str(tmp_path / "out.json"), "--request-id", "one",
                 "--role", "leader"]) == 2
    assert "--allow-paid-request" in capsys.readouterr().err


def test_http_transport_uses_count_then_response_endpoint(tmp_path: Path) -> None:
    calls: list[tuple[str, dict]] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers["Content-Length"])
            payload = json.loads(self.rfile.read(length))
            calls.append((self.path, payload))
            assert self.headers["Authorization"] == "Bearer test-only-key"
            if self.path.endswith("/input_tokens"):
                response = {"object": "response.input_tokens", "input_tokens": 8}
            else:
                response = {"id": "resp_local_2", "model": "gpt-6-luna",
                            "status": "completed",
                            "usage": {"input_tokens": 8, "output_tokens": 4,
                                      "total_tokens": 12}, "output": []}
            raw = json.dumps(response).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *args: object) -> None:
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        transport = OpenAIResponsesHTTP(
            "test-only-key", base_url=f"http://127.0.0.1:{server.server_port}/v1")
        output = _output_dir(tmp_path) / "one.json"
        receipt = dispatch_response(_ledger(tmp_path), request_id="one", role="leader",
                                    request=REQUEST, response_path=output,
                                    transport=transport)
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()
    assert receipt["usage"]["total_tokens"] == 12
    assert [path for path, _ in calls] == ["/v1/responses/input_tokens", "/v1/responses"]


def test_http_transport_rejects_redirect_without_forwarding_key() -> None:
    leaked_headers: list[str | None] = []

    class Target(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            leaked_headers.append(self.headers.get("Authorization"))
            self.send_response(200)
            self.end_headers()

        def do_POST(self) -> None:
            self.do_GET()

        def log_message(self, *args: object) -> None:
            pass

    target = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Target)

    class Redirect(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{target.server_port}/leak")
            self.end_headers()

        def log_message(self, *args: object) -> None:
            pass

    source = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Redirect)
    workers = [threading.Thread(target=server.serve_forever, daemon=True)
               for server in (source, target)]
    for worker in workers:
        worker.start()
    try:
        transport = OpenAIResponsesHTTP(
            "test-only-key", base_url=f"http://127.0.0.1:{source.server_port}/v1")
        with pytest.raises(DispatchError, match="provider HTTP 302"):
            transport.count_input({"model": "gpt-6-luna", "input": "public"})
    finally:
        for server in (source, target):
            server.shutdown()
            server.server_close()
        for worker in workers:
            worker.join(timeout=3)
    assert leaked_headers == []
