"""Contract tests; all data is synthetic and stays inside /trial."""
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
CLI = ROOT / "backup.py"


def tree(root):
    return {p.relative_to(root).as_posix():
            ("dir" if p.is_dir() else hashlib.sha256(p.read_bytes()).hexdigest())
            for p in root.rglob("*")}


def repo_bytes(root):
    return sum(p.lstat().st_size for p in root.rglob("*")
               if stat.S_ISREG(p.lstat().st_mode))


class BackupContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="test-", dir=ROOT / "testing")
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.repo = self.root / "repo"
        self.dest = self.root / "dest"
        self.source.mkdir()
        (self.source / "vacío con espacios").mkdir()
        (self.source / "nested").mkdir()
        (self.source / "nested" / "empty").mkdir()
        (self.source / "nested" / "binary.bin").write_bytes(bytes(range(256)) * 103)
        (self.source / "日本語 🦊.txt").write_bytes(b"hello\x00\xff\n")
        (self.source / "zero").write_bytes(b"")
        (self.source / "manifest.json").write_bytes(b"source metadata-looking name")

    def tearDown(self):
        self.temp.cleanup()

    def call(self, command, identifier=None, ok=True, **kwargs):
        argv = [sys.executable, str(CLI), command, "--repo", str(kwargs.pop("repo", self.repo))]
        if command != "list":
            argv += ["--id", identifier or "v1"]
        if command == "create":
            kwargs.setdefault("source", self.source)
        if command == "restore":
            kwargs.setdefault("dest", self.dest)
        for key, value in kwargs.items():
            argv += ["--" + key.replace("_", "-"), str(value)]
        result = subprocess.run(argv, capture_output=True, text=True, timeout=30)
        if ok:
            self.assertEqual(result.returncode, 0, (argv, result.stderr))
            self.assertEqual(result.stderr, "")
            value = json.loads(result.stdout)
            self.assertIsInstance(value, dict)
            self.assertEqual(len(result.stdout.splitlines()), 1)
            return value
        self.assertNotEqual(result.returncode, 0, argv)
        self.assertEqual(result.stdout, "", (argv, result.stdout))
        # The contract fixes successful JSON; argparse may emit usage on error.
        self.assertTrue(result.stderr, argv)

    def test_roundtrip_autosufficient_and_source_unchanged(self):
        before = tree(self.source)
        self.assertEqual(self.call("create"), {"id": "v1"})
        self.assertEqual(before, tree(self.source))
        self.assertEqual(self.call("verify"), {"id": "v1", "valid": True})
        shutil.rmtree(self.source)
        self.assertEqual(self.call("restore"), {"id": "v1"})
        self.assertEqual(tree(self.dest), before)

    def test_empty_source_and_existing_empty_destination(self):
        shutil.rmtree(self.source)
        self.source.mkdir()
        self.dest.mkdir()
        self.call("create")
        self.call("restore")
        self.assertEqual(tree(self.dest), {})

    def test_versions_sorted_and_exact(self):
        versions = {}
        for identifier in ("z9", "A0", "mid"):
            (self.source / "zero").write_bytes(identifier.encode())
            if identifier == "A0":
                (self.source / "added").write_bytes(b"new")
                (self.source / "日本語 🦊.txt").unlink()
            if identifier == "mid":
                (self.source / "added").unlink()
                shutil.rmtree(self.source / "nested")
            versions[identifier] = tree(self.source)
            self.call("create", identifier)
        self.assertEqual(self.call("list"), {"snapshots": ["A0", "mid", "z9"]})
        for identifier, expected in versions.items():
            self.call("verify", identifier)
            self.call("restore", identifier, dest=self.root / identifier)
            self.assertEqual(tree(self.root / identifier), expected)

    def test_new_repo_and_missing_ids(self):
        self.assertEqual(self.call("list"), {"snapshots": []})
        self.repo.mkdir()
        self.assertEqual(self.call("list"), {"snapshots": []})
        self.call("verify", ok=False)
        self.call("restore", ok=False)
        self.assertFalse(self.dest.exists())

    def test_ids(self):
        for bad in ("../escape", ".", "a/b", "-a", "a b", "á", "a" * 65, "x\n"):
            with self.subTest(id=bad):
                for cmd in ("create", "verify", "restore"):
                    self.call(cmd, bad, ok=False)
        for good in ("0", "a-_1", "Z" * 64):
            self.call("create", good)
            self.call("verify", good)

    def test_existing_id_not_overwritten(self):
        self.call("create")
        original = tree(self.repo)
        (self.source / "zero").write_bytes(b"new")
        self.call("create", ok=False)
        self.assertEqual(tree(self.repo), original)
        self.call("verify")

    def test_protected_nonempty_destination(self):
        self.call("create")
        self.dest.mkdir()
        (self.dest / "protected").write_bytes(b"keep these bytes")
        original = tree(self.dest)
        self.call("restore", ok=False)
        self.assertEqual(tree(self.dest), original)
        (self.dest / "link").symlink_to(self.source)
        self.call("restore", ok=False)
        self.assertEqual((self.dest / "protected").read_bytes(), b"keep these bytes")

    def test_overlap(self):
        before = tree(self.source)
        for repo in (self.source, self.source / "backup", self.root):
            self.call("create", repo=repo, ok=False)
            self.assertEqual(tree(self.source), before)
        self.call("create")
        before_repo = tree(self.repo)
        for dest in (self.repo, self.repo / "output", self.root):
            self.call("restore", dest=dest, ok=False)
            self.assertEqual(tree(self.repo), before_repo)

    def test_symlinks_source_paths_and_ancestors(self):
        link = self.source / "linked"
        for target in (self.root / "missing", self.source / "zero", self.root):
            link.symlink_to(target)
            self.call("create", ok=False)
            link.unlink()
        alias = self.root / "alias"
        alias.symlink_to(self.source, target_is_directory=True)
        self.call("create", source=alias, ok=False)
        self.call("create", source=alias / "nested", ok=False)
        self.call("create", source=str(alias) + "/../source", ok=False)

    def test_symlinks_repo_dest_and_snapshot(self):
        self.call("create")
        alias = self.root / "repo-alias"
        alias.symlink_to(self.repo, target_is_directory=True)
        for cmd in ("list", "verify", "create", "restore"):
            self.call(cmd, repo=alias, ok=False)
        self.dest.symlink_to(self.root / "missing")
        self.call("restore", ok=False)
        self.dest.unlink()
        (self.repo / "snapshots" / "v1" / "tree" / "zero").unlink()
        (self.repo / "snapshots" / "v1" / "tree" / "zero").symlink_to(self.source / "zero")
        for cmd in ("list", "verify", "create", "restore"):
            self.call(cmd, "new" if cmd == "create" else "v1", ok=False)

    def test_special_files(self):
        fifo = self.source / "pipe"
        os.mkfifo(fifo)
        self.call("create", ok=False)
        fifo.unlink()
        self.call("create")
        for path in (self.repo / ".staging" / "pipe", self.repo / "snapshots" / "v1" / "pipe"):
            os.mkfifo(path)
            for cmd in ("list", "verify", "restore", "create"):
                self.call(cmd, "new" if cmd == "create" else "v1", ok=False)
            path.unlink()
        os.mkfifo(self.dest)
        self.call("restore", ok=False)

    def test_socket_source_when_environment_allows(self):
        with socket.socket(socket.AF_UNIX) as sock:
            try:
                sock.bind(str(self.source / "socket"))
            except PermissionError as exc:
                self.skipTest(f"sandbox prevents creating Unix socket: {exc}")
            self.call("create", ok=False)

    def test_every_regular_snapshot_file_corrupted_or_deleted(self):
        self.call("create")
        original = self.repo / "snapshots" / "v1"
        files = sorted(p.relative_to(original) for p in original.rglob("*") if p.is_file())
        for relative in files:
            for mutation in ("change", "delete"):
                with self.subTest(file=str(relative), mutation=mutation):
                    sandbox_repo = self.root / "corrupt-repo"
                    shutil.copytree(self.repo, sandbox_repo)
                    victim = sandbox_repo / "snapshots" / "v1" / relative
                    if mutation == "delete":
                        victim.unlink()
                    else:
                        data = victim.read_bytes()
                        victim.write_bytes(bytes([data[0] ^ 0xff]) + data[1:] if data else b"x")
                    self.call("verify", repo=sandbox_repo, ok=False)
                    self.call("restore", repo=sandbox_repo, ok=False)
                    self.assertFalse(self.dest.exists())
                    self.dest.mkdir()
                    self.call("restore", repo=sandbox_repo, ok=False)
                    self.assertEqual(tree(self.dest), {})
                    self.dest.rmdir()
                    self.assertEqual(self.call("list", repo=sandbox_repo), {"snapshots": []})
                    shutil.rmtree(sandbox_repo)
        self.call("verify")

    def test_snapshot_structure_corruption(self):
        self.call("create")
        snapshot = self.repo / "snapshots" / "v1"
        for name, kind in (("extra", "file"), ("empty-extra", "dir")):
            entry = snapshot / "tree" / name
            entry.mkdir() if kind == "dir" else entry.write_bytes(b"extra")
            self.call("verify", ok=False)
            self.call("restore", ok=False)
            self.assertEqual(self.call("list"), {"snapshots": []})
            entry.rmdir() if kind == "dir" else entry.unlink()
        (snapshot / "tree" / "vacío con espacios").rmdir()
        self.call("verify", ok=False)

    def test_malformed_resealed_manifest(self):
        self.call("create")
        snap = self.repo / "snapshots" / "v1"
        base = json.loads((snap / "manifest.json").read_bytes())
        variants = []
        for path in ("../escape", "/absolute", "a//b", "a/./b", "a/../b", "a\x00b"):
            variants.append({"format": 1, "id": "v1", "entries": {path: {"type": "dir"}}})
        variants += [[], {**base, "format": True}, {**base, "id": "other"},
                     {**base, "entries": {"zero": {"type": "file", "size": True, "sha256": "a" * 64}}},
                     {**base, "entries": {"parent/child": {"type": "dir"}}}]
        raw_variants = [json.dumps(v).encode() for v in variants]
        raw_variants += [b'{"format":1,"format":1,"id":"v1","entries":{}}', b"{invalid"]
        for raw in raw_variants:
            with self.subTest(raw=raw):
                (snap / "manifest.json").write_bytes(raw)
                (snap / "seal.sha256").write_text(hashlib.sha256(raw).hexdigest() + "\n")
                self.call("verify", ok=False)
                self.call("restore", ok=False)
                self.assertFalse(self.dest.exists())
        self.assertFalse((self.root / "escape").exists())

    def test_unfinished_staging_and_incomplete_snapshot(self):
        self.call("create")
        partial = self.repo / ".staging" / "abandoned"
        partial.mkdir()
        (partial / "partial").write_bytes(b"unfinished")
        unfinished = self.repo / "snapshots" / "unfinished"
        unfinished.mkdir()
        (unfinished / "manifest.json").write_bytes(b"not complete")
        self.assertEqual(self.call("list"), {"snapshots": ["v1"]})
        self.call("create", "fresh")
        self.call("verify", "fresh")
        self.assertFalse(partial.exists())
        self.assertTrue(unfinished.exists())

    def test_sigkill_real_create_recovery(self):
        self.call("create", "previous")
        before = tree(self.repo / "snapshots" / "previous")
        big = self.source / "large.bin"
        with big.open("wb") as stream:
            stream.truncate(128 * 1024 * 1024)
        source_before = tree(self.source)
        limit = repo_bytes(self.repo) + repo_bytes(self.source) + 65536
        argv = [sys.executable, str(CLI), "create", "--source", str(self.source),
                "--repo", str(self.repo), "--id", "interrupted",
                "--max-bytes", str(limit)]
        proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        observed = False
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and proc.poll() is None:
                staged = list((self.repo / ".staging").glob("create-*/tree/large.bin"))
                if staged and staged[0].stat().st_size >= 1024 * 1024:
                    observed = True
                    os.kill(proc.pid, signal.SIGKILL)
                    break
                time.sleep(0.001)
            stdout, stderr = proc.communicate(timeout=15)
            self.assertTrue(observed, "create completed before observable SIGKILL; test is inconclusive")
            self.assertEqual(proc.returncode, -signal.SIGKILL)
            self.assertEqual(stdout, b"")
            self.assertEqual(stderr, b"")
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.communicate()
        self.assertFalse((self.repo / "snapshots" / "interrupted").exists())
        self.assertTrue(list((self.repo / ".staging").glob("create-*")))
        self.assertEqual(self.call("list"), {"snapshots": ["previous"]})
        self.assertEqual(tree(self.repo / "snapshots" / "previous"), before)
        self.call("verify", "previous")
        self.call("create", "interrupted", max_bytes=limit)
        self.assertLessEqual(repo_bytes(self.repo), limit)
        self.assertEqual(list((self.repo / ".staging").iterdir()), [])
        self.call("verify", "interrupted")
        self.call("restore", "interrupted")
        self.assertEqual(tree(self.dest), source_before)
        self.assertEqual(tree(self.source), source_before)
        self.assertEqual(self.call("list"), {"snapshots": ["interrupted", "previous"]})

    def test_concurrent_creates_same_id(self):
        argv = [sys.executable, str(CLI), "create", "--source", str(self.source),
                "--repo", str(self.repo), "--id", "race"]
        # Initialize the repository first to isolate duplicate ID locking.
        self.call("create", "init")
        processes = [subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                     for _ in range(2)]
        results = [(p.communicate(timeout=30), p.returncode) for p in processes]
        self.assertEqual(sorted(code for _, code in results), [0, 1])
        self.call("verify", "race")
        self.call("restore", "race")
        self.assertEqual(tree(self.dest), tree(self.source))

    def test_long_nested_and_unusual_names(self):
        nested = self.source
        for number in range(30):
            nested = nested / str(number)
            nested.mkdir()
        (nested / "line\nbreak\\file").write_bytes(b"arbitrary")
        self.call("create")
        self.call("restore")
        self.assertEqual(tree(self.dest), tree(self.source))

    def test_quota_high_and_exact_boundary(self):
        source_before = tree(self.source)
        self.call("create", max_bytes=10**9)
        size = repo_bytes(self.repo)
        self.assertGreater(size, repo_bytes(self.source))
        probe = self.root / "exact-repo"
        self.call("create", repo=probe, max_bytes=size)
        self.assertEqual(repo_bytes(probe), size)
        self.call("verify", repo=probe)
        self.call("restore", repo=probe)
        self.assertEqual(tree(self.dest), source_before)
        self.assertEqual(tree(self.source), source_before)

    def test_quota_one_byte_below_including_metadata(self):
        self.call("create")
        size = repo_bytes(self.repo)
        probe = self.root / "too-small-repo"
        before = tree(self.source)
        self.call("create", repo=probe, max_bytes=size - 1, ok=False)
        self.assertEqual(repo_bytes(probe), 0)
        self.assertEqual(self.call("list", repo=probe), {"snapshots": []})
        self.assertEqual(list((probe / ".staging").iterdir()), [])
        self.assertEqual(tree(self.source), before)
        self.call("create", repo=probe, max_bytes=size)
        self.call("verify", repo=probe)

    def test_quota_below_existing_repeated_rejection(self):
        self.call("create")
        size, before = repo_bytes(self.repo), tree(self.repo)
        for limit in (0, size - 1, size):
            for _ in range(2):
                self.call("create", "v2", max_bytes=limit, ok=False)
                self.assertEqual(repo_bytes(self.repo), size)
                self.assertEqual(tree(self.repo), before)
                self.call("verify")
        self.call("create", "v2", max_bytes=2 * size)
        self.assertEqual(repo_bytes(self.repo), 2 * size)
        self.call("verify", "v2")

    def test_quota_partial_data_failure_and_retry(self):
        self.call("create")
        before, size = tree(self.repo), repo_bytes(self.repo)
        # Sorts late, so earlier data was written before quota failure.
        (self.source / "zz-large").write_bytes(b"X" * (2 * 1024 * 1024))
        source_before = tree(self.source)
        self.call("create", "v2", max_bytes=size + 1024 * 1024, ok=False)
        self.assertEqual(tree(self.repo), before)
        self.assertEqual(repo_bytes(self.repo), size)
        self.assertEqual(tree(self.source), source_before)
        self.call("verify")
        self.call("create", "v2", max_bytes=size + repo_bytes(self.source) + 65536)
        self.call("verify", "v2")

    def test_quota_empty_files_and_directories_need_metadata(self):
        shutil.rmtree(self.source)
        self.source.mkdir()
        for n in range(30):
            (self.source / ("empty-dir-" + str(n))).mkdir()
            (self.source / ("empty-file-" + str(n))).touch()
        self.assertEqual(repo_bytes(self.source), 0)
        self.call("create", max_bytes=0, ok=False)
        self.assertEqual(repo_bytes(self.repo), 0)
        self.call("create", max_bytes=65536)
        size = repo_bytes(self.repo)
        self.assertGreater(size, 0)
        self.assertEqual(size, sum(p.stat().st_size for p in
                         (self.repo / "snapshots" / "v1").glob("*") if p.is_file()))
        self.call("restore")
        self.assertEqual(tree(self.dest), tree(self.source))

    def test_quota_invalid_limits_without_repository_mutation(self):
        for limit in ("-1", "1.5", "no", "", "NaN"):
            with self.subTest(limit=limit):
                self.call("create", max_bytes=limit, ok=False)
                self.assertFalse(self.repo.exists())

    def test_quota_counts_incomplete_published_regular_files(self):
        self.call("create")
        incomplete = self.repo / "snapshots" / "incomplete"
        incomplete.mkdir()
        (incomplete / "unknown-metadata").write_bytes(b"Z" * 50000)
        size, before = repo_bytes(self.repo), tree(self.repo)
        self.call("create", "v2", max_bytes=size - 1, ok=False)
        self.assertEqual(tree(self.repo), before)
        self.assertEqual(self.call("list"), {"snapshots": ["v1"]})
        self.call("create", "v2", max_bytes=size + 65536)
        self.assertLessEqual(repo_bytes(self.repo), size + 65536)

    def test_quota_reclaims_abandoned_staging_at_exact_limit(self):
        self.call("create")
        existing = repo_bytes(self.repo)
        probe = self.root / "probe"
        self.call("create", "fresh", repo=probe)
        limit = existing + repo_bytes(probe)
        partial = self.repo / ".staging" / "create-abandoned"
        partial.mkdir()
        (partial / "leftover").write_bytes(b"X" * (limit + 100))
        before = tree(self.repo / "snapshots" / "v1")
        self.call("create", "fresh", max_bytes=limit)
        self.assertEqual(repo_bytes(self.repo), limit)
        self.assertFalse(partial.exists())
        self.assertEqual(tree(self.repo / "snapshots" / "v1"), before)
        self.call("verify")
        self.call("verify", "fresh")

    def test_quota_existing_id_rejection_preserves_bytes(self):
        self.call("create")
        before = tree(self.repo)
        self.call("create", max_bytes=10**9, ok=False)
        self.assertEqual(tree(self.repo), before)

    def test_quota_concurrent_writers_share_budget(self):
        self.call("create")
        size, previous = repo_bytes(self.repo), tree(self.repo / "snapshots" / "v1")
        processes = []
        try:
            for identifier in ("aa", "bb"):
                argv = [sys.executable, str(CLI), "create", "--source", str(self.source),
                        "--repo", str(self.repo), "--id", identifier,
                        "--max-bytes", str(2 * size)]
                processes.append(subprocess.Popen(argv, stdout=subprocess.PIPE,
                                                  stderr=subprocess.PIPE))
            results = [(p.communicate(timeout=30), p.returncode) for p in processes]
            self.assertEqual(sorted(code for _, code in results), [0, 1])
            self.assertEqual(repo_bytes(self.repo), 2 * size)
            self.assertEqual(tree(self.repo / "snapshots" / "v1"), previous)
            self.assertEqual(list((self.repo / ".staging").iterdir()), [])
            for identifier in self.call("list")["snapshots"]:
                self.call("verify", identifier)
        finally:
            for p in processes:
                if p.poll() is None:
                    p.kill()
                    p.communicate()


if __name__ == "__main__":
    unittest.main(verbosity=2)
