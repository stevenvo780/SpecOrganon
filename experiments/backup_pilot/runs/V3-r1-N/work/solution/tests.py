#!/usr/bin/env python3
"""Contract checks through the public CLI; all fixtures stay under /trial."""

import copy
import hashlib
import json
import os
from pathlib import Path
import shlex
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import time
import unittest

import backup


HERE = Path(__file__).resolve().parent
PROGRAM = HERE / "backup.py"
LOG = HERE / "commands-results-v3.log"


def record(command, result):
    with LOG.open("a", encoding="utf-8") as output:
        output.write(f"$ {shlex.join(map(str, command))}\n")
        output.write(f"exit={result.returncode}\n")
        output.write(f"stdout={result.stdout.strip()}\n")
        output.write(f"stderr={result.stderr.strip()}\n\n")


def tree(root):
    result = {}
    for path in root.rglob("*"):
        name = path.relative_to(root).as_posix()
        result[name] = None if path.is_dir() else path.read_bytes()
    return result


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="check-", dir=HERE)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.repo = self.root / "repo"
        self.dest = self.root / "dest"
        self.source.mkdir()

    def cli(self, command, *, identifier="first", source=None, repo=None, dest=None,
            max_bytes=None, ok=True):
        arguments = [sys.executable, str(PROGRAM), command, "--repo", str(repo or self.repo)]
        if command != "list":
            arguments += ["--id", identifier]
        if command == "create":
            arguments += ["--source", str(source or self.source)]
            if max_bytes is not None:
                arguments += ["--max-bytes", str(max_bytes)]
        if command == "restore":
            arguments += ["--dest", str(dest or self.dest)]
        result = subprocess.run(arguments, capture_output=True, text=True, timeout=30)
        record(arguments, result)
        if not ok:
            self.assertNotEqual(result.returncode, 0, result)
            self.assertEqual(result.stdout, "", result)
            self.assertIn("error", json.loads(result.stderr))
            return result
        self.assertEqual(result.returncode, 0, result)
        self.assertEqual(result.stderr, "", result)
        parsed = json.loads(result.stdout)
        self.assertIsInstance(parsed, dict)
        if command == "verify":
            self.assertEqual(parsed, {"id": identifier, "valid": True})
        elif command != "list":
            self.assertEqual(parsed, {"id": identifier})
        return parsed

    def snapshot(self, identifier="first"):
        return self.repo / "snapshots" / f"{identifier}.snap"

    def seed(self):
        (self.source / "empty nested" / "vacío").mkdir(parents=True)
        (self.source / "datos ñ 日本語.bin").write_bytes(bytes(range(256)) * 41)
        (self.source / "empty file").touch()
        (self.source / "empty nested" / "text\nfile").write_bytes(b"hello\x00\xff\n")
        (self.source / "literal\\backslash").write_bytes(b"backslash")

    def used_bytes(self):
        return sum(path.stat().st_size for path in self.repo.rglob("*") if path.is_file())

    def test_limit_exact_boundary_and_no_residual_growth(self):
        self.seed()
        probe = self.root / "probe"
        self.cli("create", repo=probe)
        required = (probe / "snapshots" / "first.snap").stat().st_size
        payload = sum(path.stat().st_size for path in self.source.rglob("*") if path.is_file())
        self.assertGreater(required, payload)  # Metadata and both checksum levels count.
        for limit in (0, payload, required - 1):
            for _ in range(2):
                self.cli("create", max_bytes=limit, ok=False)
                self.assertEqual(self.used_bytes(), 0)
                self.assertEqual(self.cli("list"), {"snapshots": []})
                self.assertEqual(list(self.repo.glob(".pending-*")), [])
        self.cli("create", max_bytes=required)
        self.assertEqual(self.used_bytes(), required)
        self.cli("verify")
        self.cli("restore")
        self.assertEqual(tree(self.dest), tree(self.source))

    def test_limit_counts_every_regular_file_and_preserves_previous_snapshots(self):
        self.seed()
        self.cli("create", max_bytes=10**7)
        snapshot_bytes = self.used_bytes()
        (self.repo / "other" / "nested").mkdir(parents=True)
        (self.repo / "other" / "nested" / "metadata.json").write_bytes(b"metadata" * 101)
        (self.repo / "foreign").write_bytes(b"foreign" * 73)
        before = tree(self.repo)
        used = self.used_bytes()
        self.assertGreater(used, snapshot_bytes)
        for limit in (used - 1, used, used + snapshot_bytes - 1):
            self.cli("create", identifier="second", max_bytes=limit, ok=False)
            self.assertEqual(tree(self.repo), before)
            self.assertEqual(self.used_bytes(), used)
            self.cli("verify")
        self.cli("create", identifier="second", max_bytes=used + snapshot_bytes)
        self.assertEqual(self.used_bytes(), used + snapshot_bytes)
        self.assertEqual(self.cli("list"), {"snapshots": ["first", "second"]})
        # Corrupt snapshots are still regular bytes and cannot be excluded.
        self.snapshot("second").write_bytes(b"corrupt bytes" * 100)
        used = self.used_bytes()
        self.cli("create", identifier="third", max_bytes=used - 1, ok=False)
        self.assertEqual(self.used_bytes(), used)
        self.cli("verify")

    def test_empty_source_still_requires_persistent_metadata_bytes(self):
        self.cli("create", max_bytes=0, ok=False)
        self.assertEqual(self.used_bytes(), 0)
        self.cli("create", max_bytes=10000)
        used = self.used_bytes()
        self.assertGreater(used, backup.FOOTER_SIZE + len(backup.MAGIC))
        self.cli("create", identifier="empty-two", max_bytes=2 * used - 1, ok=False)
        self.assertEqual(self.used_bytes(), used)
        self.cli("create", identifier="empty-two", max_bytes=2 * used)
        self.assertEqual(self.used_bytes(), 2 * used)

    def test_invalid_limits_leave_paths_unchanged(self):
        for value in ("-1", "1.5", "nan", "", "+10", " 10", "10x"):
            self.cli("create", max_bytes=value, ok=False)
            self.assertFalse(self.repo.exists())
        self.cli("create", max_bytes="00010000")

    def test_stale_pending_reclaimed_before_budget_check(self):
        self.seed()
        self.cli("create")
        used = self.used_bytes()
        (self.repo / ".pending-interrupted").write_bytes(b"abandoned" * 10000)
        self.cli("create", identifier="second", max_bytes=2 * used)
        self.assertEqual(self.used_bytes(), 2 * used)
        self.assertEqual(list(self.repo.glob(".pending-*")), [])
        self.cli("verify")
        self.cli("verify", identifier="second")
        # Model SIGKILL after publication but before unlinking the staging name.
        os.link(self.snapshot(), self.repo / ".pending-published")
        self.cli("create", max_bytes=2 * used, ok=False)
        self.assertEqual(self.used_bytes(), 2 * used)
        self.assertEqual(list(self.repo.glob(".pending-*")), [])
        self.cli("verify")

    def test_concurrent_creates_share_one_total_budget(self):
        self.seed()
        probe = self.root / "probe"
        self.cli("create", repo=probe)
        required = (probe / "snapshots" / "first.snap").stat().st_size
        processes = []
        for identifier in ("one", "two"):
            command = [sys.executable, str(PROGRAM), "create", "--source", str(self.source),
                       "--repo", str(self.repo), "--id", identifier, "--max-bytes", str(required)]
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.addCleanup(lambda p=process: p.kill() if p.poll() is None else None)
            processes.append((command, process, identifier))
        winners = []
        for command, process, identifier in processes:
            stdout, stderr = process.communicate(timeout=30)
            record(command, subprocess.CompletedProcess(command, process.returncode, stdout, stderr))
            if process.returncode == 0:
                self.assertEqual(json.loads(stdout), {"id": identifier})
                self.assertEqual(stderr, "")
                winners.append(identifier)
            else:
                self.assertEqual(stdout, "")
                self.assertIn("error", json.loads(stderr))
        self.assertEqual(len(winners), 1)
        self.assertEqual(self.used_bytes(), required)
        self.assertEqual(self.cli("list"), {"snapshots": winners})
        self.assertEqual(list(self.repo.glob(".pending-*")), [])
        self.cli("verify", identifier=winners[0])

    def test_roundtrip_self_contained_and_source_unchanged(self):
        self.seed()
        expected = tree(self.source)
        self.cli("create")
        self.assertEqual(tree(self.source), expected)
        self.cli("verify")
        self.assertEqual(self.cli("list"), {"snapshots": ["first"]})
        import shutil
        shutil.rmtree(self.source)
        self.cli("restore")
        self.assertEqual(tree(self.dest), expected)

    def test_successive_versions_and_sorted_list(self):
        expected = {}
        (self.source / "keep").write_bytes(b"v1")
        (self.source / "delete").write_bytes(b"gone")
        for identifier in ("z", "A", "a"):
            if identifier == "A":
                (self.source / "keep").write_bytes(b"v2")
                (self.source / "delete").unlink()
                (self.source / "new").write_bytes(b"new")
            if identifier == "a":
                (self.source / "keep").write_bytes(b"v3")
                (self.source / "empty").mkdir()
            expected[identifier] = tree(self.source)
            self.cli("create", identifier=identifier)
        self.assertEqual(self.cli("list"), {"snapshots": ["A", "a", "z"]})
        for identifier, contents in expected.items():
            self.cli("verify", identifier=identifier)
            dest = self.root / identifier
            self.cli("restore", identifier=identifier, dest=dest)
            self.assertEqual(tree(dest), contents)

    def test_empty_source_and_new_repository(self):
        self.assertEqual(self.cli("list"), {"snapshots": []})
        self.assertFalse(self.repo.exists())
        self.repo.mkdir()
        self.assertEqual(self.cli("list"), {"snapshots": []})
        self.cli("create")
        self.cli("verify")
        self.cli("restore")
        self.assertEqual(tree(self.dest), {})

    def test_empty_existing_and_nested_destination(self):
        self.seed()
        self.cli("create")
        self.dest.mkdir()
        self.cli("restore")
        self.assertEqual(tree(self.dest), tree(self.source))
        nested = self.root / "absent" / "parents" / "dest"
        self.cli("restore", dest=nested)
        self.assertEqual(tree(nested), tree(self.source))

    def test_nonempty_destination_and_existing_id_unchanged(self):
        self.seed()
        self.cli("create")
        original = self.snapshot().read_bytes()
        (self.source / "new").write_bytes(b"changed")
        source_before = tree(self.source)
        self.cli("create", ok=False)
        self.assertEqual(self.snapshot().read_bytes(), original)
        self.assertEqual(tree(self.source), source_before)
        self.dest.mkdir()
        (self.dest / "protected").write_bytes(b"do not modify\x00\xff")
        before = tree(self.dest)
        self.cli("restore", ok=False)
        self.assertEqual(tree(self.dest), before)
        (self.dest / "protected").unlink()
        (self.dest / "empty directory").mkdir()
        self.cli("restore", ok=False)
        self.assertEqual(tree(self.dest), {"empty directory": None})

    def test_invalid_ids_and_missing_ids(self):
        for identifier in ("", ".", "../escape", "a/b", "-x", "_x", "é", "a\n", "x" * 65):
            for command in ("create", "verify", "restore"):
                with self.subTest(identifier=identifier, command=command):
                    self.cli(command, identifier=identifier, ok=False)
        self.assertFalse(self.repo.exists())
        self.cli("verify", ok=False)
        self.cli("restore", ok=False)
        self.assertFalse(self.dest.exists())
        self.cli("create", identifier="Z" + "_" * 62 + "9")

    def test_source_repository_overlap(self):
        (self.source / "protected").write_bytes(b"source")
        before = tree(self.source)
        self.cli("create", repo=self.source, ok=False)
        self.cli("create", repo=self.source / "child", ok=False)
        self.cli("create", repo=self.root, ok=False)
        self.assertEqual(tree(self.source), before)
        # Similar textual prefixes are distinct paths.
        self.cli("create", repo=self.root / "source-more")

    def test_concurrent_same_id_cannot_overwrite(self):
        other_source = self.root / "other-source"
        other_source.mkdir()
        (self.source / "file").write_bytes(b"A" * (2 * backup.CHUNK + 17))
        (other_source / "file").write_bytes(b"B" * (2 * backup.CHUNK + 17))
        (self.repo / "snapshots").mkdir(parents=True)
        processes = []
        for source in (self.source, other_source):
            command = [sys.executable, str(PROGRAM), "create", "--source", str(source),
                       "--repo", str(self.repo), "--id", "first"]
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.addCleanup(lambda p=process: p.kill() if p.poll() is None else None)
            processes.append((command, process, source))
        results = []
        for command, process, source in processes:
            stdout, stderr = process.communicate(timeout=30)
            record(command, subprocess.CompletedProcess(command, process.returncode, stdout, stderr))
            results.append((process.returncode, source))
            if process.returncode == 0:
                self.assertEqual(json.loads(stdout), {"id": "first"})
                self.assertEqual(stderr, "")
            else:
                self.assertEqual(stdout, "")
                self.assertIn("error", json.loads(stderr))
        self.assertEqual(sorted(code for code, _ in results), [0, 1])
        winner = next(source for code, source in results if code == 0)
        self.cli("verify")
        self.cli("restore")
        self.assertEqual(tree(self.dest), tree(winner))

    def test_relative_paths_and_many_nested_entries(self):
        # Paths are relative to the CLI's inherited cwd (/trial).
        nested = self.source
        for depth in range(60):
            nested /= f"dir-{depth}"
            nested.mkdir()
            (nested / "file").write_bytes(bytes([depth]))
        self.cli("create", source=self.source.relative_to(Path.cwd()),
                 repo=self.repo.relative_to(Path.cwd()))
        self.cli("restore", dest=self.dest.relative_to(Path.cwd()))
        self.assertEqual(tree(self.source), tree(self.dest))

    def test_source_symlinks_are_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        target = outside / "protected"
        target.write_bytes(b"unchanged")
        for target_path in (target, outside, outside / "missing"):
            with self.subTest(target=target_path):
                link = self.source / "link"
                link.symlink_to(target_path)
                self.cli("create", ok=False)
                self.assertEqual(target.read_bytes(), b"unchanged")
                self.assertFalse(self.snapshot().exists())
                link.unlink()
        root_link = self.root / "root-link"
        root_link.symlink_to(self.source, target_is_directory=True)
        self.cli("create", source=root_link, ok=False)
        self.cli("create", source=root_link / ".." / "source", ok=False)

    def test_repo_symlinks_are_rejected_including_ancestors_and_remnants(self):
        self.cli("create")
        repo_link = self.root / "repo-link"
        repo_link.symlink_to(self.repo, target_is_directory=True)
        self.cli("list", repo=repo_link, ok=False)
        self.cli("verify", repo=repo_link / ".." / "repo", ok=False)
        for name in (".pending-broken", "other", "snapshots/unused.snap"):
            link = self.repo / name
            link.symlink_to(self.root / "nonexistent")
            for command in ("create", "verify", "restore", "list"):
                self.cli(command, identifier="new" if command == "create" else "first", ok=False)
            link.unlink()
        original = self.snapshot().read_bytes()
        self.snapshot().unlink()
        target = self.root / "outside-snapshot"
        target.write_bytes(original)
        self.snapshot().symlink_to(target)
        self.cli("verify", ok=False)
        self.cli("restore", ok=False)
        self.assertEqual(target.read_bytes(), original)

    def test_destination_symlinks_and_regular_file_rejected(self):
        self.seed()
        self.cli("create")
        protected = self.root / "protected"
        protected.mkdir()
        (protected / "file").write_bytes(b"protected")
        self.dest.symlink_to(protected, target_is_directory=True)
        self.cli("restore", ok=False)
        self.cli("restore", dest=self.dest / "nested", ok=False)
        self.cli("restore", dest=self.dest / ".." / "other", ok=False)
        self.assertEqual(tree(protected), {"file": b"protected"})
        self.dest.unlink()
        self.dest.mkdir()
        (self.dest / "broken").symlink_to(self.root / "missing")
        self.cli("restore", ok=False)
        self.assertTrue((self.dest / "broken").is_symlink())
        self.cli("restore", dest=protected / "file", ok=False)
        self.assertEqual((protected / "file").read_bytes(), b"protected")

    def test_special_files_are_rejected(self):
        fifo = self.source / "fifo"
        os.mkfifo(fifo)
        self.cli("create", ok=False)
        self.cli("create", source=fifo, ok=False)
        fifo.unlink()
        sock = socket.socket(socket.AF_UNIX)
        self.addCleanup(sock.close)
        sock_path = self.source / "socket"
        try:
            sock.bind(str(sock_path))
        except PermissionError as error:
            with LOG.open("a", encoding="utf-8") as output:
                output.write(f"Socket fixture unavailable in sandbox: {error}\n\n")
        else:
            self.cli("create", ok=False)
            sock_path.unlink()
        self.cli("create")
        os.mkfifo(self.repo / "fifo")
        for command in ("create", "verify", "restore", "list"):
            self.cli(command, ok=False)
        (self.repo / "fifo").unlink()
        os.mkfifo(self.dest)
        self.cli("restore", ok=False)

    def test_corruption_rejected_without_publishing_restores(self):
        self.seed()
        self.cli("create")
        self.cli("create", identifier="good")
        original = self.snapshot().read_bytes()
        manifest_start = len(original) - backup.FOOTER_SIZE - struct.unpack(">Q", original[-40:-32])[0]
        mutations = {}
        for label, offset in (("header", 0), ("data", len(backup.MAGIC)),
                              ("manifest", manifest_start + 3), ("length", len(original) - 40),
                              ("checksum", len(original) - 1)):
            altered = bytearray(original)
            altered[offset] ^= 1
            mutations[label] = bytes(altered)
        mutations.update(truncate=original[:-1], empty=b"", append=original + b"x",
                         remove_payload=original[:len(backup.MAGIC)] + original[len(backup.MAGIC) + 1:])
        self.dest.mkdir()
        identity = self.dest.stat().st_ino
        for label, data in mutations.items():
            with self.subTest(corruption=label):
                self.snapshot().write_bytes(data)
                self.cli("verify", ok=False)
                self.cli("restore", ok=False)
                self.assertEqual(tree(self.dest), {})
                self.assertEqual(self.dest.stat().st_ino, identity)
                missing_dest = self.root / "not-published"
                self.cli("restore", dest=missing_dest, ok=False)
                self.assertFalse(missing_dest.exists())
                self.assertEqual(self.cli("list"), {"snapshots": ["good"]})
                self.cli("verify", identifier="good")
        self.snapshot().unlink()
        self.cli("verify", ok=False)
        self.cli("restore", ok=False)

    def test_malformed_metadata_even_with_recomputed_outer_digest(self):
        self.seed()
        self.cli("create")
        original = self.snapshot().read_bytes()
        manifest_size = struct.unpack(">Q", original[-40:-32])[0]
        start = len(original) - 40 - manifest_size
        manifest = json.loads(original[start:-40])
        file_index = next(i for i, entry in enumerate(manifest["entries"]) if entry["type"] == "file")
        cases = []
        for path in ("../escaped", "/absolute", "a//b", "a/./b", "a/../b", "bad\x00name", "missing/child"):
            changed = copy.deepcopy(manifest)
            changed["entries"][file_index]["path"] = path
            cases.append(changed)
        for key, value in (("size", -1), ("size", True), ("offset", True), ("sha256", "0" * 64)):
            changed = copy.deepcopy(manifest)
            changed["entries"][file_index][key] = value
            cases.append(changed)
        changed = copy.deepcopy(manifest)
        changed["entries"].append(changed["entries"][0])
        cases.append(changed)
        cases.append({"version": True, "entries": []})
        cases.append({"version": 1, "entries": [{"path": "x", "type": "symlink"}]})
        for case in cases:
            raw = json.dumps(case).encode()
            data = original[:start] + raw + struct.pack(">Q", len(raw))
            self.snapshot().write_bytes(data + hashlib.sha256(data).digest())
            self.cli("verify", ok=False)
            self.cli("restore", ok=False)
            self.assertFalse(self.dest.exists())
            self.assertFalse((self.root / "escaped").exists())
        raw = b'{"version":1,"version":1,"entries":[]}'
        data = backup.MAGIC + raw + struct.pack(">Q", len(raw))
        self.snapshot().write_bytes(data + hashlib.sha256(data).digest())
        self.cli("verify", ok=False)

    def test_sigkill_create_and_retry_same_id(self):
        (self.source / "small").write_bytes(b"original version")
        self.cli("create", identifier="previous")
        previous = self.snapshot("previous").read_bytes()
        large = self.source / "large"
        with large.open("wb") as output:
            output.write(b"start")
            output.seek(128 * 1024 * 1024 - 3)
            output.write(b"end")
        with large.open("rb") as input_file:
            source_digest = hashlib.file_digest(input_file, "sha256").hexdigest()
        for attempt in range(2):
            old_remnants = set(self.repo.glob(".pending-*"))
            command = [sys.executable, str(PROGRAM), "create", "--source", str(self.source),
                       "--repo", str(self.repo), "--id", "interrupted",
                       "--max-bytes", str(512 * 1024 * 1024)]
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.addCleanup(lambda p=process: p.kill() if p.poll() is None else None)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                remnants = set(self.repo.glob(".pending-*")) - old_remnants
                if any(path.stat().st_size >= 65536 for path in remnants):
                    process.send_signal(signal.SIGKILL)
                    break
                if process.poll() is not None:
                    self.fail("create terminó antes de poder interrumpirlo")
                time.sleep(0.001)
            else:
                self.fail("No apareció el archivo temporal de create")
            stdout, stderr = process.communicate(timeout=10)
            record(command, subprocess.CompletedProcess(command, process.returncode, stdout, stderr))
            self.assertEqual(process.returncode, -signal.SIGKILL)
            self.assertFalse(self.snapshot("interrupted").exists())
            self.assertEqual(self.snapshot("previous").read_bytes(), previous)
            self.assertEqual(self.cli("list"), {"snapshots": ["previous"]})
            self.cli("verify", identifier="previous")
            self.cli("verify", identifier="interrupted", ok=False)
        self.cli("create", identifier="interrupted", max_bytes=len(previous) - 1, ok=False)
        self.assertEqual(self.used_bytes(), len(previous))
        self.assertEqual(list(self.repo.glob(".pending-*")), [])
        self.cli("verify", identifier="previous")
        self.cli("create", identifier="interrupted", max_bytes=512 * 1024 * 1024)
        self.assertLessEqual(self.used_bytes(), 512 * 1024 * 1024)
        self.assertEqual(list(self.repo.glob(".pending-*")), [])
        self.cli("verify", identifier="interrupted")
        self.cli("restore", identifier="interrupted")
        with (self.dest / "large").open("rb") as input_file:
            self.assertEqual(hashlib.file_digest(input_file, "sha256").hexdigest(), source_digest)
        with large.open("rb") as input_file:
            self.assertEqual(hashlib.file_digest(input_file, "sha256").hexdigest(), source_digest)
        self.assertEqual((self.dest / "small").read_bytes(), b"original version")
        self.assertEqual(self.snapshot("previous").read_bytes(), previous)
        self.assertEqual(self.cli("list"), {"snapshots": ["interrupted", "previous"]})


if __name__ == "__main__":
    LOG.write_text(f"$ python3 solution/tests.py\nPython: {sys.version}\n\n", encoding="utf-8")
    unittest.main(verbosity=2)
