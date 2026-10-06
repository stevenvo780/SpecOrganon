"""Pruebas propias de C01–C11; no requieren dependencias ni datos externos."""

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


SOLUTION = Path(__file__).resolve().parents[1]
CLI = SOLUTION / "backup.py"
WORK = SOLUTION / "tests" / "work"


def tree(path: Path) -> dict:
    """Inventario independiente del formato y de las funciones del producto."""
    if not path.exists():
        return {}
    result = {}
    for item in sorted(path.rglob("*")):
        mode = item.lstat().st_mode
        relative = item.relative_to(path).as_posix()
        if stat.S_ISREG(mode):
            result[relative] = ("file", item.read_bytes())
        elif stat.S_ISDIR(mode):
            result[relative] = ("dir",)
        elif stat.S_ISLNK(mode):
            result[relative] = ("link", os.readlink(item))
        else:
            result[relative] = ("special", stat.S_IFMT(mode))
    return result


def repo_bytes(path: Path) -> int:
    return sum(item.lstat().st_size for item in path.rglob("*")
               if stat.S_ISREG(item.lstat().st_mode))


class BackupTests(unittest.TestCase):
    def setUp(self):
        WORK.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="case-", dir=WORK)
        self.root = Path(self.temp.name)
        self.source = self.root / "fuente con espacios"
        self.repo = self.root / "repo"
        self.source.mkdir()
        (self.source / "vacío").mkdir()
        (self.source / "árbol").mkdir()
        (self.source / "árbol" / "espacio ñ.bin").write_bytes(bytes(range(256)) * 7)
        (self.source / "empty").write_bytes(b"")
        (self.source / ".oculto").write_bytes(b"\x00\xff\ntexto")
        self.addCleanup(self.temp.cleanup)

    def cli(self, *args, ok=True, expected=None):
        result = subprocess.run([sys.executable, str(CLI), *map(str, args)],
                                capture_output=True, text=True, timeout=30)
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            value = json.loads(result.stdout)
            self.assertIsInstance(value, dict)
            self.assertEqual(len(result.stdout.splitlines()), 1)
            if expected is not None:
                self.assertEqual(value, expected)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertEqual(result.stdout, "")
            self.assertIn("error", json.loads(result.stderr))
        return result

    def create(self, identifier="v1", repo=None, source=None, limit=None, ok=True):
        args = ["create", "--source", source or self.source, "--repo", repo or self.repo,
                "--id", identifier]
        if limit is not None:
            args += ["--max-bytes", str(limit)]
        return self.cli(*args, ok=ok, expected={"id": identifier} if ok else None)

    def verify(self, identifier="v1", repo=None, ok=True):
        return self.cli("verify", "--repo", repo or self.repo, "--id", identifier,
                        ok=ok, expected={"id": identifier, "valid": True} if ok else None)

    def restore(self, dest, identifier="v1", repo=None, ok=True):
        return self.cli("restore", "--repo", repo or self.repo, "--id", identifier,
                        "--dest", dest, ok=ok,
                        expected={"id": identifier} if ok else None)

    def test_01_cli_empty_repo_and_errors(self):
        self.cli("list", "--repo", self.repo, expected={"snapshots": []})
        self.repo.mkdir()
        self.cli("list", "--repo", self.repo, expected={"snapshots": []})
        for args in [[], ["create"], ["unknown"], ["list", "--repo", self.repo, "--oops"],
                     ["list", "--repo", self.repo, "--max-bytes", "100"]]:
            with self.subTest(args=args):
                self.cli(*args, ok=False)
        self.verify("absent", ok=False)
        self.restore(self.root / "dest", "absent", ok=False)
        self.assertFalse((self.root / "dest").exists())

    def test_02_exact_bytes_and_source_unchanged(self):
        before = tree(self.source)
        self.create()
        self.verify()
        self.restore(self.root / "dest")
        self.assertEqual(tree(self.root / "dest"), before)
        self.assertEqual(tree(self.source), before)

    def test_03_versions_and_source_independence(self):
        first = tree(self.source)
        self.create("z_version")
        (self.source / ".oculto").unlink()
        (self.source / "empty").write_bytes(b"version two")
        (self.source / "nuevo").write_bytes(b"added")
        second = tree(self.source)
        self.create("A_version")
        shutil.rmtree(self.source)
        self.cli("list", "--repo", self.repo,
                 expected={"snapshots": ["A_version", "z_version"]})
        for identifier, wanted in [("z_version", first), ("A_version", second)]:
            self.verify(identifier)
            dest = self.root / identifier
            self.restore(dest, identifier)
            self.assertEqual(tree(dest), wanted)

    def test_04_ids_and_no_overwrite(self):
        for identifier in ["", "../x", ".hidden", "ñ", "a/b", "a.b", "x" * 65, "a\n"]:
            with self.subTest(identifier=identifier):
                self.create(identifier, ok=False)
                self.verify(identifier, ok=False)
        for identifier in ["a", "Z0_-", "x" * 64]:
            self.create(identifier)
        before = tree(self.repo)
        (self.source / "empty").write_bytes(b"changed")
        self.create("a", ok=False)
        self.assertEqual(tree(self.repo), before)
        self.verify("a")

    def test_05_source_symlinks_and_specials(self):
        before = tree(self.source)
        outside = self.root / "sentinel"
        outside.write_bytes(b"protected")
        for target in [outside, self.source / "vacío", self.root / "absent"]:
            with self.subTest(target=target):
                link = self.source / "link"
                link.symlink_to(target)
                self.create(ok=False)
                self.assertFalse(self.repo.exists())
                link.unlink()
        fifo = self.source / "fifo"
        os.mkfifo(fifo)
        self.create(ok=False)
        fifo.unlink()
        self.assertEqual(tree(self.source), before)
        self.assertEqual(outside.read_bytes(), b"protected")

    def test_06_route_components_and_repo_symlinks(self):
        alias = self.root / "alias"
        alias.symlink_to(self.source, target_is_directory=True)
        self.create(source=alias, ok=False)
        self.create(source=str(alias) + "/../" + self.source.name, ok=False)
        actual_repo = self.root / "actual_repo"
        actual_repo.mkdir()
        repo_link = self.root / "repo_link"
        repo_link.symlink_to(actual_repo, target_is_directory=True)
        self.create(repo=repo_link, ok=False)
        self.create(repo=repo_link / "nested", ok=False)
        self.cli("list", "--repo", repo_link, ok=False)
        self.assertEqual(tree(actual_repo), {})

    def test_07_overlaps_rejected_before_mutation(self):
        before = tree(self.source)
        for repo in [self.source, self.source / "new_repo", self.root]:
            with self.subTest(repo=repo):
                self.create(repo=repo, ok=False)
                self.assertEqual(tree(self.source), before)
        self.assertFalse((self.source / "new_repo").exists())

    def test_08_protected_and_empty_destinations(self):
        self.create()
        protected = self.root / "protected"
        protected.mkdir()
        (protected / "sentinel").write_bytes(b"do not replace")
        before = tree(protected)
        self.restore(protected, ok=False)
        self.assertEqual(tree(protected), before)
        empty = self.root / "empty_dest"
        empty.mkdir()
        self.restore(empty)
        self.assertEqual(tree(empty), tree(self.source))
        self.restore(self.repo / "new", ok=False)
        self.verify()
        self.assertFalse((self.repo / "new").exists())

    def test_09_destination_symlinks_and_specials(self):
        self.create()
        protected = self.root / "protected"
        protected.mkdir()
        (protected / "sentinel").write_bytes(b"safe")
        before = tree(protected)
        alias = self.root / "alias"
        alias.symlink_to(protected, target_is_directory=True)
        self.restore(alias, ok=False)
        self.restore(alias / "new", ok=False)
        self.assertEqual(tree(protected), before)
        fifo = self.root / "fifo"
        os.mkfifo(fifo)
        self.restore(fifo, ok=False)
        self.assertTrue(stat.S_ISFIFO(fifo.lstat().st_mode))

    def test_10_every_regular_snapshot_file_corruption(self):
        self.create("prior")
        self.create("victim")
        files = [p.relative_to(self.repo / "victim") for p in
                 (self.repo / "victim").rglob("*") if p.is_file()]
        self.assertGreaterEqual(len(files), 5)
        for relative in files:
            for corruption in ["alter", "truncate", "delete"]:
                with self.subTest(file=relative, corruption=corruption):
                    clone = self.root / "clone"
                    shutil.copytree(self.repo, clone)
                    target = clone / "victim" / relative
                    if corruption == "delete":
                        target.unlink()
                    elif corruption == "truncate":
                        raw = target.read_bytes()
                        target.write_bytes(raw[:-1] if raw else b"x")
                    else:
                        raw = target.read_bytes()
                        target.write_bytes(bytes([raw[0] ^ 1]) + raw[1:] if raw else b"x")
                    damaged = tree(clone)
                    self.verify("victim", repo=clone, ok=False)
                    dest = self.root / "restore_corrupt"
                    self.restore(dest, "victim", repo=clone, ok=False)
                    self.assertFalse(dest.exists())
                    self.verify("prior", repo=clone)
                    self.cli("list", "--repo", clone, expected={"snapshots": ["prior"]})
                    self.assertEqual(tree(clone), damaged)
                    self.assertFalse(list(self.root.glob(".restore-*")))
                    shutil.rmtree(clone)

    def test_11_structure_and_metadata_schema(self):
        self.create()
        original = json.loads((self.repo / "v1" / "manifest.json").read_text())
        for change in ["extra-data", "missing-directory", "extra-root", "parent-path",
                       "duplicate-path", "bool-size", "wrong-id", "duplicate-json-key"]:
            with self.subTest(change=change):
                clone = self.root / "clone"
                shutil.copytree(self.repo, clone)
                snap = clone / "v1"
                manifest = json.loads(json.dumps(original))
                if change == "extra-data":
                    (snap / "data" / "extra").write_bytes(b"extra")
                elif change == "missing-directory":
                    (snap / "data" / "vacío").rmdir()
                elif change == "extra-root":
                    (snap / "extra").write_bytes(b"extra")
                else:
                    if change == "parent-path":
                        manifest["entries"][0]["path"] = ["..", "escape"]
                    elif change == "duplicate-path":
                        manifest["entries"].append(manifest["entries"][0])
                    elif change == "bool-size":
                        next(e for e in manifest["entries"] if e["kind"] == "file")["size"] = True
                    elif change == "wrong-id":
                        manifest["id"] = "other"
                    raw = json.dumps(manifest).encode()
                    if change == "duplicate-json-key":
                        raw = raw[:-1] + b', "version": 1}'
                    (snap / "manifest.json").write_bytes(raw)
                    (snap / "seal").write_bytes(hashlib.sha256(raw).hexdigest().encode() + b"\n")
                self.verify(repo=clone, ok=False)
                self.restore(self.root / "dest", repo=clone, ok=False)
                self.assertFalse((self.root / "dest").exists())
                shutil.rmtree(clone)

    def test_12_unsafe_snapshot_and_repo_entries(self):
        self.create()
        outside = self.root / "sentinel"
        outside.write_bytes(b"safe")
        for placement, filetype in [("snapshot", "link"), ("snapshot", "fifo"),
                                    ("repo", "link"), ("repo", "fifo")]:
            with self.subTest(placement=placement, filetype=filetype):
                entry = (self.repo / "v1" / "data" if placement == "snapshot" else self.repo) / "unsafe"
                if filetype == "link":
                    entry.symlink_to(outside)
                else:
                    os.mkfifo(entry)
                before = tree(self.repo)
                self.verify(ok=False)
                self.restore(self.root / "dest", ok=False)
                self.create("new", ok=False)
                self.cli("list", "--repo", self.repo, ok=False)
                self.assertEqual(tree(self.repo), before)
                self.assertEqual(outside.read_bytes(), b"safe")
                entry.unlink()

    def test_13_only_complete_snapshots_listed(self):
        self.create("complete")
        (self.repo / "incomplete").mkdir()
        (self.repo / "incomplete" / "data").mkdir()
        pending = self.repo / (".pending-" + "a" * 32)
        pending.mkdir()
        (pending / "bytes").write_bytes(b"partial")
        self.cli("list", "--repo", self.repo, expected={"snapshots": ["complete"]})
        self.verify("incomplete", ok=False)
        self.create("incomplete", ok=False)
        self.create("new")
        self.assertFalse(pending.exists())
        self.verify("complete")

    def test_14_limit_arguments(self):
        for value in ["-1", "1.5", "NaN", "+10", " 10", "１０", "", "1e6"]:
            with self.subTest(value=value):
                self.create(limit=value, ok=False)
                self.assertFalse(self.repo.exists())
        self.cli("create", "--source", self.source, "--repo", self.repo,
                 "--id", "v1", "--max-bytes", ok=False)
        self.create(limit="0001000000")
        self.assertLessEqual(repo_bytes(self.repo), 1000000)

    def test_15_limit_counts_metadata_and_exact_boundary(self):
        reference = self.root / "reference"
        self.create(repo=reference)
        required = repo_bytes(reference)
        payload = repo_bytes(reference / "v1" / "data")
        self.assertGreater(required, payload)
        expected = tree(reference)
        self.create(limit=required - 1, ok=False)
        self.assertEqual(tree(self.repo), {})
        self.assertEqual(repo_bytes(self.repo), 0)
        self.create(limit=required)
        self.assertEqual(repo_bytes(self.repo), required)
        self.assertEqual(tree(self.repo), expected)
        self.verify()
        self.restore(self.root / "dest")
        self.assertEqual(tree(self.root / "dest"), tree(self.source))

    def test_16_empty_source_still_requires_metadata(self):
        empty = self.root / "empty_source"
        empty.mkdir()
        reference = self.root / "reference"
        self.create(source=empty, repo=reference)
        required = repo_bytes(reference)
        self.assertGreater(required, 65)
        for limit in [0, 65, required - 1]:
            with self.subTest(limit=limit):
                self.create(source=empty, limit=limit, ok=False)
                self.assertEqual(tree(self.repo), {})
        self.create(source=empty, limit=required)
        self.restore(self.root / "dest")
        self.assertEqual(tree(self.root / "dest"), {})

    def test_17_rejection_preserves_previous_and_has_no_residual(self):
        self.create("prior")
        before = tree(self.repo)
        existing = repo_bytes(self.repo)
        for limit in [0, existing - 1, existing, existing + 1]:
            with self.subTest(limit=limit):
                self.create("new", limit=limit, ok=False)
                self.assertEqual(tree(self.repo), before)
                self.assertEqual(repo_bytes(self.repo), existing)
                self.verify("prior")
        self.restore(self.root / "dest", "prior")
        self.assertEqual(tree(self.root / "dest"), tree(self.source))
        self.create("new", limit=10**9)
        self.assertLessEqual(repo_bytes(self.repo), 10**9)
        self.verify("new")

    def test_18_total_limit_over_multiple_snapshots(self):
        self.create("prior")
        before = tree(self.repo)
        existing = repo_bytes(self.repo)
        (self.source / "empty").write_bytes(b"next version")
        reference = self.root / "reference"
        self.create("next", repo=reference)
        extra = repo_bytes(reference)
        self.create("next", limit=existing + extra - 1, ok=False)
        self.assertEqual(tree(self.repo), before)
        self.create("next", limit=existing + extra)
        self.assertEqual(repo_bytes(self.repo), existing + extra)
        self.verify("prior")
        self.verify("next")

    def test_19_sigkill_and_retry_with_budget(self):
        self.create("prior")
        before = tree(self.repo / "prior")
        (self.source / "large").write_bytes(b"\x00\xff\x42" * 700000)
        reference = self.root / "reference"
        self.create("interrupted", repo=reference)
        limit = repo_bytes(self.repo) + repo_bytes(reference)
        ready = self.root / "ready"
        # Detener el proceso justo después de escribir el primer bloque real
        # del temporal. La operación es la misma main/create del producto.
        worker = self.root / "kill_worker.py"
        worker.write_text(
            "import importlib.util, os, signal, sys\n"
            f"spec = importlib.util.spec_from_file_location('backup', {str(CLI)!r})\n"
            "b = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(b)\n"
            "original = b.write_all\n"
            "def stop_after_write(fd, data):\n"
            "    original(fd, data)\n"
            f"    open({str(ready)!r}, 'w').close()\n"
            "    os.kill(os.getpid(), signal.SIGSTOP)\n"
            "b.write_all = stop_after_write\n"
            "sys.exit(b.main(sys.argv[1:]))\n"
        )
        process = subprocess.Popen([sys.executable, str(worker), "create", "--source",
                                    str(self.source), "--repo", str(self.repo), "--id",
                                    "interrupted", "--max-bytes", str(limit)],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 10
            while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(ready.exists(), "no se alcanzó el punto de interrupción")
            pending = list(self.repo.glob(".pending-*"))
            self.assertEqual(len(pending), 1)
            self.assertGreater(repo_bytes(pending[0]), 0)
            process.kill()
            stdout, stderr = process.communicate(timeout=10)
            self.assertEqual(process.returncode, -signal.SIGKILL)
            self.assertEqual(stdout, b"")
            self.assertEqual(stderr, b"")
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=10)
        self.assertEqual(tree(self.repo / "prior"), before)
        self.cli("list", "--repo", self.repo, expected={"snapshots": ["prior"]})
        self.verify("prior")
        self.verify("interrupted", ok=False)
        self.create("interrupted", limit=limit)
        self.assertFalse(list(self.repo.glob(".pending-*")))
        self.assertEqual(repo_bytes(self.repo), limit)
        self.verify("interrupted")
        self.restore(self.root / "restored", "interrupted")
        self.assertEqual(tree(self.root / "restored"), tree(self.source))

    def test_20_budget_rejection_cleans_abandoned_stage(self):
        self.create("prior")
        before = tree(self.repo)
        existing = repo_bytes(self.repo)
        pending = self.repo / (".pending-" + "b" * 32)
        (pending / "data").mkdir(parents=True)
        (pending / "data" / "partial").write_bytes(b"partial" * 100)
        self.create("new", limit=existing - 1, ok=False)
        self.assertEqual(tree(self.repo), before)
        self.assertEqual(repo_bytes(self.repo), existing)
        self.verify("prior")

    def test_21_corrupt_snapshot_preserved_on_budget_rejection(self):
        self.create("victim")
        (self.repo / "victim" / "data" / "empty").write_bytes(b"corruption")
        before = tree(self.repo)
        self.create("new", limit=repo_bytes(self.repo) - 1, ok=False)
        self.assertEqual(tree(self.repo), before)
        self.verify("victim", ok=False)
        self.restore(self.root / "dest", "victim", ok=False)
        self.assertFalse((self.root / "dest").exists())

    def test_22_source_socket(self):
        with socket.socket(socket.AF_UNIX) as sock:
            try:
                sock.bind(str(self.source / "sock"))
            except PermissionError as exc:
                self.skipTest(f"sandbox no permite crear sockets AF_UNIX: {exc}")
            self.create(ok=False)
            self.assertFalse(self.repo.exists())

    def test_23_concurrent_creates_share_total_budget(self):
        reference = self.root / "reference"
        self.create("one", repo=reference)
        limit = repo_bytes(reference)
        args = [sys.executable, str(CLI), "create", "--source", str(self.source),
                "--repo", str(self.repo), "--max-bytes", str(limit), "--id"]
        processes = [subprocess.Popen(args + [identifier], stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE) for identifier in ["one", "two"]]
        outputs = [p.communicate(timeout=30) for p in processes]
        self.assertEqual(sorted(p.returncode for p in processes), [0, 1])
        for process, (out, err) in zip(processes, outputs):
            if process.returncode == 0:
                identifier = json.loads(out)["id"]
                self.assertEqual(err, b"")
                self.verify(identifier)
                self.cli("list", "--repo", self.repo, expected={"snapshots": [identifier]})
            else:
                self.assertEqual(out, b"")
                self.assertIn("error", json.loads(err))
        self.assertEqual(repo_bytes(self.repo), limit)
        self.assertFalse(list(self.repo.glob(".pending-*")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
