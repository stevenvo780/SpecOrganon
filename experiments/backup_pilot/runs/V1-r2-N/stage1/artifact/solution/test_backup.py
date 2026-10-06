"""Own functional/failure checks. All temporary data lives under /trial/solution."""

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock


BASE = Path(__file__).absolute().parent
CLI = BASE / "backup.py"
SPEC = importlib.util.spec_from_file_location("backup_under_test", CLI)
BACKUP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BACKUP)


def tree_bytes(root):
    result = {}
    for path in root.rglob("*"):
        name = path.relative_to(root).as_posix()
        result[name] = None if path.is_dir() else path.read_bytes()
    return result


def populate(root):
    root.mkdir()
    (root / "vacío ü" / "otro vacío").mkdir(parents=True)
    (root / "documentos con espacios").mkdir()
    (root / "documentos con espacios" / "café 日本語.txt").write_bytes("Hola, mundo\n🌍\n".encode())
    (root / "bytes.bin").write_bytes(bytes(range(256)) * 23 + b"\0\xff\0")
    (root / "sin bytes").write_bytes(b"")
    (root / "línea\nsiguiente\\nombre").write_bytes(b"\x00\xfe\x10")
    (root / "a" / "b" / "c").mkdir(parents=True)
    (root / "a" / "b" / "c" / "documento").write_bytes(b"deep")


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory(prefix=".tests-", dir=BASE)
        self.root = Path(self.workspace.name)
        self.source = self.root / "source"
        self.repo = self.root / "repo"
        self.dest = self.root / "restored"
        populate(self.source)

    def tearDown(self):
        self.workspace.cleanup()

    def command(self, *args, success=True):
        result = subprocess.run([sys.executable, str(CLI), *map(str, args)], capture_output=True, text=True, timeout=30)
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            self.assertEqual(len(result.stdout.splitlines()), 1)
            payload = json.loads(result.stdout)
            self.assertIsInstance(payload, dict)
            return payload
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.stdout, "")
        self.assertIn("error", json.loads(result.stderr))
        return result

    def create(self, identifier="v1", source=None, repo=None, success=True):
        return self.command("create", "--source", source or self.source, "--repo", repo or self.repo, "--id", identifier, success=success)

    def verify(self, identifier="v1", repo=None, success=True):
        return self.command("verify", "--repo", repo or self.repo, "--id", identifier, success=success)

    def restore(self, identifier="v1", repo=None, dest=None, success=True):
        return self.command("restore", "--repo", repo or self.repo, "--id", identifier, "--dest", dest or self.dest, success=success)

    def listing(self, repo=None, success=True):
        return self.command("list", "--repo", repo or self.repo, success=success)

    def test_exact_roundtrip_and_source_unchanged(self):
        original = tree_bytes(self.source)
        self.assertEqual(self.create(), {"id": "v1"})
        self.assertEqual(self.verify(), {"id": "v1", "valid": True})
        self.assertEqual(self.restore(), {"id": "v1"})
        self.assertEqual(tree_bytes(self.dest), original)
        self.assertEqual(tree_bytes(self.source), original)
        self.assertEqual(self.listing(), {"snapshots": ["v1"]})

    def test_restore_without_original_source(self):
        expected = tree_bytes(self.source)
        self.create()
        shutil.rmtree(self.source)
        self.restore()
        self.assertEqual(tree_bytes(self.dest), expected)

    def test_empty_source_and_empty_existing_destination(self):
        shutil.rmtree(self.source)
        self.source.mkdir()
        self.dest.mkdir()
        self.create()
        self.verify()
        self.restore()
        self.assertEqual(tree_bytes(self.dest), {})

    def test_missing_repository_and_new_empty_repository(self):
        self.assertEqual(self.listing(), {"snapshots": []})
        self.assertFalse(self.repo.exists())
        self.repo.mkdir()
        self.assertEqual(self.listing(), {"snapshots": []})
        self.verify(success=False)
        self.restore(success=False)
        self.assertFalse(self.dest.exists())
        self.assertEqual(tree_bytes(self.repo), {})

    def test_nested_missing_repo_and_destination_parents(self):
        repo = self.root / "new" / "deep" / "repo"
        dest = self.root / "another" / "deep" / "dest"
        self.create(repo=repo)
        self.restore(repo=repo, dest=dest)
        self.assertEqual(tree_bytes(dest), tree_bytes(self.source))

    def test_existing_id_cannot_be_overwritten(self):
        self.create()
        original = tree_bytes(self.repo)
        (self.source / "bytes.bin").write_bytes(b"changed")
        self.create(success=False)
        self.assertEqual(tree_bytes(self.repo), original)
        self.verify()

    def test_unknown_id_rejected_without_mutation(self):
        self.create()
        before = tree_bytes(self.repo)
        self.verify("missing", success=False)
        self.restore("missing", success=False)
        self.assertEqual(tree_bytes(self.repo), before)
        self.assertFalse(self.dest.exists())

    def test_existing_nonempty_destination_preserved(self):
        self.create()
        populate(self.dest)
        original = tree_bytes(self.dest)
        self.restore(success=False)
        self.assertEqual(tree_bytes(self.dest), original)
        # An empty subdirectory also makes the root nonempty.
        shutil.rmtree(self.dest)
        (self.dest / "empty").mkdir(parents=True)
        self.restore(success=False)
        self.assertEqual(tree_bytes(self.dest), {"empty": None})

    def test_invalid_ids_all_operations(self):
        self.create()
        before = tree_bytes(self.repo)
        for identifier in ("", "../escape", ".hidden", "a/b", "a b", "é", "-x", "x\n", "A" * 65):
            with self.subTest(identifier=identifier):
                self.create(identifier, success=False)
                self.verify(identifier, success=False)
                self.restore(identifier, success=False)
        self.assertEqual(tree_bytes(self.repo), before)
        self.assertFalse(self.dest.exists())

    def test_valid_id_boundaries_and_sorted_listing(self):
        identifiers = ["z", "0", "A", "a_b-9", "X" * 64]
        for identifier in identifiers:
            self.create(identifier)
            self.verify(identifier)
        self.assertEqual(self.listing(), {"snapshots": sorted(identifiers)})

    def test_successive_versions_remain_exact(self):
        first = tree_bytes(self.source)
        self.create("first")
        (self.source / "bytes.bin").write_bytes(b"version two\0")
        (self.source / "sin bytes").unlink()
        (self.source / "new").write_bytes(b"new")
        (self.source / "vacío ü" / "otro vacío").rmdir()
        second = tree_bytes(self.source)
        self.create("second")
        for identifier, expected in (("first", first), ("second", second)):
            dest = self.root / identifier
            self.verify(identifier)
            self.restore(identifier, dest=dest)
            self.assertEqual(tree_bytes(dest), expected)

    def test_source_repo_overlap_both_directions(self):
        original = tree_bytes(self.source)
        for repo in (self.source, self.source / "inside", self.root):
            with self.subTest(repo=str(repo)):
                self.create(repo=repo, success=False)
        self.assertEqual(tree_bytes(self.source), original)
        self.assertFalse((self.source / "inside").exists())

    def test_repo_destination_overlap(self):
        self.create()
        original = tree_bytes(self.repo)
        for dest in (self.repo, self.repo / "new", self.root):
            self.restore(dest=dest, success=False)
        self.assertEqual(tree_bytes(self.repo), original)

    def test_source_links_and_link_ancestors_rejected(self):
        for target in (self.source / "bytes.bin", self.source / "a", self.root / "absent"):
            with self.subTest(target=str(target)):
                link = self.source / "link"
                link.symlink_to(target)
                self.create(success=False)
                self.assertFalse(self.repo.exists())
                self.assertTrue(link.is_symlink())
                link.unlink()
        ancestor = self.root / "alias"
        ancestor.symlink_to(self.source, target_is_directory=True)
        self.create(source=ancestor, success=False)
        self.create(source=ancestor / "a", success=False)
        self.create(source=str(ancestor) + "/../source", success=False)

    def test_repo_links_rejected_by_all_operations(self):
        self.create()
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "sentinel").write_bytes(b"preserve")
        for location in (self.repo / "link", self.repo / ".staging" / "link", self.repo / "snapshots" / "v1" / "tree" / "link"):
            location.symlink_to(outside, target_is_directory=True)
            self.create("second", success=False)
            self.verify(success=False)
            self.restore(success=False)
            self.listing(success=False)
            self.assertEqual((outside / "sentinel").read_bytes(), b"preserve")
            location.unlink()
        alias = self.root / "repo-alias"
        alias.symlink_to(self.repo, target_is_directory=True)
        self.listing(repo=alias, success=False)
        self.create("second", repo=alias, success=False)

    def test_destination_links_and_ancestors_rejected(self):
        self.create()
        outside = self.root / "outside"
        outside.mkdir()
        self.dest.symlink_to(outside, target_is_directory=True)
        self.restore(success=False)
        self.restore(dest=self.dest / "child", success=False)
        self.assertEqual(tree_bytes(outside), {})
        self.dest.unlink()
        self.dest.mkdir()
        (self.dest / "dangling").symlink_to(self.root / "absent")
        self.restore(success=False)
        self.assertTrue((self.dest / "dangling").is_symlink())

    def test_special_files_rejected_without_blocking(self):
        fifo = self.source / "fifo"
        os.mkfifo(fifo)
        self.create(success=False)
        fifo.unlink()
        unix_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            unix_socket.bind(str(self.source / "socket"))
            self.create(success=False)
        finally:
            unix_socket.close()
            (self.source / "socket").unlink()
        self.create()
        fifo = self.repo / "snapshots" / "v1" / "tree" / "fifo"
        os.mkfifo(fifo)
        self.verify(success=False)
        self.restore(success=False)
        self.listing(success=False)
        self.create("second", success=False)
        fifo.unlink()
        self.dest.mkdir()
        os.mkfifo(self.dest / "fifo")
        self.restore(success=False)
        self.assertTrue((self.dest / "fifo").exists())

    def test_directory_arguments_reject_regular_and_special_files(self):
        regular = self.root / "regular"
        regular.write_bytes(b"preserve")
        fifo = self.root / "fifo"
        os.mkfifo(fifo)
        for path in (regular, fifo):
            self.create(source=path, success=False)
            self.create(repo=path, success=False)
            self.listing(repo=path, success=False)
        self.create()
        for path in (regular, fifo):
            self.restore(dest=path, success=False)
        self.assertEqual(regular.read_bytes(), b"preserve")

    def test_alteration_and_deletion_of_each_snapshot_regular_file(self):
        self.create()
        snapshot = self.repo / "snapshots" / "v1"
        originals = [path.relative_to(self.repo) for path in snapshot.rglob("*") if path.is_file()]
        for relative in originals:
            for operation in ("alter", "delete"):
                with self.subTest(file=str(relative), operation=operation):
                    damaged = self.root / "damaged"
                    shutil.copytree(self.repo, damaged)
                    path = damaged / relative
                    if operation == "delete":
                        path.unlink()
                    else:
                        content = path.read_bytes()
                        path.write_bytes(bytes([content[0] ^ 1]) + content[1:] if content else b"altered")
                    self.verify(repo=damaged, success=False)
                    self.restore(repo=damaged, success=False)
                    self.assertFalse(self.dest.exists())
                    self.dest.mkdir()
                    self.restore(repo=damaged, success=False)
                    self.assertEqual(tree_bytes(self.dest), {})
                    self.dest.rmdir()
                    self.assertEqual(self.listing(repo=damaged), {"snapshots": []})
                    self.assertEqual(list(self.root.glob(".backup-restore-*")), [])
                    shutil.rmtree(damaged)

    def test_unrecorded_entries_and_missing_empty_directory_detected(self):
        self.create()
        tree = self.repo / "snapshots" / "v1" / "tree"
        for name, kind in (("extra-file", "file"), ("extra-dir", "dir")):
            path = tree / name
            path.write_bytes(b"extra") if kind == "file" else path.mkdir()
            self.verify(success=False)
            self.restore(success=False)
            path.unlink() if kind == "file" else path.rmdir()
        (tree / "vacío ü" / "otro vacío").rmdir()
        self.verify(success=False)
        self.restore(success=False)

    def test_malformed_manifest_even_with_matching_checksum(self):
        self.create()
        snapshot = self.repo / "snapshots" / "v1"
        manifest_file = snapshot / "manifest.json"
        checksum_file = snapshot / "manifest.sha256"
        original_bytes = manifest_file.read_bytes()
        original = json.loads(original_bytes)
        variants = []
        for bad_path in ("../escape", "/absolute", "a//b", "a/../escape", "\0"):
            altered = copy.deepcopy(original)
            altered["files"][0]["path"] = bad_path
            variants.append(json.dumps(altered).encode())
        altered = copy.deepcopy(original)
        altered["files"][0]["size"] = True
        variants.append(json.dumps(altered).encode())
        altered = copy.deepcopy(original)
        altered["files"].append(altered["files"][0])
        variants.append(json.dumps(altered).encode())
        variants.extend([b"[]", b"{}", b"not json", b'{"version":1,"version":1,"directories":[],"files":[]}'])
        for content in variants:
            with self.subTest(content=content[:80]):
                manifest_file.write_bytes(content)
                checksum_file.write_bytes((hashlib.sha256(content).hexdigest() + "\n").encode())
                self.verify(success=False)
                self.restore(success=False)
                self.assertFalse(self.dest.exists())
        self.assertFalse((self.root / "escape").exists())

    def test_staging_and_incomplete_snapshots_never_listed(self):
        self.create("complete")
        unfinished = self.repo / ".staging" / "create-retry-old"
        (unfinished / "tree").mkdir(parents=True)
        (unfinished / "tree" / "partial").write_bytes(b"partial")
        incomplete = self.repo / "snapshots" / "incomplete"
        incomplete.mkdir()
        self.assertEqual(self.listing(), {"snapshots": ["complete"]})
        self.verify("incomplete", success=False)
        self.restore("incomplete", success=False)
        self.create("retry")
        self.verify("retry")
        self.assertTrue((unfinished / "tree" / "partial").exists())

    def test_failed_publication_cleans_own_staging_and_can_retry(self):
        self.create("old")
        before = tree_bytes(self.repo / "snapshots" / "old")
        with mock.patch.object(BACKUP.os, "rename", side_effect=OSError("injected publication failure")):
            with self.assertRaises(OSError):
                BACKUP.create(str(self.source), str(self.repo), "retry")
        self.assertEqual(list((self.repo / ".staging").iterdir()), [])
        self.assertFalse((self.repo / "snapshots" / "retry").exists())
        self.assertEqual(tree_bytes(self.repo / "snapshots" / "old"), before)
        self.create("retry")
        self.verify("old")
        self.verify("retry")

    def test_failed_restore_publication_preserves_empty_dest_and_can_retry(self):
        self.create()
        self.dest.mkdir()
        with mock.patch.object(BACKUP.os, "rename", side_effect=OSError("injected publication failure")):
            with self.assertRaises(OSError):
                BACKUP.restore(str(self.repo), "v1", str(self.dest))
        self.assertEqual(tree_bytes(self.dest), {})
        self.assertEqual(list(self.root.glob(".backup-restore-*")), [])
        self.restore()
        self.assertEqual(tree_bytes(self.dest), tree_bytes(self.source))

    def test_sigkill_create_preserves_old_snapshots_and_same_id_retry(self):
        self.create("old")
        old = tree_bytes(self.repo / "snapshots" / "old")
        large = self.source / "large.bin"
        with large.open("wb") as stream:
            stream.truncate(128 * 1024 * 1024)
        command = [sys.executable, str(CLI), "create", "--source", str(self.source), "--repo", str(self.repo), "--id", "interrupted"]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 10
            while True:
                partials = list((self.repo / ".staging").glob("create-interrupted-*/tree/large.bin"))
                if any(path.stat().st_size > 0 for path in partials):
                    break
                self.assertIsNone(process.poll(), "create completed before interruption")
                self.assertLess(time.monotonic(), deadline, "staging was not observed")
                time.sleep(0.001)
            process.kill()
            stdout, stderr = process.communicate(timeout=10)
            self.assertEqual(process.returncode, -signal.SIGKILL)
            self.assertEqual(stdout, b"")
            self.assertEqual(stderr, b"")
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate()
        self.assertEqual(self.listing(), {"snapshots": ["old"]})
        self.assertEqual(tree_bytes(self.repo / "snapshots" / "old"), old)
        self.verify("old")
        self.create("interrupted")
        self.verify("interrupted")
        self.restore("interrupted")
        self.assertEqual((self.dest / "large.bin").stat().st_size, large.stat().st_size)
        self.assertEqual(BACKUP.digest_file(self.dest / "large.bin"), BACKUP.digest_file(large))
        self.assertEqual(self.listing(), {"snapshots": ["interrupted", "old"]})


