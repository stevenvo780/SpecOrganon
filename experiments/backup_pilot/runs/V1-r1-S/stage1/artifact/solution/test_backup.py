"""Contract-derived CLI tests; all temporary fixtures remain inside /trial."""

from __future__ import annotations

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
from unittest import mock

import backup


HERE = Path(__file__).absolute().parent
CLI = HERE / "backup.py"
WORK = HERE / ".test-work"


def tree(root: Path) -> dict:
    result = {}
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        result[relative] = ("dir",) if path.is_dir() else ("file", path.read_bytes())
    return result


class ContractTests(unittest.TestCase):
    def setUp(self):
        WORK.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="case-", dir=WORK)
        self.base = Path(self.temp.name)
        self.source = self.base / "source"
        self.repo = self.base / "repo"
        self.dest = self.base / "restored"
        self.source.mkdir()
        (self.source / "empty").mkdir()
        (self.source / "documentos con espacios").mkdir()
        (self.source / "documentos con espacios" / "niño 日本語.txt").write_text("¡Hola!\n世界\n", encoding="utf-8")
        (self.source / "all bytes.bin").write_bytes(bytes(range(256)) * 17)
        (self.source / "zero").touch()
        (self.source / "empty" / "deep").mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def cli(self, command, *, success=True, repo=None, snapshot_id="v1", source=None, dest=None):
        args = [sys.executable, str(CLI), command, "--repo", str(repo or self.repo)]
        if command != "list":
            args += ["--id", snapshot_id]
        if command == "create":
            args += ["--source", str(source or self.source)]
        if command == "restore":
            args += ["--dest", str(dest or self.dest)]
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            self.assertEqual(len(result.stdout.splitlines()), 1)
            value = json.loads(result.stdout)
            self.assertIsInstance(value, dict)
            return value
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.stdout, "")
        self.assertIn("error", json.loads(result.stderr))
        return result

    def test_C01_C02_C03_exact_round_trip_without_source(self):
        (self.source / "back\\slash").write_bytes(b"POSIX filename")
        before = tree(self.source)
        self.assertEqual(self.cli("create"), {"id": "v1"})
        self.assertEqual(tree(self.source), before)
        self.assertEqual(self.cli("verify"), {"id": "v1", "valid": True})
        shutil.rmtree(self.source)
        self.assertEqual(self.cli("restore"), {"id": "v1"})
        self.assertEqual(tree(self.dest), before)

    def test_C02_empty_source_and_existing_empty_destination(self):
        shutil.rmtree(self.source)
        self.source.mkdir()
        self.dest.mkdir()
        self.cli("create")
        self.cli("restore")
        self.assertEqual(tree(self.dest), {})
        self.cli("verify")

    def test_C02_large_multichunk_file(self):
        (self.source / "large").write_bytes(bytes(range(256)) * 17000)
        before = tree(self.source)
        self.cli("create")
        self.cli("restore", dest=self.base / "new" / "parents" / "dest")
        self.assertEqual(tree(self.base / "new" / "parents" / "dest"), before)

    def test_C04_valid_ids_and_sorted_list(self):
        ids = ["z", "A", "a-b_7", "0", "x" * 64]
        for snapshot_id in ids:
            self.cli("create", snapshot_id=snapshot_id)
        self.assertEqual(self.cli("list"), {"snapshots": sorted(ids)})

    def test_C04_invalid_ids_do_not_create_repo(self):
        for snapshot_id in ("", "../bad", "a/b", "a.b", "_a", "-a", "é", "a\n", "x" * 65):
            for command in ("create", "verify", "restore"):
                with self.subTest(snapshot_id=snapshot_id, command=command):
                    self.cli(command, snapshot_id=snapshot_id, success=False)
                    self.assertFalse(self.repo.exists())
                    self.assertFalse(self.dest.exists())

    def test_C04_missing_ids(self):
        self.repo.mkdir()
        self.cli("verify", success=False)
        self.cli("restore", success=False)
        self.assertFalse(self.dest.exists())

    def test_C04_C07_duplicate_does_not_change_snapshot(self):
        self.cli("create")
        before = tree(self.repo)
        (self.source / "zero").write_bytes(b"changed")
        self.cli("create", success=False)
        self.assertEqual(tree(self.repo), before)
        self.cli("verify")

    def test_C05_source_symlinks(self):
        for target in (self.base / "missing", self.source / "all bytes.bin", self.source / "empty"):
            with self.subTest(target=target):
                link = self.source / "link"
                link.symlink_to(target)
                self.cli("create", success=False)
                self.assertFalse(self.repo.exists())
                link.unlink()
        link = self.base / "source-link"
        link.symlink_to(self.source, target_is_directory=True)
        self.cli("create", source=link, success=False)
        self.cli("create", source=str(link) + "/../source", success=False)

    def test_C05_repo_and_snapshot_symlinks(self):
        self.cli("create")
        snapshot = self.repo / "snapshots" / "v1"
        candidates = [self.repo / "unrelated-link", self.repo / ".staging" / "abandoned-link", snapshot / "data" / "link"]
        for link in candidates:
            link.symlink_to(self.base / "missing")
            for command in ("list", "verify", "restore", "create"):
                self.cli(command, success=False)
            link.unlink()
        datafile = snapshot / "data" / "zero"
        datafile.unlink()
        datafile.symlink_to(self.source / "zero")
        self.cli("verify", success=False)
        self.cli("restore", success=False)
        self.assertFalse(self.dest.exists())

    def test_C05_path_ancestor_and_destination_symlinks(self):
        self.cli("create")
        link = self.base / "repo-link"
        link.symlink_to(self.repo, target_is_directory=True)
        self.cli("list", repo=link, success=False)
        outer = self.base / "outer"
        outer.mkdir()
        link2 = self.base / "outer-link"
        link2.symlink_to(outer, target_is_directory=True)
        self.cli("restore", dest=link2 / "child", success=False)
        self.dest.symlink_to(outer, target_is_directory=True)
        self.cli("restore", success=False)
        self.assertEqual(tree(outer), {})

    def test_C05_special_nodes_source_repo_snapshot_dest(self):
        pipe = self.source / "pipe"
        os.mkfifo(pipe)
        self.cli("create", success=False)
        pipe.unlink()
        self.cli("create")
        for path in (self.repo / "pipe", self.repo / "snapshots" / "v1" / "data" / "pipe"):
            os.mkfifo(path)
            for command in ("verify", "list", "restore", "create"):
                self.cli(command, success=False)
            path.unlink()
        os.mkfifo(self.dest)
        self.cli("restore", success=False)
        self.assertTrue(self.dest.exists())

    def test_C05_socket_source_if_environment_allows_bind(self):
        sock = socket.socket(socket.AF_UNIX)
        try:
            try:
                sock.bind(str(self.source / "socket"))
            except PermissionError as error:
                self.skipTest(f"sandbox prohibits AF_UNIX bind: {error}")
            self.cli("create", success=False)
        finally:
            sock.close()
            (self.source / "socket").unlink(missing_ok=True)

    def test_C05_node_classification_all_special_types(self):
        for mode in (stat.S_IFIFO, stat.S_IFSOCK, stat.S_IFCHR, stat.S_IFBLK, stat.S_IFLNK):
            info = os.stat_result((mode | 0o600, 0, 0, 1, 0, 0, 0, 0, 0, 0))
            with self.subTest(mode=mode):
                with self.assertRaises(backup.BackupError):
                    backup.kind(info, self.source / "special")

    def test_C06_source_repo_overlap(self):
        before = tree(self.source)
        for repo in (self.source, self.source / "inside", self.base):
            self.cli("create", repo=repo, success=False)
        self.assertEqual(tree(self.source), before)
        repo_alias = str(self.source / "empty") + "/../inside"
        self.cli("create", repo=repo_alias, success=False)

    def test_C07_protected_destinations_and_repo_overlap(self):
        self.cli("create")
        self.dest.mkdir()
        (self.dest / "protected.bin").write_bytes(b"\x00DO NOT CHANGE\xff")
        (self.dest / "empty").mkdir()
        before = tree(self.dest)
        self.cli("restore", success=False)
        self.assertEqual(tree(self.dest), before)
        self.cli("restore", dest=self.repo / "new", success=False)
        self.cli("restore", dest=self.base, success=False)
        existing_file = self.base / "protected-file"
        existing_file.write_bytes(b"original")
        self.cli("restore", dest=existing_file, success=False)
        self.assertEqual(existing_file.read_bytes(), b"original")

    def test_C08_C11_staging_and_incomplete_snapshots_hidden(self):
        self.repo.mkdir()
        self.assertEqual(self.cli("list"), {"snapshots": []})
        (self.repo / ".staging" / "v1-abandoned" / "data").mkdir(parents=True)
        (self.repo / ".staging" / "v1-abandoned" / "data" / "partial").write_bytes(b"partial")
        (self.repo / "snapshots" / "incomplete").mkdir(parents=True)
        self.assertEqual(self.cli("list"), {"snapshots": []})
        self.cli("verify", snapshot_id="incomplete", success=False)
        self.cli("restore", snapshot_id="incomplete", success=False)
        self.cli("create")
        self.assertEqual(self.cli("list"), {"snapshots": ["v1"]})

    def test_C08_SIGKILL_repeat_same_id_preserves_previous(self):
        self.cli("create", snapshot_id="previous")
        previous = tree(self.repo / "snapshots" / "previous")
        with (self.source / "large-interrupted").open("wb") as output:
            output.truncate(128 * 1024 * 1024)
        args = [sys.executable, str(CLI), "create", "--source", str(self.source), "--repo", str(self.repo), "--id", "interrupted"]
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        killed = False
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and process.poll() is None:
                for path in (self.repo / ".staging").glob("interrupted-*/data/large-interrupted"):
                    if path.stat().st_size >= 4 * 1024 * 1024:
                        process.send_signal(signal.SIGKILL)
                        killed = True
                        break
                if killed:
                    break
                time.sleep(0.001)
            out, err = process.communicate(timeout=10)
            self.assertTrue(killed, (out, err))
            self.assertEqual(process.returncode, -signal.SIGKILL)
            self.assertEqual(out, b"")
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
        self.assertEqual(self.cli("list"), {"snapshots": ["previous"]})
        self.assertEqual(tree(self.repo / "snapshots" / "previous"), previous)
        self.cli("verify", snapshot_id="previous")
        self.cli("create", snapshot_id="interrupted")
        self.cli("verify", snapshot_id="interrupted")
        self.assertEqual(self.cli("list"), {"snapshots": ["interrupted", "previous"]})
        self.assertEqual(tree(self.repo / "snapshots" / "previous"), previous)
        self.cli("restore", snapshot_id="interrupted")
        self.assertEqual((self.dest / "large-interrupted").stat().st_size, 128 * 1024 * 1024)
        self.assertEqual(hashlib.sha256((self.dest / "large-interrupted").read_bytes()).digest(), hashlib.sha256((self.source / "large-interrupted").read_bytes()).digest())

    def test_C09_every_regular_snapshot_file_mutated_or_deleted(self):
        self.cli("create")
        original = self.repo / "snapshots" / "v1"
        paths = sorted(path.relative_to(original) for path in original.rglob("*") if path.is_file())
        for relative in paths:
            for mode in ("alter", "delete"):
                with self.subTest(path=relative, mode=mode):
                    corrupt = self.base / "corrupt"
                    shutil.copytree(self.repo, corrupt)
                    victim = corrupt / "snapshots" / "v1" / relative
                    if mode == "delete":
                        victim.unlink()
                    else:
                        data = victim.read_bytes()
                        victim.write_bytes(bytes([data[0] ^ 1]) + data[1:] if data else b"x")
                    self.cli("verify", repo=corrupt, success=False)
                    self.cli("restore", repo=corrupt, success=False)
                    self.assertFalse(self.dest.exists())
                    self.dest.mkdir()
                    self.cli("restore", repo=corrupt, success=False)
                    self.assertEqual(tree(self.dest), {})
                    self.dest.rmdir()
                    shutil.rmtree(corrupt)

    def test_C09_extra_missing_directory_and_truncated_file(self):
        self.cli("create")
        data = self.repo / "snapshots" / "v1" / "data"
        extra = data / "extra"
        extra.write_bytes(b"extra")
        self.cli("verify", success=False)
        self.cli("list", success=False)
        extra.unlink()
        (data / "empty" / "deep").rmdir()
        self.cli("verify", success=False)
        (data / "empty" / "deep").mkdir()
        (data / "all bytes.bin").write_bytes(b"short")
        self.cli("verify", success=False)
        self.cli("restore", success=False)
        self.assertFalse(self.dest.exists())

    def test_C08_create_io_failure_cleanup_and_retry(self):
        before = tree(self.source)
        real_copy = backup.file_data
        calls = 0

        def fail_second_file(path, target=None):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected copy failure")
            return real_copy(path, target)

        with mock.patch.object(backup, "file_data", side_effect=fail_second_file):
            with self.assertRaises(OSError):
                backup.create(self.source, self.repo, "v1")
        self.assertEqual(tree(self.source), before)
        self.assertEqual(self.cli("list"), {"snapshots": []})
        self.assertEqual(list((self.repo / ".staging").iterdir()), [])
        self.cli("create")
        self.cli("verify")

    def test_C07_C09_restore_publish_failure_preserves_dest(self):
        self.cli("create")
        for exists in (False, True):
            if exists:
                self.dest.mkdir()
            with mock.patch.object(backup.os, "replace", side_effect=OSError("injected publication failure")):
                with self.assertRaises(OSError):
                    backup.restore(self.repo, "v1", self.dest)
            self.assertEqual(self.dest.exists(), exists)
            if exists:
                self.assertEqual(tree(self.dest), {})
            self.assertEqual(list(self.base.glob(".backup-restore-*")), [])

    def test_C09_C10_manifest_validation_even_with_recomputed_hash(self):
        self.cli("create")
        snapshot = self.repo / "snapshots" / "v1"
        manifest = snapshot / "manifest.json"
        original = json.loads(manifest.read_bytes())
        mutations = [
            lambda m: m.update(version=True),
            lambda m: m.update(id="other"),
            lambda m: m["entries"][0].update(path="../outside"),
            lambda m: m["entries"][0].update(path="/absolute"),
            lambda m: m["entries"][0].update(path="a/../b"),
            lambda m: m["entries"][0].update(size=True),
            lambda m: m["entries"][0].update(sha256="x" * 64),
            lambda m: m["entries"].append(dict(m["entries"][0])),
            lambda m: m["entries"].reverse(),
            lambda m: m.update(extra="unexpected"),
        ]
        for mutate in mutations:
            document = json.loads(json.dumps(original))
            mutate(document)
            raw = (json.dumps(document, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")
            manifest.write_bytes(raw)
            (snapshot / "COMMIT").write_text(hashlib.sha256(raw).hexdigest() + "\n", encoding="ascii")
            self.cli("verify", success=False)
            self.cli("restore", success=False)
            self.assertFalse(self.dest.exists())
        self.assertFalse((self.base / "outside").exists())

    def test_C10_argument_and_wrong_path_errors(self):
        for args in ([], ["unknown"], ["create"], ["list", "--repo", str(self.repo), "--extra"], ["verify", "--repo", str(self.repo)]):
            result = subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
        wrong = self.base / "not-directory"
        wrong.write_bytes(b"keep")
        self.cli("create", source=wrong, success=False)
        self.cli("create", repo=wrong, success=False)
        self.cli("list", repo=wrong, success=False)
        self.assertEqual(wrong.read_bytes(), b"keep")

    def test_C11_nonexistent_repo_list_does_not_create_it(self):
        self.assertEqual(self.cli("list"), {"snapshots": []})
        self.assertFalse(self.repo.exists())

    def test_base_successive_versions_remain_independent(self):
        first = tree(self.source)
        self.cli("create", snapshot_id="first")
        (self.source / "zero").write_bytes(b"modified")
        (self.source / "all bytes.bin").unlink()
        (self.source / "added").write_bytes(b"added")
        second = tree(self.source)
        self.cli("create", snapshot_id="second")
        self.cli("restore", snapshot_id="first")
        self.assertEqual(tree(self.dest), first)
        shutil.rmtree(self.dest)
        self.cli("restore", snapshot_id="second")
        self.assertEqual(tree(self.dest), second)


if __name__ == "__main__":
    unittest.main(verbosity=2)
