"""CLI integration checks derived from SPEC.md; all fixtures are private."""

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

    def create(self, snapshot_id="v1", **kwargs):
        return self.run_cli("create", "--source", self.source, "--repo", self.repo,
                            "--id", snapshot_id, **kwargs)

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
        sock = socket.socket(socket.AF_UNIX)
        try:
            sock.bind(str(self.source / "socket"))
            self.create(fail=True)
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
        process = subprocess.Popen([sys.executable, str(BACKUP), "create", "--source", str(self.source),
                                    "--repo", str(self.repo), "--id", "interrupted"],
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
            self.create("interrupted", expected={"id": "interrupted"})
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
