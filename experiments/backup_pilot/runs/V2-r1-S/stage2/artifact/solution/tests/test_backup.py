"""Acceptance tests; all generated files stay under /trial/solution/tests/.work."""

from __future__ import annotations

import hashlib
import importlib.util
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


HERE = Path(__file__).resolve().parent
PROGRAM = HERE.parent / "backup.py"
WORK = HERE / ".work"
WORK.mkdir(exist_ok=True)
spec = importlib.util.spec_from_file_location("backup", PROGRAM)
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


def tree_bytes(root: Path) -> dict:
    """Independent oracle, retaining directories, file bytes and link targets."""
    result = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            result[relative] = ("link", os.readlink(path))
        elif path.is_dir():
            result[relative] = ("dir",)
        elif path.is_file():
            result[relative] = ("file", path.read_bytes())
        else:
            result[relative] = ("special", path.lstat().st_mode)
    return result


def regular_bytes(root: Path) -> int:
    """Independent st_size oracle; no production counting helper is used."""
    return sum(info.st_size for path in root.rglob("*")
               if stat.S_ISREG((info := path.lstat()).st_mode))


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="case-", dir=WORK)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.repo = self.root / "repo"
        self.dest = self.root / "restored"
        self.source.mkdir()

    def run_cli(self, command, *, success=True, **options):
        arguments = [sys.executable, str(PROGRAM), command]
        for key, value in options.items():
            arguments.extend(["--" + key.replace("_", "-"), str(value)])
        completed = subprocess.run(arguments, capture_output=True, text=True, timeout=30)
        if success:
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stderr, "")
            result = json.loads(completed.stdout)
            self.assertIsInstance(result, dict)
            self.assertEqual(len(completed.stdout.splitlines()), 1)
            return result
        self.assertNotEqual(completed.returncode, 0, completed.stdout)
        self.assertEqual(completed.stdout, "")
        self.assertIn("error", json.loads(completed.stderr))
        return completed

    def create(self, snapshot_id="v1", **options):
        return self.run_cli("create", source=options.pop("source", self.source),
                            repo=options.pop("repo", self.repo), id=snapshot_id, **options)

    def verify(self, snapshot_id="v1", **options):
        return self.run_cli("verify", repo=self.repo, id=snapshot_id, **options)

    def restore(self, snapshot_id="v1", **options):
        return self.run_cli("restore", repo=self.repo, id=snapshot_id, dest=options.pop("dest", self.dest), **options)

    def test_cli_and_empty_repository(self):
        self.assertEqual(self.run_cli("list", repo=self.repo), {"snapshots": []})
        self.assertFalse(self.repo.exists())
        self.repo.mkdir()
        self.assertEqual(self.run_cli("list", repo=self.repo), {"snapshots": []})
        self.assertEqual(self.create(), {"id": "v1"})
        self.assertEqual(self.verify(), {"id": "v1", "valid": True})
        self.assertEqual(self.restore(), {"id": "v1"})
        self.run_cli("create", repo=self.repo, success=False)
        completed = subprocess.run([sys.executable, str(PROGRAM), "unknown"], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stdout, "")
        self.assertIn("error", json.loads(completed.stderr))

    def test_successive_versions(self):
        (self.source / "carpeta ñ 空").mkdir()
        (self.source / "vacío").mkdir()
        (self.source / "carpeta ñ 空" / "bits con espacios.bin").write_bytes(bytes(range(256)) * 37 + b"\0\xff\r\n")
        (self.source / "change.txt").write_bytes(b"first version")
        (self.source / "deleted.txt").write_bytes(b"only in v1")
        (self.source / "empty file").touch()
        (self.source / "quote' newline\nback\\slash").write_bytes(b"unusual filename")
        expected = {}
        for snapshot_id in ("v1", "v2", "v3"):
            if snapshot_id == "v2":
                (self.source / "change.txt").write_bytes(b"second version\0")
                (self.source / "deleted.txt").unlink()
                (self.source / "added.txt").write_bytes(b"added")
                (self.source / "vacío").rmdir()
            elif snapshot_id == "v3":
                (self.source / "change.txt").unlink()
                (self.source / "added.txt").unlink()
                (self.source / "added.txt").mkdir()
                (self.source / "added.txt" / "nested").write_bytes(b"file became directory")
                (self.source / "new empty").mkdir()
            expected[snapshot_id] = tree_bytes(self.source)
            self.create(snapshot_id)
            self.assertEqual(tree_bytes(self.source), expected[snapshot_id])
        shutil.rmtree(self.source)
        for snapshot_id in ("v3", "v1", "v2"):
            self.assertEqual(self.verify(snapshot_id), {"id": snapshot_id, "valid": True})
            dest = self.root / ("restore-" + snapshot_id)
            self.restore(snapshot_id, dest=dest)
            self.assertEqual(tree_bytes(dest), expected[snapshot_id])
        self.assertEqual(self.run_cli("list", repo=self.repo), {"snapshots": ["v1", "v2", "v3"]})

    def test_empty_source(self):
        self.create()
        self.restore()
        self.assertEqual(tree_bytes(self.dest), {})

    def test_max_bytes_argument(self):
        for value in ("", "-1", "+1", "1.0", "1e6", "NaN", "1_000", "１", " 1"):
            with self.subTest(value=value):
                result = self.create(max_bytes=value, success=False)
                self.assertEqual(result.returncode, 2)
                self.assertFalse(self.repo.exists())
        result = subprocess.run([sys.executable, str(PROGRAM), "create", "--source",
                                 str(self.source), "--repo", str(self.repo), "--id", "v1",
                                 "--max-bytes"], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("error", json.loads(result.stderr))
        self.assertFalse(self.repo.exists())
        # Zero is valid syntax, but even an empty snapshot needs metadata.
        result = self.create(max_bytes=0, success=False)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(regular_bytes(self.repo), 0)
        self.assertEqual(self.run_cli("list", repo=self.repo), {"snapshots": []})

    def test_max_bytes_exact_fit(self):
        (self.source / "dir 空").mkdir()
        (self.source / "dir 空" / "binary").write_bytes(bytes(range(256)) * 3)
        (self.source / "empty").mkdir()
        (self.source / "zero").touch()
        before = tree_bytes(self.source)
        control = self.root / "control"
        self.create("exact", repo=control)
        required = regular_bytes(control)
        self.assertGreater(required, 768)
        self.create("exact", max_bytes=required - 1, success=False)
        self.assertEqual(regular_bytes(self.repo), 0)
        self.assertEqual(list((self.repo / ".staging").iterdir()), [])
        self.verify("exact", success=False)
        self.assertEqual(self.create("exact", max_bytes="000" + str(required)), {"id": "exact"})
        self.assertEqual(regular_bytes(self.repo), required)
        self.assertEqual(tree_bytes(self.source), before)
        shutil.rmtree(self.source)
        self.verify("exact")
        self.restore("exact")
        self.assertEqual(tree_bytes(self.dest), before)

    def test_max_bytes_counts_metadata_and_lock(self):
        (self.source / "file").write_bytes(b"x")
        self.create()
        lock_bytes = b"persistent lock bytes"
        (self.repo / ".lock").write_bytes(lock_bytes)
        baseline = regular_bytes(self.repo)
        before = tree_bytes(self.repo)
        control = self.root / "control"
        self.create("v2", repo=control)
        addition = regular_bytes(control)
        # Enough for the payload alone is insufficient for its metadata.
        self.create("v2", max_bytes=baseline + 1, success=False)
        self.assertEqual(tree_bytes(self.repo), before)
        # Assuming a zero-byte lock would also produce an incorrect admission.
        self.create("v2", max_bytes=baseline + addition - len(lock_bytes), success=False)
        self.assertEqual(tree_bytes(self.repo), before)
        self.create("v2", max_bytes=baseline + addition)
        self.assertEqual(regular_bytes(self.repo), baseline + addition)
        self.assertEqual((self.repo / ".lock").read_bytes(), lock_bytes)
        self.verify("v1")
        self.verify("v2")

    def test_max_bytes_rejection_and_retry(self):
        (self.source / "file").write_bytes(b"old\0\xff")
        self.create("previous", max_bytes=100_000)
        before = tree_bytes(self.repo)
        used = regular_bytes(self.repo)
        (self.source / "file").write_bytes(b"changed")
        (self.source / "added").write_bytes(b"addition")
        source_before = tree_bytes(self.source)
        for limit in (used - 1, 0, used, used + 15, used - 1):
            with self.subTest(limit=limit):
                self.create("retry", max_bytes=limit, success=False)
                self.assertEqual(regular_bytes(self.repo), used)
                self.assertEqual(tree_bytes(self.repo), before)
                self.assertEqual(tree_bytes(self.source), source_before)
                self.verify("previous")
                self.verify("retry", success=False)
                self.assertEqual(self.run_cli("list", repo=self.repo), {"snapshots": ["previous"]})
        self.restore("previous")
        self.assertEqual((self.dest / "file").read_bytes(), b"old\0\xff")
        self.create("retry", max_bytes=100_000)
        self.assertLessEqual(regular_bytes(self.repo), 100_000)
        self.restore("retry", dest=self.root / "new-restored")
        self.assertEqual(tree_bytes(self.root / "new-restored"), source_before)

    def test_max_bytes_successive_versions(self):
        (self.source / "changed").write_bytes(b"first")
        (self.source / "deleted").write_bytes(b"old only")
        (self.source / "empty directory").mkdir()
        expected = {}
        for index in range(3):
            if index == 1:
                (self.source / "changed").write_bytes(b"second\0\xff")
                (self.source / "deleted").unlink()
                (self.source / "added ñ").write_bytes(bytes(range(256)))
            elif index == 2:
                (self.source / "changed").unlink()
                (self.source / "empty directory").rmdir()
                (self.source / "new empty").mkdir()
            snapshot_id = "version" + str(index)
            if self.repo.exists():
                before = tree_bytes(self.repo)
                self.create(snapshot_id, max_bytes=regular_bytes(self.repo) - 1, success=False)
                self.assertEqual(tree_bytes(self.repo), before)
            expected[snapshot_id] = tree_bytes(self.source)
            self.create(snapshot_id, max_bytes=1_000_000)
            self.assertLessEqual(regular_bytes(self.repo), 1_000_000)
            self.assertEqual(tree_bytes(self.source), expected[snapshot_id])
        shutil.rmtree(self.source)
        for snapshot_id, content in expected.items():
            self.verify(snapshot_id)
            dest = self.root / snapshot_id
            self.restore(snapshot_id, dest=dest)
            self.assertEqual(tree_bytes(dest), content)
        self.assertEqual(self.run_cli("list", repo=self.repo), {"snapshots": sorted(expected)})

    def test_max_bytes_orphan_cleanup(self):
        (self.source / "file").write_bytes(b"safe")
        self.create("previous")
        previous = tree_bytes(self.repo / "snapshots")
        used = regular_bytes(self.repo)
        orphan = self.repo / ".staging" / "create-abandoned"
        orphan.mkdir()
        (orphan / "partial").write_bytes(b"z" * 1024 * 1024)
        self.create("retry", max_bytes=used - 1, success=False)
        self.assertFalse(orphan.exists())
        self.assertEqual(regular_bytes(self.repo), used)
        self.assertEqual(tree_bytes(self.repo / "snapshots"), previous)
        orphan.mkdir()
        (orphan / "partial").write_bytes(b"z" * 1024 * 1024)
        self.create("retry", max_bytes=100_000)
        self.assertFalse(orphan.exists())
        self.assertLessEqual(regular_bytes(self.repo), 100_000)
        self.verify("previous")
        self.verify("retry")

    def test_concurrent_max_bytes(self):
        (self.source / "file").write_bytes(bytes(range(256)) * 1024)
        control = self.root / "control"
        self.create("one", repo=control)
        limit = regular_bytes(control)
        self.repo.mkdir()
        processes = []
        try:
            for snapshot_id in ("one", "two"):
                args = [sys.executable, str(PROGRAM), "create", "--source", str(self.source),
                        "--repo", str(self.repo), "--id", snapshot_id, "--max-bytes", str(limit)]
                processes.append(subprocess.Popen(args, stdout=subprocess.PIPE,
                                                  stderr=subprocess.PIPE, text=True))
            results = [(process, *process.communicate(timeout=30)) for process in processes]
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.communicate()
        successes = []
        for process, stdout, stderr in results:
            if process.returncode == 0:
                successes.append(json.loads(stdout)["id"])
                self.assertEqual(stderr, "")
            else:
                self.assertEqual(stdout, "")
                self.assertIn("error", json.loads(stderr))
        self.assertEqual(len(successes), 1)
        self.assertEqual(regular_bytes(self.repo), limit)
        self.assertEqual(list((self.repo / ".staging").iterdir()), [])
        self.assertEqual(self.run_cli("list", repo=self.repo), {"snapshots": successes})
        self.verify(successes[0])
        self.restore(successes[0])
        self.assertEqual(tree_bytes(self.dest), tree_bytes(self.source))

    def test_empty_existing_destination(self):
        (self.source / "file").write_bytes(b"contents")
        self.create()
        self.dest.mkdir()
        self.restore()
        self.assertEqual(tree_bytes(self.dest), tree_bytes(self.source))

    def test_invalid_ids_and_missing_snapshots(self):
        invalid = ["", ".", "..", "../escape", "a/b", "/absolute", "_first", "-first", "has space", "ñ", "a\n", "x" * 65]
        for value in invalid:
            for command in ("create", "verify", "restore"):
                with self.subTest(id=value, command=command):
                    options = {"repo": self.repo, "id": value}
                    if command == "create":
                        options["source"] = self.source
                    if command == "restore":
                        options["dest"] = self.dest
                    self.run_cli(command, success=False, **options)
        self.assertFalse(self.repo.exists())
        self.verify("missing", success=False)
        self.restore("missing", success=False)
        self.assertFalse(self.dest.exists())
        for value in ("A", "0", "a_-B", "x" * 64):
            self.create(value)
        self.verify("missing", success=False)
        self.restore("missing", success=False)

    def test_existing_id_is_preserved(self):
        (self.source / "file").write_bytes(b"original")
        self.create()
        before = tree_bytes(self.repo)
        (self.source / "file").write_bytes(b"new")
        self.create(success=False)
        self.assertEqual(tree_bytes(self.repo), before)
        self.restore()
        self.assertEqual((self.dest / "file").read_bytes(), b"original")

    def test_source_repository_overlap(self):
        (self.source / "protected").write_bytes(b"unchanged")
        before = tree_bytes(self.source)
        for repo in (self.source, self.source / "nested", self.root):
            with self.subTest(repo=repo):
                self.create(repo=repo, success=False)
                self.assertEqual(tree_bytes(self.source), before)
        self.assertFalse((self.source / "nested").exists())

    def test_protected_destination(self):
        (self.source / "data").write_bytes(b"snapshot")
        self.create()
        self.dest.mkdir()
        (self.dest / "keep").write_bytes(b"protected\0\xff")
        (self.dest / "empty directory").mkdir()
        before = tree_bytes(self.dest)
        self.restore(success=False)
        self.assertEqual(tree_bytes(self.dest), before)
        nested_dest = self.repo / "snapshots" / "v1" / "data" / "empty"
        self.restore(dest=nested_dest, success=False)
        self.assertFalse(nested_dest.exists())
        file_dest = self.root / "file-destination"
        file_dest.write_bytes(b"keep bytes")
        self.restore(dest=file_dest, success=False)
        self.assertEqual(file_dest.read_bytes(), b"keep bytes")

    def test_symlinks_are_rejected(self):
        target = self.root / "target"
        target.write_bytes(b"secret test bytes")
        linked = self.source / "link"
        linked.symlink_to(target)
        self.create(success=False)
        self.assertFalse(self.repo.exists())
        linked.unlink()
        directory_link = self.source / "directory-link"
        directory_link.symlink_to(self.root, target_is_directory=True)
        self.create(success=False)
        directory_link.unlink()
        linked.symlink_to(self.root / "nonexistent")
        self.create(success=False)
        linked.unlink()
        self.create()
        repo_link = self.root / "repo-link"
        repo_link.symlink_to(self.repo, target_is_directory=True)
        self.run_cli("list", repo=repo_link, success=False)
        self.run_cli("create", source=self.source, repo=repo_link, id="other", success=False)
        self.dest.symlink_to(self.source, target_is_directory=True)
        source_before = tree_bytes(self.source)
        self.restore(success=False)
        self.assertEqual(tree_bytes(self.source), source_before)
        self.dest.unlink()
        snapshot_link = self.repo / "snapshots" / "v1" / "data" / "link"
        snapshot_link.symlink_to(target)
        self.verify(success=False)
        self.restore(success=False)
        self.run_cli("list", repo=self.repo, success=False)
        snapshot_link.unlink()
        repo_nested_link = self.repo / ".staging" / "create-orphan"
        repo_nested_link.mkdir()
        (repo_nested_link / "link").symlink_to(target)
        self.create("v2", success=False)
        self.assertEqual(target.read_bytes(), b"secret test bytes")
        self.assertFalse(self.dest.exists())

    def test_symlink_parent_and_dotdot(self):
        alias = self.root / "alias"
        alias.symlink_to(self.source, target_is_directory=True)
        raw = str(alias) + "/../source"
        self.create(source=raw, success=False)
        self.run_cli("list", repo=str(alias) + "/../repo", success=False)
        self.create()
        self.restore(dest=alias / "new", success=False)
        self.assertFalse((self.source / "new").exists())
        # Ordinary relative paths and '..' with actual directories work.
        relative_source = os.path.relpath(self.source, Path.cwd())
        self.create("relative", source=relative_source)
        self.restore("relative", dest=str(self.root / "source") + "/../nested/out")
        self.assertEqual(tree_bytes(self.root / "nested" / "out"), {})

    def test_special_files_are_rejected(self):
        fifo = self.source / "fifo"
        os.mkfifo(fifo)
        self.create(success=False)
        fifo.unlink()
        self.create()
        os.mkfifo(self.repo / "snapshots" / "v1" / "data" / "fifo")
        self.verify(success=False)
        self.restore(success=False)
        self.run_cli("list", repo=self.repo, success=False)
        (self.repo / "snapshots" / "v1" / "data" / "fifo").unlink()
        self.dest.mkdir()
        os.mkfifo(self.dest / "fifo")
        self.restore(success=False)
        self.assertTrue((self.dest / "fifo").exists())

    def test_socket_files_are_rejected(self):
        with socket.socket(socket.AF_UNIX) as sock:
            try:
                sock.bind(str(self.source / "socket"))
            except PermissionError:
                self.skipTest("El sandbox prohíbe crear sockets Unix (bind: EPERM)")
            self.create(success=False)
            self.assertFalse(self.repo.exists())

    def test_corruption_of_every_snapshot_file(self):
        (self.source / "nested").mkdir()
        (self.source / "nested" / "binary").write_bytes(bytes(range(256)))
        (self.source / "empty").touch()
        self.create()
        snapshot = self.repo / "snapshots" / "v1"
        files = sorted(path for path in snapshot.rglob("*") if path.is_file())
        for path in files:
            original = path.read_bytes()
            for mutation in ("flip", "truncate", "delete", "append"):
                with self.subTest(path=path.relative_to(snapshot), mutation=mutation):
                    if mutation == "flip":
                        path.write_bytes(bytes([original[0] ^ 1]) + original[1:] if original else b"x")
                    elif mutation == "truncate":
                        if original:
                            path.write_bytes(original[:-1])
                        else:
                            path.unlink()
                    elif mutation == "delete":
                        path.unlink()
                    else:
                        path.write_bytes(original + b" ")
                    self.verify(success=False)
                    self.restore(success=False)
                    self.assertFalse(self.dest.exists())
                    self.assertEqual(self.run_cli("list", repo=self.repo), {"snapshots": []})
                    path.write_bytes(original)
        self.verify()
        self.restore()
        self.assertEqual(tree_bytes(self.dest), tree_bytes(self.source))

    def test_extra_and_missing_entries(self):
        (self.source / "empty-dir").mkdir()
        (self.source / "file").write_bytes(b"a")
        self.create()
        snapshot = self.repo / "snapshots" / "v1"
        for path in (snapshot / "extra", snapshot / "data" / "extra"):
            with self.subTest(path=path):
                path.write_bytes(b"unexpected")
                self.verify(success=False)
                self.restore(success=False)
                path.unlink()
        empty = snapshot / "data" / "empty-dir"
        empty.rmdir()
        self.verify(success=False)
        self.restore(success=False)
        empty.mkdir()
        self.verify()
        self.assertFalse(self.dest.exists())

    def test_invalid_manifests(self):
        (self.source / "file").write_bytes(b"safe")
        self.create()
        snapshot = self.repo / "snapshots" / "v1"
        manifest_path = snapshot / "manifest.json"
        digest_path = snapshot / "manifest.sha256"
        original = manifest_path.read_bytes()
        variants = []
        for path in ("../escaped", "/absolute", "a/../../escaped", "a//b", ".", "a\0b", "absent/child"):
            altered = json.loads(original)
            altered["entries"][0]["path"] = path
            variants.append(altered)
        duplicate = json.loads(original)
        duplicate["entries"].append(duplicate["entries"][0].copy())
        variants.append(duplicate)
        for key, value in (("size", True), ("size", -1), ("sha256", "no hash"), ("type", "link"), ("path", 7)):
            altered = json.loads(original)
            altered["entries"][0][key] = value
            variants.append(altered)
        variants.extend([[], {"format": True, "id": "v1", "entries": []}, {"format": 1, "id": "other", "entries": []}])
        for index, altered in enumerate(variants):
            with self.subTest(variant=index):
                raw = backup.canonical_json(altered)
                manifest_path.write_bytes(raw)
                digest_path.write_bytes((hashlib.sha256(raw).hexdigest() + "\n").encode("ascii"))
                self.verify(success=False)
                self.restore(success=False)
                self.assertFalse(self.dest.exists())
                self.assertFalse((self.root / "escaped").exists())
        # Even with a matching checksum, duplicate JSON keys / noncanonical JSON fail.
        for raw in (original.replace(b'"format":1', b'"format":1,"format":1'), original + b" ", b"{bad json\n", b'{"format":NaN,"id":"v1","entries":[]}\n'):
            manifest_path.write_bytes(raw)
            digest_path.write_bytes((hashlib.sha256(raw).hexdigest() + "\n").encode("ascii"))
            self.verify(success=False)
            self.restore(success=False)
        manifest_path.write_bytes(original)
        digest_path.write_bytes((hashlib.sha256(original).hexdigest() + "\n").encode("ascii"))
        self.verify()

    def test_unpublished_staging_is_not_listed(self):
        self.create("z-old")
        stage = self.repo / ".staging" / "create-abandoned"
        stage.mkdir()
        (stage / "partial").write_bytes(b"incomplete")
        self.assertEqual(self.run_cli("list", repo=self.repo), {"snapshots": ["z-old"]})
        incomplete = self.repo / "snapshots" / "incomplete"
        incomplete.mkdir()
        self.assertEqual(self.run_cli("list", repo=self.repo), {"snapshots": ["z-old"]})
        self.verify("incomplete", success=False)
        self.create("incomplete", success=False)
        incomplete.rmdir()
        self.create("a-new")
        self.assertFalse(stage.exists())
        self.assertEqual(self.run_cli("list", repo=self.repo), {"snapshots": ["a-new", "z-old"]})

    def test_sigkill_and_retry(self):
        (self.source / "file").write_bytes(b"previous snapshot")
        self.create("previous")
        previous = tree_bytes(self.repo / "snapshots" / "previous")
        large = self.source / "large"
        with large.open("wb") as stream:
            stream.truncate(128 * 1024 * 1024)
        limit = 512 * 1024 * 1024
        args = [sys.executable, str(PROGRAM), "create", "--source", str(self.source), "--repo", str(self.repo), "--id", "interrupted", "--max-bytes", str(limit)]
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 10
            reached = False
            while time.monotonic() < deadline and process.poll() is None:
                candidates = list((self.repo / ".staging").glob("create-*/data/large"))
                if candidates and candidates[0].stat().st_size > 0:
                    reached = True
                    process.send_signal(signal.SIGKILL)
                    break
                time.sleep(0.001)
            stdout, stderr = process.communicate(timeout=10)
            self.assertTrue(reached, f"create finished before interception: {stdout} {stderr}")
            self.assertEqual(process.returncode, -signal.SIGKILL)
            self.assertEqual(stdout, "")
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
        self.assertEqual(tree_bytes(self.repo / "snapshots" / "previous"), previous)
        self.assertFalse((self.repo / "snapshots" / "interrupted").exists())
        self.assertEqual(self.run_cli("list", repo=self.repo), {"snapshots": ["previous"]})
        self.verify("previous")
        self.create("interrupted", max_bytes=limit)
        self.assertLessEqual(regular_bytes(self.repo), limit)
        self.verify("interrupted")
        self.restore("interrupted")
        self.assertEqual((self.dest / "large").stat().st_size, large.stat().st_size)
        self.assertEqual(hashlib.sha256((self.dest / "large").read_bytes()).hexdigest(), hashlib.sha256(large.read_bytes()).hexdigest())
        self.assertEqual((self.dest / "file").read_bytes(), b"previous snapshot")
        self.assertEqual(list((self.repo / ".staging").iterdir()), [])

    def test_copy_failure_is_not_published(self):
        (self.source / "file").write_bytes(b"a")
        self.create("previous")
        before = tree_bytes(self.repo / "snapshots")
        with mock.patch.object(backup, "copy_file", side_effect=OSError("injected write failure")):
            with self.assertRaises(OSError):
                backup.create_snapshot(str(self.source), str(self.repo), "retry")
        self.assertEqual(tree_bytes(self.repo / "snapshots"), before)
        self.assertEqual(list((self.repo / ".staging").iterdir()), [])
        self.create("retry")
        self.verify("retry")

    def test_restore_copy_failure_is_not_published(self):
        (self.source / "file").write_bytes(b"a")
        self.create()
        with mock.patch.object(backup, "copy_file", side_effect=OSError("injected restore failure")):
            with self.assertRaises(OSError):
                backup.restore_snapshot(str(self.repo), "v1", str(self.dest))
        self.assertFalse(self.dest.exists())
        self.assertEqual(list(self.root.glob(".backup-restore-*")), [])
        self.dest.mkdir()
        original_copy = backup.copy_file

        def corrupt_then_copy(source, target, expected=None):
            source.write_bytes(b"changed after initial verification")
            return original_copy(source, target, expected)

        with mock.patch.object(backup, "copy_file", side_effect=corrupt_then_copy):
            with self.assertRaises(backup.BackupError):
                backup.restore_snapshot(str(self.repo), "v1", str(self.dest))
        self.assertEqual(tree_bytes(self.dest), {})
        self.assertEqual(list(self.root.glob(".backup-restore-*")), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
