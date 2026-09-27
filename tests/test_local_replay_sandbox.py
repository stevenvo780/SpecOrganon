"""Adversarial checks for the local single-process replay boundary."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import local_replay_sandbox as sandbox  # noqa: E402


@pytest.fixture
def replay_layout(tmp_path: Path) -> dict[str, Path]:
    paths = {name: tmp_path / name for name in ("work", "output", "temporary", "outside")}
    for path in paths.values():
        path.mkdir()
    (paths["work"] / "packet.txt").write_text("packet\n", encoding="utf-8")
    (paths["outside"] / "secret.txt").write_text("private\n", encoding="utf-8")
    return paths


def _run(paths: dict[str, Path], script: str, *, timeout_seconds: float = 2,
         cpu_seconds: int = 2, address_space_bytes: int = 256 * 1024 * 1024,
         name: str = "run") -> sandbox.SandboxResult:
    (paths["work"] / "analysis.py").write_text(script, encoding="utf-8")
    return sandbox.run_sandboxed(
        argv=[sys.executable, "-I", "analysis.py"], cwd=paths["work"],
        read_roots=[paths["work"]],
        write_roots=[paths["output"], paths["temporary"]],
        runtime_roots=sandbox.default_python_runtime_roots(),
        stdout_path=paths["work"].parent / f"{name}.stdout",
        stderr_path=paths["work"].parent / f"{name}.stderr",
        timeout_seconds=timeout_seconds, cpu_seconds=cpu_seconds,
        address_space_bytes=address_space_bytes,
        env={"HOME": str(paths["output"]), "TMPDIR": str(paths["temporary"])},
    )


@pytest.fixture
def available_sandbox() -> None:
    capability = sandbox.probe_sandbox()
    if not capability.available:
        pytest.skip(capability.reason or "sandbox unavailable")


def test_probe_and_allowed_packet_output(
    replay_layout: dict[str, Path], available_sandbox: None,
) -> None:
    paths = replay_layout
    result = _run(paths, """
from pathlib import Path
import os
assert Path('packet.txt').read_text() == 'packet\\n'
output = Path(os.environ['HOME']) / 'result.txt'
output.write_text('ok\\n')
assert output.read_text() == 'ok\\n'
Path(os.environ['TMPDIR'], 'scratch.txt').write_text('tmp')
print('done')
""")
    assert result.launch_error is None
    assert result.exit_code == 0
    assert not result.timed_out
    assert result.landlock_abi is not None and result.landlock_abi >= 5
    assert (paths["output"] / "result.txt").read_text() == "ok\n"
    assert (paths["temporary"] / "scratch.txt").read_text() == "tmp"
    assert (paths["work"].parent / "run.stdout").read_text() == "done\n"
    assert ((paths["work"].parent / "run.stdout").stat().st_mode & 0o777) == 0o600


def test_forbidden_read_write_and_metadata_mutation(
    replay_layout: dict[str, Path], available_sandbox: None,
) -> None:
    paths = replay_layout
    outside = paths["outside"] / "secret.txt"
    before_mode = outside.stat().st_mode & 0o777
    result = _run(paths, f"""
from pathlib import Path
outside = Path({str(outside)!r})
for operation in (
    lambda: outside.read_text(),
    lambda: outside.write_text('changed'),
    lambda: outside.chmod(0o600),
    lambda: Path('packet.txt').write_text('changed'),
):
    try:
        operation()
    except (OSError, PermissionError):
        pass
    else:
        raise AssertionError('forbidden filesystem operation succeeded')
print('blocked')
""")
    assert result.exit_code == 0, (paths["work"].parent / "run.stderr").read_text()
    assert (paths["work"].parent / "run.stdout").read_text() == "blocked\n"
    assert outside.read_text() == "private\n"
    assert outside.stat().st_mode & 0o777 == before_mode
    assert (paths["work"] / "packet.txt").read_text() == "packet\n"


def test_empty_write_roots_allow_only_preopened_streams(
    replay_layout: dict[str, Path], available_sandbox: None,
) -> None:
    paths = replay_layout
    (paths["work"] / "analysis.py").write_text("""
from pathlib import Path
try:
    Path('new.txt').write_text('unexpected')
except OSError:
    print('read only')
else:
    raise AssertionError('created a new work file')
""", encoding="utf-8")
    result = sandbox.run_sandboxed(
        argv=[sys.executable, "-I", "analysis.py"], cwd=paths["work"],
        read_roots=[paths["work"]], write_roots=[],
        runtime_roots=sandbox.default_python_runtime_roots(),
        stdout_path=paths["work"].parent / "readonly.stdout",
        stderr_path=paths["work"].parent / "readonly.stderr",
        timeout_seconds=2,
        env={"HOME": str(paths["work"]), "TMPDIR": str(paths["work"])},
    )
    assert result.exit_code == 0
    assert (paths["work"].parent / "readonly.stdout").read_text() == "read only\n"
    assert not (paths["work"] / "new.txt").exists()


def test_socket_and_child_process_denied(
    replay_layout: dict[str, Path], available_sandbox: None,
) -> None:
    paths = replay_layout
    result = _run(paths, """
