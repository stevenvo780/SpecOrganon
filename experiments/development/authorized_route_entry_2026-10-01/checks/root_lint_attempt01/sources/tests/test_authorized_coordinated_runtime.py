from __future__ import annotations

import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import authorized_coordinated_runtime as entry  # noqa: E402


class OperatorGates(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.parent = Path(self.temp.name)
        self.parent.chmod(0o700)
        self.declaration = self.parent / entry.DECLARATION_NAME
        self.binding = {"provider_route": entry.OPENAI_ROUTE, "ordinal": 1,
                        "controller_source_digests": {"script": "a" * 64},
                        "run_dir": str(self.parent / "run"), "plan_sha256": "b" * 64}

    def tearDown(self):
        self.temp.cleanup()

    def value(self):
        return {"schema": 1, "classification": entry.DECLARATION_CLASS, "decision": "approved",
                "valid_until_unix": int(time.time()) + 300, "binding": copy.deepcopy(self.binding)}

    def write(self, value=None):
        self.declaration.write_bytes(json.dumps(value or self.value()).encode())
        self.declaration.chmod(0o600)
        return self.declaration.read_bytes()

    def test_declaration_private_bounded_exact(self):
        raw = self.write()
        self.assertEqual(entry._declaration_bytes(self.declaration), raw)
        self.assertEqual(entry._validate_declaration(raw, self.binding)["decision"], "approved")
        self.declaration.chmod(0o644)
        with self.assertRaises(entry.AuthorizedRouteError):
            entry._declaration_bytes(self.declaration)

    def test_declaration_symlink_and_hardlink_rejected(self):
        actual = self.parent / "actual"
        actual.write_bytes(b"{}"); actual.chmod(0o600)
        self.declaration.symlink_to(actual)
        with self.assertRaises(entry.AuthorizedRouteError):
            entry._declaration_bytes(self.declaration)
        self.declaration.unlink()
        os.link(actual, self.declaration)
        with self.assertRaises(entry.AuthorizedRouteError):
            entry._declaration_bytes(self.declaration)

    def test_duplicate_keys_bool_expiry_and_wrong_schema_rejected(self):
        value = self.value()
        variants = [{**value, "schema": True}, {**value, "valid_until_unix": True},
                    {**value, "unexpected": 1}, {**value, "decision": "not_approved"},
                    {**value, "valid_until_unix": int(time.time()) - 1},
                    {**value, "valid_until_unix": int(time.time()) + 90000}]
        for candidate in variants:
            with self.subTest(candidate=candidate):
                with self.assertRaises(ValueError):
                    entry._validate_declaration(json.dumps(candidate).encode(), self.binding)
        with self.assertRaises(ValueError):
            entry._validate_declaration(b'{"schema":1,"schema":1}', self.binding)

    def test_boolean_binding_cannot_equal_integer(self):
        value = self.value(); value["binding"]["ordinal"] = True
        with self.assertRaises(entry.AuthorizedRouteError):
            entry._validate_declaration(json.dumps(value).encode(), self.binding)

    def test_missing_paid_flag_before_preflight_environment_or_transport(self):
        with patch.object(entry, "preflight") as preview, patch.object(entry, "OpenAIResponsesHTTP") as http:
            with patch.object(entry.os, "environ", {}):
                with self.assertRaises(entry.AuthorizedRouteError):
                    entry.execute_authorized_step(self.parent / "run", self.parent / "obs", self.declaration,
                                                  expected_checkpoint="a" * 64)
        preview.assert_not_called(); http.assert_not_called()

    def test_cross_route_rejected_before_declaration_environment_or_transport(self):
        binding = {**self.binding, "provider_route": {"provider": "fixture"}}
        with patch.object(entry, "preflight", return_value={"binding": binding}):
            with patch.object(entry, "_declaration_bytes") as declaration, patch.object(entry, "OpenAIResponsesHTTP") as http:
                with patch.object(entry.os, "environ", {}):
                    with self.assertRaises(entry.AuthorizedRouteError):
                        entry.execute_authorized_step(self.parent / "run", self.parent / "obs", self.declaration,
                                                      expected_checkpoint="a" * 64, allow_paid_request=True)
        declaration.assert_not_called(); http.assert_not_called()

    def test_pending_approval_rejected_before_transport(self):
        value = self.value(); value["decision"] = "not_approved"
        self.write(value)
        with patch.object(entry, "preflight", return_value={"binding": self.binding}), patch.object(entry, "OpenAIResponsesHTTP") as http:
            with self.assertRaises(entry.AuthorizedRouteError):
                entry.execute_authorized_step(self.parent / "run", self.parent / "obs", self.declaration,
                                              expected_checkpoint="a" * 64, allow_paid_request=True)
        http.assert_not_called()

    def test_paid_constructor_uses_fixed_origin_after_gates(self):
        raw = self.write()
        with patch.object(entry, "preflight", return_value={"binding": self.binding}):
            with patch.object(entry, "_declaration_guard", return_value=lambda: None):
                with patch.object(entry.os, "environ", {"OPENAI_API_KEY": "PUBLIC-TEST-ONLY"}):
                    with patch.object(entry, "OpenAIResponsesHTTP") as http, patch.object(entry, "_execute", return_value={"step_failed": False}) as execute:
                        result = entry.execute_authorized_step(self.parent / "run", self.parent / "obs", self.declaration,
                                                               expected_checkpoint="a" * 64, allow_paid_request=True)
        self.assertFalse(result["step_failed"])
        self.assertEqual(http.call_count, 4)
        self.assertTrue(all(call.kwargs["base_url"] == entry.OFFICIAL_ORIGIN for call in http.call_args_list))
        execute.assert_called_once()
        self.assertEqual(self.declaration.read_bytes(), raw)

    def test_fixture_rejects_openai_and_nonloopback(self):
        with patch.object(entry, "preflight", return_value={"binding": self.binding}), patch.object(entry, "OpenAIResponsesHTTP") as http:
            with self.assertRaises(entry.AuthorizedRouteError):
                entry.execute_fixture_step(self.parent / "run", self.parent / "obs", "http://127.0.0.1:1234/v1", expected_checkpoint="a" * 64)
        http.assert_not_called()
        for endpoint in ("https://api.openai.com/v1", "http://localhost:1234/v1", "http://127.0.0.1:1234/v1?x=1"):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                entry.execute_fixture_step(self.parent / "run", self.parent / "obs", endpoint, expected_checkpoint="a" * 64)


class TotalWait(unittest.TestCase):
    def test_payload_exact_and_timeout_bounded(self):
        class Transport:
            def count_input(self, payload, *, timeout_seconds):
                self.payload = payload
                self.timeout = timeout_seconds
                return 5
        transport = Transport(); calls = []
        proxy = entry.BoundedResponsesTransport(transport, lambda: calls.append(True), max_wait_seconds=0.5)
        payload = {"model": "fixture", "input": [{"role": "user", "content": "public"}]}
        self.assertEqual(proxy.count_input(payload, timeout_seconds=5), 5)
        self.assertEqual(transport.payload, payload)
        self.assertLessEqual(transport.timeout, 0.5)
        self.assertEqual(len(calls), 3)

    def test_timeout_discards_late_result(self):
        entered, release, done = threading.Event(), threading.Event(), threading.Event()
        class Transport:
            def send(self, _payload, *, timeout_seconds):
                entered.set(); release.wait(1); done.set()
                return {"late": True}
        proxy = entry.BoundedResponsesTransport(Transport(), lambda: None, max_wait_seconds=0.03)
        started = time.monotonic()
        with self.assertRaisesRegex(entry.AuthorizedRouteError, "local_wait_deadline"):
            proxy.send({"model": "fixture"}, timeout_seconds=1)
        self.assertLess(time.monotonic() - started, 0.5)
        self.assertTrue(entered.is_set())
        release.set(); self.assertTrue(done.wait(1))

    def test_transport_error_does_not_leak_exception_message(self):
        class Transport:
            def send(self, _payload, *, timeout_seconds):
                raise RuntimeError("PUBLIC-SYNTHETIC-SECRET-MARKER")
        proxy = entry.BoundedResponsesTransport(Transport(), lambda: None)
        with self.assertRaises(entry.AuthorizedRouteError) as caught:
            proxy.send({"model": "fixture"}, timeout_seconds=1)
        self.assertEqual(str(caught.exception), "provider_operation_failed")
        self.assertIsNone(caught.exception.__cause__)

    def test_guard_rejects_before_transport(self):
        transport = unittest.mock.Mock()
        def reject():
            raise entry.AuthorizedRouteError("gate")
        with self.assertRaises(entry.AuthorizedRouteError):
            entry.BoundedResponsesTransport(transport, reject).send({}, timeout_seconds=1)
        transport.send.assert_not_called()

    def test_slow_http_fragments_do_not_extend_local_wait(self):
        done = threading.Event()
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass
            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                body = b'{"id":"fixture","status":"incomplete"}'
                self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers()
                try:
                    for byte in body:
                        self.wfile.write(bytes([byte])); self.wfile.flush(); time.sleep(0.005)
                except OSError:
                    pass
                finally:
                    done.set()
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            http = entry.OpenAIResponsesHTTP("public-synthetic-no-credential", base_url=f"http://127.0.0.1:{server.server_port}/v1")
            proxy = entry.BoundedResponsesTransport(http, lambda: None, max_wait_seconds=0.05)
            started = time.monotonic()
            with self.assertRaisesRegex(entry.AuthorizedRouteError, "local_wait_deadline"):
                proxy.send({"model": "fixture"}, timeout_seconds=1)
            self.assertLess(time.monotonic() - started, 0.3)
            self.assertTrue(done.wait(2))
        finally:
            server.shutdown(); server.server_close(); thread.join(2)


if __name__ == "__main__":
    unittest.main()
