"""Contract tests: independent byte inventories, real CLI processes and SIGKILL."""

import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest


PROGRAM = Path(__file__).with_name("backup.py").resolve()
LOG = Path(os.environ.get("BACKUP_TEST_LOG", "/trial/solution/validation/commands.jsonl"))


def tree(root):
    """Independent inventory, including bytes; never follow symlinks."""
    result = {}
    if not root.exists():
        return result
    for folder, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            path = Path(folder) / name
            rel = path.relative_to(root).as_posix()
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                result[rel] = ("link", os.readlink(path))
            elif stat.S_ISDIR(mode):
                result[rel] = ("dir",)
            elif stat.S_ISREG(mode):
                result[rel] = ("file", path.read_bytes())
            else:
                result[rel] = ("special", stat.S_IFMT(mode))
    return result


def used(root):
    return sum(path.lstat().st_size for path in root.rglob("*")
               if stat.S_ISREG(path.lstat().st_mode))


def record(argv, exit_code, stdout, stderr, timed_out=False, **extra):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as out:
        out.write(json.dumps({"argv": argv, "exit_code": exit_code,
                              "stdout": stdout.decode("utf-8", "replace"),
                              "stderr": stderr.decode("utf-8", "replace"),
                              "timed_out": timed_out, **extra}, ensure_ascii=True) + "\n")


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="backup-test-", dir="/trial")
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.repo = self.root / "repo"
        self.dest = self.root / "dest"
        self.source.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def argv(self, command, **flags):
        return [sys.executable, str(PROGRAM), command,
                *[part for key, value in flags.items()
                  for part in ("--" + key.replace("_", "-"), str(value))]]

    def cli(self, command, ok=True, **flags):
        argv = self.argv(command, **flags)
        try:
            run = subprocess.run(argv, capture_output=True, timeout=30)
        except subprocess.TimeoutExpired as exc:
            record(argv, None, exc.stdout or b"", exc.stderr or b"", True, timeout_seconds=30)
            raise
        record(argv, run.returncode, run.stdout, run.stderr, timeout_seconds=30)
        if ok:
            self.assertEqual(run.returncode, 0, run.stderr.decode())
            self.assertEqual(run.stderr, b"")
            return json.loads(run.stdout)  # rejects extra JSON/trailing text
        self.assertNotEqual(run.returncode, 0, run.stdout.decode())
        self.assertEqual(run.stdout, b"")
        return None

    def create(self, snapshot_id="v1", ok=True, **flags):
        return self.cli("create", ok=ok, source=self.source, repo=self.repo,
                        id=snapshot_id, **flags)

    def verify(self, snapshot_id="v1", ok=True):
        return self.cli("verify", ok=ok, repo=self.repo, id=snapshot_id)

    def restore(self, snapshot_id="v1", ok=True, dest=None):
        return self.cli("restore", ok=ok, repo=self.repo, id=snapshot_id,
                        dest=self.dest if dest is None else dest)

    def assert_clean(self):
        self.assertFalse(any(p.name.startswith(".pending-") for p in self.repo.iterdir()))

    def rich_source(self):
        for rel in ["empty", "nested/empty", "á 漢字/🙂", ".hidden-dir"]:
            (self.source / rel).mkdir(parents=True)
        files = {"zero": b"", "all bytes.bin": bytes(range(256)),
                 "á 漢字/documento ñ.txt": "línea\n\0漢字".encode(),
                 "line\nbreak\".txt": b"quotes and newline in filename",
                 ".hidden": b"hidden", "nested/random": random.Random(42).randbytes(2 * 1024 * 1024),
                 "nested/.pending-name": b"a normal source filename"}
        for rel, content in files.items():
            (self.source / rel).write_bytes(content)

    def test_v1_roundtrip_and_source_independence(self):
        self.rich_source()
        expected = tree(self.source)
        self.assertEqual(self.create("z"), {"id": "z"})
        self.assertEqual(tree(self.source), expected)
        self.assertEqual(self.create("a", max_bytes=20_000_000), {"id": "a"})
        self.assertLessEqual(used(self.repo), 20_000_000)
        self.assertEqual(self.cli("list", repo=self.repo), {"snapshots": ["a", "z"]})
        shutil.rmtree(self.source)
        for snapshot_id in ["a", "z"]:
            self.assertEqual(self.verify(snapshot_id), {"id": snapshot_id, "valid": True})
            dest = self.root / ("dest-" + snapshot_id)
            self.assertEqual(self.restore(snapshot_id, dest=dest), {"id": snapshot_id})
            self.assertEqual(tree(dest), expected)

    def test_empty_source_and_existing_empty_destination(self):
        self.dest.mkdir()
        self.create(max_bytes=10_000)
        self.verify()
        self.restore()
        self.assertEqual(tree(self.dest), {})

    def test_sorted_list_and_empty_repository(self):
        self.assertEqual(self.cli("list", repo=self.repo), {"snapshots": []})
        self.repo.mkdir()
        self.assertEqual(self.cli("list", repo=self.repo), {"snapshots": []})
        for snapshot_id in ["Z", "b-2", "A_1"]:
            self.create(snapshot_id)
        self.assertEqual(self.cli("list", repo=self.repo), {"snapshots": ["A_1", "Z", "b-2"]})

    def test_invalid_duplicate_and_missing_ids(self):
        for snapshot_id in ["", "../x", "a/b", ".", "_a", "a" * 65, "ñ", "a.b", "a b"]:
            with self.subTest(id=snapshot_id):
                self.create(snapshot_id, ok=False)
        self.create("a" * 64)
        self.create()
        expected = tree(self.repo)
        (self.source / "new").write_bytes(b"new")
        self.create(ok=False)
        self.assertEqual(tree(self.repo), expected)
        self.verify("missing", ok=False)
        self.restore("missing", ok=False)
        self.assertFalse(self.dest.exists())

    def test_versions_remain_exact(self):
        (self.source / "removed").write_bytes(b"first")
        (self.source / "modified").write_bytes(b"old")
        first = tree(self.source)
        self.create("first")
        (self.source / "removed").unlink()
        (self.source / "modified").write_bytes(b"new")
        (self.source / "added").write_bytes(b"second")
        second = tree(self.source)
        self.create("second", max_bytes=100_000)
        for snapshot_id, expected in [("first", first), ("second", second)]:
            dest = self.root / snapshot_id
            self.restore(snapshot_id, dest=dest)
            self.assertEqual(tree(dest), expected)

    def test_overlap_rejected_without_source_mutation(self):
        (self.source / "file").write_bytes(b"unchanged")
        expected = tree(self.source)
        for repo in [self.source, self.source / "repo", self.root]:
            self.cli("create", ok=False, source=self.source, repo=repo, id="x", max_bytes=100_000)
            self.assertEqual(tree(self.source), expected)
        self.create()
        expected_repo = tree(self.repo)
        self.restore(ok=False, dest=self.repo / "inside")
        self.assertEqual(tree(self.repo), expected_repo)

    def test_nonempty_destination_preserved(self):
        self.create()
        self.dest.mkdir()
        (self.dest / "bytes").write_bytes(bytes(range(256)))
        (self.dest / "empty").mkdir()
        before = tree(self.dest)
        self.restore(ok=False)
        self.assertEqual(tree(self.dest), before)

    def test_symlinks_source_paths_and_descendants(self):
        external = self.root / "external"
        external.mkdir()
        (external / "file").write_bytes(b"protected")
        link = self.root / "linked"
        link.symlink_to(external, target_is_directory=True)
        for source in [link, link / ".." / "source"]:
            self.cli("create", ok=False, source=source, repo=self.repo, id="x")
        for target in [external / "file", external, self.root / "absent"]:
            nested = self.source / "link"
            nested.symlink_to(target)
            self.create(ok=False)
            nested.unlink()
        self.assertEqual((external / "file").read_bytes(), b"protected")
        self.assertFalse(self.repo.exists())

    def test_symlinks_repository_and_destination(self):
        target = self.root / "target"
        target.mkdir()
        self.repo.symlink_to(target, target_is_directory=True)
        self.create(ok=False)
        self.cli("list", ok=False, repo=self.repo)
        self.repo.unlink()
        self.create()
        before = tree(self.repo)
        self.dest.symlink_to(target, target_is_directory=True)
        self.restore(ok=False)
        self.dest.unlink()
        parent = self.root / "parent-link"
        parent.symlink_to(target, target_is_directory=True)
        self.restore(ok=False, dest=parent / "dest")
        self.assertEqual(tree(target), {})
        self.assertEqual(tree(self.repo), before)
        data_link = self.repo / "v1" / "data" / "link"
        data_link.symlink_to(target)
        self.verify(ok=False)
        self.restore(ok=False)
        data_link.unlink()
        lock = self.repo / ".lock"
        lock.unlink()
        lock.symlink_to(target / "absent")
        self.create("second", ok=False)
        self.assertFalse((target / "absent").exists())

    def test_special_files_rejected_without_hanging(self):
        fifo = self.source / "fifo"
        os.mkfifo(fifo)
        self.create(ok=False)
        fifo.unlink()
        self.create()
        os.mkfifo(self.repo / "v1" / "data" / "fifo")
        self.verify(ok=False)
        self.restore(ok=False)
        (self.repo / "v1" / "data" / "fifo").unlink()
        os.mkfifo(self.dest)
        self.restore(ok=False)
        self.assertTrue(stat.S_ISFIFO(self.dest.lstat().st_mode))

    def test_corruption_of_every_snapshot_regular_file(self):
        self.rich_source()
        self.create()
        snapshot = self.repo / "v1"
        originals = {p.relative_to(snapshot): p.read_bytes()
                     for p in snapshot.rglob("*") if p.is_file()}
        for rel, original in originals.items():
            path = snapshot / rel
            for action in ["alter", "delete"]:
                with self.subTest(file=str(rel), corruption=action):
                    if action == "alter":
                        path.write_bytes(bytes([original[0] ^ 1]) + original[1:] if original else b"x")
                    else:
                        path.unlink()
                    self.verify(ok=False)
                    self.restore(ok=False)
                    self.assertFalse(self.dest.exists())
                    path.write_bytes(original)
        self.verify()
        self.restore()
        self.assertEqual(tree(self.dest), tree(self.source))

    def test_inventory_corruption(self):
        (self.source / "empty").mkdir()
        self.create()
        data = self.repo / "v1" / "data"
        (data / "extra").write_bytes(b"extra")
        self.verify(ok=False)
        (data / "extra").unlink()
        (data / "empty").rmdir()
        self.verify(ok=False)
        self.restore(ok=False)
        self.assertFalse(self.dest.exists())

    def test_quota_counts_metadata_and_accepts_exact_limit(self):
        (self.source / "payload").write_bytes(b"abc")
        self.create("sample")
        exact = used(self.repo)
        self.assertGreater(exact, 3 + 65)
        shutil.rmtree(self.repo)
        self.create("sample", max_bytes=exact - 1, ok=False)
        self.assertEqual(used(self.repo), 0)
        self.assert_clean()
        self.assertEqual(self.cli("list", repo=self.repo), {"snapshots": []})
        self.create("sample", max_bytes=exact)
        self.assertEqual(used(self.repo), exact)
        self.verify("sample")
        self.restore("sample")
        self.assertEqual(tree(self.dest), tree(self.source))

    def test_quota_existing_snapshots_lock_bytes_and_retry(self):
        self.rich_source()
        self.create("old")
        # Nonzero existing lock bytes are regular bytes and must count too.
        with (self.repo / ".lock").open("ab") as lock:
            lock.write(b"persistent regular bytes" * 100)
        before, byte_count = tree(self.repo), used(self.repo)
        source_before = tree(self.source)
        for limit in [0, byte_count - 1, byte_count, byte_count + 1]:
            with self.subTest(limit=limit):
                self.create("new", max_bytes=limit, ok=False)
                self.assertEqual(tree(self.repo), before)
                self.assertEqual(used(self.repo), byte_count)
                self.assertEqual(tree(self.source), source_before)
                self.assert_clean()
                self.verify("old")
        self.create("new", max_bytes=byte_count + 10_000_000)
        self.assertLessEqual(used(self.repo), byte_count + 10_000_000)
        self.verify("old")
        self.verify("new")

    def test_quota_zero_negative_and_invalid_values(self):
        for limit in [0, -1, "abc", "1.5"]:
            self.create(max_bytes=limit, ok=False)
            if self.repo.exists():
                self.assertEqual(used(self.repo), 0)
                self.assert_clean()
        self.create(max_bytes=1000)
        self.verify()

    def test_abandoned_staging_ignored_cleaned_and_counted(self):
        self.create("old")
        expected = tree(self.repo)
        before = used(self.repo)
        pending = self.repo / ".pending-abandoned"
        pending.mkdir()
        (pending / "unfinished").write_bytes(b"x" * 10_000)
        self.assertEqual(self.cli("list", repo=self.repo), {"snapshots": ["old"]})
        self.create("new", max_bytes=before - 1, ok=False)
        self.assertEqual(used(self.repo), before)
        self.assertEqual(tree(self.repo), expected)
        self.create("new", max_bytes=before + 1000)
        self.assert_clean()

    def test_sigkill_and_same_id_retry_with_quota(self):
        (self.source / "small").write_bytes(b"old snapshot")
        self.create("old")
        old_before = tree(self.repo / "old")
        original_bytes = used(self.repo)
        # A sparse input keeps fixture generation cheap; copied bytes are real.
        with (self.source / "large").open("wb") as out:
            out.truncate(128 * 1024 * 1024)
        argv = self.argv("create", source=self.source, repo=self.repo, id="retry", max_bytes=300_000_000)
        proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        deadline = time.monotonic() + 15
        observed = False
        while time.monotonic() < deadline and proc.poll() is None:
            candidates = list(self.repo.glob(".pending-*/data/large"))
            if candidates and candidates[0].exists() and candidates[0].stat().st_size > 0:
                observed = True
                proc.send_signal(signal.SIGKILL)
                break
            time.sleep(0.001)
        if not observed and proc.poll() is None:
            proc.kill()
        stdout, stderr = proc.communicate(timeout=10)
        record(argv, proc.returncode, stdout, stderr, timeout_seconds=15,
               injected_signal="SIGKILL", observed_staging_data=observed)
        self.assertTrue(observed, "Could not observe a create before completion")
        self.assertEqual(proc.returncode, -signal.SIGKILL)
        self.assertEqual(stdout, b"")
        self.assertEqual(self.cli("list", repo=self.repo), {"snapshots": ["old"]})
        self.verify("old")
        self.assertEqual(tree(self.repo / "old"), old_before)
        self.create("retry", max_bytes=original_bytes - 1, ok=False)
        self.assertEqual(used(self.repo), original_bytes)
        self.assert_clean()
        (self.source / "large").unlink()
        self.create("retry", max_bytes=original_bytes + 1000)
        self.verify("retry")
        self.assertEqual(tree(self.repo / "old"), old_before)
        self.restore("retry")
        self.assertEqual(tree(self.dest), tree(self.source))

    def test_concurrent_creates_cannot_exceed_quota(self):
        (self.source / "file").write_bytes(b"x" * 4096)
        self.create("aa")
        budget = used(self.repo)
        shutil.rmtree(self.repo)
        self.repo.mkdir()
        # Precreate lock to make both starts independent of initialization.
        (self.repo / ".lock").touch()
        jobs = []
        for snapshot_id in ["aa", "bb"]:
            argv = self.argv("create", source=self.source, repo=self.repo,
                             id=snapshot_id, max_bytes=budget)
            jobs.append((argv, subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)))
        exits = []
        for argv, proc in jobs:
            stdout, stderr = proc.communicate(timeout=30)
            record(argv, proc.returncode, stdout, stderr, timeout_seconds=30)
            exits.append(proc.returncode)
        self.assertEqual(sum(code == 0 for code in exits), 1)
        self.assertLessEqual(used(self.repo), budget)
        self.assertEqual(len(self.cli("list", repo=self.repo)["snapshots"]), 1)
        self.assert_clean()


if __name__ == "__main__":
    unittest.main(verbosity=2)
