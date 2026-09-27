"""Adversarial checks for the local single-process replay boundary."""

from __future__ import annotations

import hashlib
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


def _run_sealed(paths: dict[str, Path], payload: bytes, *,
                source: Path | None = None, name: str = "sealed",
                expected_sha256: str | None = None) -> sandbox.SandboxResult:
    original = source or paths["work"] / "original-tool.py"
    return sandbox.run_sandboxed(
        argv=[str(original), "argument"], cwd=paths["work"],
        read_roots=[paths["work"]],
        write_roots=[paths["output"], paths["temporary"]],
        runtime_roots=sandbox.default_python_runtime_roots(),
        stdout_path=paths["work"].parent / f"{name}.stdout",
        stderr_path=paths["work"].parent / f"{name}.stderr",
        timeout_seconds=3,
        env={"HOME": str(paths["output"]), "TMPDIR": str(paths["temporary"])},
        sealed_executable_bytes=payload,
        sealed_executable_sha256=(expected_sha256 or hashlib.sha256(payload).hexdigest()),
    )


def test_sealed_shebang_executes_authenticated_bytes(
    replay_layout: dict[str, Path], available_sandbox: None,
) -> None:
    paths = replay_layout
    script = (f"#!{sys.executable} -I\n"
              "import sys\n"
              "from pathlib import Path\n"
              "assert sys.argv[1] == 'argument'\n"
              "assert Path('packet.txt').read_text() == 'packet\\n'\n"
              "try:\n"
              "    Path('/proc/self/environ').read_bytes()\n"
              "except OSError:\n"
              "    pass\n"
              "else:\n"
              "    raise AssertionError('general procfs read succeeded')\n"
              "print('sealed script')\n").encode()
    result = _run_sealed(paths, script)
    assert result.exit_code == 0, (paths["work"].parent / "sealed.stderr").read_text()
    assert result.launch_error is None
    assert result.sealed_executable_sha256 == hashlib.sha256(script).hexdigest()
    assert (paths["work"].parent / "sealed.stdout").read_text() == "sealed script\n"
    assert not (paths["work"] / "original-tool.py").exists()


def test_sealed_elf_executes_authenticated_bytes(
    replay_layout: dict[str, Path], available_sandbox: None,
) -> None:
    executable = Path("/bin/echo")
    if not executable.is_file():
        pytest.skip("/bin/echo is unavailable")
    payload = executable.read_bytes()
    paths = replay_layout
    result = _run_sealed(paths, payload, source=executable, name="sealed-elf")
    assert result.exit_code == 0, (paths["work"].parent / "sealed-elf.stderr").read_text()
    assert result.sealed_executable_sha256 == hashlib.sha256(payload).hexdigest()
    assert (paths["work"].parent / "sealed-elf.stdout").read_text() == "argument\n"


def test_sealed_digest_mismatch_fails_before_streams(
    replay_layout: dict[str, Path], available_sandbox: None,
) -> None:
    paths = replay_layout
    script = f"#!{sys.executable} -I\nprint('must not run')\n".encode()
    with pytest.raises(sandbox.SandboxError, match="digest mismatch"):
        _run_sealed(paths, script, expected_sha256="0" * 64)
    assert not (paths["work"].parent / "sealed.stdout").exists()
    assert not (paths["work"].parent / "sealed.stderr").exists()


def test_sealed_exec_failure_has_no_launch_digest(
    replay_layout: dict[str, Path], available_sandbox: None,
) -> None:
    paths = replay_layout
    result = _run_sealed(paths, b"not an ELF or shebang executable\n")
    assert result.exit_code is None
    assert result.launch_error is not None and "ERROR exec" in result.launch_error
    assert result.sealed_executable_sha256 is None


def test_sealed_missing_seal_support_fails_closed(
    replay_layout: dict[str, Path], available_sandbox: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = replay_layout
    actual_fcntl = sandbox.fcntl.fcntl

    def reject_seal(fd: int, operation: int, *args: object) -> int:
        if operation == sandbox._F_ADD_SEALS:
            raise OSError("seals unavailable")
        return actual_fcntl(fd, operation, *args)

    monkeypatch.setattr(sandbox.fcntl, "fcntl", reject_seal)
    script = f"#!{sys.executable} -I\nprint('must not run')\n".encode()
    with pytest.raises(sandbox.SandboxUnavailable, match="sealed memfd preparation failed"):
        _run_sealed(paths, script)
    assert not (paths["work"].parent / "sealed.stdout").exists()
    assert not (paths["work"].parent / "sealed.stderr").exists()


def test_sealed_source_swap_does_not_change_executed_bytes(
    replay_layout: dict[str, Path], available_sandbox: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = replay_layout
    source = paths["work"] / "tool.py"
    original = f"#!{sys.executable} -I\nprint('original')\n".encode()
    replacement = f"#!{sys.executable} -I\nprint('swapped')\n".encode()
    source.write_bytes(original)
    create_sealed_fd = sandbox._sealed_executable_fd

    def swap_after_sealing(contents: bytes, expected_sha256: str) -> int:
        fd = create_sealed_fd(contents, expected_sha256)
        source.write_bytes(replacement)
        return fd

    monkeypatch.setattr(sandbox, "_sealed_executable_fd", swap_after_sealing)
    result = _run_sealed(paths, original, source=source)
    assert result.exit_code == 0, (paths["work"].parent / "sealed.stderr").read_text()
    assert result.sealed_executable_sha256 == hashlib.sha256(original).hexdigest()
    assert (paths["work"].parent / "sealed.stdout").read_text() == "original\n"
    assert source.read_bytes() == replacement


@pytest.mark.parametrize("payload,digest", [
    (b"", "0" * 64),
    (b"x", "not-a-digest"),
    (b"x", "A" * 64),
    (b"x" * (16 * 1024 * 1024 + 1), "0" * 64),
])
def test_sealed_input_bounds_rejected_before_streams(
    replay_layout: dict[str, Path], available_sandbox: None,
    payload: bytes, digest: str,
) -> None:
    paths = replay_layout
    with pytest.raises(sandbox.SandboxError, match="invalid sealed executable"):
        _run_sealed(paths, payload, expected_sha256=digest)
    assert not (paths["work"].parent / "sealed.stdout").exists()