import os
import socket
for operation in (
    lambda: socket.socket(socket.AF_INET, socket.SOCK_STREAM),
    lambda: socket.socketpair(),
    lambda: os.fork(),
    lambda: os.memfd_create('unaccounted'),
):
    try:
        operation()
    except OSError:
        pass
    else:
        raise AssertionError('forbidden syscall succeeded')
print('denied')
""")
    assert result.exit_code == 0, (paths["work"].parent / "run.stderr").read_text()
    assert (paths["work"].parent / "run.stdout").read_text() == "denied\n"


def test_cannot_change_other_process_priority(
    replay_layout: dict[str, Path], available_sandbox: None,
) -> None:
    target = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        before = os.getpriority(os.PRIO_PROCESS, target.pid)
        if before >= 10:
            pytest.skip("test target already has priority 10 or greater")
        result = _run(replay_layout, f"""
import os
try:
    os.setpriority(os.PRIO_PROCESS, {target.pid}, 10)
except OSError:
    print('blocked')
else:
    raise AssertionError('changed sibling priority')
""")
        assert result.exit_code == 0
        assert (replay_layout["work"].parent / "run.stdout").read_text() == "blocked\n"
        assert os.getpriority(os.PRIO_PROCESS, target.pid) == before
    finally:
        target.terminate()
        target.wait(timeout=5)


def test_wall_timeout_and_memory_limit(
    replay_layout: dict[str, Path], available_sandbox: None,
) -> None:
    paths = replay_layout
    timeout = _run(paths, "import time\ntime.sleep(5)\n", timeout_seconds=0.2,
                   cpu_seconds=3, name="timeout")
    assert timeout.timed_out
    assert timeout.exit_code is None
    limited = _run(paths, """
try:
    data = bytearray(512 * 1024 * 1024)
except MemoryError:
    print('limited')
else:
    raise AssertionError('memory allocation succeeded')
""", address_space_bytes=128 * 1024 * 1024, name="memory")
    assert limited.exit_code == 0, (paths["work"].parent / "memory.stderr").read_text()
    assert (paths["work"].parent / "memory.stdout").read_text() == "limited\n"


def test_missing_capability_fails_before_payload_or_streams(
    replay_layout: dict[str, Path], monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = replay_layout
    monkeypatch.setattr(sandbox, "probe_sandbox", lambda: sandbox.SandboxCapability(
        False, None, "Landlock disabled"))
    with pytest.raises(sandbox.SandboxUnavailable, match="Landlock disabled"):
        _run(paths, "from pathlib import Path\nPath('ran').write_text('yes')\n",
             name="unavailable")
    assert not (paths["work"] / "ran").exists()
    assert not (paths["work"].parent / "unavailable.stdout").exists()
    assert not (paths["work"].parent / "unavailable.stderr").exists()


def test_streams_are_exclusive(
    replay_layout: dict[str, Path], available_sandbox: None,
) -> None:
    paths = replay_layout
    (paths["work"].parent / "run.stdout").write_text("existing", encoding="utf-8")
    with pytest.raises(FileExistsError):
        _run(paths, "print('must not run')", name="run")
    assert (paths["work"].parent / "run.stdout").read_text() == "existing"
    assert not (paths["work"].parent / "run.stderr").exists()


def test_inherited_parent_descriptor_is_closed(
    replay_layout: dict[str, Path], available_sandbox: None,
) -> None:
    paths = replay_layout
    source = os.open(paths["outside"] / "secret.txt", os.O_RDONLY)
    try:
        os.dup2(source, 222, inheritable=True)
        result = _run(paths, """
import os
try:
    os.fstat(222)
except OSError:
    print('closed')
else:
    raise AssertionError('parent descriptor leaked')
""")
    finally:
        os.close(222)
        os.close(source)
    assert result.exit_code == 0, (paths["work"].parent / "run.stderr").read_text()
    assert (paths["work"].parent / "run.stdout").read_text() == "closed\n"


def test_write_root_cannot_contain_read_only_work(
    replay_layout: dict[str, Path], available_sandbox: None,
) -> None:
    paths = replay_layout
    with pytest.raises(sandbox.SandboxError, match="cwd must stay outside"):
        sandbox.run_sandboxed(
            argv=[sys.executable, "-I", "analysis.py"], cwd=paths["work"],
            read_roots=[paths["work"]], write_roots=[paths["work"].parent],
            runtime_roots=sandbox.default_python_runtime_roots(),
            stdout_path=paths["work"].parent / "run.stdout",
            stderr_path=paths["work"].parent / "run.stderr",
            timeout_seconds=1,
        )
    assert not (paths["work"].parent / "run.stdout").exists()
