"""Contract tests against the actual CLI, using only private synthetic data."""

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


ROOT = Path(__file__).resolve().parents[1]
PROGRAM = ROOT / "solution" / "backup.py"
RUNS = []


def tree_bytes(root):
    return {str(p.relative_to(root)): ("dir" if p.is_dir() else p.read_bytes())
            for p in root.rglob("*")}


def repository_size(root):
    # Independent measurement, not the implementation's accounting helper.
    total = 0
    for directory, _, files in os.walk(root, followlinks=False):
        for name in files:
            metadata = os.lstat(os.path.join(directory, name))
            if stat.S_ISREG(metadata.st_mode):
                total += metadata.st_size
    return total


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="backup-test-", dir=ROOT / "validation")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / "fuente ü con espacios"
        self.source.mkdir()
        (self.source / "vacío").mkdir()
        (self.source / "nivel").mkdir()
        (self.source / "nivel" / "子 archivo.bin").write_bytes(bytes(range(256)) * 31 + b"\x00\xff\r\n")
        (self.source / "cero").write_bytes(b"")
        (self.source / "texto.txt").write_bytes("mañana\n".encode())
        self.repo = self.base / "repo"
        self.dest = self.base / "destino"

    def cli(self, *args, ok=True, expected=None):
        argv = [sys.executable, str(PROGRAM), *map(str, args)]
        started = time.monotonic()
        result = subprocess.run(argv, capture_output=True, timeout=20)
        RUNS.append({"argv": argv, "exit_code": result.returncode, "timed_out": False,
                     "stdout": result.stdout.decode(), "stderr": result.stderr.decode(),
                     "elapsed_seconds": time.monotonic() - started})
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr)
            value = json.loads(result.stdout)
            self.assertIsInstance(value, dict)
            self.assertEqual(result.stderr, b"")
            if expected is not None:
                self.assertEqual(value, expected)
            return value
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"", "a failed operation must not print success")
        self.assertTrue(result.stderr)

    def create(self, name="one", max_bytes=None):
        extra = [] if max_bytes is None else ["--max-bytes", str(max_bytes)]
        return self.cli("create", "--source", self.source, "--repo", self.repo,
                        "--id", name, *extra, expected={"id": name})

    def verify(self, name="one", ok=True):
        return self.cli("verify", "--repo", self.repo, "--id", name, ok=ok,
                        expected={"id": name, "valid": True} if ok else None)

    def restore(self, name="one", ok=True, dest=None):
        return self.cli("restore", "--repo", self.repo, "--id", name,
                        "--dest", dest or self.dest, ok=ok, expected={"id": name} if ok else None)

    def test_roundtrip_exact_self_contained(self):
        before = tree_bytes(self.source)
        self.create()
        self.assertEqual(tree_bytes(self.source), before)
        shutil.rmtree(self.source)
        self.verify()
        self.restore()
        self.assertEqual(tree_bytes(self.dest), before)
        self.cli("list", "--repo", self.repo, expected={"snapshots": ["one"]})

    def test_empty_source_and_existing_empty_destination(self):
        shutil.rmtree(self.source)
        self.source.mkdir()
        self.create()
        self.dest.mkdir()
        self.restore()
        self.assertEqual(tree_bytes(self.dest), {})

    def test_multiple_versions_and_sorted_list(self):
        first = tree_bytes(self.source)
        self.create("z-last")
        (self.source / "texto.txt").unlink()
        (self.source / "cero").write_bytes(b"changed")
        (self.source / "new dir").mkdir()
        (self.source / "new dir" / "new").write_bytes(b"new")
        second = tree_bytes(self.source)
        self.create("A_first")
        self.restore("z-last")
        self.assertEqual(tree_bytes(self.dest), first)
        self.restore("A_first", dest=self.base / "second")
        self.assertEqual(tree_bytes(self.base / "second"), second)
        self.cli("list", "--repo", self.repo, expected={"snapshots": ["A_first", "z-last"]})

    def test_new_and_missing_repository(self):
        self.verify(ok=False)
        self.restore(ok=False)
        self.assertFalse(self.dest.exists())
        self.cli("list", "--repo", self.repo, expected={"snapshots": []})
        self.verify(ok=False)
        self.restore(ok=False)

    def test_invalid_ids_all_commands(self):
        for name in ("", "../x", "a/b", ".", "-foo", "ñ", "x" * 65, "a\n"):
            for command in ("create", "verify", "restore"):
                with self.subTest(name=name, command=command):
                    args = [command, "--repo", self.repo, "--id", name]
                    if command == "create":
                        args += ["--source", self.source]
                    if command == "restore":
                        args += ["--dest", self.dest]
                    self.cli(*args, ok=False)
        self.assertFalse(self.repo.exists())

    def test_boundary_valid_ids(self):
        self.create("x" * 64)
        self.verify("x" * 64)
        self.create("0")

    def test_duplicate_id_no_overwrite(self):
        self.create()
        original = tree_bytes(self.repo / "snapshots")
        (self.source / "cero").write_bytes(b"changed")
        self.cli("create", "--source", self.source, "--repo", self.repo, "--id", "one", ok=False)
        self.assertEqual(tree_bytes(self.repo / "snapshots"), original)
        self.verify()

    def test_nonempty_destination_unchanged(self):
        self.create()
        self.dest.mkdir()
        (self.dest / "keep").write_bytes(b"do not touch\x00")
        (self.dest / "empty").mkdir()
        before = tree_bytes(self.dest)
        self.restore(ok=False)
        self.assertEqual(tree_bytes(self.dest), before)

    def test_regular_file_destination_unchanged(self):
        self.create()
        self.dest.write_bytes(b"protected")
        self.restore(ok=False)
        self.assertEqual(self.dest.read_bytes(), b"protected")

    def test_source_repository_overlap(self):
        for repo in (self.source, self.source / "nested", self.base):
            with self.subTest(repo=repo):
                before = tree_bytes(self.source)
                self.cli("create", "--source", self.source, "--repo", repo, "--id", "x", ok=False)
                self.assertEqual(tree_bytes(self.source), before)

    def test_restore_repository_overlap(self):
        self.create()
        before = tree_bytes(self.repo)
        self.restore(ok=False, dest=self.repo / "out")
        self.restore(ok=False, dest=self.base)
        self.assertEqual(tree_bytes(self.repo), before)

    def test_source_symlinks_and_ancestors(self):
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "keep").write_bytes(b"secret test fixture")
        for target in (outside, outside / "keep", outside / "missing"):
            link = self.source / "link"
            link.symlink_to(target)
            self.cli("create", "--source", self.source, "--repo", self.repo, "--id", "x", ok=False)
            link.unlink()
        ancestor = self.base / "ancestor"
        ancestor.symlink_to(self.source, target_is_directory=True)
        self.cli("create", "--source", ancestor, "--repo", self.repo, "--id", "x", ok=False)
        self.cli("create", "--source", str(ancestor) + "/../" + self.source.name,
                 "--repo", self.repo, "--id", "x", ok=False)
        self.assertFalse(self.repo.exists())
        self.assertEqual((outside / "keep").read_bytes(), b"secret test fixture")

    def test_repo_symlink_and_nested_symlink(self):
        self.create()
        alias = self.base / "alias"
        alias.symlink_to(self.repo, target_is_directory=True)
        for command in ("list", "verify", "restore", "create"):
            args = [command, "--repo", alias]
            if command != "list":
                args += ["--id", "one"]
            if command == "create":
                args += ["--source", self.source]
            if command == "restore":
                args += ["--dest", self.dest]
            self.cli(*args, ok=False)
        (self.repo / ".staging" / "unsafe").symlink_to(self.source)
        self.cli("list", "--repo", self.repo, ok=False)
        self.verify(ok=False)

    def test_destination_symlink_and_ancestor(self):
        self.create()
        outside = self.base / "outside"
        outside.mkdir()
        self.dest.symlink_to(outside, target_is_directory=True)
        self.restore(ok=False)
        self.restore(ok=False, dest=self.dest / "child")
        self.assertEqual(tree_bytes(outside), {})

    def test_special_files_source_repo_dest_snapshot(self):
        fifo = self.source / "fifo"
        os.mkfifo(fifo)
        self.cli("create", "--source", self.source, "--repo", self.repo, "--id", "x", ok=False)
        fifo.unlink()
        self.create()
        os.mkfifo(self.dest)
        self.restore(ok=False)
        self.dest.unlink()
        os.mkfifo(self.repo / "bad")
        self.verify(ok=False)
        self.cli("list", "--repo", self.repo, ok=False)
        (self.repo / "bad").unlink()
        os.mkfifo(self.repo / "snapshots" / "one" / "bad")
        self.verify(ok=False)
        self.restore(ok=False)

    def test_socket_source_when_sandbox_allows(self):
        path = self.source / "socket"
        with socket.socket(socket.AF_UNIX) as sock:
            try:
                sock.bind(str(path))
            except PermissionError as error:
                self.skipTest(f"sandbox prevents socket fixture: {error}")
            self.addCleanup(lambda: path.unlink(missing_ok=True))
            self.cli("create", "--source", self.source, "--repo", self.repo,
                     "--id", "socket", ok=False)

    def test_corrupt_every_regular_snapshot_file(self):
        self.create()
        snapshot = self.repo / "snapshots" / "one"
        files = [p for p in snapshot.rglob("*") if p.is_file()]
        for path in files:
            original = path.read_bytes()
            for mutation in ("flip", "truncate", "delete", "append"):
                with self.subTest(file=path.name, mutation=mutation):
                    if mutation == "delete":
                        path.unlink()
                    elif mutation == "truncate":
                        if not original:
                            continue
                        path.write_bytes(original[:len(original) // 2])
                    elif mutation == "flip":
                        path.write_bytes(bytes([original[0] ^ 1]) + original[1:] if original else b"x")
                    else:
                        path.write_bytes(original + b"x")
                    self.verify(ok=False)
                    self.restore(ok=False)
                    self.assertFalse(self.dest.exists())
                    self.cli("list", "--repo", self.repo, expected={"snapshots": []})
                    path.write_bytes(original)
        self.verify()

    def test_corruption_preserves_empty_and_nonempty_destinations(self):
        self.create()
        (self.repo / "snapshots" / "one" / "data" / "00000000").write_bytes(b"tampered")
        self.dest.mkdir()
        self.restore(ok=False)
        self.assertEqual(tree_bytes(self.dest), {})
        (self.dest / "keep").write_bytes(b"preserve")
        self.restore(ok=False)
        self.assertEqual(tree_bytes(self.dest), {"keep": b"preserve"})

    def test_snapshot_symlinks(self):
        self.create()
        blob = self.repo / "snapshots" / "one" / "data" / "00000000"
        blob.unlink()
        blob.symlink_to(self.source / "cero")
        self.verify(ok=False)
        self.restore(ok=False)
        self.cli("list", "--repo", self.repo, ok=False)
        self.assertFalse(self.dest.exists())

    def test_manifest_unsafe_paths_and_structure_even_if_resealed(self):
        self.create()
        snapshot = self.repo / "snapshots" / "one"
        manifest_path = snapshot / "manifest.json"
        initial = json.loads(manifest_path.read_bytes())
        variants = []
        for parts in (["..", "escape"], ["/absolute"], ["."], ["a/b"], [""], ["nul\x00"]):
            variant = json.loads(json.dumps(initial))
            variant["entries"][0]["path"] = parts
            variants.append(variant)
        variant = json.loads(json.dumps(initial))
        variant["entries"].append(variant["entries"][0])
        variants.append(variant)
        variant = json.loads(json.dumps(initial))
        variant["entries"] = [e for e in variant["entries"] if e["path"] != ["nivel"]]
        variants.append(variant)
        for value in variants:
            raw = json.dumps(value).encode()
            manifest_path.write_bytes(raw)
            (snapshot / "COMPLETE").write_text(hashlib.sha256(raw).hexdigest() + "\n")
            self.verify(ok=False)
            self.restore(ok=False)
        self.assertFalse(self.dest.exists())
        self.assertFalse((self.base / "escape").exists())

    def test_extra_snapshot_objects_and_incomplete_final(self):
        self.create()
        snapshot = self.repo / "snapshots" / "one"
        (snapshot / "data" / "extra").write_bytes(b"unlisted")
        self.verify(ok=False)
        self.restore(ok=False)
        (self.repo / "snapshots" / "unfinished").mkdir()
        self.cli("list", "--repo", self.repo, expected={"snapshots": []})
        self.cli("create", "--source", self.source, "--repo", self.repo, "--id", "unfinished", ok=False)

    def start_stopped_create(self, name, after_publish=False, max_bytes=None):
        # Instrument only the timing of the real publication syscall, in this subprocess.
        code = """import importlib.util, os, signal, sys
spec = importlib.util.spec_from_file_location('backup_under_test', sys.argv[1])
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)
rename = backup.os.rename
def stopped_rename(source, dest):
    if sys.argv[2] == 'after':
        rename(source, dest)
        os.kill(os.getpid(), signal.SIGSTOP)
    else:
        os.kill(os.getpid(), signal.SIGSTOP)
        rename(source, dest)
backup.os.rename = stopped_rename
sys.exit(backup.main(sys.argv[3:]))
"""
        argv = [sys.executable, "-c", code, str(PROGRAM), "after" if after_publish else "before",
                "create", "--source", str(self.source), "--repo", str(self.repo), "--id", name]
        if max_bytes is not None:
            argv += ["--max-bytes", str(max_bytes)]
        process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(lambda: process.poll() is None and process.kill())
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            pid, status = os.waitpid(process.pid, os.WNOHANG | os.WUNTRACED)
            if pid and os.WIFSTOPPED(status):
                return process, argv
            if pid:
                self.fail(f"create terminated before stop: {status}")
            time.sleep(0.002)
        self.fail("create did not reach publication in 15 seconds")

    def kill_and_record(self, process, argv):
        process.kill()
        stdout, stderr = process.communicate(timeout=10)
        RUNS.append({"argv": argv, "exit_code": process.returncode, "timed_out": False,
                     "stdout": stdout.decode(), "stderr": stderr.decode(),
                     "signal": "SIGKILL"})
        self.assertEqual(process.returncode, -signal.SIGKILL)
        self.assertEqual(stdout, b"")

    def test_sigkill_before_publication_repeat_same_id(self):
        self.create("prior")
        before = tree_bytes(self.source)
        previous = tree_bytes(self.repo / "snapshots")
        process, argv = self.start_stopped_create("interrupted")
        self.kill_and_record(process, argv)
        self.assertEqual(tree_bytes(self.repo / "snapshots"), previous)
        self.cli("list", "--repo", self.repo, expected={"snapshots": ["prior"]})
        self.verify("interrupted", ok=False)
        self.verify("prior")
        self.create("interrupted")
        self.verify("interrupted")
        self.restore("interrupted")
        self.assertEqual(tree_bytes(self.dest), before)
        self.assertEqual(tree_bytes(self.source), before)

    def test_sigkill_after_publication_preserves_valid_snapshot(self):
        self.create("prior")
        process, argv = self.start_stopped_create("published", after_publish=True)
        self.kill_and_record(process, argv)
        self.verify("prior")
        self.verify("published")
        self.cli("list", "--repo", self.repo, expected={"snapshots": ["prior", "published"]})
        self.cli("create", "--source", self.source, "--repo", self.repo, "--id", "published", ok=False)

    def test_sigkill_during_data_copy_repeat_same_id(self):
        self.create("prior")
        large = self.source / "large"
        with large.open("wb") as stream:
            stream.truncate(128 * 1024 * 1024)
        argv = [sys.executable, str(PROGRAM), "create", "--source", str(self.source),
                "--repo", str(self.repo), "--id", "partial"]
        process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(lambda: process.poll() is None and process.kill())
        deadline = time.monotonic() + 15
        observed = False
        while time.monotonic() < deadline and process.poll() is None:
            blobs = list((self.repo / ".staging").glob("partial-*/data/*"))
            if any(p.stat().st_size > 0 for p in blobs):
                os.kill(process.pid, signal.SIGSTOP)
                observed = True
                break
            time.sleep(0.001)
        self.assertTrue(observed, "must actually interrupt data copying")
        self.kill_and_record(process, argv)
        self.assertFalse((self.repo / "snapshots" / "partial").exists())
        self.cli("list", "--repo", self.repo, expected={"snapshots": ["prior"]})
        self.verify("prior")
        self.create("partial")
        self.verify("partial")
        self.restore("partial")
        self.assertEqual((self.dest / "large").stat().st_size, 128 * 1024 * 1024)
        self.assertEqual(hashlib.sha256((self.dest / "large").read_bytes()).digest(),
                         hashlib.sha256(large.read_bytes()).digest())

    def test_concurrent_duplicate_creation(self):
        argv = [sys.executable, str(PROGRAM), "create", "--source", str(self.source),
                "--repo", str(self.repo), "--id", "same"]
        processes = [subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(2)]
        results = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=20)
            results.append(process.returncode)
            RUNS.append({"argv": argv, "exit_code": process.returncode, "timed_out": False,
                         "stdout": stdout.decode(), "stderr": stderr.decode()})
        self.assertEqual(sorted(results), [0, 1])
        self.verify("same")

    def predicted_snapshot_size(self, name="one"):
        probe = self.base / "probe"
        self.cli("create", "--source", self.source, "--repo", probe,
                 "--id", name, expected={"id": name})
        measured = repository_size(probe)
        shutil.rmtree(probe)
        return measured

    def test_max_bytes_exact_boundary_includes_metadata(self):
        needed = self.predicted_snapshot_size()
        payload = repository_size(self.source)
        self.assertGreater(needed, payload)
        self.cli("create", "--source", self.source, "--repo", self.repo,
                 "--id", "one", "--max-bytes", needed - 1, ok=False)
        self.assertEqual(repository_size(self.repo), 0)
        self.assertEqual(list((self.repo / ".staging").iterdir()), [])
        self.assertEqual(list((self.repo / "snapshots").iterdir()), [])
        self.create(max_bytes=needed)
        self.assertEqual(repository_size(self.repo), needed)
        self.verify()
        self.restore()
        self.assertEqual(tree_bytes(self.dest), tree_bytes(self.source))

    def test_max_bytes_payload_alone_cannot_cover_metadata(self):
        payload = repository_size(self.source)
        self.cli("create", "--source", self.source, "--repo", self.repo,
                 "--id", "one", "--max-bytes", payload, ok=False)
        self.assertEqual(repository_size(self.repo), 0)
        self.cli("list", "--repo", self.repo, expected={"snapshots": []})

    def test_max_bytes_high_and_multiple_versions(self):
        limit = 1_000_000
        first = tree_bytes(self.source)
        self.create("before", max_bytes=limit)
        (self.source / "texto.txt").unlink()
        (self.source / "cero").write_bytes(b"new bytes")
        (self.source / "added").write_bytes(bytes(range(256)))
        second = tree_bytes(self.source)
        self.create("after", max_bytes=limit)
        self.assertLessEqual(repository_size(self.repo), limit)
        self.restore("before")
        self.restore("after", dest=self.base / "new-dest")
        self.assertEqual(tree_bytes(self.dest), first)
        self.assertEqual(tree_bytes(self.base / "new-dest"), second)
        self.cli("list", "--repo", self.repo, expected={"snapshots": ["after", "before"]})

    def test_max_bytes_below_existing_no_growth(self):
        self.create("prior")
        original = tree_bytes(self.repo)
        source = tree_bytes(self.source)
        size = repository_size(self.repo)
        for limit in (0, size - 1, size):
            self.cli("create", "--source", self.source, "--repo", self.repo,
                     "--id", "next", "--max-bytes", limit, ok=False)
            self.assertEqual(repository_size(self.repo), size)
            self.assertEqual(tree_bytes(self.repo), original)
            self.assertEqual(tree_bytes(self.source), source)
        self.verify("prior")
        self.restore("prior")
        self.assertEqual(tree_bytes(self.dest), source)

    def test_max_bytes_failed_attempts_no_residual_then_retry(self):
        self.create("prior")
        old_size = repository_size(self.repo)
        needed = old_size + self.predicted_snapshot_size("next")
        original = tree_bytes(self.repo)
        for _ in range(3):
            self.cli("create", "--source", self.source, "--repo", self.repo,
                     "--id", "next", "--max-bytes", needed - 1, ok=False)
            self.assertEqual(tree_bytes(self.repo), original)
        self.create("next", max_bytes=needed)
        self.assertEqual(repository_size(self.repo), needed)
        self.verify("prior")
        self.verify("next")

    def test_max_bytes_counts_all_existing_regular_files(self):
        self.cli("list", "--repo", self.repo, expected={"snapshots": []})
        (self.repo / "extra dir").mkdir()
        (self.repo / "extra dir" / "extra.bin").write_bytes(b"x" * 311)
        (self.repo / ".staging" / "standalone").write_bytes(b"y" * 97)
        (self.repo / ".lock").write_bytes(b"persistent lock bytes")
        existing = repository_size(self.repo)
        needed = existing + self.predicted_snapshot_size()
        original = tree_bytes(self.repo)
        self.cli("create", "--source", self.source, "--repo", self.repo,
                 "--id", "one", "--max-bytes", needed - 1, ok=False)
        self.assertEqual(tree_bytes(self.repo), original)
        self.create(max_bytes=needed)
        self.assertEqual(repository_size(self.repo), needed)
        self.assertEqual((self.repo / ".staging" / "standalone").read_bytes(), b"y" * 97)
        self.verify()

    def test_max_bytes_zero_even_empty_source_needs_metadata(self):
        shutil.rmtree(self.source)
        self.source.mkdir()
        self.cli("create", "--source", self.source, "--repo", self.repo,
                 "--id", "empty", "--max-bytes", 0, ok=False)
        self.assertEqual(repository_size(self.repo), 0)
        needed = self.predicted_snapshot_size("empty")
        self.assertGreater(needed, 0)
        self.create("empty", max_bytes=needed)
        self.assertEqual(repository_size(self.repo), needed)

    def test_max_bytes_invalid_arguments_no_mutation(self):
        for value in ("-1", "1.5", "1e6", "NaN", "", "+1", " 1", "１２", "9" * 5000):
            with self.subTest(value=value):
                self.cli("create", "--source", self.source, "--repo", self.repo,
                         "--id", "one", "--max-bytes", value, ok=False)
                self.assertFalse(self.repo.exists())
        self.create(max_bytes="0001000000")
        self.verify()

    def test_max_bytes_duplicate_preserves_repository(self):
        self.create()
        original = tree_bytes(self.repo)
        self.cli("create", "--source", self.source, "--repo", self.repo,
                 "--id", "one", "--max-bytes", 1_000_000, ok=False)
        self.assertEqual(tree_bytes(self.repo), original)

    def test_max_bytes_sigkill_before_publish_retry_at_exact_limit(self):
        self.create("prior")
        prior = tree_bytes(self.repo / "snapshots" / "prior")
        needed = repository_size(self.repo) + self.predicted_snapshot_size("next")
        process, argv = self.start_stopped_create("next", max_bytes=needed)
        self.kill_and_record(process, argv)
        self.assertTrue(any((self.repo / ".staging").iterdir()))
        self.cli("list", "--repo", self.repo, expected={"snapshots": ["prior"]})
        self.verify("next", ok=False)
        self.create("next", max_bytes=needed)
        self.assertEqual(repository_size(self.repo), needed)
        self.assertEqual(list((self.repo / ".staging").iterdir()), [])
        self.assertEqual(tree_bytes(self.repo / "snapshots" / "prior"), prior)
        self.verify("prior")
        self.verify("next")
        self.restore("next")
        self.assertEqual(tree_bytes(self.dest), tree_bytes(self.source))

    def test_max_bytes_sigkill_after_publish_within_limit(self):
        needed = self.predicted_snapshot_size("published")
        process, argv = self.start_stopped_create("published", after_publish=True, max_bytes=needed)
        self.kill_and_record(process, argv)
        self.assertEqual(repository_size(self.repo), needed)
        self.verify("published")
        self.restore("published")
        self.assertEqual(tree_bytes(self.dest), tree_bytes(self.source))

    def test_max_bytes_sigkill_during_copy_retry_at_exact_limit(self):
        self.create("prior")
        prior = tree_bytes(self.repo / "snapshots" / "prior")
        large = self.source / "large"
        with large.open("wb") as stream:
            stream.truncate(4 * 1024 * 1024)
        needed = repository_size(self.repo) + self.predicted_snapshot_size("partial")
        # Only timing is instrumented: the original copier writes and flushes
        # its first real block, then stops. A real SIGKILL prevents cleanup.
        code = """import importlib.util, os, signal, sys
spec = importlib.util.spec_from_file_location('backup_under_test', sys.argv[1])
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)
digest = backup.digest_file
class StopAfterWrite:
    def __init__(self, target):
        self.target = target
    def write(self, block):
        self.target.write(block)
        self.target.flush()
        os.kill(os.getpid(), signal.SIGSTOP)
def stopped_digest(path, target=None):
    if target is not None and path.name == 'large':
        return digest(path, StopAfterWrite(target))
    return digest(path, target)
backup.digest_file = stopped_digest
sys.exit(backup.main(sys.argv[2:]))
"""
        argv = [sys.executable, "-c", code, str(PROGRAM), "create", "--source", str(self.source),
                "--repo", str(self.repo), "--id", "partial", "--max-bytes", str(needed)]
        process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(lambda: process.poll() is None and process.kill())
        deadline = time.monotonic() + 15
        stopped = False
        while time.monotonic() < deadline:
            pid, status = os.waitpid(process.pid, os.WNOHANG | os.WUNTRACED)
            if pid and os.WIFSTOPPED(status):
                stopped = True
                break
            if pid:
                self.fail(f"copy ended before SIGSTOP: {status}")
            time.sleep(0.002)
        self.assertTrue(stopped, "copier must stop with actual bytes written")
        stage = next((self.repo / ".staging").glob("partial-*"))
        sizes = [p.stat().st_size for p in (stage / "data").iterdir()]
        self.assertIn(1024 * 1024, sizes)
        self.assertNotIn(4 * 1024 * 1024, sizes)
        self.kill_and_record(process, argv)
        self.assertFalse((self.repo / "snapshots" / "partial").exists())
        self.create("partial", max_bytes=needed)
        self.assertEqual(repository_size(self.repo), needed)
        self.assertEqual(list((self.repo / ".staging").iterdir()), [])
        self.assertEqual(tree_bytes(self.repo / "snapshots" / "prior"), prior)
        self.verify("prior")
        self.verify("partial")
        self.restore("partial")
        self.assertEqual(tree_bytes(self.dest), tree_bytes(self.source))

    def test_max_bytes_corruption_of_all_snapshot_files(self):
        self.create(max_bytes=1_000_000)
        snapshot = self.repo / "snapshots" / "one"
        for path in sorted(p for p in snapshot.rglob("*") if p.is_file()):
            original = path.read_bytes()
            for deleted in (False, True):
                with self.subTest(path=path.name, deleted=deleted):
                    if deleted:
                        path.unlink()
                    else:
                        path.write_bytes(original + b"corruption")
                    self.verify(ok=False)
                    self.dest.mkdir(exist_ok=True)
                    self.restore(ok=False)
                    self.assertEqual(tree_bytes(self.dest), {})
                    path.write_bytes(original)
        self.verify()

    def test_max_bytes_concurrent_distinct_creates_share_budget(self):
        needed = self.predicted_snapshot_size("aaa")
        processes = []
        for name in ("aaa", "bbb"):
            argv = [sys.executable, str(PROGRAM), "create", "--source", str(self.source),
                    "--repo", str(self.repo), "--id", name, "--max-bytes", str(needed)]
            processes.append((subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE), argv))
        codes = []
        for process, argv in processes:
            stdout, stderr = process.communicate(timeout=20)
            codes.append(process.returncode)
            RUNS.append({"argv": argv, "exit_code": process.returncode, "timed_out": False,
                         "stdout": stdout.decode(), "stderr": stderr.decode()})
            if process.returncode:
                self.assertEqual(stdout, b"")
            else:
                self.assertEqual(json.loads(stdout), {"id": argv[-3]})
        self.assertEqual(sorted(codes), [0, 1])
        self.assertEqual(repository_size(self.repo), needed)
        ids = self.cli("list", "--repo", self.repo)["snapshots"]
        self.assertEqual(len(ids), 1)
        self.verify(ids[0])

    def test_max_bytes_unsafe_staging_rejected_without_following(self):
        self.create("prior")
        link = self.repo / ".staging" / "bad"
        link.symlink_to(self.source)
        source = tree_bytes(self.source)
        self.cli("create", "--source", self.source, "--repo", self.repo,
                 "--id", "next", "--max-bytes", 1_000_000, ok=False)
        self.assertTrue(link.is_symlink())
        self.assertEqual(tree_bytes(self.source), source)
        link.unlink()
        os.mkfifo(link)
        self.cli("create", "--source", self.source, "--repo", self.repo,
                 "--id", "next", "--max-bytes", 1_000_000, ok=False)
        self.assertTrue(stat.S_ISFIFO(link.lstat().st_mode))
        link.unlink()
        self.verify("prior")


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(BackupTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    (ROOT / "validation" / "subcommands.json").write_text(json.dumps(RUNS, ensure_ascii=True, indent=2) + "\n")
    print(json.dumps({"tests_run": result.testsRun, "failures": len(result.failures),
                      "errors": len(result.errors), "subprocesses": len(RUNS),
                      "skipped": len(result.skipped),
                      "tests_executed": result.testsRun - len(result.skipped),
                      "successful": result.wasSuccessful()}, sort_keys=True))
    sys.exit(0 if result.wasSuccessful() else 1)
