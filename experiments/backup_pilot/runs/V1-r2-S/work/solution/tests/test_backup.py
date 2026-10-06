"""CLI integration checks derived from SPEC.md; all fixtures are private."""

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


SOLUTION = Path(__file__).resolve().parents[1]
BACKUP = SOLUTION / "backup.py"


def tree_signature(root):
    directories, files = [], {}
    for current, names, filenames in os.walk(root):
        relative = Path(current).relative_to(root)
        directories.extend((relative / name).as_posix() for name in names)
        for filename in filenames:
            path = Path(current) / filename
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                while block := stream.read(1024 * 1024):
                    digest.update(block)
            files[(relative / filename).as_posix()] = (path.stat().st_size, digest.hexdigest())
    return sorted(directories), files


def regular_bytes(root):
    """Independent oracle: sum lstat sizes of every file, including hidden files."""
    return sum(path.lstat().st_size for path in root.rglob("*") if path.is_file())


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="backup-test-", dir=SOLUTION / "tests")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.repo = self.root / "repo"
        self.dest = self.root / "dest"
        self.source.mkdir()
        (self.source / "café 文档").mkdir()
        (self.source / "café 文档" / "vacío").mkdir()
        (self.source / "vacío raíz").mkdir()
        (self.source / "documento con espacios.txt").write_bytes("¡Hola!\n世界\n".encode())
        (self.source / "café 文档" / "datos.bin").write_bytes(bytes(range(256)) * 17 + b"\x00\xff\r\n")
        (self.source / "empty.bin").write_bytes(b"")

    def run_cli(self, *args, expected=None, fail=False):
        result = subprocess.run([sys.executable, str(BACKUP), *map(str, args)],
                                text=True, capture_output=True, timeout=30)
        if fail:
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertEqual(result.stdout, "")
            self.assertTrue(result.stderr)
        else:
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            self.assertEqual(len(result.stdout.splitlines()), 1)
            obj = json.loads(result.stdout)
            self.assertIsInstance(obj, dict)
            if expected is not None:
                self.assertEqual(obj, expected)
        return result

    def create(self, snapshot_id="v1", max_bytes=None, **kwargs):
        limit = [] if max_bytes is None else ["--max-bytes", max_bytes]
        return self.run_cli("create", "--source", self.source, "--repo", self.repo,
                            "--id", snapshot_id, *limit, **kwargs)

    def verify(self, snapshot_id="v1", **kwargs):
        return self.run_cli("verify", "--repo", self.repo, "--id", snapshot_id, **kwargs)

    def restore(self, snapshot_id="v1", **kwargs):
        return self.run_cli("restore", "--repo", self.repo, "--id", snapshot_id,
                            "--dest", self.dest, **kwargs)

    def test_C01_C02_C03_roundtrip_autonomous_and_source_unchanged(self):
        before = tree_signature(self.source)
        self.create(expected={"id": "v1"})
        self.assertEqual(tree_signature(self.source), before)
        self.verify(expected={"id": "v1", "valid": True})
        shutil.rmtree(self.source)
        self.restore(expected={"id": "v1"})
        self.assertEqual(tree_signature(self.dest), before)
        self.run_cli("list", "--repo", self.repo, expected={"snapshots": ["v1"]})

    def test_C02_empty_source_and_existing_empty_destination(self):
        shutil.rmtree(self.source)
        self.source.mkdir()
        self.dest.mkdir()
        self.create()
        self.restore()
        self.assertEqual(tree_signature(self.dest), ([], {}))

    def test_C02_deep_tree_large_bytes_and_posix_names(self):
        nested = self.source
        for index in range(35):
            nested /= f"nivel {index}"
            nested.mkdir()
        (nested / "último.bin").write_bytes(bytes(range(256)) * 16385)
        (self.source / "back\\slash:名字").write_bytes(b"punctuation")
        signature = tree_signature(self.source)
        self.create()
        self.restore()
        self.assertEqual(tree_signature(self.dest), signature)

    def test_C04_sorted_ids_exact_versions_and_no_overwrite(self):
        first = tree_signature(self.source)
        self.create("zeta")
        published = tree_signature(self.repo)
        (self.source / "documento con espacios.txt").write_bytes(b"changed")
        (self.source / "empty.bin").unlink()
        (self.source / "new.bin").write_bytes(b"new")
        self.create("zeta", fail=True)
        self.assertEqual(tree_signature(self.repo), published)
        second = tree_signature(self.source)
        self.create("Alpha_2-0")
        self.run_cli("list", "--repo", self.repo, expected={"snapshots": ["Alpha_2-0", "zeta"]})
        self.restore("zeta")
        self.assertEqual(tree_signature(self.dest), first)
        shutil.rmtree(self.dest)
        self.restore("Alpha_2-0")
        self.assertEqual(tree_signature(self.dest), second)

    def test_C04_invalid_and_boundary_ids(self):
        for invalid in ("", ".", "..", "../escape", "a/b", "-first", "_first",
                        "á", "a b", "x\n", "a" * 65):
            for operation in ("create", "verify", "restore"):
                with self.subTest(id=repr(invalid), operation=operation):
                    args = [operation, "--repo", self.repo, "--id", invalid]
                    if operation == "create":
                        args += ["--source", self.source]
                    elif operation == "restore":
                        args += ["--dest", self.dest]
                    self.run_cli(*args, fail=True)
        self.assertFalse(self.repo.exists())
        self.create("a")
        self.create("Z" + "x" * 63)

    def test_C04_missing_snapshot(self):
        self.verify("missing", fail=True)
        self.restore("missing", fail=True)
        self.assertFalse(self.dest.exists())
        self.create()
        self.verify("missing", fail=True)
        self.restore("missing", fail=True)

    def test_C05_source_links_and_specials(self):
        link = self.source / "link"
        for target in (self.source / "empty.bin", self.source / "vacío raíz", self.root / "missing"):
            with self.subTest(target=str(target)):
                link.symlink_to(target)
                self.create(fail=True)
                self.assertTrue(link.is_symlink())
                link.unlink()
        fifo = self.source / "fifo"
        os.mkfifo(fifo)
        self.create(fail=True)
        fifo.unlink()
        self.assertFalse(self.repo.exists())

    def test_C05_source_socket(self):
        path = self.source / "socket"
        sock = socket.socket(socket.AF_UNIX)
        try:
            try:
                sock.bind(str(path))
            except PermissionError as error:
                try:
                    os.mknod(path, stat.S_IFSOCK | 0o600)
                except OSError as node_error:
                    self.skipTest(f"container forbids bind ({error}) and socket inode ({node_error})")
            self.assertTrue(stat.S_ISSOCK(path.lstat().st_mode))
            self.create(fail=True)
            self.assertTrue(stat.S_ISSOCK(path.lstat().st_mode))
        finally:
            sock.close()
        self.assertFalse(self.repo.exists())

    def test_C05_symlink_ancestors_and_before_dotdot(self):
        alias = self.root / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        self.run_cli("create", "--source", alias / "source", "--repo", self.repo, "--id", "x", fail=True)
        self.run_cli("create", "--source", self.source, "--repo", alias / "repo", "--id", "x", fail=True)
        self.run_cli("create", "--source", str(alias) + "/../" + self.root.name + "/source",
                     "--repo", self.repo, "--id", "x", fail=True)
        self.create()
        self.run_cli("restore", "--repo", self.repo, "--id", "v1", "--dest", alias / "dest", fail=True)
        self.run_cli("verify", "--repo", alias / "repo", "--id", "v1", fail=True)
        self.assertFalse(self.dest.exists())

    def test_C05_repo_root_link_and_fifo(self):
        actual = self.root / "actual"
        actual.mkdir()
        self.repo.symlink_to(actual, target_is_directory=True)
        self.create(fail=True)
        self.run_cli("list", "--repo", self.repo, fail=True)
        self.repo.unlink()
        os.mkfifo(self.repo)
        self.create(fail=True)
        self.run_cli("list", "--repo", self.repo, fail=True)
        self.assertEqual(list(actual.iterdir()), [])

    def test_C05_repo_staging_and_snapshot_unsafe_entries(self):
        self.create()
        snapshot = self.repo / "snapshots" / "v1"
        for parent in (self.repo, self.repo / ".staging", snapshot / "data"):
            for kind in ("link", "fifo"):
                with self.subTest(parent=str(parent), kind=kind):
                    entry = parent / "unsafe"
                    if kind == "link":
                        entry.symlink_to(self.source / "empty.bin")
                    else:
                        os.mkfifo(entry)
                    self.verify(fail=True)
                    self.restore(fail=True)
                    self.run_cli("list", "--repo", self.repo, fail=True)
                    self.create("other", fail=True)
                    self.assertFalse(self.dest.exists())
                    entry.unlink()
        for target in (snapshot / "manifest.json", snapshot / "data" / "empty.bin"):
            raw = target.read_bytes()
            target.unlink()
            target.symlink_to(self.source / "empty.bin")
            self.verify(fail=True)
            self.restore(fail=True)
            target.unlink()
            target.write_bytes(raw)
        original = self.root / "saved-snapshot"
        snapshot.rename(original)
        snapshot.symlink_to(original, target_is_directory=True)
        self.verify(fail=True)
        self.restore(fail=True)
        self.run_cli("list", "--repo", self.repo, fail=True)

    def test_C05_dest_link_fifo_and_internal_link(self):
        self.create()
        protected = self.root / "protected"
        protected.mkdir()
        (protected / "keep").write_bytes(b"DO NOT CHANGE\x00")
        before = tree_signature(protected)
        self.dest.symlink_to(protected, target_is_directory=True)
        self.restore(fail=True)
        self.assertEqual(tree_signature(protected), before)
        self.dest.unlink()
        self.dest.symlink_to(self.root / "absent")
        self.restore(fail=True)
        self.dest.unlink()
        os.mkfifo(self.dest)
        self.restore(fail=True)
        self.dest.unlink()
        self.dest.mkdir()
        (self.dest / "link").symlink_to(protected)
        self.restore(fail=True)
        self.assertTrue((self.dest / "link").is_symlink())
        self.assertEqual(tree_signature(protected), before)

    def test_C06_source_repo_overlap(self):
        for repo in (self.source, self.source / "nested repo", self.root):
            with self.subTest(repo=str(repo)):
                signature = tree_signature(self.source)
                self.run_cli("create", "--source", self.source, "--repo", repo, "--id", "x", fail=True)
                self.assertEqual(tree_signature(self.source), signature)
        self.assertFalse((self.source / "nested repo").exists())

    def test_C07_nonempty_destination_unchanged(self):
        self.create()
        self.dest.mkdir()
        (self.dest / "keep.bin").write_bytes(bytes(range(256)))
        (self.dest / "empty directory").mkdir()
        before = tree_signature(self.dest)
        self.restore(fail=True)
        self.assertEqual(tree_signature(self.dest), before)
        shutil.rmtree(self.dest)
        self.dest.mkdir()
        (self.dest / "empty only").mkdir()
        self.restore(fail=True)
        self.assertTrue((self.dest / "empty only").is_dir())
        shutil.rmtree(self.dest)
        self.dest.write_bytes(b"regular destination")
        self.restore(fail=True)
        self.assertEqual(self.dest.read_bytes(), b"regular destination")

    def test_C07_destination_repo_overlap(self):
        self.create()
        before = tree_signature(self.repo)
        for dest in (self.repo, self.repo / "new-dest", self.root):
            self.run_cli("restore", "--repo", self.repo, "--id", "v1", "--dest", dest, fail=True)
            self.assertEqual(tree_signature(self.repo), before)

    def test_C08_each_regular_snapshot_file_modified_or_removed(self):
        self.create()
        snapshot = self.repo / "snapshots" / "v1"
        all_files = sorted(path for path in snapshot.rglob("*") if path.is_file())
        for path in all_files:
            original = path.read_bytes()
            for corruption in ("change", "remove"):
                with self.subTest(path=str(path.relative_to(snapshot)), corruption=corruption):
                    if corruption == "change":
                        changed = bytes([original[0] ^ 1]) + original[1:] if original else b"added"
                        path.write_bytes(changed)
                    else:
                        path.unlink()
                    self.verify(fail=True)
                    self.restore(fail=True)
                    self.assertFalse(self.dest.exists())
                    self.dest.mkdir()
                    self.restore(fail=True)
                    self.assertEqual(list(self.dest.iterdir()), [])
                    self.dest.rmdir()
                    self.run_cli("list", "--repo", self.repo, expected={"snapshots": []})
                    self.create(fail=True)
                    path.write_bytes(original)
            self.verify(expected={"id": "v1", "valid": True})

    def test_C08_extra_and_missing_tree_entries(self):
        self.create()
        data = self.repo / "snapshots" / "v1" / "data"
        for kind in ("file", "directory"):
            extra = data / "extra"
            if kind == "file":
                extra.write_bytes(b"extra")
            else:
                extra.mkdir()
            self.verify(fail=True)
            self.restore(fail=True)
            if kind == "file":
                extra.unlink()
            else:
                extra.rmdir()
        (data / "vacío raíz").rmdir()
        self.verify(fail=True)
        self.restore(fail=True)
        (data / "vacío raíz").mkdir()
        self.verify()
        extra = data.parent / "unexpected"
        extra.write_bytes(b"extra metadata")
        self.verify(fail=True)
        self.restore(fail=True)
        self.assertFalse(self.dest.exists())

    def test_C08_manifest_schema_and_path_validation(self):
        self.create()
        snapshot = self.repo / "snapshots" / "v1"
        original = (snapshot / "manifest.json").read_bytes()
        base = json.loads(original)
        invalid = []
        for version in (True, 2, "1"):
            invalid.append(dict(base, version=version))
        invalid += [dict(base, id="other"), dict(base, files={}),
                    dict(base, directories=["../escape"]), dict(base, directories=["/absolute"]),
                    dict(base, directories=["a//b"]), dict(base, directories=["a/./b"]),
                    dict(base, directories=["a/b"]), dict(base, directories=["x", "x"]),
                    dict(base, directories=["empty.bin"])]
        for update in ({"size": -1}, {"size": True}, {"sha256": "bad"},
                       {"path": "../escape"}, {"path": "a\0b"}, {"path": 7}):
            files = [dict(record) for record in base["files"]]
            files[0].update(update)
            invalid.append(dict(base, files=files))
        invalid.append(dict(base, files=base["files"] * 2))
        invalid.append(dict(base, extra="unknown"))
        encoded = [json.dumps(value).encode() for value in invalid]
        encoded += [b'{"version":1,"version":1}', b"{", b"\xff", b"[]"]
        for raw in encoded:
            with self.subTest(raw=raw[:90]):
                (snapshot / "manifest.json").write_bytes(raw)
                (snapshot / "manifest.sha256").write_text(hashlib.sha256(raw).hexdigest() + "\n")
                self.verify(fail=True)
                self.restore(fail=True)
                self.assertFalse(self.dest.exists())
        (snapshot / "manifest.json").write_bytes(original)
        (snapshot / "manifest.sha256").write_text(hashlib.sha256(original).hexdigest() + "\n")
        self.verify()
        self.assertFalse((self.root / "escape").exists())

    def test_C09_SIGKILL_preserves_previous_and_retry_same_id(self):
        self.create("previous")
        previous = tree_signature(self.repo / "snapshots" / "previous")
        with (self.source / "000-large.bin").open("wb") as stream:
            stream.truncate(64 * 1024 * 1024)
        probe = self.root / "capacity-probe"
        self.run_cli("create", "--source", self.source, "--repo", probe, "--id", "interrupted")
        budget = regular_bytes(self.repo) + regular_bytes(probe)
        shutil.rmtree(probe)
        process = subprocess.Popen([sys.executable, str(BACKUP), "create", "--source", str(self.source),
                                    "--repo", str(self.repo), "--id", "interrupted",
                                    "--max-bytes", str(budget)],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 10
            observed = False
            while time.monotonic() < deadline and process.poll() is None:
                stages = list((self.repo / ".staging").glob("interrupted-*"))
                if any((stage / "data" / "000-large.bin").exists() for stage in stages):
                    os.kill(process.pid, signal.SIGKILL)
                    observed = True
                    break
                time.sleep(0.002)
            stdout, stderr = process.communicate(timeout=10)
            self.assertTrue(observed, f"could not observe incomplete create: {stdout!r} {stderr!r}")
            self.assertEqual(process.returncode, -signal.SIGKILL)
            self.assertEqual(stdout, b"")
            self.assertFalse((self.repo / "snapshots" / "interrupted").exists())
            self.assertTrue(list((self.repo / ".staging").iterdir()))
            self.assertEqual(tree_signature(self.repo / "snapshots" / "previous"), previous)
            self.run_cli("list", "--repo", self.repo, expected={"snapshots": ["previous"]})
            self.verify("previous")
            self.create("interrupted", max_bytes=budget, expected={"id": "interrupted"})
            self.assertEqual(regular_bytes(self.repo), budget)
            self.assertEqual(list((self.repo / ".staging").iterdir()), [])
            self.verify("interrupted")
            self.restore("interrupted")
            self.assertEqual(tree_signature(self.dest), tree_signature(self.source))
            self.assertEqual(tree_signature(self.repo / "snapshots" / "previous"), previous)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()

    def test_C10_empty_absent_repo_and_incomplete_snapshots(self):
        self.run_cli("list", "--repo", self.repo, expected={"snapshots": []})
        self.assertFalse(self.repo.exists())
        self.repo.mkdir()
        self.run_cli("list", "--repo", self.repo, expected={"snapshots": []})
        self.create("complete")
        (self.repo / "snapshots" / "incomplete").mkdir()
        abandoned = self.repo / ".staging" / "abandoned"
        abandoned.mkdir()
        (abandoned / "partial").write_bytes(b"partial")
        self.run_cli("list", "--repo", self.repo, expected={"snapshots": ["complete"]})
        self.verify("incomplete", fail=True)
        self.restore("incomplete", fail=True)
        self.create("next")
        self.run_cli("list", "--repo", self.repo, expected={"snapshots": ["complete", "next"]})

    def test_C11_errors_and_wrong_root_types(self):
        self.run_cli(fail=True)
        self.run_cli("create", "--repo", self.repo, fail=True)
        self.run_cli("unknown", fail=True)
        self.run_cli("create", "--source", self.root / "missing", "--repo", self.repo, "--id", "x", fail=True)
        self.run_cli("create", "--source", self.source / "empty.bin", "--repo", self.repo, "--id", "x", fail=True)
        self.repo.write_bytes(b"keep")
        self.create(fail=True)
        self.run_cli("list", "--repo", self.repo, fail=True)
        self.assertEqual(self.repo.read_bytes(), b"keep")
        self.repo.unlink()
        self.repo.mkdir()
        (self.repo / "unknown").write_bytes(b"keep")
        self.create(fail=True)
        self.run_cli("list", "--repo", self.repo, fail=True)
        self.assertEqual((self.repo / "unknown").read_bytes(), b"keep")

    def test_C12_invalid_limits_leave_repo_absent(self):
        before = tree_signature(self.source)
        for value in ("-1", "1.5", "abc", "", "+1", " 1", "1e6", "１２", "NaN"):
            with self.subTest(limit=value):
                self.create(max_bytes=value, fail=True)
                self.assertFalse(self.repo.exists())
                self.assertEqual(tree_signature(self.source), before)
        self.run_cli("create", "--source", self.source, "--repo", self.repo,
                     "--id", "v1", "--max-bytes", fail=True)
        self.assertFalse(self.repo.exists())
        self.create(max_bytes="000100000", expected={"id": "v1"})
        self.verify()

    def test_C13_high_limit_counts_all_metadata_and_roundtrip(self):
        before = tree_signature(self.source)
        source_bytes = regular_bytes(self.source)
        self.create(max_bytes=100000, expected={"id": "v1"})
        used = regular_bytes(self.repo)
        self.assertGreater(used, source_bytes)
        self.assertLessEqual(used, 100000)
        snapshot = self.repo / "snapshots" / "v1"
        self.assertEqual(used, source_bytes + (snapshot / "manifest.json").stat().st_size
                         + (snapshot / "manifest.sha256").stat().st_size)
        self.assertEqual(tree_signature(self.source), before)
        self.verify(expected={"id": "v1", "valid": True})
        shutil.rmtree(self.source)
        self.restore(expected={"id": "v1"})
        self.assertEqual(tree_signature(self.dest), before)

    def test_C13_C14_exact_capacity_and_one_byte_short(self):
        # Discover capacity from an actual independent successful repository.
        self.create()
        capacity = regular_bytes(self.repo)
        shutil.rmtree(self.repo)
        before = tree_signature(self.source)
        for _ in range(3):
            self.create(max_bytes=capacity - 1, fail=True)
            self.assertEqual(regular_bytes(self.repo), 0)
            self.assertEqual(list((self.repo / ".staging").iterdir()), [])
            self.assertFalse((self.repo / "snapshots" / "v1").exists())
            self.run_cli("list", "--repo", self.repo, expected={"snapshots": []})
            self.assertEqual(tree_signature(self.source), before)
        self.create(max_bytes=capacity, expected={"id": "v1"})
        self.assertEqual(regular_bytes(self.repo), capacity)
        self.verify()

    def test_C13_metadata_cannot_be_excluded_for_empty_source(self):
        shutil.rmtree(self.source)
        self.source.mkdir()
        for capacity in (0, 1, 65):
            self.create(max_bytes=capacity, fail=True)
            self.assertEqual(regular_bytes(self.repo), 0)
            self.assertEqual(list((self.repo / ".staging").iterdir()), [])
        self.create(max_bytes=10000)
        used = regular_bytes(self.repo)
        self.assertGreater(used, 65)
        self.assertLessEqual(used, 10000)
        shutil.rmtree(self.repo)
        self.create(max_bytes=used)
        self.assertEqual(regular_bytes(self.repo), used)
        self.restore()
        self.assertEqual(tree_signature(self.dest), ([], {}))

    def test_C13_C14_previous_snapshots_count_and_never_change(self):
        self.create("previous")
        prior = tree_signature(self.repo)
        prior_bytes = regular_bytes(self.repo)
        probe = self.root / "probe"
        self.run_cli("create", "--source", self.source, "--repo", probe, "--id", "next")
        extra = regular_bytes(probe)
        shutil.rmtree(probe)
        for capacity in (0, prior_bytes - 1, prior_bytes, prior_bytes + extra - 1):
            with self.subTest(limit=capacity):
                self.create("next", max_bytes=capacity, fail=True)
                self.assertEqual(tree_signature(self.repo), prior)
                self.assertEqual(regular_bytes(self.repo), prior_bytes)
                self.verify("previous")
                self.run_cli("list", "--repo", self.repo, expected={"snapshots": ["previous"]})
        self.create("next", max_bytes=prior_bytes + extra)
        self.assertEqual(regular_bytes(self.repo), prior_bytes + extra)
        self.verify("next")
        published = tree_signature(self.repo)
        self.create("next", max_bytes=100000, fail=True)
        self.assertEqual(tree_signature(self.repo), published)

    def test_C13_C14_C15_staging_and_incomplete_files_count(self):
        self.create("previous")
        previous = tree_signature(self.repo / "snapshots" / "previous")
        abandoned = self.repo / ".staging" / "abandoned"
        abandoned.mkdir()
        (abandoned / ".hidden-metadata").write_bytes(b"old stage" * 123)
        (self.repo / ".staging" / "loose-file").write_bytes(b"loose stage")
        incomplete = self.repo / "snapshots" / "incomplete"
        incomplete.mkdir()
        (incomplete / "partial").write_bytes(b"partial published tree" * 10)
        usage = regular_bytes(self.repo)
        signature = tree_signature(self.repo)
        self.create("next", max_bytes=usage - 1, fail=True)
        self.assertEqual(tree_signature(self.repo), signature)
        self.create("next", max_bytes=100000)
        self.assertEqual(list((self.repo / ".staging").iterdir()), [])
        self.assertEqual(tree_signature(self.repo / "snapshots" / "previous"), previous)
        self.assertEqual((incomplete / "partial").read_bytes(), b"partial published tree" * 10)
        self.assertLessEqual(regular_bytes(self.repo), 100000)
        self.run_cli("list", "--repo", self.repo, expected={"snapshots": ["next", "previous"]})

    def test_C13_serialized_creates_cannot_exceed_global_budget(self):
        self.create("seed")
        # Equal-length IDs have equal metadata size for the same source tree.
        budget = regular_bytes(self.repo) * 2
        processes = [subprocess.Popen([sys.executable, str(BACKUP), "create", "--source",
                                       str(self.source), "--repo", str(self.repo), "--id", ident,
                                       "--max-bytes", str(budget)],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                     for ident in ("race", "peer")]
        self.addCleanup(lambda: [process.kill() for process in processes if process.poll() is None])
        successes = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=30)
            if process.returncode == 0:
                self.assertEqual(stderr, "")
                self.assertEqual(len(stdout.splitlines()), 1)
                successes.append(json.loads(stdout)["id"])
            else:
                self.assertEqual(stdout, "")
                self.assertTrue(stderr)
        self.assertEqual(len(successes), 1)
        self.assertEqual(regular_bytes(self.repo), budget)
        self.assertEqual(list((self.repo / ".staging").iterdir()), [])
        self.verify("seed")
        self.verify(successes[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
