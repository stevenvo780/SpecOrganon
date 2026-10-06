"""Contract tests. All fixtures are private directories beneath /trial/solution."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import time
import unittest


HERE = Path(__file__).resolve().parent
PROGRAM = HERE / "backup.py"
WORK = HERE / ".test-work"
WORK.mkdir(exist_ok=True)


def fingerprint(path: Path) -> tuple[list[str], dict[str, bytes]]:
    dirs = [""]
    files = {}
    for current, children, names in os.walk(path):
        relative = Path(current).relative_to(path)
        dirs.extend((relative / name).as_posix() for name in children)
        for name in names:
            files[(relative / name).as_posix()] = (Path(current) / name).read_bytes()
    return sorted(dirs), files


def size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


class BackupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="case-", dir=WORK)
        self.base = Path(self.temp.name)
        self.source = self.base / "source"
        self.source.mkdir()
        self.repo = self.base / "repo"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def cli(self, command: str, *options: object, ok: bool = True) -> dict | None:
        arguments = [sys.executable, str(PROGRAM), command, *map(str, options)]
        result = subprocess.run(arguments, capture_output=True, text=True, timeout=30)
        if ok:
            self.assertEqual(result.returncode, 0, (arguments, result.stdout, result.stderr))
            self.assertEqual(result.stderr, "")
            value = json.loads(result.stdout)
            self.assertIsInstance(value, dict)
            return value
        self.assertNotEqual(result.returncode, 0, (arguments, result.stdout))
        self.assertEqual(result.stdout, "", (arguments, result.stdout))
        self.assertTrue(result.stderr)
        return None

    def create(self, ident: str = "v1", *, repo: Path | None = None,
               limit: int | None = None, ok: bool = True) -> dict | None:
        options: list[object] = ["--source", self.source, "--repo", repo or self.repo, "--id", ident]
        if limit is not None:
            options.extend(["--max-bytes", limit])
        return self.cli("create", *options, ok=ok)

    def verify(self, ident: str = "v1", *, repo: Path | None = None, ok: bool = True) -> dict | None:
        return self.cli("verify", "--repo", repo or self.repo, "--id", ident, ok=ok)

    def restore(self, ident: str = "v1", *, dest: Path | None = None,
                repo: Path | None = None, ok: bool = True) -> dict | None:
        return self.cli("restore", "--repo", repo or self.repo, "--id", ident,
                        "--dest", dest or self.base / "restored", ok=ok)

    def assert_no_stages(self) -> None:
        self.assertEqual(list(self.repo.glob(".backup-stage-*")), [])

    def test_empty_new_repository_and_missing_id(self) -> None:
        self.assertEqual(self.cli("list", "--repo", self.repo), {"snapshots": []})
        self.repo.mkdir()
        self.assertEqual(self.cli("list", "--repo", self.repo), {"snapshots": []})
        self.verify("missing", ok=False)
        self.restore("missing", ok=False)
        self.assertFalse((self.base / "restored").exists())

    def test_empty_source_roundtrip(self) -> None:
        self.assertEqual(self.create(), {"id": "v1"})
        self.assertEqual(self.verify(), {"id": "v1", "valid": True})
        self.assertEqual(self.restore(), {"id": "v1"})
        self.assertEqual(fingerprint(self.source), fingerprint(self.base / "restored"))

    def test_arbitrary_bytes_unicode_and_empty_directories(self) -> None:
        (self.source / "空 vacío" / "más vacío").mkdir(parents=True)
        (self.source / "datos con espacios 😀").write_bytes(bytes(range(256)) * 9000)
        (self.source / "空 vacío" / "zero").touch()
        (self.source / "barra\\literal").write_bytes(b"\x00\xff\r\n")
        before = fingerprint(self.source)
        mtimes = {p: p.stat().st_mtime_ns for p in self.source.rglob("*")}
        self.create(limit=10_000_000)
        self.assertEqual(fingerprint(self.source), before)
        self.assertEqual({p: p.stat().st_mtime_ns for p in mtimes}, mtimes)
        self.restore()
        self.assertEqual(fingerprint(self.base / "restored"), before)

    def test_five_successive_versions_exact_and_self_contained(self) -> None:
        rng = random.Random(70431)
        expected = {}
        (self.source / "vacío").mkdir()
        for number in range(5):
            (self.source / "changing").write_bytes(rng.randbytes(1000 + number))
            (self.source / f"nuevo {number} é").write_bytes(rng.randbytes(257))
            if number >= 2:
                (self.source / f"nuevo {number - 2} é").unlink()
            if number == 3:
                (self.source / "vacío").rmdir()
                (self.source / "other empty" / "nested").mkdir(parents=True)
            ident = f"V{number}"
            expected[ident] = fingerprint(self.source)
            self.create(ident, limit=1_000_000)
        self.assertEqual(self.cli("list", "--repo", self.repo), {"snapshots": sorted(expected)})
        moved = self.base / "moved-repo"
        shutil.move(self.repo, moved)
        shutil.rmtree(self.source)
        for ident, contents in expected.items():
            with self.subTest(version=ident):
                self.verify(ident, repo=moved)
                dest = self.base / ident
                self.restore(ident, repo=moved, dest=dest)
                self.assertEqual(fingerprint(dest), contents)

    def test_ids_and_duplicate_do_not_change_repository(self) -> None:
        (self.source / "a").write_bytes(b"first")
        for ident in ("a", "A_0-", "x" * 64):
            self.create(ident)
        self.assertEqual(self.cli("list", "--repo", self.repo), {"snapshots": ["A_0-", "a", "x" * 64]})
        before = fingerprint(self.repo)
        (self.source / "a").write_bytes(b"second")
        self.create("a", ok=False)
        for ident in ("", "../escape", "a/b", "-a", "_a", "é", "x" * 65, "a\n"):
            with self.subTest(id=ident):
                self.create(ident, ok=False)
                self.verify(ident, ok=False)
                self.restore(ident, ok=False)
        self.assertEqual(fingerprint(self.repo), before)

    def test_exact_limit_and_metadata_is_counted(self) -> None:
        (self.source / "data").write_bytes(b"1234567")
        (self.source / "empty").mkdir()
        probe = self.base / "probe"
        self.create(repo=probe)
        required = size(probe)
        self.assertGreater(required, 7)
        self.create(limit=required - 1, ok=False)
        self.assertEqual(size(self.repo), 0)
        self.assert_no_stages()
        self.create(limit=required)
        self.assertEqual(size(self.repo), required)
        self.verify()

    def test_zero_limit_and_invalid_limits(self) -> None:
        self.create(limit=0, ok=False)
        self.assertEqual(size(self.repo), 0)
        for value in ("-1", "1.0", "no", "+2"):
            self.cli("create", "--source", self.source, "--repo", self.repo,
                     "--id", "v1", "--max-bytes", value, ok=False)
        self.create(limit=100_000)

    def test_existing_bytes_and_repeated_quota_rejections(self) -> None:
        (self.source / "a").write_bytes(b"original")
        self.create("old", limit=100_000)
        before = fingerprint(self.repo)
        used = size(self.repo)
        (self.source / "a").write_bytes(b"new" * 100)
        for number in range(3):
            self.create(f"new{number}", limit=used - 1, ok=False)
            self.assertEqual(size(self.repo), used)
            self.assertEqual(fingerprint(self.repo), before)
            self.assert_no_stages()
        self.verify("old")
        self.restore("old")
        self.assertEqual((self.base / "restored" / "a").read_bytes(), b"original")

    def test_quota_counts_all_nested_regular_files(self) -> None:
        self.repo.mkdir()
        (self.repo / "unrelated" / "empty").mkdir(parents=True)
        (self.repo / "unrelated" / "metadata").write_bytes(b"M" * 777)
        (self.repo / "outside").write_bytes(b"X" * 333)
        probe = self.base / "probe"
        self.create(repo=probe)
        snapshot_bytes = size(probe)
        self.create(limit=1110 + snapshot_bytes - 1, ok=False)
        self.assertEqual(size(self.repo), 1110)
        self.create(limit=1110 + snapshot_bytes)
        self.assertEqual(size(self.repo), 1110 + snapshot_bytes)
        self.assertEqual((self.repo / "unrelated" / "metadata").read_bytes(), b"M" * 777)

    def test_successive_versions_at_exact_aggregate_limit(self) -> None:
        (self.source / "a").write_bytes(b"one")
        self.create("one")
        used = size(self.repo)
        (self.source / "a").write_bytes(b"two-two")
        probe = self.base / "probe"
        self.create("two", repo=probe)
        required = used + size(probe)
        self.create("two", limit=required - 1, ok=False)
        self.assertEqual(size(self.repo), used)
        self.create("two", limit=required)
        self.assertEqual(size(self.repo), required)
        for ident, content in (("one", b"one"), ("two", b"two-two")):
            self.restore(ident, dest=self.base / ident)
            self.assertEqual((self.base / ident / "a").read_bytes(), content)

    def test_nonempty_destination_preserved_and_empty_allowed(self) -> None:
        (self.source / "a").write_bytes(b"backup")
        self.create()
        protected = self.base / "protected"
        (protected / "empty").mkdir(parents=True)
        (protected / "keep").write_bytes(b"DO NOT CHANGE\x00\xff")
        before = fingerprint(protected)
        self.restore(dest=protected, ok=False)
        self.assertEqual(fingerprint(protected), before)
        empty = self.base / "empty-destination"
        empty.mkdir()
        self.restore(dest=empty)
        self.assertEqual(fingerprint(empty), fingerprint(self.source))

    def test_source_symlinks_root_ancestor_and_nested(self) -> None:
        target = self.base / "target"
        target.write_bytes(b"safe")
        (self.source / "link").symlink_to(target)
        self.create(ok=False)
        self.assertEqual(size(self.repo), 0)
        (self.source / "link").unlink()
        linked = self.base / "linked"
        linked.symlink_to(self.source, target_is_directory=True)
        for path in (linked, linked / ".." / "source"):
            self.cli("create", "--source", path, "--repo", self.repo, "--id", "v1", ok=False)
        parent_link = self.base / "parent-link"
        parent_link.symlink_to(self.base, target_is_directory=True)
        self.cli("create", "--source", parent_link / "source", "--repo", self.repo, "--id", "v1", ok=False)
        self.assertEqual(target.read_bytes(), b"safe")

    def test_repo_symlinks_root_ancestor_nested_and_snapshot(self) -> None:
        self.create()
        linked = self.base / "linked-repo"
        linked.symlink_to(self.repo, target_is_directory=True)
        self.verify(repo=linked, ok=False)
        self.restore(repo=linked, ok=False)
        self.cli("list", "--repo", linked, ok=False)
        parent_link = self.base / "parent-link"
        parent_link.symlink_to(self.base, target_is_directory=True)
        self.verify(repo=parent_link / "repo", ok=False)
        target = self.base / "outside"
        target.write_bytes(b"protected")
        (self.repo / "nested").mkdir()
        (self.repo / "nested" / "link").symlink_to(target)
        self.verify(ok=False)
        self.create("v2", ok=False)
        (self.repo / "nested" / "link").unlink()
        archive = self.repo / "v1.bkp"
        moved = self.base / "archive"
        archive.rename(moved)
        archive.symlink_to(moved)
        self.verify(ok=False)
        self.restore(ok=False)
        self.assertEqual(target.read_bytes(), b"protected")

    def test_destination_symlinks_and_special_file_preserved(self) -> None:
        (self.source / "a").write_bytes(b"data")
        self.create()
        actual = self.base / "actual"
        actual.mkdir()
        link = self.base / "dest-link"
        link.symlink_to(actual, target_is_directory=True)
        self.restore(dest=link, ok=False)
        self.assertEqual(os.listdir(actual), [])
        self.assertTrue(link.is_symlink())
        parent_link = self.base / "parent-link"
        parent_link.symlink_to(actual, target_is_directory=True)
        self.restore(dest=parent_link / "dest", ok=False)
        self.assertEqual(os.listdir(actual), [])
        fifo = self.base / "fifo"
        os.mkfifo(fifo)
        self.restore(dest=fifo, ok=False)
        self.assertTrue(fifo.exists())

    def test_special_files_in_source_repo_and_snapshot(self) -> None:
        fifo = self.source / "fifo"
        os.mkfifo(fifo)
        self.create(ok=False)
        fifo.unlink()
        self.create()
        fifo = self.repo / "fifo"
        os.mkfifo(fifo)
        self.verify(ok=False)
        self.restore(ok=False)
        self.create("v2", ok=False)
        fifo.unlink()
        (self.repo / "v1.bkp").unlink()
        os.mkfifo(self.repo / "v1.bkp")
        self.verify(ok=False)
        self.restore(ok=False)

    def test_overlap_rejected_without_modifying_source(self) -> None:
        (self.source / "a").write_bytes(b"immutable")
        before = fingerprint(self.source)
        for repo in (self.source, self.source / "new-repo", self.base):
            self.create(repo=repo, ok=False)
            self.assertEqual(fingerprint(self.source), before)
        alias = self.source / ".." / "separate"
        self.create(repo=alias)
        self.assertEqual(fingerprint(self.source), before)

    def test_corruption_header_metadata_data_digest_and_truncation(self) -> None:
        (self.source / "a").write_bytes(b"payload" * 100)
        self.create()
        archive = self.repo / "v1.bkp"
        original = archive.read_bytes()
        metadata_length = struct.unpack(">Q", original[12:20])[0]
        positions = (0, 12, 20, 20 + metadata_length, len(original) - 1)
        protected = self.base / "protected"
        protected.mkdir()
        (protected / "keep").write_bytes(b"unchanged")
        for position in positions:
            with self.subTest(position=position):
                modified = bytearray(original)
                modified[position] ^= 0x80
                archive.write_bytes(modified)
                self.verify(ok=False)
                self.restore(ok=False)
                self.restore(dest=protected, ok=False)
                self.assertFalse((self.base / "restored").exists())
                self.assertEqual((protected / "keep").read_bytes(), b"unchanged")
                self.assertEqual(list(self.base.glob(".backup-restore-*")), [])
        for length in (0, 19, 20 + metadata_length, len(original) - 1):
            archive.write_bytes(original[:length])
            self.verify(ok=False)
            self.restore(ok=False)
        archive.unlink()
        self.verify(ok=False)
        self.restore(ok=False)
        self.assertFalse((self.base / "restored").exists())

    def test_corrupt_snapshot_does_not_break_other_versions(self) -> None:
        (self.source / "a").write_bytes(b"old")
        self.create("old")
        (self.source / "a").write_bytes(b"new")
        self.create("new")
        (self.repo / "new.bkp").write_bytes(b"broken")
        self.verify("new", ok=False)
        self.verify("old")
        self.restore("old")
        self.assertEqual((self.base / "restored" / "a").read_bytes(), b"old")
        self.create("third", limit=100_000)
        self.verify("third")

    def test_invalid_manifest_with_recomputed_checksum(self) -> None:
        self.create()
        archive = self.repo / "v1.bkp"
        manifest = {"format": 2, "id": "v1", "dirs": [""], "files": []}
        cases = [
            {**manifest, "files": [{"path": "../escaped", "size": 0}]},
            {**manifest, "files": [{"path": "/escaped", "size": 0}]},
            {**manifest, "files": [{"path": "a", "size": True}]},
            {**manifest, "files": [{"path": "a/b", "size": 0}]},
            {**manifest, "dirs": ["", "a", "a"]},
            {**manifest, "dirs": ["", "../escaped"]},
            {**manifest, "dirs": ["", "a/b"]},
            {**manifest, "id": "other"},
            {**manifest, "extra": "hidden"},
        ]
        for case in cases:
            with self.subTest(manifest=case):
                raw = json.dumps(case, sort_keys=True, separators=(",", ":")).encode("ascii")
                body = struct.pack(">12sQ", b"PYBACKUP\x00\x02\r\n", len(raw)) + raw
                archive.write_bytes(body + hashlib.sha256(body).digest())
                self.verify(ok=False)
                self.restore(ok=False)
                self.assertFalse((self.base / "restored").exists())
                self.assertFalse((self.base / "escaped").exists())

    def test_stale_stage_cleanup_including_published_hardlink(self) -> None:
        self.create("old")
        before = (self.repo / "old.bkp").read_bytes()
        os.link(self.repo / "old.bkp", self.repo / (".backup-stage-" + "a" * 32 + ".tmp"))
        (self.repo / (".backup-stage-" + "b" * 32 + ".tmp")).write_bytes(b"partial")
        self.assertEqual(self.cli("list", "--repo", self.repo), {"snapshots": ["old"]})
        self.create("new", limit=len(before) - 1, ok=False)
        self.assertEqual(size(self.repo), len(before))
        self.assert_no_stages()
        self.assertEqual((self.repo / "old.bkp").read_bytes(), before)
        self.verify("old")
        self.create("new", limit=100_000)

    def test_sigkill_and_retry_same_id_without_residual_growth(self) -> None:
        (self.source / "a").write_bytes(b"previous")
        self.create("previous")
        original = (self.repo / "previous.bkp").read_bytes()
        with (self.source / "large").open("wb") as stream:
            stream.truncate(256 * 1024 * 1024)
        args = [sys.executable, str(PROGRAM), "create", "--source", str(self.source),
                "--repo", str(self.repo), "--id", "interrupted", "--max-bytes", "400000000"]
        child = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 10
            while not list(self.repo.glob(".backup-stage-*")):
                if child.poll() is not None or time.monotonic() >= deadline:
                    self.fail("no se pudo observar create durante staging")
                time.sleep(0.002)
            os.kill(child.pid, signal.SIGKILL)
            stdout, stderr = child.communicate(timeout=10)
            self.assertEqual(child.returncode, -signal.SIGKILL, (stdout, stderr))
            self.assertEqual(stdout, b"")
        finally:
            if child.poll() is None:
                child.kill()
                child.communicate(timeout=10)
        self.assertEqual(self.cli("list", "--repo", self.repo), {"snapshots": ["previous"]})
        self.verify("previous")
        self.assertEqual((self.repo / "previous.bkp").read_bytes(), original)
        self.create("interrupted", limit=len(original) - 1, ok=False)
        self.assertEqual(size(self.repo), len(original))
        self.assert_no_stages()
        (self.source / "large").unlink()
        (self.source / "a").write_bytes(b"retried")
        self.create("interrupted", limit=100_000)
        self.assert_no_stages()
        self.restore("interrupted")
        self.assertEqual((self.base / "restored" / "a").read_bytes(), b"retried")
        self.verify("previous")

    def test_concurrent_creates_same_id_cannot_overwrite(self) -> None:
        (self.source / "a").write_bytes(b"stable")
        args = [sys.executable, str(PROGRAM), "create", "--source", str(self.source),
                "--repo", str(self.repo), "--id", "same", "--max-bytes", "100000"]
        children = [subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(3)]
        results = [child.communicate(timeout=30) for child in children]
        self.assertEqual(sorted(child.returncode for child in children), [0, 1, 1], results)
        self.verify("same")
        self.assert_no_stages()
        self.assertEqual(self.cli("list", "--repo", self.repo), {"snapshots": ["same"]})


if __name__ == "__main__":
    unittest.main(verbosity=2)
