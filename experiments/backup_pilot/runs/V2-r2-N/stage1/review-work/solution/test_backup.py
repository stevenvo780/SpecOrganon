"""Pruebas de contrato con procesos CLI reales; no requiere dependencias."""

import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest


SCRIPT = Path(__file__).with_name("backup.py")
WORK = Path(__file__).with_name(".test-work")


def tree(root):
    result = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        result[relative] = None if path.is_dir() else path.read_bytes()
    return result


class BackupContract(unittest.TestCase):
    def setUp(self):
        WORK.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=WORK)
        self.base = Path(self.temporary.name)
        self.source = self.base / "fuente con espacios"
        self.source.mkdir()
        self.repo = self.base / "repositorio"

    def tearDown(self):
        self.temporary.cleanup()

    def command(self, command, *, ok=True, **arguments):
        arguments.setdefault("repo", self.repo)
        argv = [sys.executable, str(SCRIPT), command]
        for name, value in arguments.items():
            argv.extend(["--" + name, str(value)])
        result = subprocess.run(argv, capture_output=True, text=True, timeout=30)
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            # json.loads también rechaza varios objetos concatenados.
            response = json.loads(result.stdout)
            self.assertIsInstance(response, dict)
            return response
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.stdout, "")
        self.assertNotEqual(result.stderr, "")
        return result

    def create(self, snapshot_id="v1", **kwargs):
        return self.command("create", source=self.source, id=snapshot_id, **kwargs)

    def restore(self, snapshot_id="v1", dest=None, **kwargs):
        dest = dest or self.base / ("restaurado-" + snapshot_id)
        response = self.command("restore", id=snapshot_id, dest=dest, **kwargs)
        if kwargs.get("ok", True):
            self.assertEqual(response, {"id": snapshot_id})
        return dest

    def snapshot(self, snapshot_id="v1"):
        return self.repo / "snapshots" / (snapshot_id + ".bkp")

    def seed(self):
        (self.source / "vacío ü").mkdir()
        (self.source / "subcarpeta").mkdir()
        (self.source / "subcarpeta" / "bytes ñ.bin").write_bytes(bytes(range(256)) * 1025)
        (self.source / "cero").write_bytes(b"")
        (self.source / "documento.txt").write_text("primera versión\n", encoding="utf-8")

    def test_successive_versions_are_exact_and_self_contained(self):
        self.seed()
        versions = {}
        for snapshot_id in ("v1", "v2", "v3"):
            if snapshot_id == "v2":
                (self.source / "documento.txt").write_bytes(b"modificado\x00\xff")
                (self.source / "cero").unlink()
                (self.source / "nuevo archivo").write_bytes(b"nuevo")
                (self.source / "vacío ü").rmdir()
            elif snapshot_id == "v3":
                (self.source / "nuevo archivo").unlink()
                (self.source / "nuevo archivo").mkdir()
                (self.source / "nuevo archivo" / "hijo").write_bytes(b"cambio de tipo")
                (self.source / "subcarpeta" / "bytes ñ.bin").unlink()
                (self.source / "subcarpeta").rmdir()
                (self.source / "subcarpeta").write_bytes(b"ahora es archivo")
                (self.source / "otro vacío").mkdir()
            versions[snapshot_id] = tree(self.source)
            self.assertEqual(self.create(snapshot_id), {"id": snapshot_id})
            self.assertEqual(tree(self.source), versions[snapshot_id])
        # La fuente deja de estar disponible antes de verificar/restaurar.
        self.source.rename(self.base / "fuente retirada")
        self.assertEqual(self.command("list"), {"snapshots": ["v1", "v2", "v3"]})
        for snapshot_id, expected in versions.items():
            self.assertEqual(self.command("verify", id=snapshot_id),
                             {"id": snapshot_id, "valid": True})
            self.assertEqual(tree(self.restore(snapshot_id)), expected)

    def test_empty_source_and_existing_empty_destination(self):
        self.create()
        dest = self.base / "vacío"
        dest.mkdir()
        self.restore(dest=dest)
        self.assertEqual(tree(dest), {})

    def test_large_file_streaming(self):
        data = bytes(range(256)) * (3 * 4096 + 13)
        (self.source / "grande").write_bytes(data)
        self.create()
        self.assertEqual((self.restore() / "grande").read_bytes(), data)

    def test_empty_and_missing_repository_list(self):
        self.assertEqual(self.command("list"), {"snapshots": []})
        self.assertFalse(self.repo.exists())
        self.repo.mkdir()
        self.assertEqual(self.command("list"), {"snapshots": []})

    def test_list_order(self):
        for snapshot_id in ("z", "A", "a", "0", "a_1", "a-1"):
            self.create(snapshot_id)
        self.assertEqual(self.command("list"),
                         {"snapshots": ["0", "A", "a", "a-1", "a_1", "z"]})

    def test_id_validation_and_boundary(self):
        for snapshot_id in ("", ".", "..", "../escape", "a/b", "á", "-a", "a b",
                            "a\n", "a" * 65):
            with self.subTest(id=snapshot_id):
                for command in ("create", "verify", "restore"):
                    args = {"id": snapshot_id, "ok": False}
                    if command == "create":
                        args["source"] = self.source
                    elif command == "restore":
                        args["dest"] = self.base / "no creado"
                    self.command(command, **args)
        self.create("A" + "_-9" * 21)

    def test_missing_id(self):
        self.repo.mkdir()
        self.command("verify", id="ausente", ok=False)
        dest = self.restore("ausente", ok=False)
        self.assertFalse(dest.exists())

    def test_existing_id_preserved(self):
        self.seed()
        self.create()
        original = self.snapshot().read_bytes()
        (self.source / "documento.txt").write_bytes(b"distinto")
        self.create(ok=False)
        self.assertEqual(self.snapshot().read_bytes(), original)
        self.command("verify", id="v1")

    def test_nonempty_destination_preserves_every_byte(self):
        self.seed()
        self.create()
        dest = self.base / "protegido"
        dest.mkdir()
        (dest / "propio").write_bytes(b"NO CAMBIAR\x00\xff")
        (dest / "directorio vacío").mkdir()
        expected = tree(dest)
        self.restore(dest=dest, ok=False)
        self.assertEqual(tree(dest), expected)

    def test_source_repository_overlap_in_both_directions(self):
        self.seed()
        expected = tree(self.source)
        self.create(repo=self.source, ok=False)
        self.create(repo=self.source / "nuevo-repo", ok=False)
        self.create(repo=self.base, ok=False)
        self.assertEqual(tree(self.source), expected)
        self.assertFalse((self.source / "nuevo-repo").exists())

    def test_source_symlinks_and_special_files(self):
        protected = self.base / "ajeno"
        protected.write_bytes(b"protegido")
        bad = self.source / "prohibido"
        for target in (protected, self.base / "ausente", self.source):
            bad.symlink_to(target)
            self.create(ok=False)
            bad.unlink()
        os.mkfifo(bad)
        self.create(ok=False)
        bad.unlink()
        self.assertEqual(protected.read_bytes(), b"protegido")

    def test_socket_source_is_rejected(self):
        bad = self.source / "socket"
        with socket.socket(socket.AF_UNIX) as sock:
            try:
                sock.bind(str(bad))
            except PermissionError:
                self.skipTest("El sandbox no permite crear sockets Unix")
            self.create(ok=False)
        bad.unlink()

    def test_path_component_symlinks_are_rejected_even_before_dotdot(self):
        (self.base / "enlace").symlink_to(self.source, target_is_directory=True)
        for source in (self.base / "enlace", self.base / "enlace" / ".." / self.source.name):
            self.command("create", source=source, id="v1", ok=False)
        self.create()
        self.command("list", repo=self.base / "enlace" / ".." / self.repo.name, ok=False)
        self.restore(dest=self.base / "enlace" / ".." / "destino", ok=False)

    def test_repository_symlinks_and_special_entries(self):
        self.create()
        for area in (self.repo, self.repo / "snapshots", self.repo / "staging"):
            bad = area / ("mal.bkp" if area.name == "snapshots" else "mal")
            for form in ("symlink", "fifo", "directory"):
                with self.subTest(area=area.name, form=form):
                    if form == "symlink":
                        bad.symlink_to(self.base / "ausente")
                    elif form == "fifo":
                        os.mkfifo(bad)
                    else:
                        bad.mkdir()
                    self.command("verify", id="v1", ok=False)
                    self.command("list", ok=False)
                    self.create("v2", ok=False)
                    self.restore(ok=False)
                    bad.rmdir() if form == "directory" else bad.unlink()
        target = self.base / "repo enlace"
        target.symlink_to(self.repo, target_is_directory=True)
        self.command("list", repo=target, ok=False)
        self.command("verify", repo=target, id="v1", ok=False)
        self.command("create", repo=target, source=self.source, id="v2", ok=False)

    def test_destination_links_and_special_paths(self):
        self.create()
        target = self.base / "intacto"
        target.mkdir()
        (target / "dato").write_bytes(b"intacto")
        dest = self.base / "destino"
        dest.symlink_to(target, target_is_directory=True)
        self.restore(dest=dest, ok=False)
        self.restore(dest=dest / "hijo", ok=False)
        self.assertEqual(tree(target), {"dato": b"intacto"})
        dest.unlink()
        os.mkfifo(dest)
        self.restore(dest=dest, ok=False)
        dest.unlink()
        dest.write_bytes(b"archivo destino intacto")
        self.restore(dest=dest, ok=False)
        self.assertEqual(dest.read_bytes(), b"archivo destino intacto")

    def test_all_snapshot_regions_detect_corruption(self):
        self.seed()
        self.create()
        snapshot = self.snapshot()
        pristine = snapshot.read_bytes()
        offsets = [0, 8, 15, 16, 40, len(pristine) // 2, len(pristine) - 33,
                   len(pristine) - 32, len(pristine) - 1]
        for offset in offsets:
            with self.subTest(offset=offset):
                damaged = bytearray(pristine)
                damaged[offset] ^= 1
                snapshot.write_bytes(damaged)
                self.command("verify", id="v1", ok=False)
                dest = self.restore(ok=False)
                self.assertFalse(dest.exists())
                self.assertEqual(self.command("list"), {"snapshots": []})
        snapshot.write_bytes(pristine)
        self.command("verify", id="v1")

    def test_truncation_extra_bytes_and_deletion(self):
        self.seed()
        self.create()
        pristine = self.snapshot().read_bytes()
        for damaged in (b"", pristine[:12], pristine[:-1], pristine[:len(pristine) // 2],
                        pristine + b"extra"):
            self.snapshot().write_bytes(damaged)
            self.command("verify", id="v1", ok=False)
            self.restore(ok=False)
        self.snapshot().unlink()
        self.command("verify", id="v1", ok=False)
        self.restore(ok=False)
        self.assertEqual(self.command("list"), {"snapshots": []})

    def test_corrupt_snapshot_does_not_affect_previous_versions(self):
        self.seed()
        first = tree(self.source)
        self.create()
        (self.source / "documento.txt").write_bytes(b"segunda")
        self.create("v2")
        self.snapshot("v2").write_bytes(b"corrupto")
        self.command("verify", id="v2", ok=False)
        dest = self.base / "vacío preservado"
        dest.mkdir()
        initial = dest.stat().st_ino
        self.restore("v2", dest=dest, ok=False)
        self.assertEqual(tree(dest), {})
        self.assertEqual(dest.stat().st_ino, initial)
        self.command("verify", id="v1")
        self.assertEqual(tree(self.restore()), first)

    def test_sigkill_create_can_retry_same_id(self):
        (self.source / "pequeño").write_bytes("versión anterior".encode("utf-8"))
        expected = tree(self.source)
        self.create("anterior")
        previous = self.snapshot("anterior").read_bytes()
        large = self.source / "grande"
        with large.open("wb") as output:
            output.truncate(256 * 1024 * 1024)
        process = subprocess.Popen(
            [sys.executable, str(SCRIPT), "create", "--source", str(self.source),
             "--repo", str(self.repo), "--id", "interrumpido"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                leftovers = list((self.repo / "staging").iterdir())
                if leftovers and any(path.stat().st_size > 65536 for path in leftovers):
                    process.send_signal(signal.SIGKILL)
                    break
                self.assertIsNone(process.poll(), "create terminó antes de poder interrumpirlo")
                time.sleep(0.001)
            else:
                self.fail("No se observó create escribiendo el archivo temporal")
            stdout, stderr = process.communicate(timeout=10)
            self.assertEqual(process.returncode, -signal.SIGKILL)
            self.assertEqual(stdout, b"")
            self.assertFalse(self.snapshot("interrumpido").exists())
            self.assertEqual(self.snapshot("anterior").read_bytes(), previous)
            self.assertEqual(self.command("list"), {"snapshots": ["anterior"]})
            self.assertEqual(tree(self.restore("anterior")), expected)
            # Repite con la misma fuente estable usada por el proceso interrumpido.
            self.create("interrumpido")
            self.command("verify", id="interrumpido")
            restored = self.restore("interrumpido")
            for original in self.source.iterdir():
                copy = restored / original.name
                self.assertEqual(copy.stat().st_size, original.stat().st_size)
                with original.open("rb") as first, copy.open("rb") as second:
                    self.assertEqual(hashlib.file_digest(first, "sha256").digest(),
                                     hashlib.file_digest(second, "sha256").digest())
            self.command("verify", id="anterior")
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate()

    def test_concurrent_creates_never_overwrite(self):
        self.seed()
        # Inicializa el repositorio antes de iniciar los dos procesos.
        self.create("inicial")
        argv = [sys.executable, str(SCRIPT), "create", "--source", str(self.source),
                "--repo", str(self.repo), "--id", "competido"]
        processes = [subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                     for _ in range(2)]
        results = [process.communicate(timeout=30) for process in processes]
        self.assertEqual(sorted(process.returncode for process in processes), [0, 1])
        for process, (stdout, stderr) in zip(processes, results):
            if process.returncode == 0:
                self.assertEqual(json.loads(stdout), {"id": "competido"})
            else:
                self.assertEqual(stdout, b"")
        self.command("verify", id="competido")
        self.assertEqual(tree(self.restore("competido")), tree(self.source))


if __name__ == "__main__":
    unittest.main(verbosity=2)
