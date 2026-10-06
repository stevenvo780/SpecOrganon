"""Pruebas locales trazables a SPEC.md; solo utilizan datos sintéticos en /trial."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock


SOLUTION = Path(__file__).resolve().parents[1]
PROGRAM = SOLUTION / "backup.py"
WORK = SOLUTION / "tests" / "work"
WORK.mkdir(exist_ok=True)
spec = importlib.util.spec_from_file_location("backup", PROGRAM)
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


def tree(root: Path) -> dict:
    result = {}
    for current, directories, files in os.walk(root, followlinks=False):
        for name in directories:
            path = Path(current) / name
            result[str(path.relative_to(root))] = ("link", os.readlink(path)) if path.is_symlink() else ("dir",)
        for name in files:
            path = Path(current) / name
            result[str(path.relative_to(root))] = ("link", os.readlink(path)) if path.is_symlink() else ("file", path.read_bytes())
    return result


def regular_bytes(root: Path) -> int:
    """Medición externa al programa; incluye cualquier archivo persistente."""
    total = 0
    for current, _, files in os.walk(root, followlinks=False):
        for name in files:
            info = (Path(current) / name).lstat()
            if not stat.S_ISREG(info.st_mode):
                raise AssertionError("La medición encontró un archivo no regular")
            total += info.st_size
    return total


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory(prefix="case-", dir=WORK)
        self.root = Path(self.workspace.name)
        self.source = self.root / "fuente con espacios"
        self.source.mkdir()
        self.repo = self.root / "repo"
        self.dest = self.root / "dest"

    def tearDown(self):
        self.workspace.cleanup()

    def run_cli(self, command, *, success=True, **arguments):
        args = [sys.executable, str(PROGRAM), command]
        for key, value in arguments.items():
            args.extend(["--" + key.replace("_", "-"), str(value)])
        process = subprocess.run(args, capture_output=True, text=True, timeout=30, cwd=self.root)
        if success:
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(process.stderr, "")
            output = json.loads(process.stdout)
            self.assertIsInstance(output, dict)
            self.assertEqual(len(process.stdout.splitlines()), 1)
            return output
        self.assertNotEqual(process.returncode, 0, process.stdout)
        self.assertEqual(process.stdout, "")
        self.assertIn("error", json.loads(process.stderr))
        return process

    def create(self, identifier="v1", **arguments):
        return self.run_cli("create", source=self.source, repo=self.repo, id=identifier, **arguments)

    def verify(self, identifier="v1", success=True):
        return self.run_cli("verify", repo=self.repo, id=identifier, success=success)

    def restore(self, identifier="v1", dest=None, success=True):
        return self.run_cli("restore", repo=self.repo, id=identifier, dest=dest or self.dest, success=success)

    def populated(self):
        (self.source / "árbol 日本語").mkdir()
        (self.source / "árbol 日本語" / "vacío").mkdir()
        (self.source / "otros vacíos").mkdir()
        (self.source / "bytes.bin").write_bytes(bytes(range(256)) * 41)
        (self.source / "árbol 日本語" / "texto con espacios.txt").write_bytes("Español\n日本語\n".encode())
        (self.source / "cero").write_bytes(b"")
        (self.source / "nombre\\literal\nsalto").write_bytes(b"\0\xff\r\n")

    def test_c01_cli_and_json(self):
        self.assertEqual(self.create(), {"id": "v1"})
        self.assertEqual(self.verify(), {"id": "v1", "valid": True})
        self.assertEqual(self.restore(), {"id": "v1"})
        self.assertEqual(self.run_cli("list", repo=self.repo), {"snapshots": ["v1"]})
        for args in ([], ["bad"], ["create"], ["list", "--repo", str(self.repo), "--unknown"]):
            process = subprocess.run([sys.executable, str(PROGRAM), *args], capture_output=True, text=True, timeout=10)
            self.assertNotEqual(process.returncode, 0)
            self.assertEqual(process.stdout, "")
            self.assertIn("error", json.loads(process.stderr))

    def test_c02_arbitrary_bytes_names_empty_dirs_and_source_unchanged(self):
        self.populated()
        before = tree(self.source)
        timestamps = {str(p.relative_to(self.source)): (p.stat().st_mtime_ns, p.stat().st_mode)
                      for p in self.source.rglob("*")}
        self.create()
        self.verify()
        self.restore()
        self.assertEqual(tree(self.source), before)
        self.assertEqual(tree(self.dest), before)
        self.assertEqual(timestamps, {str(p.relative_to(self.source)): (p.stat().st_mtime_ns, p.stat().st_mode)
                                      for p in self.source.rglob("*")})

    def test_c03_three_versions_exact_and_self_contained(self):
        self.populated()
        versions = {"v1": tree(self.source)}
        limit = 1_000_000
        self.create("v1", max_bytes=limit)
        first = tree(self.repo / "v1")
        (self.source / "bytes.bin").write_bytes(b"modificado\0\xff")
        (self.source / "nuevo").write_bytes(b"nuevo")
        (self.source / "cero").unlink()
        versions["v2"] = tree(self.source)
        self.create("v2", max_bytes=limit)
        (self.source / "nuevo").unlink()
        shutil.rmtree(self.source / "árbol 日本語")
        (self.source / "bytes.bin").unlink()
        (self.source / "bytes.bin").mkdir()
        (self.source / "bytes.bin" / "ahora directorio").write_bytes(b"tercera")
        versions["v3"] = tree(self.source)
        self.create("v3", max_bytes=limit)
        self.assertLessEqual(regular_bytes(self.repo), limit)
        self.assertEqual(tree(self.repo / "v1"), first)
        shutil.rmtree(self.source)
        for identifier, expected in versions.items():
            self.verify(identifier)
            dest = self.root / identifier
            self.restore(identifier, dest=dest)
            self.assertEqual(tree(dest), expected)

    def test_c02_empty_source(self):
        self.create()
        self.verify()
        self.restore()
        self.assertEqual(tree(self.dest), {})

    def test_c04_invalid_ids(self):
        for identifier in ("", ".", "..", "../x", "/abs", "a/b", "_inicio", "-inicio", "a.b", "á", "a" * 65, "a\n"):
            with self.subTest(identifier=identifier):
                self.run_cli("create", source=self.source, repo=self.repo, id=identifier, success=False)
                self.run_cli("verify", repo=self.repo, id=identifier, success=False)
                self.run_cli("restore", repo=self.repo, id=identifier, dest=self.dest, success=False)
        self.assertFalse(self.repo.exists())
        self.assertFalse(self.dest.exists())

    def test_c04_valid_boundary_ids_and_sorted_list(self):
        identifiers = ["z", "A_9-", "0", "a" * 64]
        for identifier in identifiers:
            self.create(identifier)
            self.verify(identifier)
        self.assertEqual(self.run_cli("list", repo=self.repo), {"snapshots": sorted(identifiers)})

    def test_c04_duplicate_and_unknown_ids(self):
        self.populated()
        self.create()
        before = tree(self.repo)
        (self.source / "nuevo").write_bytes(b"nuevo")
        self.run_cli("create", source=self.source, repo=self.repo, id="v1", success=False)
        self.assertEqual(tree(self.repo), before)
        self.verify("inexistente", success=False)
        self.restore("inexistente", success=False)
        self.assertFalse(self.dest.exists())

    def test_c05_new_empty_incomplete_and_corrupt_list(self):
        self.assertEqual(self.run_cli("list", repo=self.repo), {"snapshots": []})
        self.assertFalse(self.repo.exists())
        self.repo.mkdir()
        self.assertEqual(self.run_cli("list", repo=self.repo), {"snapshots": []})
        (self.repo / ".incomplete-abandoned").mkdir()
        (self.repo / ".incomplete-abandoned" / "partial").write_bytes(b"partial")
        (self.repo / "incomplete").mkdir()
        self.create("good")
        self.create("broken")
        (self.repo / "broken" / "manifest.sha256").unlink()
        self.assertEqual(self.run_cli("list", repo=self.repo), {"snapshots": ["good"]})

    def test_c06_source_symlinks_files_dirs_dangling(self):
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "file").write_bytes(b"protected")
        before = tree(outside)
        for target in (outside, outside / "file", outside / "absent"):
            link = self.source / "link"
            link.symlink_to(target)
            self.run_cli("create", source=self.source, repo=self.repo, id="v1", success=False)
            self.assertFalse(self.repo.exists())
            self.assertEqual(tree(outside), before)
            link.unlink()

    def test_c06_ancestor_symlinks_all_arguments_and_dotdot(self):
        alias = self.root / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        self.run_cli("create", source=alias / self.source.name, repo=self.repo, id="v1", success=False)
        self.run_cli("create", source=self.source, repo=alias / "repo", id="v1", success=False)
        self.create()
        self.run_cli("verify", repo=alias / "repo", id="v1", success=False)
        self.run_cli("list", repo=alias / "repo", success=False)
        self.restore(dest=alias / "dest", success=False)
        raw = str(alias) + "/../" + self.root.name + "/" + self.source.name
        self.run_cli("create", source=raw, repo=self.repo, id="v2", success=False)

    def test_c06_missing_component_dotdot_cannot_hide_symlink(self):
        outside = self.root / "outside"
        outside.mkdir()
        alias = self.root / "alias"
        alias.symlink_to(outside, target_is_directory=True)
        raw = str(self.root) + "/missing/../alias/hidden"
        self.run_cli("create", source=self.source, repo=raw, id="v1",
                     max_bytes=1_000_000, success=False)
        self.assertEqual(tree(outside), {})
        self.create()
        self.restore(dest=raw, success=False)
        self.assertEqual(tree(outside), {})

    def test_c06_repo_symlink_and_symlink_in_abandoned_stage(self):
        self.create()
        saved = tree(self.repo)
        alias = self.root / "alias"
        alias.symlink_to(self.repo, target_is_directory=True)
        self.run_cli("create", source=self.source, repo=alias, id="v2", success=False)
        self.run_cli("list", repo=alias, success=False)
        (self.repo / ".incomplete-stage").mkdir()
        link = self.repo / ".incomplete-stage" / "link"
        link.symlink_to(self.source)
        self.verify(success=False)
        self.restore(success=False)
        self.run_cli("list", repo=self.repo, success=False)
        self.run_cli("create", source=self.source, repo=self.repo, id="v2", success=False)
        link.unlink()
        (self.repo / ".incomplete-stage").rmdir()
        self.assertEqual(tree(self.repo), saved)

    def test_c06_snapshot_symlinks(self):
        self.populated()
        self.create()
        snapshot = self.repo / "v1"
        for relative in ("manifest.json", "manifest.sha256", "data/00000000.bin", "data"):
            original = snapshot / relative
            held = self.root / "held"
            original.rename(held)
            original.symlink_to(held, target_is_directory=held.is_dir())
            self.verify(success=False)
            self.restore(success=False)
            self.run_cli("list", repo=self.repo, success=False)
            self.assertFalse(self.dest.exists())
            original.unlink()
            held.rename(original)
        outside = self.root / "whole"
        snapshot.rename(outside)
        snapshot.symlink_to(outside, target_is_directory=True)
        self.verify(success=False)
        self.restore(success=False)

    def test_c06_destination_symlink_and_special_files(self):
        self.create()
        outside = self.root / "outside"
        outside.mkdir()
        self.dest.symlink_to(outside, target_is_directory=True)
        self.restore(success=False)
        self.assertEqual(tree(outside), {})
        self.dest.unlink()
        self.dest.mkdir()
        (self.dest / "link").symlink_to(outside)
        self.restore(success=False)
        self.assertTrue((self.dest / "link").is_symlink())
        (self.dest / "link").unlink()
        os.mkfifo(self.dest / "fifo")
        self.restore(success=False)
        self.assertTrue((self.dest / "fifo").exists())

    def test_c06_fifo_and_socket_source_repo_snapshots(self):
        for kind in ("fifo", "socket"):
            with self.subTest(kind=kind):
                special = self.source / "special"
                if kind == "fifo":
                    os.mkfifo(special)
                else:
                    # Inodo real de socket, sin bind/conexión (red bloqueada).
                    os.mknod(special, stat.S_IFSOCK | 0o600)
                try:
                    self.run_cli("create", source=self.source, repo=self.repo, id="v1", success=False)
                finally:
                    special.unlink()
        self.create()
        for special in (self.repo / "special", self.repo / "v1" / "data" / "fifo"):
            os.mkfifo(special)
            self.verify(success=False)
            self.restore(success=False)
            self.run_cli("list", repo=self.repo, success=False)
            self.run_cli("create", source=self.source, repo=self.repo, id="v2", success=False)
            special.unlink()

    def test_c07_overlaps_both_directions_equal_and_normalized(self):
        self.run_cli("create", source=self.source, repo=self.source, id="v1", success=False)
        self.run_cli("create", source=self.source, repo=self.source / "repo", id="v1", success=False)
        self.assertEqual(tree(self.source), {})
        self.run_cli("create", source=self.source, repo=self.root, id="v1", success=False)
        raw = str(self.source) + "/../" + self.source.name + "/repo"
        self.run_cli("create", source=self.source, repo=raw, id="v1", success=False)
        self.create()
        before = tree(self.repo)
        for dest in (self.repo, self.repo / "v1" / "empty", self.root):
            self.restore(dest=dest, success=False)
        self.assertEqual(tree(self.repo), before)

    def test_c07_existing_nonempty_dest_preserved(self):
        self.populated()
        self.create()
        self.dest.mkdir()
        (self.dest / "protected").write_bytes(b"keep these bytes\0\xff")
        (self.dest / "empty").mkdir()
        before = tree(self.dest)
        self.restore(success=False)
        self.assertEqual(tree(self.dest), before)
        (self.dest / "protected").unlink()
        self.restore(success=False)
        self.assertEqual(tree(self.dest), {"empty": ("dir",)})

    def test_c07_regular_file_dest_preserved(self):
        self.create()
        self.dest.write_bytes(b"protected")
        self.restore(success=False)
        self.assertEqual(self.dest.read_bytes(), b"protected")

    def test_c08_every_snapshot_file_altered_and_deleted(self):
        self.populated()
        self.create()
        files = sorted(path for path in (self.repo / "v1").rglob("*") if path.is_file())
        for path in files:
            original = path.read_bytes()
            for damage in ("alter", "delete"):
                with self.subTest(file=path.name, damage=damage):
                    if damage == "alter":
                        path.write_bytes((bytes([original[0] ^ 1]) + original[1:]) if original else b"changed")
                    else:
                        path.unlink()
                    self.verify(success=False)
                    self.restore(success=False)
                    self.assertFalse(self.dest.exists())
                    self.assertEqual(self.run_cli("list", repo=self.repo), {"snapshots": []})
                    path.write_bytes(original)
        self.verify()

    def test_c08_extra_objects_and_structure(self):
        self.create()
        for path in (self.repo / "v1" / "extra", self.repo / "v1" / "data" / "extra"):
            path.write_bytes(b"extra")
            self.verify(success=False)
            self.restore(success=False)
            path.unlink()
        (self.repo / "v1" / "data" / "nested").mkdir()
        self.verify(success=False)
        self.restore(success=False)

    def test_c08_malformed_manifests_with_recomputed_seal(self):
        self.populated()
        self.create()
        path = self.repo / "v1" / "manifest.json"
        seal = self.repo / "v1" / "manifest.sha256"
        original = path.read_bytes()
        baseline = json.loads(original)

        def bad_mutation(change):
            manifest = json.loads(original)
            change(manifest)
            return json.dumps(manifest).encode()

        cases = [
            b"not json", b"[]", b'{"id":"v1","id":"v1"}', b"\xff", b"[" * 1100,
            bad_mutation(lambda m: m.update(format=True)),
            bad_mutation(lambda m: m.update(format=99)),
            bad_mutation(lambda m: m.update(id="other")),
            bad_mutation(lambda m: m.update(extra=0)),
            bad_mutation(lambda m: m.update(directories="invalid")),
            bad_mutation(lambda m: m["directories"].append(m["directories"][0])),
            bad_mutation(lambda m: m["files"][0].update(path=["..", "escape"])),
            bad_mutation(lambda m: m["files"][0].update(path=["/absolute"])),
            bad_mutation(lambda m: m["files"][0].update(path=["a/b"])),
            bad_mutation(lambda m: m["files"][0].update(path=["nul\0"])),
            bad_mutation(lambda m: m["files"][0].update(path=[])),
            bad_mutation(lambda m: m["files"][0].update(path=[42])),
            bad_mutation(lambda m: m["files"][0].update(path=["missing", "file"])),
            bad_mutation(lambda m: m["files"][0].update(path=baseline["directories"][0])),
            bad_mutation(lambda m: m["files"][0].update(size=True)),
            bad_mutation(lambda m: m["files"][0].update(size=-1)),
            bad_mutation(lambda m: m["files"][0].update(sha256="invalid")),
            bad_mutation(lambda m: m["files"][0].update(object="../../escape")),
            bad_mutation(lambda m: m["files"][0].update(object=[])),
            bad_mutation(lambda m: m["files"].append(m["files"][0])),
        ]
        for index, encoded in enumerate(cases):
            with self.subTest(case=index):
                path.write_bytes(encoded)
                seal.write_text(hashlib.sha256(encoded).hexdigest() + "\n", encoding="ascii")
                self.verify(success=False)
                self.restore(success=False)
                self.assertFalse(self.dest.exists())
                self.assertFalse((self.root / "escape").exists())
        path.write_bytes(original)
        seal.write_text(hashlib.sha256(original).hexdigest() + "\n", encoding="ascii")
        self.verify()

    def test_c09_sigkill_partial_create_then_same_id_retry(self):
        (self.source / "small").write_bytes(b"previous")
        self.create("previous", max_bytes=1_000_000)
        old = tree(self.repo / "previous")
        large = self.source / "large"
        with large.open("wb") as stream:
            stream.truncate(256 * 1024 * 1024)
        before = {p.name: (p.stat().st_size, p.stat().st_mtime_ns) for p in self.source.iterdir()}
        budget = 2 * large.stat().st_size + regular_bytes(self.repo) + 65_536
        args = [sys.executable, str(PROGRAM), "create", "--source", str(self.source),
                "--repo", str(self.repo), "--id", "interrupted", "--max-bytes", str(budget)]
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        observed_partial = False
        deadline = time.monotonic() + 15
        try:
            while time.monotonic() < deadline and process.poll() is None:
                for stage in self.repo.glob(".incomplete-*"):
                    for data in stage.glob("data/*.bin"):
                        try:
                            size = data.stat().st_size
                        except FileNotFoundError:
                            continue
                        if 0 < size < large.stat().st_size:
                            os.kill(process.pid, signal.SIGKILL)
                            observed_partial = True
                            break
                    if observed_partial:
                        break
                if observed_partial:
                    break
                time.sleep(0.001)
            stdout, stderr = process.communicate(timeout=10)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
        self.assertTrue(observed_partial, "No se observó la ventana de copia incompleta")
        self.assertEqual(process.returncode, -signal.SIGKILL)
        self.assertEqual(stdout, b"")
        self.assertEqual(stderr, b"")
        self.assertFalse((self.repo / "interrupted").exists())
        self.assertTrue(list(self.repo.glob(".incomplete-*")))
        self.assertEqual(self.run_cli("list", repo=self.repo), {"snapshots": ["previous"]})
        self.assertEqual(tree(self.repo / "previous"), old)
        killed_bytes = regular_bytes(self.repo)
        stages = sorted(p.name for p in self.repo.glob(".incomplete-*"))
        self.create("interrupted", max_bytes=killed_bytes - 1, success=False)
        self.assertEqual(regular_bytes(self.repo), killed_bytes)
        self.assertEqual(sorted(p.name for p in self.repo.glob(".incomplete-*")), stages)
        self.create("interrupted", max_bytes=budget)
        self.assertLessEqual(regular_bytes(self.repo), budget)
        self.verify("interrupted")
        self.verify("previous")
        self.restore("interrupted")
        self.assertEqual((self.dest / "large").stat().st_size, large.stat().st_size)
        self.assertEqual(backup.digest_file(self.dest / "large"), backup.digest_file(large))
        self.assertEqual({p.name: (p.stat().st_size, p.stat().st_mtime_ns) for p in self.source.iterdir()}, before)

    def test_c09_write_error_cleanup_and_retry(self):
        self.populated()
        self.create("previous")
        old = tree(self.repo)
        with mock.patch.object(backup, "write_synced", side_effect=OSError("simulated disk failure")):
            with self.assertRaises(OSError):
                backup.create(str(self.source), str(self.repo), "retry")
        self.assertEqual(tree(self.repo), old)
        self.create("retry")
        self.verify("retry")

    def test_c10_existing_empty_dest_and_missing_parents(self):
        self.populated()
        self.create()
        expected = tree(self.source)
        self.dest.mkdir()
        self.restore()
        self.assertEqual(tree(self.dest), expected)
        nested = self.root / "new" / "parents" / "restore"
        self.restore(dest=nested)
        self.assertEqual(tree(nested), expected)

    def test_c10_corruption_preserves_empty_dest_and_no_parent_creation(self):
        (self.source / "file").write_bytes(b"correct")
        self.create()
        (self.repo / "v1" / "data" / "00000000.bin").write_bytes(b"corrupt")
        self.dest.mkdir()
        inode = self.dest.stat().st_ino
        self.restore(success=False)
        self.assertEqual(tree(self.dest), {})
        self.assertEqual(self.dest.stat().st_ino, inode)
        self.restore(dest=self.root / "absent" / "deep" / "dest", success=False)
        self.assertFalse((self.root / "absent").exists())

    def test_c10_copy_error_does_not_publish_and_can_retry(self):
        self.populated()
        self.create()
        self.dest.mkdir()
        inode = self.dest.stat().st_ino
        with mock.patch.object(backup, "copy_checked", side_effect=OSError("simulated copy failure")):
            with self.assertRaises(OSError):
                backup.restore(str(self.repo), "v1", str(self.dest))
        self.assertEqual(self.dest.stat().st_ino, inode)
        self.assertEqual(tree(self.dest), {})
        self.assertFalse(list(self.root.glob(".restore-*")))
        self.restore()
        self.assertEqual(tree(self.dest), tree(self.source))

    def test_c10_corruption_between_validation_and_copy(self):
        (self.source / "file").write_bytes(b"correct")
        self.create()
        real_copy = backup.copy_checked

        def corrupt_then_copy(source, target, expected=None):
            source.write_bytes(b"altered")
            return real_copy(source, target, expected)

        with mock.patch.object(backup, "copy_checked", side_effect=corrupt_then_copy):
            with self.assertRaises(backup.BackupError):
                backup.restore(str(self.repo), "v1", str(self.dest))
        self.assertFalse(self.dest.exists())
        self.assertFalse(list(self.root.glob(".restore-*")))

    def test_c11_source_permissions_not_needed_for_restore(self):
        self.populated()
        self.create()
        expected = tree(self.source)
        shutil.rmtree(self.source)
        self.restore()
        self.assertEqual(tree(self.dest), expected)

    def test_c12_max_bytes_argument_validation_and_optional_compatibility(self):
        before = tree(self.source)
        for value in ("", "-1", "+1", "1.5", "1e6", "NaN", " 1000", "1000 ", "１２３"):
            with self.subTest(value=value):
                self.create(max_bytes=value, success=False)
                self.assertFalse(self.repo.exists())
                self.assertEqual(tree(self.source), before)
        process = subprocess.run([sys.executable, str(PROGRAM), "create", "--source", str(self.source),
                                  "--repo", str(self.repo), "--id", "v1", "--max-bytes"],
                                 capture_output=True, text=True, timeout=10)
        self.assertNotEqual(process.returncode, 0)
        self.assertEqual(process.stdout, "")
        self.assertIn("error", json.loads(process.stderr))
        self.create("legacy")
        self.create("limited", max_bytes="0001000000")
        self.create("huge", max_bytes=10**30)
        for identifier in ("legacy", "limited", "huge"):
            self.verify(identifier)

    def test_c12_max_bytes_is_create_only(self):
        self.create()
        saved = tree(self.repo)
        for command in ("verify", "restore", "list"):
            arguments = {"repo": self.repo, "max_bytes": 1_000_000}
            if command != "list":
                arguments["id"] = "v1"
            if command == "restore":
                arguments["dest"] = self.dest
            self.run_cli(command, **arguments, success=False)
        self.assertEqual(tree(self.repo), saved)
        self.assertFalse(self.dest.exists())

    def test_c13_exact_limit_and_one_byte_short(self):
        self.populated()
        before = tree(self.source)
        reference = self.root / "reference"
        self.run_cli("create", source=self.source, repo=reference, id="v1")
        needed = regular_bytes(reference)
        self.create(max_bytes=needed - 1, success=False)
        self.assertEqual(regular_bytes(self.repo), 0)
        self.assertEqual(tree(self.repo), {})
        self.assertEqual(self.run_cli("list", repo=self.repo), {"snapshots": []})
        self.create(max_bytes=needed)
        self.assertEqual(regular_bytes(self.repo), needed)
        self.verify()
        self.restore()
        self.assertEqual(tree(self.dest), before)
        self.assertEqual(tree(self.source), before)

    def test_c13_metadata_counts_even_for_empty_source_and_directories(self):
        self.create(max_bytes=0, success=False)
        self.assertEqual(tree(self.repo), {})
        (self.source / "empty Unicode 日本語").mkdir()
        (self.source / "zero").write_bytes(b"")
        reference = self.root / "reference"
        self.run_cli("create", source=self.source, repo=reference, id="v1")
        needed = regular_bytes(reference)
        self.assertGreater(needed, 65)
        self.assertEqual(needed, (reference / "v1" / "manifest.json").stat().st_size + 65)
        self.create(max_bytes=needed - 1, success=False)
        self.assertEqual(tree(self.repo), {})
        self.create(max_bytes=needed)
        self.assertEqual(regular_bytes(self.repo), needed)
        self.restore()
        self.assertEqual(tree(self.dest), tree(self.source))

    def test_c13_prior_snapshots_and_abandoned_files_all_count(self):
        self.populated()
        self.create("previous")
        old = tree(self.repo / "previous")
        stage = self.repo / ".incomplete-abandoned" / "nested"
        stage.mkdir(parents=True)
        (stage / "persistent-metadata").write_bytes(b"M" * 4096)
        (self.source / "added").write_bytes(b"new bytes")
        reference = self.root / "reference"
        self.run_cli("create", source=self.source, repo=reference, id="next")
        new_size = regular_bytes(reference)
        old_size = regular_bytes(self.repo)
        saved = tree(self.repo)
        self.create("next", max_bytes=old_size + new_size - 4096, success=False)
        self.assertEqual(tree(self.repo), saved)
        self.create("next", max_bytes=old_size + new_size)
        self.assertEqual(regular_bytes(self.repo), old_size + new_size)
        self.assertEqual(tree(self.repo / "previous"), old)
        self.assertEqual((stage / "persistent-metadata").read_bytes(), b"M" * 4096)
        self.assertEqual(self.run_cli("list", repo=self.repo), {"snapshots": ["next", "previous"]})
        self.verify("previous")
        self.verify("next")

    def test_c14_below_existing_rejects_without_writes(self):
        self.populated()
        self.create("previous")
        saved = tree(self.repo)
        source = tree(self.source)
        existing = regular_bytes(self.repo)
        with mock.patch.object(backup.tempfile, "mkdtemp", side_effect=AssertionError("No debe escribir")):
            with self.assertRaises(backup.BackupError):
                backup.create(str(self.source), str(self.repo), "next", existing - 1)
        self.create("next", max_bytes=existing - 1, success=False)
        self.assertEqual(tree(self.repo), saved)
        self.assertEqual(tree(self.source), source)
        self.assertEqual(regular_bytes(self.repo), existing)
        self.verify("previous")
        self.restore("previous")
        self.assertEqual(tree(self.dest), source)

    def test_c14_repeated_rejection_leaves_no_residue_and_same_id_can_retry(self):
        self.populated()
        self.create("previous")
        (self.source / "bytes.bin").write_bytes(b"changed\0\xff")
        (self.source / "new").write_bytes(b"new")
        (self.source / "cero").unlink()
        source = tree(self.source)
        saved = tree(self.repo)
        reference = self.root / "reference"
        self.run_cli("create", source=self.source, repo=reference, id="next")
        needed = regular_bytes(self.repo) + regular_bytes(reference)
        for _ in range(3):
            self.create("next", max_bytes=needed - 1, success=False)
            self.assertEqual(tree(self.repo), saved)
            self.assertEqual(tree(self.source), source)
            self.assertFalse(list(self.repo.glob(".incomplete-*")))
            self.assertEqual(self.run_cli("list", repo=self.repo), {"snapshots": ["previous"]})
            self.verify("next", success=False)
        self.create("next", max_bytes=needed)
        self.assertEqual(regular_bytes(self.repo), needed)
        self.verify("previous")
        self.verify("next")
        self.restore("next")
        self.assertEqual(tree(self.dest), source)

    def test_c14_failure_in_final_accounting_cleans_stage(self):
        self.populated()
        self.create("previous")
        saved = tree(self.repo)
        with mock.patch.object(backup, "repository_bytes", side_effect=[regular_bytes(self.repo), OSError("count failure")]):
            with self.assertRaises(OSError):
                backup.create(str(self.source), str(self.repo), "next", 1_000_000)
        self.assertEqual(tree(self.repo), saved)
        self.create("next", max_bytes=1_000_000)
        self.verify("next")

    def test_c15_limited_create_preserves_ids_overlap_and_link_rejections(self):
        self.populated()
        self.create(max_bytes=1_000_000)
        saved = tree(self.repo)
        source = tree(self.source)
        self.create(max_bytes=1_000_000, success=False)
        self.create("../escape", max_bytes=1_000_000, success=False)
        self.run_cli("create", source=self.source, repo=self.source / "repo", id="v2",
                     max_bytes=1_000_000, success=False)
        (self.source / "link").symlink_to(self.repo)
        self.create("v2", max_bytes=1_000_000, success=False)
        (self.source / "link").unlink()
        self.assertEqual(tree(self.repo), saved)
        self.assertEqual(tree(self.source), source)
        self.verify()


if __name__ == "__main__":
    unittest.main(verbosity=2)