def examples():
    with tempfile.TemporaryDirectory(prefix=".examples-", dir=BASE) as workspace:
        root = Path(workspace)
        source, repo, dest = root / "documentos", root / "repo", root / "restaurado"
        populate(source)
        original = tree_bytes(source)
        commands = [
            ["list", "--repo", str(repo)],
            ["create", "--source", str(source), "--repo", str(repo), "--id", "ejemplo_V1"],
            ["verify", "--repo", str(repo), "--id", "ejemplo_V1"],
            ["list", "--repo", str(repo)],
            ["restore", "--repo", str(repo), "--id", "ejemplo_V1", "--dest", str(dest)],
        ]
        for args in commands:
            command = [sys.executable, str(CLI), *args]
            print("$ " + shlex.join(command), flush=True)
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            print(result.stdout, end="")
            if result.stderr:
                print(result.stderr, end="", file=sys.stderr)
            print(f"exit={result.returncode}", flush=True)
            if result.returncode != 0:
                raise RuntimeError("Example failed")
        if tree_bytes(source) != original or tree_bytes(dest) != original:
            raise RuntimeError("Example byte/tree comparison failed")
        print("Comparación exacta de fuente y restauración: OK", flush=True)


if __name__ == "__main__":
    if sys.argv[1:] == ["--examples"]:
        examples()
    else:
        unittest.main()
