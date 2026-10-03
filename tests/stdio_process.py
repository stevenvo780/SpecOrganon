"""Test-only cleanup and failure diagnostics for a raw stdio child."""

from __future__ import annotations

import asyncio
import os
import signal
from contextlib import asynccontextmanager


_STDERR_LIMIT = 4096


async def _cleanup(
    process: asyncio.subprocess.Process, timeout: float
) -> tuple[str, bool]:
    before = process.returncode
    actions: list[str] = []
    expected_returncodes = {0}
    errors: list[str] = []
    if process.stdin is not None:
        try:
            process.stdin.close()
        except Exception as error:
            errors.append(f"stdin.close: {error!r}"[:500])

    # Keep one pipe reader through every deadline. Cancelling and restarting
    # communicate() can discard output already consumed by its first read.
    output = asyncio.create_task(process.communicate())
    reaped = asyncio.create_task(process.wait())
    tasks = {output, reaped}
    try:
        for action in (None, "terminate", "kill"):
            if action is not None and process.returncode is None:
                try:
                    getattr(process, action)()
                except ProcessLookupError:
                    actions.append(f"{action}: exit race")
                except Exception as error:
                    errors.append(f"{action}: {error!r}"[:500])
                else:
                    actions.append(action)
                    if os.name == "nt":
                        # subprocess uses TerminateProcess(..., 1) for both.
                        expected_returncodes.add(1)
                    else:
                        expected_returncodes.add(
                            -signal.SIGTERM
                            if action == "terminate"
                            else -signal.SIGKILL
                        )
            _, pending = await asyncio.wait(tasks, timeout=timeout)
            if not pending:
                break
        else:
            errors.append("cleanup deadline exceeded; process or pipes still pending")
    finally:
        pending = {task for task in tasks if not task.done()}
        for task in pending:
            task.cancel()
        if pending:
            # Cancellation of pipe readers is a last resort, never a retry.
            _, pending = await asyncio.wait(pending, timeout=timeout)
            if pending:
                errors.append("cleanup tasks did not cancel before deadline")

    stderr = "unavailable (pipe collection incomplete)"
    for task, label in ((output, "communicate"), (reaped, "wait")):
        if not task.done() or task.cancelled():
            errors.append(f"{label}: incomplete or cancelled")
            continue
        try:
            result = task.result()
        except Exception as error:
            errors.append(f"{label}: {error!r}"[:500])
        else:
            if task is output:
                raw = result[1]
                if raw is None:
                    stderr = "unavailable (not piped)"
                else:
                    omitted = max(0, len(raw) - _STDERR_LIMIT)
                    stderr = repr(raw[-_STDERR_LIMIT:])
                    if omitted:
                        stderr = f"[{omitted} earlier bytes omitted] {stderr}"

    if process.returncode is None:
        errors.append("child has no observed exit status after cleanup")
    elif process.returncode not in expected_returncodes:
        errors.append(
            f"unexpected child exit status; expected {sorted(expected_returncodes)!r}"
        )
    diagnostic = (
        f"stdio child: returncode before cleanup={before!r}; "
        f"returncode after cleanup={process.returncode!r}; "
        f"cleanup actions={actions!r}; stderr={stderr}"
    )
    if errors:
        diagnostic += f"; cleanup errors={errors!r}"
    return diagnostic, bool(errors)


async def _finish_cleanup(
    process: asyncio.subprocess.Process, timeout: float
) -> tuple[str, bool, asyncio.CancelledError | None]:
    # Cleanup owns its deadlines and child independently of the exercising
    # task. Repeated cancellation must not cancel readers or skip escalation.
    cleanup = asyncio.create_task(_cleanup(process, timeout))
    cancellation = None
    cancellations = 0
    while True:
        try:
            diagnostic, failed = await asyncio.shield(cleanup)
            break
        except asyncio.CancelledError as error:
            if cleanup.cancelled():
                raise
            if cancellation is None:
                cancellation = error
            cancellations += 1
    if cancellation is not None:
        diagnostic += (
            f"; cleanup wait cancelled {cancellations} time(s); "
            f"first cancellation={cancellation!r}"[:500]
        )
    return diagnostic, failed, cancellation


@asynccontextmanager
async def managed_stdio_process(
    process: asyncio.subprocess.Process, *, timeout: float = 5
):
    """Reap a test child without replacing the test body's original failure."""
    try:
        yield process
    except BaseException as error:
        try:
            diagnostic, _, _ = await _finish_cleanup(process, timeout)
        except BaseException as cleanup_error:
            error.add_note(f"stdio cleanup failed: {cleanup_error!r}"[:500])
        else:
            error.add_note(diagnostic)
        raise
    else:
        diagnostic, failed, cancellation = await _finish_cleanup(process, timeout)
        if cancellation is not None:
            cancellation.add_note(diagnostic)
            raise cancellation
        if failed:
            raise AssertionError(diagnostic)
