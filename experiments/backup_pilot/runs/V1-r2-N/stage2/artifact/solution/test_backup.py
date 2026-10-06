"""Integration tests. All fixtures stay under /trial and are removed afterwards."""

import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest


SCRIPT = Path(__file__).resolve().with_name("backup.py")
TRIAL = SCRIPT.parent.parent


def tree(path):
    result = {}
    for entry in sorted(path.rglob("*")):
        name = str(entry.relative_to(path))
        result[name] = None if entry.is_dir() else entry.read_bytes()
    return result


def regular_bytes(path):
    return sum(entry.stat().st_size for entry in path.rglob("*") if entry.is_file())


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix=".backup-tests-", dir=TRIAL)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.repo = self.root / "repo"
        self.dest = self.root / "dest"
        self.source.mkdir()

    def cli(self, *args, success=True):
        process = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)],
                                 capture_output=True, text=True, timeout=30)
        if success:
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(process.stderr, "")
            # Exactly one JSON object, including the required keys only.
            self.assertEqual(len(process.stdout.splitlines()), 1)
            result = json.loads(process.stdout)
            self.assertIsInstance(result, dict)
            return result
        self.assertNotEqual(process.returncode, 0, process.stdout)
        self.assertEqual(process.stdout, "")
        self.assertTrue(process.stderr)
        return process

    def create(self, snapshot="v1", **kwargs):
        args = ["create", "--source", self.source, "--repo", self.repo, "--id", snapshot]
        if "limit" in kwargs:
            args += ["--max-bytes", kwargs.pop("limit")]
        return self.cli(*args, **kwargs)

    def verify(self, snapshot="v1", **kwargs):
        return self.cli("verify", "--repo", self.repo, "--id", snapshot, **kwargs)

    def restore(self, snapshot="v1", **kwargs):
        return self.cli("restore", "--repo", self.repo, "--id", snapshot,
                        "--dest", kwargs.pop("dest", self.dest), **kwargs)

    def listing(self, **kwargs):
        return self.cli("list", "--repo", self.repo, **kwargs)

    def populate(self):
        (self.source / "vacío con espacios").mkdir()
        (self.source / "文書").mkdir()
        (self.source / "文書" / "hola ñ.txt").write_text("Hola\n日本語\n", encoding="utf-8")
        (self.source / "binary \n name").write_bytes(bytes(range(256)) * 8193)
        (self.source / ".hidden").write_bytes(b"\x00\xff\x80\n")
        (self.source / "zero").touch()
        deep = self.source / "nested" / "empty"
        deep.mkdir(parents=True)

    def test_v1_roundtrip_and_source_preserved(self):
        self.populate()
        before = tree(self.source)
        self.assertEqual(self.create(), {"id": "v1"})
        self.assertEqual(tree(self.source), before)
        self.assertEqual(self.verify(), {"id": "v1", "valid": True})
        self.assertEqual(self.listing(), {"snapshots": ["v1"]})
        # The repository must work independently of the original source.
        import shutil
        shutil.rmtree(self.source)
        self.assertEqual(self.restore(), {"id": "v1"})
        self.assertEqual(tree(self.dest), before)

    def test_empty_source_and_empty_existing_destination(self):
        self.repo.mkdir()
        self.assertEqual(self.listing(), {"snapshots": []})
        self.create()
        self.dest.mkdir()
        self.restore()
        self.assertEqual(tree(self.dest), {})
        self.verify()

    def test_missing_repo_list_is_empty(self):
        self.assertEqual(self.listing(), {"snapshots": []})
        self.assertFalse(self.repo.exists())

    def test_versions_are_exact_and_list_sorted(self):
        (self.source / "file").write_bytes(b"first")
        first = tree(self.source)
        self.create("z")
        (self.source / "file").write_bytes(b"second")
        (self.source / "added").write_bytes(b"new")
        (self.source / "empty").mkdir()
        second = tree(self.source)
        self.create("a")
        (self.source / "file").unlink()
        third = tree(self.source)
        self.create("m")
        self.assertEqual(self.listing(), {"snapshots": ["a", "m", "z"]})
        for snapshot, expected in (("z", first), ("a", second), ("m", third)):
            dest = self.root / ("restore-" + snapshot)
            self.restore(snapshot, dest=dest)
            self.assertEqual(tree(dest), expected)

    def test_duplicate_and_missing_ids(self):
        self.populate()
        self.create()
        before = tree(self.repo)
        (self.source / "new").write_bytes(b"must not overwrite")
        self.create(success=False)
        self.assertEqual(tree(self.repo), before)
        self.verify("missing", success=False)
        self.restore("missing", success=False)
        self.assertFalse(self.dest.exists())
        self.assertEqual(tree(self.repo), before)

    def test_ids(self):
        for invalid in ("", ".", "..", "a/b", "../escape", "ñ", "a.b",
                        "_a", "-a", "a" * 65, "a b", "a\n"):
            with self.subTest(invalid=invalid):
                self.cli("create", "--source", self.source, "--repo", self.repo,
                         "--id=" + invalid, success=False)
        self.assertFalse(self.repo.exists())
        self.create("a" * 64)
        self.verify("a" * 64)
        self.create("A0_-z")

    def test_nonempty_destination_protected(self):
        self.populate()
        self.create()
        self.dest.mkdir()
        (self.dest / "protected").write_bytes(bytes(range(256)))
        before = tree(self.dest)
        self.restore(success=False)
        self.assertEqual(tree(self.dest), before)
        # Nonempty destination containing only directories is also protected.
        (self.dest / "protected").unlink()
        (self.dest / "empty").mkdir()
        before = tree(self.dest)
        self.restore(success=False)
        self.assertEqual(tree(self.dest), before)

    def test_overlap_without_source_mutation(self):
        self.populate()
        before = tree(self.source)
        for repo in (self.source, self.source / "new" / "repo", self.root):
            with self.subTest(repo=repo):
                self.cli("create", "--source", self.source, "--repo", repo,
                         "--id", "overlap", success=False)
                self.assertEqual(tree(self.source), before)

    def test_symlinks_in_source_and_ancestors(self):
        (self.source / "file").write_bytes(b"safe")
        link = self.source / "link"
        link.symlink_to("file")
        self.create(success=False)
        self.assertEqual(link.readlink(), Path("file"))
        self.assertEqual((self.source / "file").read_bytes(), b"safe")
        link.unlink()
        ancestor = self.root / "alias"
        ancestor.symlink_to(self.source, target_is_directory=True)
        for source in (ancestor, ancestor / ".." / "source"):
            self.cli("create", "--source", source, "--repo", self.repo,
                     "--id", "v1", success=False)
        self.create()
        repo_alias = self.root / "repo-alias"
        repo_alias.symlink_to(self.repo, target_is_directory=True)
        self.cli("verify", "--repo", repo_alias, "--id", "v1", success=False)
        self.cli("list", "--repo", repo_alias / ".." / "repo", success=False)
        target = self.root / "target"
        target.mkdir()
        self.dest.symlink_to(target, target_is_directory=True)
        self.restore(success=False)
        self.assertEqual(tree(target), {})
        self.assertTrue(self.dest.is_symlink())
        self.restore(dest=self.dest / "child", success=False)
        self.assertEqual(tree(target), {})

    def test_symlinks_in_repo_and_snapshot(self):
        self.create()
        other = self.root / "outside"
        other.write_bytes(b"do not touch")
        (self.repo / "link").symlink_to(other)
        self.verify(success=False)
        self.listing(success=False)
        self.create("v2", success=False)
        self.restore(success=False)
        self.assertEqual(other.read_bytes(), b"do not touch")
        (self.repo / "link").unlink()
        (self.repo / "v1.snapshot").unlink()
        (self.repo / "v1.snapshot").symlink_to(other)
        self.verify(success=False)
        self.restore(success=False)
        self.assertEqual(other.read_bytes(), b"do not touch")

    def test_fifo_and_socket_rejected(self):
        fifo = self.source / "fifo"
        os.mkfifo(fifo)
        self.create(success=False)
        fifo.unlink()
        with socket.socket(socket.AF_UNIX) as sock:
            sock.bind(str(self.source / "socket"))
            self.create(success=False)
        (self.source / "socket").unlink()
        self.create()
        os.mkfifo(self.repo / "fifo")
        self.verify(success=False)
        self.listing(success=False)
        self.create("v2", success=False)
        self.restore(success=False)
        (self.repo / "fifo").unlink()
        self.dest.mkdir()
        os.mkfifo(self.dest / "fifo")
        self.restore(success=False)
        self.assertTrue((self.dest / "fifo").exists())

    def test_corruption_any_region_or_deletion_rejected(self):
        self.populate()
        self.create()
        archive = self.repo / "v1.snapshot"
        pristine = archive.read_bytes()
        # Header, manifest, payload, checksum, truncation and trailing garbage.
        variants = []
        for offset in (0, 25, len(pristine) // 2, len(pristine) - 1):
            damaged = bytearray(pristine)
            damaged[offset] ^= 1
            variants.append(bytes(damaged))
        variants += [pristine[:-1], pristine[:20], pristine + b"extra"]
        for number, damaged in enumerate(variants):
            with self.subTest(number=number):
                archive.write_bytes(damaged)
                self.verify(success=False)
                self.listing(success=False)
                self.restore(success=False)
                self.assertFalse(self.dest.exists())
                self.assertFalse(list(self.root.glob(".restore-*")))
                self.dest.mkdir()
                inode = self.dest.stat().st_ino
                self.restore(success=False)
                self.assertEqual(self.dest.stat().st_ino, inode)
                self.assertEqual(tree(self.dest), {})
                self.dest.rmdir()
        archive.unlink()
        self.verify(success=False)
        self.restore(success=False)
        self.assertFalse(self.dest.exists())

    def test_limit_includes_metadata_and_exact_boundary(self):
        (self.source / "f").write_bytes(b"data")
        self.create()
        archive_size = regular_bytes(self.repo)
        self.assertGreater(archive_size, 4)
        before = tree(self.repo)
        # v1 and v2 have identical metadata length.
        self.create("v2", limit=2 * archive_size - 1, success=False)
        self.assertEqual(tree(self.repo), before)
        self.create("v2", limit=2 * archive_size)
        self.assertEqual(regular_bytes(self.repo), 2 * archive_size)
        self.verify("v1")
        self.verify("v2")
        self.restore("v2")
        self.assertEqual(tree(self.dest), tree(self.source))

    def test_limit_below_existing_preserves_repo_and_no_residual(self):
        self.populate()
        self.create()
        (self.repo / "extra metadata").mkdir()
        (self.repo / "extra metadata" / "blob").write_bytes(b"x" * 93)
        # Hardlinks count once for each regular file name, as st_size requires.
        os.link(self.repo / "extra metadata" / "blob", self.repo / "another")
        baseline = regular_bytes(self.repo)
        before = tree(self.repo)
        for limit in (0, baseline - 1, baseline):
            self.create("new", limit=limit, success=False)
            self.assertEqual(tree(self.repo), before)
            self.assertEqual(regular_bytes(self.repo), baseline)
            self.assertFalse(list(self.repo.glob(".pending-*")))
            self.verify()

    def test_limit_counts_all_nested_regular_files(self):
        self.create()
        snapshot_size = regular_bytes(self.repo)
        (self.repo / "misc").mkdir()
        (self.repo / "misc" / "regular").write_bytes(b"x" * 1000)
        before = tree(self.repo)
        self.create("v2", limit=2 * snapshot_size, success=False)
        self.assertEqual(tree(self.repo), before)
        self.create("v2", limit=2 * snapshot_size + 1000)
        self.assertEqual(regular_bytes(self.repo), 2 * snapshot_size + 1000)

    def test_limit_high_and_empty_source_low(self):
        self.create(limit=0, success=False)
        self.assertEqual(regular_bytes(self.repo), 0)
        self.assertEqual(self.listing(), {"snapshots": []})
        self.populate()
        self.create(limit=10_000_000)
        self.assertLessEqual(regular_bytes(self.repo), 10_000_000)
        self.restore()
        self.assertEqual(tree(self.dest), tree(self.source))

    def test_limit_parser(self):
        for invalid in ("-1", "1.5", "abc", "+1", "", "١"):
            with self.subTest(invalid=invalid):
                self.create(limit=invalid, success=False)
        self.assertFalse(self.repo.exists())

    def test_abandoned_temporaries_cleaned_before_quota(self):
        self.create()
        size = regular_bytes(self.repo)
        pending = self.repo / (".pending-" + "a" * 32)
        pending.write_bytes(b"unfinished" * 10000)
        self.assertEqual(self.listing(), {"snapshots": ["v1"]})
        self.verify()
        self.verify("v2", success=False)
        self.create("v2", limit=size * 2)
        self.assertFalse(pending.exists())
        self.assertEqual(regular_bytes(self.repo), size * 2)

    def test_sigkill_create_and_retry_same_id(self):
        self.create("old")
        old_digest = hashlib.sha256((self.repo / "old.snapshot").read_bytes()).digest()
        with (self.source / "large").open("wb") as output:
            output.truncate(64 * 1024 * 1024)
        process = subprocess.Popen([sys.executable, str(SCRIPT), "create", "--source",
                                    str(self.source), "--repo", str(self.repo), "--id", "new"],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 15
            observed = False
            while time.monotonic() < deadline and process.poll() is None:
                temporaries = list(self.repo.glob(".pending-*"))
                if any(path.stat().st_size >= 64 * 1024 for path in temporaries):
                    observed = True
                    process.kill()
                    break
                time.sleep(0.001)
            stdout, stderr = process.communicate(timeout=15)
            self.assertTrue(observed, (stdout, stderr))
            self.assertEqual(process.returncode, -9)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
        self.assertEqual(self.listing(), {"snapshots": ["old"]})
        self.assertEqual(hashlib.sha256((self.repo / "old.snapshot").read_bytes()).digest(),
                         old_digest)
        self.verify("old")
        self.verify("new", success=False)
        self.create("new", limit=70 * 1024 * 1024)
        self.assertFalse(list(self.repo.glob(".pending-*")))
        self.assertLessEqual(regular_bytes(self.repo), 70 * 1024 * 1024)
        self.verify("new")
        self.restore("new")
        self.assertEqual((self.dest / "large").stat().st_size, 64 * 1024 * 1024)
        with (self.dest / "large").open("rb") as stream:
            self.assertEqual(stream.read(1024), b"\x00" * 1024)

    def test_concurrent_duplicate_create(self):
        self.populate()
        command = [sys.executable, str(SCRIPT), "create", "--source", str(self.source),
                   "--repo", str(self.repo), "--id", "v1"]
        processes = [subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                     for _ in range(2)]
        outputs = [process.communicate(timeout=30) for process in processes]
        self.assertEqual(sorted(process.returncode for process in processes), [0, 1], outputs)
        self.verify()
        self.restore()
        self.assertEqual(tree(self.dest), tree(self.source))

    def test_concurrent_create_quota(self):
        self.create("v0")
        size = regular_bytes(self.repo)
        commands = [[sys.executable, str(SCRIPT), "create", "--source", str(self.source),
                     "--repo", str(self.repo), "--id", snapshot, "--max-bytes", str(size * 2)]
                    for snapshot in ("v1", "v2")]
        processes = [subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                     for command in commands]
        outputs = [process.communicate(timeout=30) for process in processes]
        self.assertEqual(sorted(process.returncode for process in processes), [0, 1], outputs)
        self.assertEqual(regular_bytes(self.repo), size * 2)
        self.assertEqual(len(self.listing()["snapshots"]), 2)
        self.verify("v0")


if __name__ == "__main__":
    unittest.main(verbosity=2)
