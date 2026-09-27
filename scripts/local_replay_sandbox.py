"""Bounded Linux execution for a locally reviewed analysis script.

``run_sandboxed`` is a single-process, offline replay primitive.  The caller
must review the script, authenticate its bytes, and prepare private read and
write directories before calling it.  The payload starts only after a fresh
child has applied Landlock, libseccomp, and resource limits.  The parent never
restricts itself.  Landlock is not a container: it does not mediate all
metadata operations or protect every same-UID host action.  This module also
does not provide mount, PID, user, or network namespace isolation, or an
aggregate cgroup or filesystem-write quota.  ``file_bytes_per_file`` is a
per-file ``RLIMIT_FSIZE`` ceiling; many files can exceed it in aggregate.
``address_space_bytes`` is an ``RLIMIT_AS`` ceiling, not total resident memory.
Use only for a reviewed local replay, not arbitrary hostile code.

Example::

    result = run_sandboxed(
        argv=[sys.executable, "-I", "analysis.py"], cwd=work,
        read_roots=[work], write_roots=[replay_home, replay_tmp],
        runtime_roots=default_python_runtime_roots(),
        stdout_path=run_dir / "analysis_replay.stdout",
        stderr_path=run_dir / "analysis_replay.stderr",
        timeout_seconds=30,
        env={"HOME": str(replay_home), "TMPDIR": str(replay_tmp)},
    )

``read_roots`` receive read access only, ``runtime_roots`` read and execute,
and ``write_roots`` read plus regular-file/directory creation and modification.
An empty ``write_roots`` forbids new filesystem writes apart from the
preopened stdout/stderr streams.  No other filesystem roots are granted.
The parent opens stdout and stderr
exclusively as private files; their paths need not be writable by the child.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import errno
import fcntl
import hashlib
import json
import math
import os
import platform
import resource
import select
import signal
import stat
import subprocess
import sys
import sysconfig
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence


_LANDLOCK_SYSCALLS = {"x86_64": (444, 445, 446), "aarch64": (444, 445, 446)}
_MIN_LANDLOCK_ABI = 5  # ABI 3 adds TRUNCATE; ABI 5 adds IOCTL_DEV.
_FS_EXECUTE = 1 << 0
_FS_WRITE_FILE = 1 << 1
_FS_READ_FILE = 1 << 2
_FS_READ_DIR = 1 << 3
_FS_REMOVE_DIR = 1 << 4
_FS_REMOVE_FILE = 1 << 5
_FS_MAKE_DIR = 1 << 7
_FS_MAKE_REG = 1 << 8
_FS_REFER = 1 << 13
_FS_TRUNCATE = 1 << 14
_FS_IOCTL_DEV = 1 << 15
_HANDLED_FS = (1 << 16) - 1
_HANDLED_NET = 3  # LANDLOCK_ACCESS_NET_BIND_TCP | CONNECT_TCP (ABI >= 4)
_READ_DIR = _FS_READ_FILE | _FS_READ_DIR
_WRITE_DIR = (_READ_DIR | _FS_WRITE_FILE | _FS_REMOVE_DIR | _FS_REMOVE_FILE |
              _FS_MAKE_DIR | _FS_MAKE_REG | _FS_REFER | _FS_TRUNCATE)
_SCMP_ACT_ALLOW = 0x7FFF0000
_SCMP_ACT_ERRNO = 0x00050000 | errno.EPERM
_MAX_CONFIG_BYTES = 65536
_MAX_SEALED_EXECUTABLE_BYTES = 16 * 1024 * 1024
# Linux UAPI values. Python 3.11 builds may omit these fcntl names even when
# the running kernel supports file sealing. probe_sandbox limits us to Linux.
_F_ADD_SEALS = getattr(fcntl, "F_ADD_SEALS", 1033)
_F_GET_SEALS = getattr(fcntl, "F_GET_SEALS", 1034)
_F_SEAL_SEAL = getattr(fcntl, "F_SEAL_SEAL", 0x01)
_F_SEAL_SHRINK = getattr(fcntl, "F_SEAL_SHRINK", 0x02)
_F_SEAL_GROW = getattr(fcntl, "F_SEAL_GROW", 0x04)
_F_SEAL_WRITE = getattr(fcntl, "F_SEAL_WRITE", 0x08)
_ALLOWED_ENV = frozenset({"HOME", "TMPDIR", "PATH", "LANG", "LC_ALL",
                          "PYTHONDONTWRITEBYTECODE", "PYTHONNOUSERSITE"})

# This is a deny list, not a complete syscall allowlist.  In particular it
# prevents network endpoints, descendants, process interference, namespace and
# mount changes, handle-based file access, and metadata writes that Landlock
# cannot currently mediate.  libseccomp resolves names on the native arch.
_DENIED_SYSCALLS = (
    "socket", "socketpair", "connect", "bind", "listen", "accept", "accept4",
    "sendto", "sendmsg", "sendmmsg", "recvfrom", "recvmsg", "recvmmsg",
    "getsockname", "getpeername", "setsockopt", "getsockopt", "shutdown",
    "clone", "clone3", "fork", "vfork", "kill", "tkill", "tgkill",
    "rt_sigqueueinfo", "rt_tgsigqueueinfo",
    "setpriority", "ioprio_set", "sched_setaffinity", "sched_setparam",
    "sched_setscheduler", "sched_setattr", "prlimit64", "process_madvise",
    "move_pages", "migrate_pages", "mbind",
    "pidfd_send_signal", "pidfd_open", "pidfd_getfd", "ptrace",
    "process_vm_readv", "process_vm_writev", "open_by_handle_at",
    "name_to_handle_at", "io_uring_setup", "io_uring_enter",
    "io_uring_register", "bpf", "perf_event_open", "keyctl",
    "memfd_create", "memfd_secret",
    "inotify_init", "inotify_init1", "fanotify_init", "fanotify_mark",
    "mount", "umount2", "pivot_root", "chroot", "unshare", "setns",
    "shmget", "shmat", "shmctl", "semget", "semop", "semtimedop",
    "semctl", "msgget", "msgsnd", "msgrcv", "msgctl", "mq_open",
    "setsid", "setpgid", "execveat", "userfaultfd", "prctl",
    "chmod", "fchmod", "fchmodat", "fchmodat2", "chown", "fchown",
    "lchown", "fchownat", "setxattr", "lsetxattr", "fsetxattr",
    "removexattr", "lremovexattr", "fremovexattr", "utime", "utimes",
    "futimesat", "utimensat",
)


class SandboxUnavailable(RuntimeError):
    """The required local kernel/library capability is unavailable."""


class SandboxError(ValueError):
    """The caller supplied an unsafe or invalid execution specification."""


@dataclass(frozen=True)
class SandboxCapability:
    available: bool
    landlock_abi: int | None
    reason: str | None


@dataclass(frozen=True)
class SandboxResult:
    exit_code: int | None
    timed_out: bool
    launch_error: str | None
    landlock_abi: int | None
    duration_seconds: float
    sealed_executable_sha256: str | None = None


class _RulesetAttr(ctypes.Structure):
    _fields_ = [("handled_access_fs", ctypes.c_uint64),
                ("handled_access_net", ctypes.c_uint64)]


class _PathBeneathAttr(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32)]


def _syscall(libc: ctypes.CDLL, number: int, *args: object) -> int:
    ctypes.set_errno(0)
    result = libc.syscall(number, *args)
    if result == -1:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code))
    return int(result)


def _seccomp_library() -> ctypes.CDLL:
    name = ctypes.util.find_library("seccomp")
    if not name:
        raise OSError(errno.ENOENT, "libseccomp is unavailable")
    library = ctypes.CDLL(name, use_errno=True)
    library.seccomp_init.argtypes = [ctypes.c_uint32]
    library.seccomp_init.restype = ctypes.c_void_p
    library.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    library.seccomp_syscall_resolve_name.restype = ctypes.c_int
    library.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32,
                                         ctypes.c_int, ctypes.c_uint]
    library.seccomp_rule_add.restype = ctypes.c_int
    library.seccomp_load.argtypes = [ctypes.c_void_p]
    library.seccomp_load.restype = ctypes.c_int
    library.seccomp_release.argtypes = [ctypes.c_void_p]
    library.seccomp_release.restype = None
    return library


def probe_sandbox() -> SandboxCapability:
    """Read-only preflight; the real child setup is checked again at launch."""
    if sys.platform != "linux" or platform.machine() not in _LANDLOCK_SYSCALLS:
        return SandboxCapability(False, None, "supported Linux architecture required")
    create_nr = _LANDLOCK_SYSCALLS[platform.machine()][0]
    libc = ctypes.CDLL(None, use_errno=True)
    libc.syscall.restype = ctypes.c_long
    try:
        abi = _syscall(libc, create_nr, 0, 0, 1)
    except OSError as exc:
        return SandboxCapability(False, None, f"Landlock unavailable (errno={exc.errno})")
    if abi < _MIN_LANDLOCK_ABI:
        return SandboxCapability(False, abi, f"Landlock ABI {_MIN_LANDLOCK_ABI}+ required")
    try:
        library = _seccomp_library()
        missing = [name for name in _DENIED_SYSCALLS
                   if library.seccomp_syscall_resolve_name(name.encode("ascii")) < 0]
    except (OSError, AttributeError) as exc:
        return SandboxCapability(False, abi, f"libseccomp unavailable ({type(exc).__name__})")
    if missing:
        return SandboxCapability(False, abi, "libseccomp cannot resolve required syscalls")
    return SandboxCapability(True, abi, None)


def default_python_runtime_roots() -> tuple[Path, ...]:
    """Read/execute roots for this interpreter, its stdlib, and shared libs.

    This deliberately includes system library directories and the current
    interpreter's site-packages.  Reviewers should treat those trees as part
    of the payload's readable runtime, not as private workspace data.
    """
    candidates = [Path(sys.executable), Path(sysconfig.get_path("stdlib")),
                  Path(sysconfig.get_path("platstdlib")),
                  Path(sysconfig.get_path("purelib")),
                  Path(sysconfig.get_path("platlib")),
                  Path(sys.prefix) / "pyvenv.cfg",
                  Path(sys.base_prefix) / "lib", Path("/lib"), Path("/lib64"),
                  Path("/usr/lib"), Path("/etc/ld.so.cache"),
                  Path("/dev/urandom")]
    roots: list[Path] = []
    for candidate in candidates:
        if candidate.exists():
            resolved = candidate.resolve(strict=True)
            if resolved not in roots:
                roots.append(resolved)
    return tuple(roots)


def _roots(paths: Sequence[Path], *, directories_only: bool,
           allow_char_device: bool = False) -> list[str]:
    roots: list[str] = []
    for raw in paths:
        path = Path(raw).expanduser()
        if not path.is_absolute() or path.is_symlink():
            raise SandboxError("sandbox roots must be absolute, existing, non-symlink paths")
        try:
            resolved = path.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise SandboxError("sandbox root is unavailable") from exc
        if directories_only and not resolved.is_dir():
            raise SandboxError("write roots must be directories")
        if not (resolved.is_dir() or resolved.is_file() or
                (allow_char_device and stat.S_ISCHR(resolved.stat().st_mode))):
            raise SandboxError("sandbox roots must be regular files or directories")
        value = str(resolved)
        if value not in roots:
            roots.append(value)
    return roots


def _validate_env(env: Mapping[str, str] | None, write_roots: list[str],
                  cwd: Path) -> dict[str, str]:
    home_root = write_roots[0] if write_roots else str(cwd)
    temporary_root = write_roots[-1] if write_roots else str(cwd)
    result = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8",
              "HOME": home_root, "TMPDIR": temporary_root,
              "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1"}
    if env is not None:
        if any(key not in _ALLOWED_ENV or type(value) is not str or "\0" in value
               for key, value in env.items()):
            raise SandboxError("environment contains an unsupported key or value")
        result.update(env)
    for key in ("HOME", "TMPDIR"):
        allowed = write_roots if write_roots else [str(cwd)]
        if not Path(result[key]).is_absolute() or str(Path(result[key]).resolve()) not in allowed:
            raise SandboxError(f"{key} must name an explicit root")
    result["PYTHONDONTWRITEBYTECODE"] = "1"
    result["PYTHONNOUSERSITE"] = "1"
    return result


def _set_limits(cpu_seconds: int, address_space_bytes: int,
                file_bytes_per_file: int) -> None:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    resource.setrlimit(resource.RLIMIT_AS,
                       (address_space_bytes, address_space_bytes))
    resource.setrlimit(resource.RLIMIT_FSIZE, (file_bytes_per_file, file_bytes_per_file))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))


def _apply_landlock(read_roots: list[str], write_roots: list[str],
                    runtime_roots: list[str]) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    libc.syscall.restype = ctypes.c_long
    libc.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong,
                           ctypes.c_ulong, ctypes.c_ulong]
    libc.prctl.restype = ctypes.c_int
    if libc.prctl(38, 1, 0, 0, 0) != 0:  # PR_SET_NO_NEW_PRIVS
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code))
    create_nr, add_nr, restrict_nr = _LANDLOCK_SYSCALLS[platform.machine()]
    attributes = _RulesetAttr(_HANDLED_FS, _HANDLED_NET)
    ruleset = _syscall(libc, create_nr, ctypes.byref(attributes),
                       ctypes.sizeof(attributes), 0)
    try:
        for roots, mode in ((read_roots, _READ_DIR),
                            (runtime_roots, _READ_DIR | _FS_EXECUTE),
                            (write_roots, _WRITE_DIR)):
            for root in roots:
                fd = os.open(root, os.O_PATH | os.O_CLOEXEC | os.O_NOFOLLOW)
                try:
                    file_mode = os.fstat(fd).st_mode
                    if stat.S_ISDIR(file_mode):
                        allowed = mode
                    elif stat.S_ISREG(file_mode):
                        allowed = mode & (_FS_READ_FILE | _FS_EXECUTE)
                    else:
                        allowed = _FS_READ_FILE
                    attr = _PathBeneathAttr(allowed, fd)
                    _syscall(libc, add_nr, ruleset, 1, ctypes.byref(attr), 0)
                finally:
                    os.close(fd)
        _syscall(libc, restrict_nr, ruleset, 0)
    finally:
        os.close(ruleset)


def _apply_seccomp(library: ctypes.CDLL) -> None:
    context = library.seccomp_init(_SCMP_ACT_ALLOW)
    if not context:
        raise OSError(errno.ENOMEM, "seccomp_init failed")
    try:
        for name in _DENIED_SYSCALLS:
            number = library.seccomp_syscall_resolve_name(name.encode("ascii"))
            if number < 0:
                raise OSError(errno.ENOSYS, "required syscall resolution failed")
            result = library.seccomp_rule_add(context, _SCMP_ACT_ERRNO, number, 0)
            if result < 0:
                raise OSError(-result, "seccomp_rule_add failed")
        result = library.seccomp_load(context)
        if result < 0:
            raise OSError(-result, "seccomp_load failed")
    finally:
        library.seccomp_release(context)


def _sealed_executable_fd(contents: bytes, expected_sha256: str) -> int:
    """Make an immutable executable copy and authenticate the bytes on the FD."""
    try:
        flags = os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING
        required_seals = (_F_SEAL_WRITE | _F_SEAL_GROW |
                          _F_SEAL_SHRINK | _F_SEAL_SEAL)
        fd = os.memfd_create("local-replay-executable", flags)
    except (AttributeError, OSError) as exc:
        raise SandboxUnavailable("sealed memfd execution unavailable") from exc
    try:
        remaining = memoryview(contents)
        while remaining:
            written = os.write(fd, remaining)
            if written <= 0:
                raise OSError(errno.EIO, "memfd write did not advance")
            remaining = remaining[written:]

        def digest_on_fd() -> str:
            digest = hashlib.sha256()
            offset = 0
            while offset < len(contents):
                chunk = os.pread(fd, min(1024 * 1024, len(contents) - offset), offset)
                if not chunk:
                    raise OSError(errno.EIO, "memfd read ended early")
                digest.update(chunk)
                offset += len(chunk)
            if os.fstat(fd).st_size != len(contents):
                raise OSError(errno.EIO, "memfd size changed")
            return digest.hexdigest()

        if digest_on_fd() != expected_sha256:
            raise SandboxError("sealed executable digest mismatch")
        fcntl.fcntl(fd, _F_ADD_SEALS, required_seals)
        if fcntl.fcntl(fd, _F_GET_SEALS) & required_seals != required_seals:
            raise SandboxUnavailable("sealed memfd seals unavailable")
        if digest_on_fd() != expected_sha256:
            raise SandboxError("sealed executable digest mismatch after sealing")
        return fd
    except BaseException as exc:
        os.close(fd)
        if isinstance(exc, OSError):
            raise SandboxUnavailable("sealed memfd preparation failed") from exc
        raise


def _child_main(status_fd: int) -> None:
    stage = "configuration"
    try:
        raw = sys.stdin.buffer.read(_MAX_CONFIG_BYTES + 1)
        if len(raw) > _MAX_CONFIG_BYTES:
            raise ValueError("configuration too large")
        config = json.loads(raw)
        null_fd = os.open("/dev/null", os.O_RDONLY | os.O_CLOEXEC)
        os.dup2(null_fd, 0)
        os.close(null_fd)
        stage = "libseccomp load"
        library = _seccomp_library()
        stage = "resource limits"
        _set_limits(config["cpu_seconds"], config["address_space_bytes"],
                    config["file_bytes_per_file"])
        stage = "Landlock"
        _apply_landlock(config["read_roots"], config["write_roots"],
                        config["runtime_roots"])
        stage = "seccomp"
        _apply_seccomp(library)
        sealed_fd = config.get("sealed_executable_fd")
        if sealed_fd is not None:
            # A shebang interpreter reopens this path after execve. Keep only
            # this executable FD inherited; status_fd still closes on exec.
            os.set_inheritable(sealed_fd, True)
        os.write(status_fd, b"READY\n")
        os.set_inheritable(status_fd, False)
        stage = "exec"
        if sealed_fd is None:
            os.execve(config["argv"][0], config["argv"], config["env"])
        else:
            os.execve(f"/proc/self/fd/{sealed_fd}",
                      [f"/proc/self/fd/{sealed_fd}", *config["argv"][1:]],
                      config["env"])
    except BaseException as exc:
        code = exc.errno if isinstance(exc, OSError) else None
        # Do not send exception text, arguments, paths, or environment values.
        try:
            os.write(status_fd, f"ERROR {stage} {code}\n".encode("ascii"))
        except OSError:
            pass
    os._exit(78)


def _terminate_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        process.kill()
    except ProcessLookupError:
        pass
    process.wait()


def run_sandboxed(
    *, argv: Sequence[str], cwd: Path, read_roots: Sequence[Path],
    write_roots: Sequence[Path], runtime_roots: Sequence[Path] = (),
    stdout_path: Path, stderr_path: Path, timeout_seconds: float,
    cpu_seconds: int = 10, address_space_bytes: int = 512 * 1024 * 1024,
    file_bytes_per_file: int = 16 * 1024 * 1024,
    env: Mapping[str, str] | None = None,
    sealed_executable_bytes: bytes | None = None,
    sealed_executable_sha256: str | None = None,
) -> SandboxResult:
    """Run one process; fail closed if restrictions cannot be installed.

    ``argv[0]`` must be an absolute executable (or the original absolute name
    of a supplied sealed executable). In sealed mode, the parent copies at
    most 16 MiB into a sealed memfd and the child executes that FD after
    restrictions. Neither streams nor setup
    errors are returned as raw text; streams are private new files at the
    requested paths.  The caller must keep them private and inspect them as
    untrusted output.  A wall deadline kills the child's process group.
    """
    capability = probe_sandbox()
    if not capability.available:
        raise SandboxUnavailable(capability.reason or "sandbox unavailable")
    if (not argv or any(type(part) is not str or "\0" in part for part in argv)
            or not Path(argv[0]).is_absolute()):
        raise SandboxError("argv requires an absolute executable and string arguments")
    if sealed_executable_bytes is None:
        if sealed_executable_sha256 is not None:
            raise SandboxError("sealed executable bytes and digest must be supplied together")
    elif (type(sealed_executable_bytes) is not bytes or
          not 0 < len(sealed_executable_bytes) <= _MAX_SEALED_EXECUTABLE_BYTES or
          type(sealed_executable_sha256) is not str or
          len(sealed_executable_sha256) != 64 or
          any(char not in "0123456789abcdef" for char in sealed_executable_sha256)):
        raise SandboxError("invalid sealed executable bytes or SHA-256 digest")
    if (not math.isfinite(timeout_seconds) or timeout_seconds <= 0 or
            type(cpu_seconds) is not int or cpu_seconds < 1 or
            type(address_space_bytes) is not int or
            address_space_bytes < 64 * 1024 * 1024 or
            type(file_bytes_per_file) is not int or file_bytes_per_file < 4096):
        raise SandboxError("invalid wall or resource limit")
    cwd_path = Path(cwd).expanduser()
    if not cwd_path.is_absolute() or cwd_path.is_symlink() or not cwd_path.is_dir():
        raise SandboxError("cwd must be an absolute, existing, non-symlink directory")
    cwd_path = cwd_path.resolve(strict=True)
    reads = _roots(read_roots, directories_only=False)
    writes = _roots(write_roots, directories_only=True)
    runtimes = _roots(runtime_roots, directories_only=False, allow_char_device=True)
    for writable in map(Path, writes):
        if cwd_path == writable or cwd_path.is_relative_to(writable):
            raise SandboxError("cwd must stay outside write roots")
        if any(root == writable or root.is_relative_to(writable)
               for root in map(Path, reads + runtimes)):
            raise SandboxError("read and runtime roots must stay outside write roots")
    child_env = _validate_env(env, writes, cwd_path)
    config = {"argv": list(argv), "read_roots": reads, "write_roots": writes,
              "runtime_roots": runtimes, "env": child_env,
              "cpu_seconds": cpu_seconds,
              "address_space_bytes": address_space_bytes,
              "file_bytes_per_file": file_bytes_per_file}
    executable_fd = -1
    if sealed_executable_bytes is not None:
        assert sealed_executable_sha256 is not None
        executable_fd = _sealed_executable_fd(sealed_executable_bytes,
                                               sealed_executable_sha256)
        config["sealed_executable_fd"] = executable_fd
    try:
        encoded = json.dumps(config, separators=(",", ":")).encode("utf-8")
        if len(encoded) > _MAX_CONFIG_BYTES:
            raise SandboxError("sandbox configuration too large")
    except BaseException:
        if executable_fd >= 0:
            os.close(executable_fd)
        raise
    stdout_path = Path(stdout_path)
    stderr_path = Path(stderr_path)
    if stdout_path == stderr_path or not stdout_path.is_absolute() or not stderr_path.is_absolute():
        if executable_fd >= 0:
            os.close(executable_fd)
        raise SandboxError("distinct absolute stdout and stderr paths are required")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
    try:
        stdout_fd = os.open(stdout_path, flags, 0o600)
    except BaseException:
        if executable_fd >= 0:
            os.close(executable_fd)
        raise
    try:
        stderr_fd = os.open(stderr_path, flags, 0o600)
    except BaseException:
        os.close(stdout_fd)
        if executable_fd >= 0:
            os.close(executable_fd)
        raise
    try:
        read_fd, status_fd = os.pipe2(os.O_CLOEXEC)
    except BaseException:
        os.close(stdout_fd)
        os.close(stderr_fd)
        if executable_fd >= 0:
            os.close(executable_fd)
        raise
    process: subprocess.Popen[bytes] | None = None
    started = time.monotonic()
    try:
        with os.fdopen(stdout_fd, "wb") as stdout, os.fdopen(stderr_fd, "wb") as stderr:
            process = subprocess.Popen(
                [sys.executable, "-I", "-S", str(Path(__file__).resolve()),
                 "--child", str(status_fd)],
                cwd=cwd_path, env=child_env, stdin=subprocess.PIPE,
                stdout=stdout, stderr=stderr, close_fds=True,
                pass_fds=((status_fd, executable_fd) if executable_fd >= 0
                          else (status_fd,)), start_new_session=True,
            )
            os.close(status_fd)
            status_fd = -1
            assert process.stdin is not None
            process.stdin.write(encoded)
            process.stdin.close()
            deadline = started + timeout_seconds
            status = bytearray()
            timed_out = False
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    break
                readable, _, _ = select.select([read_fd], [], [], remaining)
                if not readable:
                    timed_out = True
                    break
                chunk = os.read(read_fd, 4096)
                if not chunk:
                    break
                status.extend(chunk)
                if len(status) > 256:
                    break
            if timed_out:
                _terminate_group(process)
                return SandboxResult(None, True, "sandbox setup timed out",
                                     capability.landlock_abi,
                                     time.monotonic() - started)
            if status != b"READY\n":
                try:
                    process.wait(timeout=max(0.01, deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    _terminate_group(process)
                detail = status.decode("ascii", errors="replace").strip()
                return SandboxResult(None, False, detail or "sandbox setup failed",
                                     capability.landlock_abi, time.monotonic() - started)
            try:
                exit_code = process.wait(timeout=max(0.01, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                _terminate_group(process)
                return SandboxResult(None, True, None, capability.landlock_abi,
                                     time.monotonic() - started,
                                     sealed_executable_sha256)
            return SandboxResult(exit_code, False, None, capability.landlock_abi,
                                 time.monotonic() - started,
                                 sealed_executable_sha256)
    except BaseException:
        if process is not None and process.poll() is None:
            _terminate_group(process)
        raise
    finally:
        os.close(read_fd)
        if status_fd >= 0:
            os.close(status_fd)
        if executable_fd >= 0:
            os.close(executable_fd)


if __name__ == "__main__" and len(sys.argv) == 3 and sys.argv[1] == "--child":
    _child_main(int(sys.argv[2]))
