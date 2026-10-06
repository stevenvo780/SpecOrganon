"""Local contract tests; all data is synthetic and confined to solution/evidence."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parent
PROGRAM = ROOT / "backup.py"
EVIDENCE = ROOT / "evidence"
COMMANDS = EVIDENCE / "commands.jsonl"


def tree(path):
    result = {}
    for child in sorted(path.rglob("*")):
        relative = child.relative_to(path).as_posix()
        if child.is_symlink():
            result[relative] = ("symlink", os.readlink(child))
        elif child.is_dir():
            result[relative] = ("dir",)
        elif child.is_file():
            result[relative] = ("file", child.read_bytes())
        else:
            result[relative] = ("special", child.lstat().st_mode)
    return result


def record(argv, proc, seconds, timed_out=False):
    item = {"argv": argv, "exit_code": proc.returncode, "timeout_seconds": seconds,
            "timed_out": timed_out, "stdout": proc.stdout, "stderr": proc.stderr}
    with COMMANDS.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(item, ensure_ascii=True) + "\n")


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="test-", dir=EVIDENCE)
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.source = self.base / "source"
        self.source.mkdir()
        self.repo = self.base / "repo"
        self.dest = self.base / "dest"
        (self.source / "empty dir").mkdir()
        (self.source / "nested").mkdir()
        (self.source / "nested" / "á 日本語.bin").write_bytes(bytes(range(256)) * 17)
        (self.source / "document.txt").write_bytes(b"original\x00\xff")
        (self.source / "zero").touch()

    def cli(self, operation, ok=True, **kwargs):
        kwargs.setdefault("repo", self.repo)
        argv = [sys.executable, str(PROGRAM), operation]
        for key, value in kwargs.items():
            argv += ["--" + key, str(value)]
        started = time.monotonic()
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired as exc:
            record(argv, subprocess.CompletedProcess(argv, -1, str(exc.stdout or ""), str(exc.stderr or "")), 30, True)
            raise
        record(argv, proc, 30)
        elapsed = time.monotonic() - started
        if ok:
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(proc.stderr, "")
            result = json.loads(proc.stdout)
            self.assertIsInstance(result, dict)
            self.assertEqual(len(proc.stdout.splitlines()), 1)
            return result
        self.assertNotEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(proc.stdout, "")
        self.assertTrue(proc.stderr)
        return {"seconds": elapsed}

    def create(self, snapshot_id="v1"):
        before = tree(self.source)
        self.assertEqual(self.cli("create", source=self.source, id=snapshot_id), {"id": snapshot_id})
        self.assertEqual(before, tree(self.source))

    def test_v2_three_exact_versions_without_source(self):
        expected = {}
        expected["v1"] = tree(self.source)
        self.create("v1")
        (self.source / "document.txt").write_bytes(b"modified version two")
        (self.source / "added file").write_bytes(b"new\x00data")
        (self.source / "nested" / "á 日本語.bin").unlink()
        expected["v2"] = tree(self.source)
        self.create("v2")
        (self.source / "document.txt").unlink()
        (self.source / "added file").unlink()
        (self.source / "nested").rmdir()
        (self.source / "new empty").mkdir()
        (self.source / "third").write_bytes(b"third version")
        expected["v3"] = tree(self.source)
        self.create("v3")
        shutil.rmtree(self.source)
        self.assertEqual(self.cli("list"), {"snapshots": ["v1", "v2", "v3"]})
        for snapshot_id, contents in expected.items():
            with self.subTest(id=snapshot_id):
                self.assertEqual(self.cli("verify", id=snapshot_id), {"id": snapshot_id, "valid": True})
                dest = self.base / ("restore " + snapshot_id)
                self.assertEqual(self.cli("restore", id=snapshot_id, dest=dest), {"id": snapshot_id})
                self.assertEqual(tree(dest), contents)

    def test_empty_repo_and_sorted_ids(self):
        self.assertEqual(self.cli("list"), {"snapshots": []})
        for snapshot_id in ("z", "A", "b_2-", "1"):
            self.create(snapshot_id)
        self.assertEqual(self.cli("list"), {"snapshots": ["1", "A", "b_2-", "z"]})

    def test_empty_source_and_empty_preexisting_destination(self):
        shutil.rmtree(self.source)
        self.source.mkdir()
        self.create()
        self.dest.mkdir()
        self.cli("restore", id="v1", dest=self.dest)
        self.assertEqual(tree(self.dest), {})

    def test_id_limits(self):
        self.create("A" * 64)
        for value in ("", ".", "..", "../escape", "a/b", "a\\b", "_bad", "-bad", "é", "a.b", "a" * 65, "a\n"):
            with self.subTest(id=value):
                self.cli("create", source=self.source, id=value, ok=False)
                self.cli("verify", id=value, ok=False)
                self.cli("restore", id=value, dest=self.dest, ok=False)
        self.assertFalse(self.dest.exists())

    def test_missing_snapshot(self):
        self.cli("list")
        self.cli("verify", id="missing", ok=False)
        self.cli("restore", id="missing", dest=self.dest, ok=False)
        self.assertFalse(self.dest.exists())

    def test_missing_source(self):
        self.cli("create", source=self.base / "absent", id="v1", ok=False)
        self.assertEqual(self.cli("list"), {"snapshots": []})

    def test_id_not_overwritten(self):
        self.create()
        original = tree(self.repo)
        (self.source / "document.txt").write_bytes(b"later")
        self.cli("create", source=self.source, id="v1", ok=False)
        self.assertEqual(tree(self.repo), original)

    def test_protected_destination(self):
        self.create()
        self.dest.mkdir()
        (self.dest / "keep").write_bytes(b"protected\x00\xff")
        (self.dest / "empty").mkdir()
        original = tree(self.dest)
        self.cli("restore", id="v1", dest=self.dest, ok=False)
        self.assertEqual(tree(self.dest), original)

    def test_destination_with_only_empty_directory_is_nonempty(self):
        self.create()
        self.dest.mkdir()
        (self.dest / "empty").mkdir()
        original = tree(self.dest)
        self.cli("restore", id="v1", dest=self.dest, ok=False)
        self.assertEqual(tree(self.dest), original)

    def test_source_repo_overlap(self):
        original = tree(self.source)
        for repo in (self.source, self.source / "repo", self.base):
            with self.subTest(repo=str(repo)):
                self.cli("create", source=self.source, repo=repo, id="v1", ok=False)
                self.assertEqual(tree(self.source), original)

    def test_restore_repo_overlap(self):
        self.create()
        original = tree(self.repo)
        for dest in (self.repo, self.repo / "restored", self.base):
            self.cli("restore", id="v1", dest=dest, ok=False)
            self.assertEqual(tree(self.repo), original)

    def test_source_symlinks(self):
        for target in (self.source / "document.txt", self.source / "nested", self.base / "absent"):
            link = self.source / "link"
            link.symlink_to(target)
            before = tree(self.source)
            self.cli("create", source=self.source, id="v1", ok=False)
            self.assertEqual(tree(self.source), before)
            link.unlink()
        self.assertEqual(self.cli("list"), {"snapshots": []})

    def test_symlink_path_components_and_dotdot(self):
        self.create()
        link = self.base / "link"
        link.symlink_to(self.source, target_is_directory=True)
        for source in (link, link / "nested", link / ".." / "source"):
            self.cli("create", source=source, id="later", ok=False)
        repo_link = self.base / "repo-link"
        repo_link.symlink_to(self.repo, target_is_directory=True)
        for op in ("list", "verify", "restore", "create"):
            kwargs = {"repo": repo_link}
            if op != "list":
                kwargs["id"] = "v1"
            if op == "create":
                kwargs["source"] = self.source
            if op == "restore":
                kwargs["dest"] = self.dest
            self.cli(op, ok=False, **kwargs)
        self.dest.symlink_to(self.source, target_is_directory=True)
        self.cli("restore", id="v1", dest=self.dest, ok=False)
        self.dest.unlink()
        parent = self.base / "dest-parent"
        parent.symlink_to(self.source, target_is_directory=True)
        self.cli("restore", id="v1", dest=parent / "new", ok=False)

    def test_symlink_in_snapshot_or_staging(self):
        self.create()
        original = tree(self.source)
        stage = self.repo / ".stage-junk"
        stage.mkdir()
        link = stage / "link"
        link.symlink_to(self.source)
        for op, kwargs in (("list", {}), ("verify", {"id": "v1"}), ("restore", {"id": "v1", "dest": self.dest})):
            self.cli(op, ok=False, **kwargs)
        link.unlink()
        stage.rmdir()
        snapshot = self.repo / "v1"
        shutil.rmtree(snapshot / "tree")
        (snapshot / "tree").symlink_to(self.source)
        self.cli("verify", id="v1", ok=False)
        self.cli("restore", id="v1", dest=self.dest, ok=False)
        self.cli("list", ok=False)
        self.assertEqual(tree(self.source), original)

    def test_special_files(self):
        fifo = self.source / "fifo"
        os.mkfifo(fifo)
        self.cli("create", source=self.source, id="v1", ok=False)
        fifo.unlink()
        with socket.socket(socket.AF_UNIX) as sock:
            sock.bind(str(self.source / "socket"))
            self.cli("create", source=self.source, id="v1", ok=False)
        (self.source / "socket").unlink()
        self.create()
        os.mkfifo(self.repo / "v1" / "tree" / "fifo")
        self.cli("verify", id="v1", ok=False)
        self.cli("list", ok=False)
        self.cli("restore", id="v1", dest=self.dest, ok=False)
        (self.repo / "v1" / "tree" / "fifo").unlink()
        self.dest.mkdir()
        os.mkfifo(self.dest / "fifo")
        self.cli("restore", id="v1", dest=self.dest, ok=False)
        self.assertTrue((self.dest / "fifo").exists())

    def test_regular_file_as_managed_directory(self):
        regular = self.base / "regular"
        regular.write_bytes(b"preserve")
        self.cli("create", source=regular, id="v1", ok=False)
        self.cli("list", repo=regular, ok=False)
        self.create()
        self.cli("restore", id="v1", dest=regular, ok=False)
        self.assertEqual(regular.read_bytes(), b"preserve")

    def test_corruption_of_each_regular_snapshot_file(self):
        self.create()
        paths = sorted(path for path in (self.repo / "v1").rglob("*") if path.is_file())
        for path in paths:
            original = path.read_bytes()
            for mode in ("alter", "truncate", "delete"):
                with self.subTest(file=str(path.relative_to(self.repo)), mode=mode):
                    if mode == "delete":
                        path.unlink()
                    elif mode == "truncate":
                        # An empty file must actually change to be a corruption.
                        path.write_bytes(b"" if original else b"damage")
                    else:
                        path.write_bytes(bytes([original[0] ^ 1]) + original[1:] if original else b"damage")
                    self.cli("verify", id="v1", ok=False)
                    self.cli("restore", id="v1", dest=self.dest, ok=False)
                    self.assertFalse(self.dest.exists())
                    self.assertEqual(self.cli("list"), {"snapshots": []})
                    self.dest.mkdir()
                    self.cli("restore", id="v1", dest=self.dest, ok=False)
                    self.assertEqual(tree(self.dest), {})
                    self.dest.rmdir()
                    path.write_bytes(original)
        self.cli("verify", id="v1")

    def test_directory_corruption_and_extra_files(self):
        self.create()
        empty = self.repo / "v1" / "tree" / "empty dir"
        empty.rmdir()
        self.cli("verify", id="v1", ok=False)
        self.cli("restore", id="v1", dest=self.dest, ok=False)
        empty.mkdir()
        extra = self.repo / "v1" / "tree" / "extra"
        extra.write_bytes(b"unexpected")
        self.cli("verify", id="v1", ok=False)
        extra.unlink()
        extra = self.repo / "v1" / "extra"
        extra.write_bytes(b"unexpected")
        self.cli("verify", id="v1", ok=False)

    def test_unsafe_manifest_rejected_even_with_matching_checksum(self):
        self.create()
        snapshot = self.repo / "v1"
        raw = (snapshot / "manifest.json").read_bytes()
        for path in ("../escape", "/absolute", "a/../../escape", "a//b", "a/./b"):
            manifest = json.loads(raw)
            manifest["entries"] = [{"type": "dir", "path": path}]
            encoded = json.dumps(manifest).encode()
            (snapshot / "manifest.json").write_bytes(encoded)
            (snapshot / "manifest.sha256").write_text(hashlib.sha256(encoded).hexdigest() + "\n")
            self.cli("verify", id="v1", ok=False)
            self.cli("restore", id="v1", dest=self.dest, ok=False)
            self.assertFalse(self.dest.exists())

    def test_failure_then_retry_same_id(self):
        bad = self.source / "link"
        bad.symlink_to(self.source / "document.txt")
        self.cli("create", source=self.source, id="v1", ok=False)
        self.assertEqual(self.cli("list"), {"snapshots": []})
        bad.unlink()
        self.create()

    def test_sigkill_create_preserves_previous_and_allows_retry(self):
        self.create("previous")
        previous = tree(self.repo / "previous")
        large = self.source / "large.bin"
        with large.open("wb") as stream:
            stream.truncate(256 * 1024 * 1024)
        argv = [sys.executable, str(PROGRAM), "create", "--source", str(self.source), "--repo", str(self.repo), "--id", "interrupted"]
        proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        killed = False
        deadline = time.monotonic() + 15
        try:
            while time.monotonic() < deadline and proc.poll() is None:
                files = list(self.repo.glob(".stage-*/tree/large.bin"))
                if files and files[0].stat().st_size > 0:
                    proc.kill()
                    killed = True
                    break
                time.sleep(0.001)
            stdout, stderr = proc.communicate(timeout=15)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
        record(argv, subprocess.CompletedProcess(argv, proc.returncode, stdout, stderr), 15)
        self.assertTrue(killed, "did not observe and interrupt an in-progress copy")
        self.assertEqual(proc.returncode, -signal.SIGKILL)
        self.assertEqual(stdout, "")
        self.assertFalse((self.repo / "interrupted").exists())
        self.assertEqual(tree(self.repo / "previous"), previous)
        self.assertEqual(self.cli("list"), {"snapshots": ["previous"]})
        self.cli("verify", id="previous")
        self.create("interrupted")
        self.cli("verify", id="interrupted")
        self.cli("restore", id="interrupted", dest=self.dest)
        self.assertEqual(tree(self.dest), tree(self.source))
        self.assertEqual(tree(self.repo / "previous"), previous)

    def test_parallel_create_same_id(self):
        argv = [sys.executable, str(PROGRAM), "create", "--source", str(self.source), "--repo", str(self.repo), "--id", "same"]
        # Establish the repo first; simultaneous repo bootstrap is tested separately.
        self.cli("list")
        procs = [subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
        codes = []
        for proc in procs:
            stdout, stderr = proc.communicate(timeout=30)
            record(argv, subprocess.CompletedProcess(argv, proc.returncode, stdout, stderr), 30)
            codes.append(proc.returncode)
        self.assertEqual(sorted(codes), [0, 1])
        self.cli("verify", id="same")


if __name__ == "__main__":
    EVIDENCE.mkdir(exist_ok=True)
    unittest.main(verbosity=2)
