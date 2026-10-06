#!/usr/bin/env python3
"""Independent local CLI contract checks; fixtures stay inside /trial."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
import unittest

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / 'backup.py'
CALLS = []
LIMITATIONS = []


def tree(root):
    result = {}
    if not root.exists():
        return None
    for parent, directories, files in os.walk(root, followlinks=False):
        for name in directories + files:
            path = Path(parent) / name
            mode = path.lstat().st_mode
            key = path.relative_to(root).as_posix()
            if stat.S_ISLNK(mode):
                result[key] = ('link', os.readlink(path))
            elif stat.S_ISDIR(mode):
                result[key] = ('dir',)
            elif stat.S_ISREG(mode):
                result[key] = ('file', path.read_bytes())
            else:
                result[key] = ('special', stat.S_IFMT(mode))
    return result


def byte_total(root):
    return sum((Path(parent) / name).lstat().st_size
               for parent, _, names in os.walk(root, followlinks=False)
               for name in names if stat.S_ISREG((Path(parent) / name).lstat().st_mode))


def record(argv, code, stdout, stderr, elapsed, timed_out=False, **extra):
    CALLS.append(dict(argv=argv, exit_code=code, timed_out=timed_out,
                      timeout_seconds=30, stdout=stdout.decode('utf-8', 'replace'),
                      stderr=stderr.decode('utf-8', 'replace'), elapsed_seconds=elapsed,
                      stdout_sha256=hashlib.sha256(stdout).hexdigest(),
                      stderr_sha256=hashlib.sha256(stderr).hexdigest(), **extra))


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='backup-test-', dir=HERE / 'evidence')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'source'
        self.repo = self.root / 'repo'
        self.dest = self.root / 'dest'
        self.source.mkdir()
        (self.source / 'vacío ñ').mkdir()
        (self.source / 'árbol con espacios').mkdir()
        (self.source / 'árbol con espacios' / 'empty child').mkdir()
        (self.source / 'árbol con espacios' / '文書.txt').write_bytes(bytes(range(256)) * 7)
        (self.source / 'zero').write_bytes(b'')
        (self.source / 'line\nbreak').write_bytes(b'\x00\xff arbitrary\n')

    def cli(self, command, *, good=True, identity='one', repo=None, source=None,
            dest=None, limit=None, raw=()):
        argv = [sys.executable, str(SCRIPT), command, '--repo', str(repo or self.repo)]
        if command != 'list':
            argv += ['--id', identity]
        if command == 'create':
            argv += ['--source', str(source or self.source)]
        if command == 'restore':
            argv += ['--dest', str(dest or self.dest)]
        if limit is not None:
            argv += ['--max-bytes', str(limit)]
        argv += list(raw)
        start = time.monotonic()
        try:
            p = subprocess.run(argv, capture_output=True, timeout=30)
        except subprocess.TimeoutExpired as e:
            record(argv, None, e.stdout or b'', e.stderr or b'', time.monotonic()-start, True)
            raise AssertionError('CLI timed out') from e
        record(argv, p.returncode, p.stdout, p.stderr, time.monotonic()-start)
        if not good:
            self.assertNotEqual(p.returncode, 0, p.stdout)
            self.assertEqual(p.stdout, b'', 'failure must never emit success stdout')
            return None
        self.assertEqual(p.returncode, 0, p.stderr.decode('utf-8', 'replace'))
        self.assertEqual(p.stderr, b'')
        value = json.loads(p.stdout)
        self.assertIsInstance(value, dict)
        expected = ({'snapshots': value.get('snapshots')} if command == 'list' else
                    {'id': identity, 'valid': True} if command == 'verify' else {'id': identity})
        self.assertEqual(value, expected)
        self.assertEqual(p.stdout.count(b'\n'), 1)
        return value

    def assert_clean(self):
        if (self.repo / 'staging').exists():
            self.assertEqual(list((self.repo / 'staging').iterdir()), [])

    def test_roundtrip_autosufficient_and_source_unchanged(self):
        before = tree(self.source)
        self.cli('create')
        self.assertEqual(tree(self.source), before)
        self.cli('verify')
        shutil.rmtree(self.source)
        self.cli('restore')
        self.assertEqual(tree(self.dest), before)
        self.assertEqual(self.cli('list'), {'snapshots': ['one']})

    def test_empty_source_and_empty_existing_destination(self):
        shutil.rmtree(self.source)
        self.source.mkdir()
        self.dest.mkdir()
        self.cli('create')
        self.cli('restore')
        self.assertEqual(tree(self.dest), {})
        self.cli('verify')

    def test_new_list_and_missing_id(self):
        self.assertEqual(self.cli('list'), {'snapshots': []})
        self.repo.mkdir()
        self.assertEqual(self.cli('list'), {'snapshots': []})
        self.cli('verify', good=False)
        self.cli('restore', good=False)
        self.assertFalse(self.dest.exists())

    def test_ids_and_no_overwrite(self):
        for identity in ('', '.', '../x', 'a/b', '-x', 'a.b', 'ñ', 'x'*65):
            with self.subTest(identity=identity):
                self.cli('create', identity=identity, good=False)
                self.assertFalse(self.repo.exists())
        self.cli('create', identity='a' + '_-Z9'*15)
        before = tree(self.repo)
        (self.source / 'new').write_bytes(b'changed source')
        self.cli('create', identity='a' + '_-Z9'*15, good=False)
        self.assertEqual(tree(self.repo), before)

    def test_successive_snapshots_sorted_and_exact(self):
        first = tree(self.source)
        self.cli('create', identity='z')
        (self.source / 'zero').unlink()
        (self.source / 'line\nbreak').write_bytes(b'changed')
        (self.source / 'added').write_bytes(b'added')
        second = tree(self.source)
        self.cli('create', identity='a')
        self.assertEqual(self.cli('list'), {'snapshots': ['a', 'z']})
        for identity, expected in [('a', second), ('z', first)]:
            self.cli('restore', identity=identity, dest=self.root / identity)
            self.assertEqual(tree(self.root / identity), expected)

    def test_nonempty_destination_is_unchanged(self):
        self.cli('create')
        self.dest.mkdir()
        (self.dest / 'protected').write_bytes(b'protected\x00\xff')
        before = tree(self.dest)
        self.cli('restore', good=False)
        self.assertEqual(tree(self.dest), before)
        self.assertFalse(list(self.root.glob('.backup-restore-*')))

    def test_overlap_and_unnormalized_symlink(self):
        before = tree(self.source)
        for repo in (self.source, self.source / 'nested', self.root):
            self.cli('create', repo=repo, good=False)
            self.assertEqual(tree(self.source), before)
        self.cli('create')
        old = tree(self.repo)
        for dest in (self.repo, self.repo / 'nested', self.root):
            self.cli('restore', dest=dest, good=False)
            self.assertEqual(tree(self.repo), old)
        (self.root / 'link').symlink_to(self.source, target_is_directory=True)
        self.cli('create', source=str(self.root / 'link') + '/../source', good=False)

    def test_symlinks_in_all_managed_paths(self):
        outside = self.root / 'outside'
        outside.write_bytes(b'leave alone')
        (self.source / 'unsafe').symlink_to(outside)
        self.cli('create', good=False)
        self.assertFalse(self.repo.exists())
        (self.source / 'unsafe').unlink()
        self.cli('create')
        linkrepo = self.root / 'linkrepo'
        linkrepo.symlink_to(self.repo, target_is_directory=True)
        self.cli('list', repo=linkrepo, good=False)
        self.dest.symlink_to(self.source, target_is_directory=True)
        old = tree(self.source)
        self.cli('restore', good=False)
        self.assertEqual(tree(self.source), old)
        self.dest.unlink()
        (self.repo / 'staging' / 'unsafe').symlink_to(outside)
        self.cli('create', identity='two', limit=100000, good=False)
        self.assertTrue((self.repo / 'staging' / 'unsafe').is_symlink())
        (self.repo / 'staging' / 'unsafe').unlink()
        path = self.repo / 'snapshots' / 'one' / 'data' / 'zero'
        path.unlink()
        path.symlink_to(outside)
        for command in ('verify', 'restore', 'list'):
            self.cli(command, good=False)
        self.assertEqual(outside.read_bytes(), b'leave alone')

    def test_special_objects_are_rejected(self):
        os.mkfifo(self.source / 'fifo')
        self.cli('create', good=False)
        (self.source / 'fifo').unlink()
        sock = socket.socket(socket.AF_UNIX)
        self.addCleanup(sock.close)
        try:
            sock.bind(str(self.source / 'socket'))
        except PermissionError as error:
            LIMITATIONS.append('Socket fixture unavailable in sandbox: ' + str(error))
        else:
            self.cli('create', good=False)
            (self.source / 'socket').unlink()
        self.cli('create')
        os.mkfifo(self.repo / 'snapshots' / 'one' / 'data' / 'fifo')
        self.cli('verify', good=False)
        self.cli('restore', good=False)
        self.cli('create', identity='two', good=False)
        self.assertFalse(self.dest.exists())
        (self.repo / 'snapshots' / 'one' / 'data' / 'fifo').unlink()
        self.dest.mkdir()
        os.mkfifo(self.dest / 'fifo')
        self.cli('restore', good=False)
        self.assertTrue(stat.S_ISFIFO((self.dest / 'fifo').lstat().st_mode))

    def test_corrupt_or_missing_every_regular_snapshot_file(self):
        self.cli('create')
        snapshot = self.repo / 'snapshots' / 'one'
        files = [p.relative_to(snapshot) for p in snapshot.rglob('*') if p.is_file()]
        for name in files:
            for action in ('change', 'delete'):
                with self.subTest(name=str(name), action=action):
                    damaged = self.root / 'damaged'
                    shutil.copytree(self.repo, damaged)
                    path = damaged / 'snapshots' / 'one' / name
                    if action == 'delete':
                        path.unlink()
                    else:
                        raw = path.read_bytes()
                        path.write_bytes(bytes([raw[0] ^ 1]) + raw[1:] if raw else b'x')
                    self.cli('verify', repo=damaged, good=False)
                    self.cli('restore', repo=damaged, good=False)
                    self.assertFalse(self.dest.exists())
                    self.assertEqual(self.cli('list', repo=damaged), {'snapshots': []})
                    shutil.rmtree(damaged)

    def test_quota_high_preserves_previous_snapshot(self):
        self.cli('create', identity='base')
        previous = tree(self.repo / 'snapshots' / 'base')
        self.cli('create', limit=100000)
        self.assertLessEqual(byte_total(self.repo), 100000)
        self.assertEqual(tree(self.repo / 'snapshots' / 'base'), previous)
        self.cli('verify')
        self.cli('restore')
        self.assertEqual(tree(self.dest), tree(self.source))
        self.assert_clean()

    def test_quota_exact_boundary_and_one_byte_less(self):
        self.cli('create')
        needed = byte_total(self.repo)
        shutil.rmtree(self.repo)
        self.cli('create', limit=needed-1, good=False)
        self.assertEqual(byte_total(self.repo), 0)
        self.assertEqual(self.cli('list'), {'snapshots': []})
        self.assert_clean()
        self.cli('create', limit=needed)
        self.assertEqual(byte_total(self.repo), needed)
        self.cli('verify')
        self.assert_clean()

    def test_quota_below_existing_and_failure_without_residue(self):
        self.cli('create', identity='base')
        previous = tree(self.repo)
        used = byte_total(self.repo)
        for _ in range(2):
            self.cli('create', limit=used-1, good=False)
            self.assertEqual(byte_total(self.repo), used)
            self.assertEqual(tree(self.repo), previous)
            self.assert_clean()
        # Equal to existing bytes: payload fits neither its own bytes nor metadata.
        self.cli('create', limit=used, good=False)
        self.assertEqual(tree(self.repo), previous)
        self.cli('verify', identity='base')
        self.cli('create', limit=used+100000)
        self.assertLessEqual(byte_total(self.repo), used+100000)

    def test_quota_includes_metadata_and_lock(self):
        payload = byte_total(self.source)
        self.cli('create', limit=payload, good=False)
        self.assertEqual(byte_total(self.repo), 0)
        self.assert_clean()
        self.cli('create')
        needed = byte_total(self.repo)
        shutil.rmtree(self.repo)
        self.repo.mkdir()
        (self.repo / '.lock').write_bytes(b'persistent lock metadata')
        locksize = (self.repo / '.lock').stat().st_size
        self.cli('create', limit=needed, good=False)
        self.assertEqual(byte_total(self.repo), locksize)
        self.assert_clean()
        self.cli('create', limit=needed+locksize)
        self.assertEqual(byte_total(self.repo), needed+locksize)
        self.assertEqual((self.repo / '.lock').read_bytes(), b'persistent lock metadata')
        self.cli('verify')

    def test_quota_zero_empty_tree_and_invalid_N(self):
        before = tree(self.source)
        for limit in ('-1', '1.5', 'NaN', 'abc', '', '+10', '1_000'):
            self.cli('create', limit=limit, good=False)
            self.assertFalse(self.repo.exists())
            self.assertEqual(tree(self.source), before)
        shutil.rmtree(self.source)
        self.source.mkdir()
        self.cli('create', limit=0, good=False)
        self.assertEqual(byte_total(self.repo), 0)
        self.assert_clean()
        self.cli('create', limit=1000)
        self.cli('verify')

    def test_quota_counts_extra_regular_bytes_in_previous_snapshot(self):
        self.cli('create', identity='base')
        (self.repo / 'snapshots' / 'base' / 'extra').write_bytes(b'x'*5000)
        before = tree(self.repo)
        used = byte_total(self.repo)
        self.cli('create', limit=used, good=False)
        self.assertEqual(tree(self.repo), before)
        self.cli('create', limit=used+100000)
        self.assertLessEqual(byte_total(self.repo), used+100000)
        self.assertEqual(tree(self.repo / 'snapshots' / 'base'),
                         {k.removeprefix('snapshots/base/'):v for k,v in before.items()
                          if k.startswith('snapshots/base/')})
        self.cli('verify', identity='base', good=False)
        self.cli('verify')

    def test_sigkill_retry_and_previous_snapshot(self):
        self.cli('create', identity='base')
        old = tree(self.repo / 'snapshots' / 'base')
        big = self.source / 'big'
        with big.open('wb') as out:
            out.truncate(128 * 1024 * 1024)
        argv = [sys.executable, str(SCRIPT), 'create', '--source', str(self.source),
                '--repo', str(self.repo), '--id', 'interrupted']
        start = time.monotonic()
        p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stopped = False
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and p.poll() is None:
                stages = list((self.repo / 'staging').glob('create-*/data/big'))
                if stages and stages[0].stat().st_size > 0:
                    os.kill(p.pid, signal.SIGSTOP)
                    stopped = True
                    break
                time.sleep(0.001)
            self.assertTrue(stopped, 'did not observe active copy before deadline')
            self.assertFalse((self.repo / 'snapshots' / 'interrupted').exists())
        finally:
            if p.poll() is None:
                p.kill()
            stdout, stderr = p.communicate(timeout=10)
            record(argv, p.returncode, stdout, stderr, time.monotonic()-start,
                   injected_signal='SIGSTOP then SIGKILL', observed_active_copy=stopped)
        self.assertEqual(p.returncode, -signal.SIGKILL)
        self.assertEqual(self.cli('list'), {'snapshots': ['base']})
        self.cli('verify', identity='base')
        self.assertEqual(tree(self.repo / 'snapshots' / 'base'), old)
        self.cli('create', identity='interrupted', limit=256*1024*1024)
        self.cli('verify', identity='interrupted')
        self.assertLessEqual(byte_total(self.repo), 256*1024*1024)
        self.assert_clean()

    def test_concurrent_creates_respect_one_shared_budget(self):
        self.cli('create')
        one_size = byte_total(self.repo)
        shutil.rmtree(self.repo)
        processes = []
        for identity in ('aaa', 'bbb'):
            argv = [sys.executable, str(SCRIPT), 'create', '--source', str(self.source),
                    '--repo', str(self.repo), '--id', identity, '--max-bytes', str(one_size)]
            processes.append((argv, time.monotonic(), subprocess.Popen(
                argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)))
        codes = []
        for argv, start, p in processes:
            try:
                stdout, stderr = p.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                p.kill()
                stdout, stderr = p.communicate()
                record(argv, p.returncode, stdout, stderr, time.monotonic()-start, True)
                self.fail('concurrent command timed out')
            record(argv, p.returncode, stdout, stderr, time.monotonic()-start)
            codes.append(p.returncode)
            if p.returncode == 0:
                self.assertEqual(json.loads(stdout), {'id': argv[argv.index('--id')+1]})
            else:
                self.assertEqual(stdout, b'')
        self.assertEqual(sum(code == 0 for code in codes), 1, codes)
        self.assertEqual(byte_total(self.repo), one_size)
        self.assertEqual(len(self.cli('list')['snapshots']), 1)
        self.assert_clean()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ContractTests)
    start = time.monotonic()
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    summary = dict(tests_run=result.testsRun, failures=len(result.failures),
                   errors=len(result.errors), passed=result.wasSuccessful(),
                   elapsed_seconds=time.monotonic()-start,
                   backup_sha256=hashlib.sha256(SCRIPT.read_bytes()).hexdigest(),
                   suite_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   limitations=LIMITATIONS,
                   adverse_results=[dict(test=str(t), traceback=trace)
                                    for t, trace in result.failures + result.errors])
    (args.output / 'calls.json').write_text(json.dumps(CALLS, indent=2), encoding='utf-8')
    (args.output / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, sort_keys=True))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())
