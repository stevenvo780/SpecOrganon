"""Local Python children exercise test cleanup without importing the MCP server."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
import traceback
import unittest
from unittest.mock import patch

from stdio_process import _STDERR_LIMIT, managed_stdio_process


class StdioProcessTests(unittest.IsolatedAsyncioTestCase):
    async def child(self, code: str) -> asyncio.subprocess.Process:
        return await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            code,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    async def ready(self, process: asyncio.subprocess.Process) -> None:
        self.assertEqual(
            await asyncio.wait_for(process.stdout.readline(), timeout=5), b"ready\n"
        )

    async def test_exited_child_preserves_original_assertion_and_traceback(self):
        process = await self.child(
            "import sys; sys.stderr.write('startup failed'); sys.exit(7)"
        )
        await asyncio.wait_for(process.wait(), timeout=5)
        original = AssertionError("MCP process ended before its response")

        def fail_at_response():
            raise original

        with (
            patch.object(process, "terminate") as terminate,
            patch.object(process, "kill") as kill,
        ):
            try:
                async with managed_stdio_process(process, timeout=0.1):
                    fail_at_response()
            except AssertionError as error:
                self.assertIs(error, original)
                self.assertIn(
                    "fail_at_response",
                    [frame.name for frame in traceback.extract_tb(error.__traceback__)],
                )
            else:
                self.fail("original assertion was swallowed")
        terminate.assert_not_called()
        kill.assert_not_called()
        note = original.__notes__[0]
        self.assertIn("before cleanup=7", note)
        self.assertIn("after cleanup=7", note)
        self.assertIn("startup failed", note)

    async def test_eof_reports_natural_child_failure(self):
        process = await self.child(
            "import sys; sys.stderr.buffer.write(b'bad\\xffstartup'); sys.exit(9)"
        )
        with self.assertRaisesRegex(AssertionError, "before its response") as raised:
            async with managed_stdio_process(process, timeout=0.1):
                line = await asyncio.wait_for(process.stdout.readline(), timeout=5)
                assert line, "MCP process ended before its response"
        self.assertEqual(process.returncode, 9)
        self.assertIn("bad\\xffstartup", raised.exception.__notes__[0])
        self.assertIn("cleanup actions=[]", raised.exception.__notes__[0])

    async def test_json_error_is_not_replaced(self):
        process = await self.child("print('not-json')")
        with self.assertRaises(json.JSONDecodeError) as raised:
            async with managed_stdio_process(process, timeout=0.1):
                json.loads(await asyncio.wait_for(process.stdout.readline(), timeout=5))
        self.assertIn("returncode after cleanup=0", raised.exception.__notes__[0])

    async def test_response_timeout_is_preserved_and_child_reaped(self):
        process = await self.child(
            "import sys; print('ready', flush=True); "
            "sys.stdin.read(); sys.stderr.write('closed')"
        )
        await self.ready(process)
        with self.assertRaises(TimeoutError) as raised:
            async with managed_stdio_process(process, timeout=0.1):
                await asyncio.wait_for(process.stdout.readline(), timeout=0.02)
        self.assertEqual(process.returncode, 0)
        self.assertIn("closed", raised.exception.__notes__[0])

    async def test_body_cancellation_is_preserved_and_child_reaped(self):
        process = await self.child(
            "import sys; print('ready', flush=True); sys.stdin.read()"
        )
        await self.ready(process)
        original = asyncio.CancelledError("cancelled body")
        with self.assertRaises(asyncio.CancelledError) as raised:
            async with managed_stdio_process(process, timeout=0.1):
                raise original
        self.assertIs(raised.exception, original)
        self.assertEqual(process.returncode, 0)
        self.assertIn("returncode after cleanup=0", original.__notes__[0])

    async def cancel_during_cleanup(self, *, body_error, repeated=False):
        child_code = "import time; print('ready', flush=True); time.sleep(60)"
        if repeated:
            child_code = (
                "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                "print('ready', flush=True); time.sleep(60)"
            )
        process = await self.child(child_code)
        original_communicate = process.communicate
        original_terminate = process.terminate
        started = asyncio.Event()
        terminated = asyncio.Event()
        original = AssertionError("original body failure")
        calls = 0
        task = None

        async def communicate():
            nonlocal calls
            calls += 1
            started.set()
            return await original_communicate()

        def terminate():
            original_terminate()
            terminated.set()

        async def exercise():
            async with managed_stdio_process(process, timeout=0.05):
                if body_error:
                    raise original

        try:
            await self.ready(process)
            with (
                patch.object(process, "communicate", side_effect=communicate),
                patch.object(process, "terminate", side_effect=terminate),
            ):
                task = asyncio.create_task(exercise())
                await asyncio.wait_for(started.wait(), timeout=2)
                task.cancel("cancel while in graceful cleanup wait")
                if repeated:
                    await asyncio.wait_for(terminated.wait(), timeout=2)
                    task.cancel("cancel again during termination wait")
                try:
                    await asyncio.wait_for(task, timeout=2)
                except BaseException as error:
                    if body_error:
                        self.assertIs(error, original)
                    else:
                        self.assertIsInstance(error, asyncio.CancelledError)
                        self.assertEqual(
                            str(error), "cancel while in graceful cleanup wait"
                        )
                    note = error.__notes__[0]
                    count = 2 if repeated else 1
                    self.assertIn(f"cleanup wait cancelled {count} time(s)", note)
                    self.assertIn("'terminate'", note)
                    if repeated:
                        self.assertIn("'kill'", note)
                else:
                    self.fail("body failure or task cancellation was swallowed")
            self.assertIsNotNone(process.returncode, "owned child was abandoned")
            self.assertTrue(process.stdout.at_eof())
            self.assertTrue(process.stderr.at_eof())
            self.assertEqual(calls, 1, "pipe collection must not restart")
        finally:
            # Make a failing regression safe even against the old helper.
            if task is not None and task.done() and not task.cancelled():
                task.exception()
            if process.returncode is None:
                process.kill()
            await asyncio.wait_for(original_communicate(), timeout=2)

    async def test_cancellation_during_successful_teardown_reaps_child(self):
        await self.cancel_during_cleanup(body_error=False)

    async def test_cancellation_during_failed_teardown_preserves_original(self):
        await self.cancel_during_cleanup(body_error=True)

    @unittest.skipUnless(os.name == "posix", "POSIX signal semantics")
    async def test_repeated_cancellation_during_successful_teardown_reaps_child(self):
        await self.cancel_during_cleanup(body_error=False, repeated=True)

    @unittest.skipUnless(os.name == "posix", "POSIX signal semantics")
    async def test_repeated_cancellation_during_failed_teardown_preserves_original(
        self,
    ):
        await self.cancel_during_cleanup(body_error=True, repeated=True)

    async def test_successful_body_closes_stdin_and_drains_large_pipes(self):
        process = await self.child(
            "import sys; sys.stdin.read(); "
            "sys.stdout.buffer.write(b'o' * 262144); sys.stdout.flush(); "
            "sys.stderr.buffer.write(b'e' * 262144)"
        )
        async with managed_stdio_process(process, timeout=1):
            pass
        self.assertEqual(process.returncode, 0)
        self.assertTrue(process.stdout.at_eof())
        self.assertTrue(process.stderr.at_eof())

    async def test_stderr_note_is_bounded_and_explicitly_truncated(self):
        process = await self.child(
            "import sys; sys.stderr.buffer.write(b'x' * 262144 + b'END\\xff'); "
            "sys.exit(2)"
        )
        original = AssertionError("original")
        with self.assertRaises(AssertionError):
            async with managed_stdio_process(process, timeout=1):
                raise original
        note = original.__notes__[0]
        self.assertIn("earlier bytes omitted", note)
        self.assertIn("END\\xff", note)
        self.assertLess(len(note), _STDERR_LIMIT + 500)
        self.assertEqual(process.returncode, 2)

    async def test_live_child_is_terminated_after_grace_period(self):
        process = await self.child(
            "import time; print('ready', flush=True); time.sleep(60)"
        )
        await self.ready(process)
        original = AssertionError("body failed")
        with self.assertRaises(AssertionError) as raised:
            async with managed_stdio_process(process, timeout=0.05):
                raise original
        self.assertIs(raised.exception, original)
        self.assertIsNotNone(process.returncode)
        self.assertIn("cleanup actions=['terminate']", original.__notes__[0])
        self.assertIn("before cleanup=None", original.__notes__[0])

    @unittest.skipUnless(os.name == "posix", "POSIX signal semantics")
    async def test_child_ignoring_terminate_is_killed_and_reaped(self):
        process = await self.child(
            "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            "print('ready', flush=True); time.sleep(60)"
        )
        await self.ready(process)
        original = RuntimeError("body failed")
        with self.assertRaises(RuntimeError):
            async with managed_stdio_process(process, timeout=0.05):
                raise original
        self.assertEqual(process.returncode, -signal.SIGKILL)
        self.assertIn("cleanup actions=['terminate', 'kill']", original.__notes__[0])

    async def test_terminate_exit_race_preserves_original_error(self):
        process = await self.child(
            "import time; print('ready', flush=True); time.sleep(60)"
        )
        await self.ready(process)
        original_terminate = process.terminate

        def race():
            original_terminate()
            raise ProcessLookupError("simulated exit between guard and signal")

        original = AssertionError("body failed")
        with patch.object(process, "terminate", side_effect=race):
            with self.assertRaises(AssertionError) as raised:
                async with managed_stdio_process(process, timeout=0.05):
                    raise original
        self.assertIs(raised.exception, original)
        self.assertIsNotNone(process.returncode)
        self.assertIn("terminate: exit race", original.__notes__[0])

    async def test_signal_error_is_reported_without_masking_body_failure(self):
        process = await self.child(
            "import time; print('ready', flush=True); time.sleep(60)"
        )
        await self.ready(process)
        original = AssertionError("body failed")
        with patch.object(
            process, "terminate", side_effect=PermissionError("signal denied")
        ):
            with self.assertRaises(AssertionError) as raised:
                async with managed_stdio_process(process, timeout=0.05):
                    raise original
        self.assertIs(raised.exception, original)
        self.assertIsNotNone(process.returncode)
        self.assertIn("PermissionError('signal denied')", original.__notes__[0])
        self.assertIn("cleanup actions=['kill']", original.__notes__[0])

    async def test_signal_error_fails_previously_successful_body(self):
        process = await self.child(
            "import time; print('ready', flush=True); time.sleep(60)"
        )
        await self.ready(process)
        with patch.object(
            process, "terminate", side_effect=PermissionError("signal denied")
        ):
            with self.assertRaisesRegex(AssertionError, "PermissionError.*denied"):
                async with managed_stdio_process(process, timeout=0.05):
                    pass
        self.assertIsNotNone(process.returncode)

    async def test_nonzero_natural_exit_fails_previously_successful_body(self):
        process = await self.child(
            "import sys; sys.stderr.write('late failure'); sys.exit(3)"
        )
        with self.assertRaisesRegex(AssertionError, "late failure"):
            async with managed_stdio_process(process, timeout=1):
                pass
        self.assertEqual(process.returncode, 3)

    @unittest.skipUnless(os.name == "posix", "POSIX signal semantics")
    async def test_nonzero_exit_from_sigterm_handler_fails_successful_body(self):
        process = await self.child(
            "import signal, sys, time; "
            "signal.signal(signal.SIGTERM, lambda *_: sys.exit(9)); "
            "print('ready', flush=True); time.sleep(60)"
        )
        await self.ready(process)
        with self.assertRaisesRegex(AssertionError, "unexpected child exit status"):
            async with managed_stdio_process(process, timeout=0.05):
                pass
        self.assertEqual(process.returncode, 9)

    @unittest.skipUnless(os.name == "posix", "POSIX signal semantics")
    async def test_sigterm_handler_failure_does_not_mask_body_error(self):
        process = await self.child(
            "import signal, sys, time; "
            "signal.signal(signal.SIGTERM, lambda *_: sys.exit(9)); "
            "print('ready', flush=True); time.sleep(60)"
        )
        await self.ready(process)
        original = AssertionError("original body failure")
        with self.assertRaises(AssertionError) as raised:
            async with managed_stdio_process(process, timeout=0.05):
                raise original
        self.assertIs(raised.exception, original)
        self.assertEqual(process.returncode, 9)
        self.assertIn("unexpected child exit status", original.__notes__[0])

    @unittest.skipUnless(os.name == "posix", "POSIX signal semantics")
    async def test_unrelated_signal_exit_fails_successful_body(self):
        process = await self.child(
            "import os, signal, time; "
            "signal.signal(signal.SIGTERM, lambda *_: "
            "os.kill(os.getpid(), signal.SIGUSR1)); "
            "print('ready', flush=True); time.sleep(60)"
        )
        await self.ready(process)
        with self.assertRaisesRegex(AssertionError, "unexpected child exit status"):
            async with managed_stdio_process(process, timeout=0.05):
                pass
        self.assertEqual(process.returncode, -signal.SIGUSR1)

    @unittest.skipUnless(os.name == "posix", "POSIX signal semantics")
    async def test_zero_exit_from_sigterm_handler_still_passes(self):
        process = await self.child(
            "import signal, sys, time; "
            "signal.signal(signal.SIGTERM, lambda *_: sys.exit(0)); "
            "print('ready', flush=True); time.sleep(60)"
        )
        await self.ready(process)
        async with managed_stdio_process(process, timeout=0.05):
            pass
        self.assertEqual(process.returncode, 0)

    async def test_final_pipe_deadline_preserves_error_and_cancels_reader(self):
        class IncompletePipes:
            stdin = None
            returncode = 0
            reader_cancelled = False
            calls = 0

            async def communicate(self):
                self.calls += 1
                try:
                    await asyncio.Future()
                finally:
                    self.reader_cancelled = True

            async def wait(self):
                return self.returncode

        process = IncompletePipes()
        original = AssertionError("original")
        started = asyncio.get_running_loop().time()
        with self.assertRaises(AssertionError) as raised:
            async with managed_stdio_process(process, timeout=0.02):
                raise original
        self.assertIs(raised.exception, original)
        self.assertLess(asyncio.get_running_loop().time() - started, 1)
        self.assertEqual(process.calls, 1)
        self.assertTrue(process.reader_cancelled)
        self.assertIn("collection incomplete", original.__notes__[0])
        self.assertIn("cleanup deadline exceeded", original.__notes__[0])

    async def test_cancelled_pipe_collection_fails_successful_body(self):
        class CancelledPipes:
            stdin = None
            returncode = 0

            async def communicate(self):
                raise asyncio.CancelledError

            async def wait(self):
                return self.returncode

        with self.assertRaisesRegex(AssertionError, "communicate: incomplete"):
            async with managed_stdio_process(CancelledPipes(), timeout=0.02):
                pass

    @unittest.skipUnless(os.name == "posix", "POSIX signal semantics")
    async def test_kill_exit_race_preserves_original_error(self):
        process = await self.child(
            "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            "print('ready', flush=True); time.sleep(60)"
        )
        await self.ready(process)
        original_kill = process.kill

        def race():
            original_kill()
            raise ProcessLookupError("simulated exit between guard and signal")

        original = AssertionError("body failed")
        with patch.object(process, "kill", side_effect=race):
            with self.assertRaises(AssertionError) as raised:
                async with managed_stdio_process(process, timeout=0.05):
                    raise original
        self.assertIs(raised.exception, original)
        self.assertEqual(process.returncode, -signal.SIGKILL)
        self.assertIn("kill: exit race", original.__notes__[0])


if __name__ == "__main__":
    unittest.main()
