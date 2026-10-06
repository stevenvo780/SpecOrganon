#!/usr/bin/env python3
"""Pruebas de integración reales de la CLI; todos los fixtures viven en /trial."""

import hashlib
import errno
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


HERE = Path(__file__).resolve().parent
PROGRAM = HERE / "backup.py"
TRACE = None


def tree(root):
    result = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            result[relative] = ("dir",)
        else:
            result[relative] = ("file", path.read_bytes())
    return result


def trace_command(args, result):
    TRACE.write("$ " + shlex.join(args) + "\n")
    TRACE.write(f"exit={result.returncode}\n")
    TRACE.write("stdout=" + repr(result.stdout) + "\n")
    TRACE.write("stderr=" + repr(result.stderr) + "\n\n")
    TRACE.flush()


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix=".tests-", dir=HERE)
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.source = self.base / "source"
        self.repo = self.base / "repo"
        self.source.mkdir()
        self.repo.mkdir()

    def cli(self, command, *, ok=True, repo=None, **options):
        args = [sys.executable, str(PROGRAM), command, "--repo", str(repo or self.repo)]
        for key, value in options.items():
            args.extend(["--" + key, str(value)])
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
        trace_command(args, result)
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            # Una sola línea, un solo objeto; ningún diagnóstico en stdout.
            self.assertEqual(len(result.stdout.splitlines()), 1)
            decoded = json.loads(result.stdout)
            self.assertIsInstance(decoded, dict)
            return decoded
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.stdout, "")
        self.assertIn("error", json.loads(result.stderr))
        return result

    def create(self, snapshot_id="v1", **kwargs):
        return self.cli("create", source=self.source, id=snapshot_id, **kwargs)

    def test_v2_versions_exactas_y_autosuficientes(self):
        (self.source / "vacío Ω").mkdir()
        (self.source / "carpeta con espacios").mkdir()
        (self.source / "carpeta con espacios" / "niño.txt").write_bytes(b"primera\x00\xff")
        (self.source / "todo.bin").write_bytes(bytes(range(256)) * 257)
        (self.source / "borrar.txt").write_bytes(b"desaparece")
        (self.source / "archivo a directorio").write_bytes(b"v1")
        (self.source / "directorio a archivo").mkdir()
        (self.source / "directorio a archivo" / "hijo").write_bytes(b"hijo")
        (self.source / "cero").write_bytes(b"")
        # En POSIX, estos nombres deben tratarse como componentes normales.
        (self.source / "barra\\invertida").write_bytes(b"nombre")
        (self.source / "salto\nde linea").write_bytes(b"nombre")
        versions = {"z_version1": tree(self.source)}
        self.assertEqual(self.create("z_version1"), {"id": "z_version1"})
        self.assertEqual(tree(self.source), versions["z_version1"])

        (self.source / "borrar.txt").unlink()
        (self.source / "carpeta con espacios" / "niño.txt").write_bytes(b"segunda")
        (self.source / "añadido.txt").write_bytes(b"nuevo")
        (self.source / "archivo a directorio").unlink()
        (self.source / "archivo a directorio").mkdir()
        (self.source / "archivo a directorio" / "nuevo").write_bytes(b"nuevo")
        shutil.rmtree(self.source / "directorio a archivo")
        (self.source / "directorio a archivo").write_bytes(b"ahora archivo")
        versions["a_version2"] = tree(self.source)
        self.create("a_version2")
        self.assertEqual(tree(self.source), versions["a_version2"])

        shutil.rmtree(self.source)
        self.source.mkdir()
        versions["m_vacia3"] = {}
        self.create("m_vacia3")
        self.assertEqual(self.cli("list"), {"snapshots": sorted(versions)})
        shutil.rmtree(self.source)  # restore no puede depender de la fuente.
        for i, (snapshot_id, expected) in enumerate(versions.items()):
            self.assertEqual(self.cli("verify", id=snapshot_id), {"id": snapshot_id, "valid": True})
            dest = self.base / "restauraciones" / snapshot_id
            if i == 0:
                dest.mkdir(parents=True)  # directorio ya existente y vacío.
            self.assertEqual(self.cli("restore", id=snapshot_id, dest=dest), {"id": snapshot_id})
            self.assertEqual(tree(dest), expected)

    def test_repositorio_nuevo_ids_y_errores_cli(self):
        self.assertEqual(self.cli("list"), {"snapshots": []})
        self.assertEqual(self.cli("list", repo=self.base / "no-existe"), {"snapshots": []})
        for snapshot_id in ("missing", "inexistente"):
            self.cli("verify", id=snapshot_id, ok=False)
            dest = self.base / "dest"
            self.cli("restore", id=snapshot_id, dest=dest, ok=False)
            self.assertFalse(dest.exists())
        for snapshot_id in ("", "../x", ".x", "_x", "-x", "ñ", "a/b", "a" * 65, "x\n"):
            with self.subTest(id=snapshot_id):
                self.create(snapshot_id, ok=False)
                self.cli("verify", id=snapshot_id, ok=False)
                self.cli("restore", id=snapshot_id, dest=self.base / "d", ok=False)
        for snapshot_id in ("A", "0_az-Z", "a" * 64):
            self.create(snapshot_id)
        self.assertEqual(self.cli("list"), {"snapshots": ["0_az-Z", "A", "a" * 64]})
        args = [sys.executable, str(PROGRAM), "create", "--repo", str(self.repo)]
        result = subprocess.run(args, capture_output=True, text=True)
        trace_command(args, result)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_id_existente_y_destino_protegido(self):
        (self.source / "a").write_bytes(b"primero")
        self.create()
        snapshot_before = tree(self.repo / "snapshots" / "v1")
        (self.source / "a").write_bytes(b"segundo")
        self.create(ok=False)
        self.assertEqual(tree(self.repo / "snapshots" / "v1"), snapshot_before)
        dest = self.base / "protegido"
        dest.mkdir()
        (dest / "bytes").write_bytes(bytes(range(256)))
        (dest / "vacio").mkdir()
        before = tree(dest)
        self.cli("restore", id="v1", dest=dest, ok=False)
        self.assertEqual(tree(dest), before)
        empty_subdir_only = self.base / "tambien-no-vacio"
        (empty_subdir_only / "vacio").mkdir(parents=True)
        self.cli("restore", id="v1", dest=empty_subdir_only, ok=False)
        self.assertEqual(tree(empty_subdir_only), {"vacio": ("dir",)})
        regular_dest = self.base / "archivo"
        regular_dest.write_bytes(b"no tocar")
        self.cli("restore", id="v1", dest=regular_dest, ok=False)
        self.assertEqual(regular_dest.read_bytes(), b"no tocar")

    def test_solapamientos(self):
        (self.source / "a").write_bytes(b"contenido")
        before = tree(self.source)
        self.create(repo=self.source, ok=False)
        self.create(repo=self.source / "repositorio", ok=False)
        self.assertEqual(tree(self.source), before)
        inside = self.repo / "source"
        inside.mkdir()
        self.cli("create", source=inside, id="x", ok=False)
        inside.rmdir()
        self.create()
        before_repo = tree(self.repo)
        self.cli("restore", id="v1", dest=self.repo / "d", ok=False)
        self.cli("restore", id="v1", dest=self.base, ok=False)
        self.assertEqual(tree(self.repo), before_repo)

    def test_symlinks_en_fuente_raices_ancestros_y_destino(self):
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "secreto-de-prueba").write_bytes(b"fixture publico")
        for target in (outside / "secreto-de-prueba", outside, self.base / "ausente"):
            link = self.source / "enlace"
            link.symlink_to(target)
            self.create(ok=False)
            link.unlink()
        root_link = self.base / "fuente-enlace"
        root_link.symlink_to(self.source)
        self.cli("create", source=root_link, id="x", ok=False)
        ancestor = self.base / "padre-enlace"
        ancestor.symlink_to(outside)
        self.cli("create", source=ancestor, repo=self.repo, id="x", ok=False)
        self.cli("list", repo=ancestor / "repositorio-ausente", ok=False)
        repo_link = self.base / "repo-enlace"
        repo_link.symlink_to(self.repo)
        self.cli("list", repo=repo_link, ok=False)
        self.create()
        dest_link = self.base / "dest-enlace"
        dest_link.symlink_to(outside)
        self.cli("restore", id="v1", dest=dest_link, ok=False)
        self.cli("restore", id="v1", dest=ancestor / "dest-ausente", ok=False)
        protected = self.base / "dest"
        protected.mkdir()
        (protected / "enlace").symlink_to(outside)
        self.cli("restore", id="v1", dest=protected, ok=False)
        self.assertTrue((protected / "enlace").is_symlink())
        self.assertEqual((outside / "secreto-de-prueba").read_bytes(), b"fixture publico")
        self.assertFalse((outside / "dest-ausente").exists())

    def test_symlinks_en_repositorio_y_snapshot(self):
        (self.source / "a").write_bytes(b"original")
        self.create()
        outside = self.base / "otro"
        outside.write_bytes(b"bytes externos")
        for relative in ("enlace", ".staging/enlace", "snapshots/v1/data/enlace"):
            link = self.repo / relative
            link.symlink_to(outside)
            for command in ("list", "verify", "create", "restore"):
                kwargs = {}
                if command != "list":
                    kwargs["id"] = "x" if command == "create" else "v1"
                if command == "create":
                    kwargs["source"] = self.source
                if command == "restore":
                    kwargs["dest"] = self.base / "d"
                self.cli(command, ok=False, **kwargs)
            link.unlink()
        for relative in ("manifest.json", "manifest.sha256", "data/a"):
            path = self.repo / "snapshots" / "v1" / relative
            original = path.read_bytes()
            path.unlink()
            path.symlink_to(outside)
            self.cli("verify", id="v1", ok=False)
            self.cli("restore", id="v1", dest=self.base / "d", ok=False)
            path.unlink()
            path.write_bytes(original)
        self.assertEqual(outside.read_bytes(), b"bytes externos")
        self.cli("verify", id="v1")

    def test_archivos_especiales_sin_bloquear(self):
        fifo = self.source / "fifo"
        os.mkfifo(fifo)
        self.create(ok=False)
        fifo.unlink()
        self.create()
        for relative in ("fifo", "snapshots/v1/data/fifo", ".staging/fifo"):
            special = self.repo / relative
            os.mkfifo(special)
            self.cli("verify", id="v1", ok=False)
            self.cli("list", ok=False)
            self.cli("restore", id="v1", dest=self.base / "d", ok=False)
            special.unlink()
        dest = self.base / "dest"
        dest.mkdir()
        os.mkfifo(dest / "fifo")
        self.cli("restore", id="v1", dest=dest, ok=False)
        self.assertTrue((dest / "fifo").exists())

    def test_socket_en_fuente(self):
        sock = socket.socket(socket.AF_UNIX)
        path = self.source / "socket"
        try:
            try:
                sock.bind(str(path))
            except OSError as exc:
                if exc.errno in (errno.EPERM, errno.EACCES):
                    self.skipTest("El contenedor prohíbe bind de sockets Unix (EPERM/EACCES)")
                raise
            self.create(ok=False)
        finally:
            sock.close()
            path.unlink(missing_ok=True)

    def test_corrupcion_de_cada_archivo_del_snapshot(self):
        (self.source / "a").write_bytes(b"ABC\x00\xff")
        (self.source / "empty").write_bytes(b"")
        (self.source / "dir").mkdir()
        self.create("buena")
        self.create("corruptible")
        snapshot = self.repo / "snapshots" / "corruptible"
        originals = {p: p.read_bytes() for p in snapshot.rglob("*") if p.is_file()}
        for path, original in originals.items():
            for alteration in ("flip", "truncate", "delete"):
                with self.subTest(path=path.name, alteration=alteration):
                    if alteration == "flip":
                        changed = bytes([original[0] ^ 1]) + original[1:] if original else b"x"
                        path.write_bytes(changed)
                    elif alteration == "truncate":
                        path.write_bytes(original[:-1] if original else b"x")
                    else:
                        path.unlink()
                    self.cli("verify", id="corruptible", ok=False)
                    self.cli("verify", id="buena")
                    missing_dest = self.base / "ausente"
                    self.cli("restore", id="corruptible", dest=missing_dest, ok=False)
                    self.assertFalse(missing_dest.exists())
                    empty_dest = self.base / "vacio"
                    empty_dest.mkdir(exist_ok=True)
                    self.cli("restore", id="corruptible", dest=empty_dest, ok=False)
                    self.assertEqual(tree(empty_dest), {})
                    self.assertEqual(self.cli("list"), {"snapshots": ["buena"]})
                    path.write_bytes(original)
                    self.cli("verify", id="corruptible")
        extra = snapshot / "data" / "extra"
        extra.write_bytes(b"bytes no inventariados")
        self.cli("verify", id="corruptible", ok=False)
        extra.unlink()
        (snapshot / "data" / "dir").rmdir()
        self.cli("verify", id="corruptible", ok=False)
        (snapshot / "data" / "dir").mkdir()
        extra = snapshot / "extra"
        extra.write_bytes(b"extra")
        self.cli("verify", id="corruptible", ok=False)
        extra.unlink()
        self.cli("verify", id="corruptible")

    def test_manifiestos_invalidos_aun_con_hash_recalculado(self):
        (self.source / "a").write_bytes(b"A")
        self.create()
        snapshot = self.repo / "snapshots" / "v1"
        path = snapshot / "manifest.json"
        original = path.read_bytes()
        seal_original = (snapshot / "manifest.sha256").read_bytes()
        manifests = []
        for invalid_path in ("../escape", "/absoluto", "a//b", "./a", "a/../b", "a\0b"):
            document = json.loads(original)
            document["entries"][0]["path"] = invalid_path
            manifests.append(document)
        document = json.loads(original)
        document["entries"].append(document["entries"][0].copy())
        manifests.append(document)
        document = json.loads(original)
        document["entries"][0]["size"] = True
        manifests.append(document)
        document = json.loads(original)
        document["id"] = "otra"
        manifests.append(document)
        for document in manifests:
            raw = (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")
            path.write_bytes(raw)
            (snapshot / "manifest.sha256").write_bytes(hashlib.sha256(raw).hexdigest().encode() + b"\n")
            self.cli("verify", id="v1", ok=False)
            self.cli("restore", id="v1", dest=self.base / "d", ok=False)
            self.assertFalse((self.base / "d").exists())
            self.assertFalse((self.base / "escape").exists())
        path.write_bytes(original)
        (snapshot / "manifest.sha256").write_bytes(seal_original)
        self.cli("verify", id="v1")

    def test_sigkill_create_y_reintento(self):
        (self.source / "pequeno").write_bytes(b"anterior intacto")
        self.create("anterior")
        before = tree(self.repo / "snapshots" / "anterior")
        # Archivo disperso: un create tarda lo suficiente para matar tras iniciar staging.
        with (self.source / "grande").open("wb") as stream:
            stream.truncate(128 * 1024 * 1024)
        args = [sys.executable, str(PROGRAM), "create", "--source", str(self.source),
                "--repo", str(self.repo), "--id", "interrumpida"]
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(lambda: process.kill() if process.poll() is None else None)
        deadline = time.monotonic() + 10
        observed_stage = False
        while time.monotonic() < deadline and process.poll() is None:
            if any((self.repo / ".staging").iterdir()):
                observed_stage = True
                process.kill()
                break
            time.sleep(0.001)
        stdout, stderr = process.communicate(timeout=10)
        trace_command(args, subprocess.CompletedProcess(args, process.returncode, stdout, stderr))
        TRACE.write("SIGKILL enviado al observar staging; reintento sin limpiar repositorio.\n\n")
        self.assertTrue(observed_stage, "No se observó la etapa temporal")
        self.assertEqual(process.returncode, -signal.SIGKILL)
        self.assertFalse((self.repo / "snapshots" / "interrumpida").exists())
        self.assertEqual(tree(self.repo / "snapshots" / "anterior"), before)
        self.assertEqual(self.cli("list"), {"snapshots": ["anterior"]})
        self.cli("verify", id="interrumpida", ok=False)
        self.create("interrumpida")
        self.cli("verify", id="interrumpida")
        self.cli("verify", id="anterior")
        self.assertEqual(self.cli("list"), {"snapshots": ["anterior", "interrumpida"]})
        self.assertEqual(tree(self.repo / "snapshots" / "anterior"), before)
        self.assertTrue(any((self.repo / ".staging").iterdir()), "Se conserva el resto incompleto")

    def test_concurrencia_mismo_id(self):
        (self.source / "a").write_bytes(b"bytes")
        args = [sys.executable, str(PROGRAM), "create", "--source", str(self.source),
                "--repo", str(self.repo), "--id", "unico"]
        processes = [subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                     for _ in range(2)]
        results = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=10)
            result = subprocess.CompletedProcess(args, process.returncode, stdout, stderr)
            trace_command(args, result)
            results.append(result)
        self.assertEqual(sorted(result.returncode for result in results), [0, 1])
        winner = next(result for result in results if result.returncode == 0)
        self.assertEqual(json.loads(winner.stdout), {"id": "unico"})
        self.cli("verify", id="unico")
        self.assertEqual(self.cli("list"), {"snapshots": ["unico"]})


if __name__ == "__main__":
    with (HERE / "cli-results.log").open("w", encoding="utf-8") as TRACE:
        TRACE.write("Python: " + sys.version + "\n")
        TRACE.write("Comando: " + shlex.join([sys.executable, str(Path(__file__).resolve())]) + "\n\n")
        unittest.main(verbosity=2)
