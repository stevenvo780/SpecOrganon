"""Stdlib-only controls; no installed CLI, MCP server, or historical artifacts."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import traceback
import unittest
from pathlib import Path
from unittest.mock import patch

from subprocess_diagnostics import _OUTPUT_LIMIT, captured_subprocess_diagnostics


class CapturedSubprocessTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="captured-subprocess-test-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.script = self.directory / "child.py"

    def child(self, source: str):
        self.script.write_text(source, encoding="utf-8")
        return [sys.executable, str(self.script)]

    def annotated(self, original):
        try:
            with captured_subprocess_diagnostics():
                raise original
        except type(original) as error:
            self.assertIs(error, original)
            return error.__notes__[-1]
        self.fail("original exception was swallowed")

    def test_baseline_loses_output_but_annotation_keeps_real_child_failure(self):
        argv = self.child(
            "import sys\n"
            "print('probe reached checkpoint')\n"
            "print('RuntimeError: synthetic startup failed', file=sys.stderr)\n"
            "sys.exit(7)\n"
        )
        options = dict(cwd=self.directory, text=True, capture_output=True,
                       check=True, timeout=5)
        with self.assertRaises(subprocess.CalledProcessError) as baseline:
            subprocess.run(argv, **options)
        before = "".join(traceback.format_exception(baseline.exception))
        self.assertNotIn("probe reached checkpoint", before)
        self.assertNotIn("RuntimeError: synthetic startup failed", before)

        run = subprocess.run
        with patch("subprocess.run", wraps=run) as observed:
            with self.assertRaises(subprocess.CalledProcessError) as raised:
                with captured_subprocess_diagnostics():
                    subprocess.run(argv, **options)
        observed.assert_called_once_with(argv, **options)
        error = raised.exception
        self.assertIs(type(error), subprocess.CalledProcessError)
        self.assertEqual(error.cmd, baseline.exception.cmd)
        self.assertEqual(error.returncode, 7)
        self.assertEqual(error.stdout, baseline.exception.stdout)
        self.assertEqual(error.stderr, baseline.exception.stderr)
        after = "".join(traceback.format_exception(error))
        self.assertIn("returncode=7", after)
        self.assertIn("stdout='probe reached checkpoint\\n'", after)
        self.assertIn("stderr='RuntimeError: synthetic startup failed\\n'", after)

    def test_real_success_returns_identical_result_without_diagnostic_work(self):
        argv = self.child("import sys\nprint('receipt')\nprint('notice', file=sys.stderr)\n")
        options = dict(text=True, capture_output=True, check=True, timeout=5)
        expected = subprocess.run(argv, **options)
        with patch("subprocess_diagnostics._output_note") as render:
            with captured_subprocess_diagnostics():
                result = subprocess.run(argv, **options)
        self.assertEqual(vars(result), vars(expected))
        render.assert_not_called()

    def test_success_object_is_not_replaced_and_options_are_not_changed(self):
        result = subprocess.CompletedProcess(["child"], 0, "out", "err")
        options = dict(cwd=self.directory, env={"EXAMPLE": "private-value"},
                       text=True, capture_output=True, check=True, timeout=90)
        with patch("subprocess.run", return_value=result) as run:
            with captured_subprocess_diagnostics():
                actual = subprocess.run(["child"], **options)
        run.assert_called_once_with(["child"], **options)
        self.assertIs(actual, result)

    def test_nonzero_check_false_result_is_not_changed(self):
        argv = self.child("raise SystemExit(9)\n")
        with captured_subprocess_diagnostics():
            result = subprocess.run(argv, capture_output=True, timeout=5, check=False)
        self.assertEqual(result.returncode, 9)

    def test_real_timeout_retains_partial_bytes_and_deadline_without_retry(self):
        argv = self.child(
            "import sys, time\n"
            "print('partial receipt', flush=True)\n"
            "print('waiting for startup', file=sys.stderr, flush=True)\n"
            "time.sleep(30)\n"
        )
        run = subprocess.run
        with patch("subprocess.run", wraps=run) as observed:
            with self.assertRaises(subprocess.TimeoutExpired) as raised:
                with captured_subprocess_diagnostics():
                    subprocess.run(argv, text=True, capture_output=True,
                                   check=True, timeout=0.5)
        self.assertEqual(observed.call_count, 1)
        error = raised.exception
        self.assertIs(type(error), subprocess.TimeoutExpired)
        self.assertEqual(error.timeout, 0.5)
        self.assertEqual(error.cmd, argv)
        self.assertEqual(error.stdout, b"partial receipt\n")
        self.assertEqual(error.stderr, b"waiting for startup\n")
        note = error.__notes__[0]
        self.assertIn("TimeoutExpired; timeout=0.5", note)
        self.assertIn("partial receipt", note)
        self.assertIn("waiting for startup", note)

    def test_original_identity_attributes_notes_and_traceback_survive(self):
        original = subprocess.CalledProcessError(-15, ["hidden-argument"], "out", "err")
        original.add_note("earlier note")

        def original_failure():
            raise original

        try:
            with captured_subprocess_diagnostics():
                original_failure()
        except subprocess.CalledProcessError as error:
            self.assertIs(error, original)
            self.assertEqual(error.returncode, -15)
            self.assertEqual(error.cmd, ["hidden-argument"])
            self.assertEqual(error.output, "out")
            self.assertEqual(error.stderr, "err")
            self.assertEqual(error.__notes__[0], "earlier note")
            self.assertIn("original_failure", [
                frame.name for frame in traceback.extract_tb(error.__traceback__)
            ])
        else:
            self.fail("original failure was swallowed")
        self.assertIn("returncode=-15", original.__notes__[1])
        self.assertNotIn("hidden-argument", original.__notes__[1])

    def test_bytes_invalid_utf8_and_controls_are_safe_to_render(self):
        original = subprocess.CalledProcessError(
            1, ["child"], b"checkpoint\xff\x00", "bad\x1b[31mstartup\r\u202e".encode()
        )
        note = self.annotated(original)
        self.assertIn("checkpoint\\ufffd\\x00", note)
        self.assertIn("bad\\x1b[31mstartup\\r", note)
        self.assertNotIn("\x1b", note)
        self.assertNotIn("\x00", note)
        self.assertNotIn("\u202e", note)
        self.assertIsInstance(original.stdout, bytes)

    def test_empty_and_absent_streams_are_distinct(self):
        note = self.annotated(subprocess.CalledProcessError(1, ["child"], "", None))
        self.assertIn("stdout=''", note)
        self.assertIn("stderr=<not captured>", note)

    def test_rendered_tails_are_bounded_even_for_control_characters(self):
        original = subprocess.CalledProcessError(
            1, ["child"], "\x00" * 10000 + "OUT-END", "\u202e" * 10000 + "ERR-END"
        )
        note = self.annotated(original)
        self.assertLess(len(note), 2 * _OUTPUT_LIMIT + 300)
        self.assertEqual(note.count("earlier rendered characters omitted"), 2)
        self.assertIn("OUT-END", note)
        self.assertIn("ERR-END", note)
        self.assertEqual(len(original.stdout), 10007)

    def test_credentials_are_redacted_before_truncation(self):
        credential_lines = [
            "PASSWORD=do-not-print-password",
            '{"api_key": "do-not-print-api-key"}',
            "Authorization: Bearer do-not-print-bearer",
            "Cookie: session=do-not-print-cookie",
            "https://user:do-not-print-url@example.test/path",
            "client_secret=do-not-print-secret",
            "--signature do-not-print-signature",
            "ghp_0123456789abcdefghijklmnop",
            "github_pat_0123456789abcdefghijklmnop",
            "sk-0123456789abcdefghijklmnop",
            "-----BEGIN PRIVATE KEY-----\ndo-not-print-pem\n-----END PRIVATE KEY-----",
            '"access_token":\n  "do-not-print-multiline"',
            "token=" + "x" * (_OUTPUT_LIMIT * 2) + "do-not-print-tail",
        ]
        for payload in credential_lines:
            with self.subTest(payload_kind=payload.split("\n")[0][:20]):
                raw = "before checkpoint\n" + payload + "\nRuntimeError: startup failed\n"
                original = subprocess.CalledProcessError(1, ["secret-argv"], raw, raw.encode())
                note = self.annotated(original)
                self.assertIn("before checkpoint", note)
                self.assertIn("RuntimeError: startup failed", note)
                self.assertIn("redacted", note)
                self.assertNotIn("do-not-print", note)
                self.assertNotIn("0123456789abcdefghijklmnop", note)
                self.assertNotIn("secret-argv", note)
                self.assertEqual(original.stdout, raw)

    def test_unterminated_private_key_is_suppressed(self):
        note = self.annotated(subprocess.CalledProcessError(
            1, ["child"], None, "-----BEGIN RSA PRIVATE KEY-----\ndo-not-print\n"
        ))
        self.assertNotIn("do-not-print", note)
        self.assertIn("redacted", note)

    def test_renderer_failure_does_not_mask_or_dump_original(self):
        original = subprocess.CalledProcessError(1, ["secret-argv"], "secret-output")
        with patch("subprocess_diagnostics._output_note", side_effect=ValueError("secret")):
            note = self.annotated(original)
        self.assertEqual(note, "captured subprocess failure: output diagnostics unavailable")
        self.assertNotIn("secret", note)

    def test_unrelated_exceptions_are_unchanged_without_notes(self):
        for original in (ValueError("bad receipt"), FileNotFoundError("missing child"),
                         KeyboardInterrupt(), subprocess.SubprocessError("other")):
            with self.subTest(error_type=type(original).__name__):
                with self.assertRaises(type(original)) as raised:
                    with captured_subprocess_diagnostics():
                        raise original
                self.assertIs(raised.exception, original)
                self.assertFalse(hasattr(original, "__notes__"))


if __name__ == "__main__":
    unittest.main()
