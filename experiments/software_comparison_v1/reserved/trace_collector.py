"""Trusted root collector for one uncredentialed, UID65534 trace probe.

Mounted only in evaluator containers, never in native author/reviewer roles.
The host-owned output directory is mode0700 UID1000; the subject UID65534
cannot enter, chmod, unlink or alter it. Root needs DAC_OVERRIDE to write there.
strace alone drops subject UID/GID via -u nobody; SETUID/SETGID/SYS_PTRACE are
scoped to this container. The main agent and ordinary tests retain their policy.
No expected result, ledger, model, provider, profile or daemon is available here.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import stat
import subprocess
import time

OUT = Path('/collector-output')
CAP = 2_097_152


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def kill_group(process):
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def main():
    info = OUT.stat()
    if os.getuid() != 0 or info.st_uid != 1000 or stat.S_IMODE(info.st_mode) != 0o700:
        raise RuntimeError('collector requires root and private UID1000 output directory')
    config = json.loads(Path('/collector-input/config.json').read_text())
    argv = config['argv']
    if (type(argv) is not list or len(argv) < 5 or argv[:4] != [
            '/opt/specorganon/venv/bin/python', '-E', '-s', '-B']
            or argv[4] != '/input/delivery/treemap.py'
            or any(type(a) is not str or '\0' in a for a in argv)):
        raise RuntimeError('invalid fixed probe subject argv')
    trace = OUT / 'trace.bin'
    # Reserve a root-owned regular trace before strace opens it. The subject
    # cannot reach OUT, regardless of permissions on this individual file.
    fd = os.open(trace, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    os.close(fd)
    command = ['/usr/bin/strace', '--kill-on-exit', '-u', 'nobody', '-f', '-qq',
               '-yy', '-s', '4096', '-e', 'trace=%file,%network,%process,exit_group',
               '-o', str(trace), *argv]
    streams = {}
    sizes = {'stdout': 0, 'stderr': 0}
    truncated = []
    timed_out = False
    began = time.monotonic()
    selector = selectors.DefaultSelector()
    process = None
    try:
        for name in sizes:
            fd = os.open(OUT / (name + '.bin'), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
            streams[name] = os.fdopen(fd, 'wb')
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, start_new_session=True,
                                   cwd='/input/delivery', close_fds=True,
                                   env={'HOME': '/tmp', 'TMPDIR': '/tmp', 'PATH': '/usr/bin:/bin',
                                        'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1'})
        for name in sizes:
            pipe = getattr(process, name)
            os.set_blocking(pipe.fileno(), False)
            selector.register(pipe, selectors.EVENT_READ, name)
        stopped = None
        while selector.get_map() or process.poll() is None:
            now = time.monotonic()
            if stopped is None and now - began >= 3:
                timed_out = True
                stopped = now
                kill_group(process)
            if trace.stat().st_size > CAP and 'trace' not in truncated:
                truncated.append('trace')
                if stopped is None:
                    stopped = now
                    kill_group(process)
            if stopped is not None and now - stopped >= 2:
                for key in list(selector.get_map().values()):
                    selector.unregister(key.fileobj)
                    key.fileobj.close()
                break
            for key, _ in selector.select(.02):
                block = os.read(key.fd, 65536)
                if not block:
                    selector.unregister(key.fileobj)
                    key.fileobj.close()
                    continue
                name = key.data
                room = CAP - sizes[name]
                streams[name].write(block[:room])
                sizes[name] += min(len(block), room)
                if len(block) > room and name not in truncated:
                    truncated.append(name)
                    if stopped is None:
                        stopped = time.monotonic()
                        kill_group(process)
        code = process.wait(timeout=2)
    finally:
        if process is not None:
            kill_group(process)
            process.wait(timeout=2)
            for pipe in (process.stdout, process.stderr):
                if not pipe.closed:
                    pipe.close()
        selector.close()
        for stream in streams.values():
            stream.flush()
            os.fsync(stream.fileno())
            stream.close()
    if trace.stat().st_size > CAP:
        with trace.open('r+b') as log:
            log.truncate(CAP)
        if 'trace' not in truncated:
            truncated.append('trace')
    observed = {}
    for name in ['stdout', 'stderr', 'trace']:
        path = OUT / (name + '.bin')
        mode = path.lstat()
        if not stat.S_ISREG(mode.st_mode) or mode.st_nlink != 1 or mode.st_uid != 0:
            raise RuntimeError('collector output identity changed')
        raw = path.read_bytes()
        if len(raw) > CAP:
            raise RuntimeError('collector output cap exceeded')
        observed[name] = {'bytes': len(raw), 'sha256': digest(raw)}
    # Packet is produced only by this root process. Subject stdout/stderr have
    # separate pipes and cannot write /proc/1/fd/1 across this UID boundary.
    print(json.dumps({'schema': 1, 'subject_argv': argv, 'tracer_argv': command,
                      'subject_uid': 65534, 'subject_gid': 65534,
                      'exit_code': code, 'timed_out': timed_out,
                      'truncated_streams': truncated, 'duration_seconds': time.monotonic() - began,
                      'streams': observed}), flush=True)


if __name__ == '__main__':
    main()
