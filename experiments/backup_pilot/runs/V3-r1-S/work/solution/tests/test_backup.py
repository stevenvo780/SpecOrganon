"""Pruebas de contrato vía CLI; fixtures privadas, sin paquetes externos."""

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


BASE = Path(__file__).resolve().parents[1]
BACKUP = BASE / "backup.py"
RESULTS = BASE / "results"
RESULTS.mkdir(exist_ok=True)
TRACE = RESULTS / "test-commands.jsonl"


def record(command, result):
    with TRACE.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"command": command, "returncode": result.returncode,
                                 "stdout": result.stdout, "stderr": result.stderr},
                                ensure_ascii=True) + "\n")


def regular_bytes(root):
    """Conteo independiente basado exclusivamente en lstat/st_size."""
    total = 0
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            info = os.lstat(Path(directory) / name)
            if stat.S_ISREG(info.st_mode):
                total += info.st_size
    return total


def tree(root):
    """Modelo independiente: directorios y hash/tamaño de cada archivo."""
    result = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            info = path.lstat()
            if stat.S_ISDIR(info.st_mode):
                result[relative] = ("dir",)
            elif stat.S_ISREG(info.st_mode):
                result[relative] = ("file", info.st_size,
                                    hashlib.sha256(path.read_bytes()).hexdigest())
            elif stat.S_ISLNK(info.st_mode):
                result[relative] = ("link", os.readlink(path))
            else:
                result[relative] = ("special", stat.S_IFMT(info.st_mode))
    return result


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="case-", dir=RESULTS)
        self.root = Path(self.temporary.name)
        self.source = self.root / "fuente con espacios"
        self.source.mkdir()
        self.repo = self.root / "repo"

    def tearDown(self):
        self.temporary.cleanup()

    def cli(self, *args, good=True):
        command = [sys.executable, str(BACKUP), *map(str, args)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=20)
        record(command, result)
        if good:
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            value = json.loads(result.stdout)
            self.assertIs(type(value), dict)
            self.assertEqual(len(result.stdout.splitlines()), 1)
            return value
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.stdout, "", "Un fallo no debe afirmar éxito")
        return result

    def create(self, sid="one", limit=None, repo=None, good=True):
        args = ["create", "--source", self.source, "--repo", repo or self.repo,
                "--id", sid]
        if limit is not None:
            args += ["--max-bytes", limit]
        return self.cli(*args, good=good)

    def verify(self, sid="one", repo=None, good=True):
        return self.cli("verify", "--repo", repo or self.repo, "--id", sid, good=good)

    def restore(self, dest, sid="one", repo=None, good=True):
        return self.cli("restore", "--repo", repo or self.repo, "--id", sid,
                        "--dest", dest, good=good)

    def listed(self, repo=None, good=True):
        return self.cli("list", "--repo", repo or self.repo, good=good)

    def fixture(self):
        (self.source / "vacío ñ" / "más vacío").mkdir(parents=True)
        (self.source / "contenido 空").mkdir()
        (self.source / "contenido 空" / "datos.bin").write_bytes(bytes(range(256)) * 7)
        (self.source / "vacío.txt").write_bytes(b"")
        (self.source / "líneas y espacios.txt").write_bytes(b"\x00\xff\r\nbackup\n")
        (self.source / "back\\slash").write_bytes(b"nombre POSIX literal")

    def test_01_cli_roundtrip_versions_and_self_contained(self):
        """C01,C02,C03,C11: bytes, Unicode, vacíos y versiones sin fuente."""
        self.assertEqual(self.listed(), {"snapshots": []})
        self.fixture()
        first = tree(self.source)
        self.assertEqual(self.create("z-first"), {"id": "z-first"})
        self.assertEqual(tree(self.source), first)
        (self.source / "líneas y espacios.txt").unlink()
        (self.source / "contenido 空" / "datos.bin").write_bytes(b"segunda\x00\xff")
        (self.source / "nuevo").write_bytes(b"added")
        second = tree(self.source)
        self.assertEqual(self.create("a-second", 100_000), {"id": "a-second"})
        self.assertEqual(tree(self.source), second)
        shutil.rmtree(self.source)
        self.assertEqual(self.listed(), {"snapshots": ["a-second", "z-first"]})
        for sid, expected in (("z-first", first), ("a-second", second)):
            self.assertEqual(self.verify(sid), {"id": sid, "valid": True})
            dest = self.root / sid
            self.assertEqual(self.restore(dest, sid), {"id": sid})
            self.assertEqual(tree(dest), expected)

    def test_02_empty_source_and_empty_existing_destination(self):
        """C02,C03,C07: también árboles totalmente vacíos."""
        self.create(limit=100_000)
        dest = self.root / "empty"
        dest.mkdir()
        self.restore(dest)
        self.assertEqual(tree(dest), {})
        self.verify()

    def test_03_ids_duplicate_missing_and_invalid_arguments(self):
        """C01,C04,C11,C13: errores y fronteras de IDs y N."""
        self.fixture()
        self.create()
        previous = tree(self.repo)
        self.create(good=False)
        self.assertEqual(tree(self.repo), previous)
        self.verify("missing", good=False)
        self.restore(self.root / "missing-dest", "missing", good=False)
        self.assertFalse((self.root / "missing-dest").exists())
        for sid in ("", ".", "..", "_bad", "-bad", "a/b", "á", "a\n", "a" * 65):
            with self.subTest(sid=sid):
                self.create(sid, good=False)
                self.verify(sid, good=False)
                self.restore(self.root / "invalid", sid, good=False)
                self.assertEqual(tree(self.repo), previous)
        for limit in ("-1", "1.5", "no", "", "+1", "１２"):
            with self.subTest(limit=limit):
                self.create("invalid-budget", limit, good=False)
                self.assertEqual(tree(self.repo), previous)
        self.create("A" * 64, "000100000")
        self.verify("A" * 64)
        self.cli("create", "--repo", self.repo, "--id", "absent-source", good=False)
        self.cli("other-command", good=False)

    def test_04_overlap_rejection_without_source_mutation(self):
        """C06,C11: igualdad y ambas direcciones de solapamiento."""
        self.fixture()
        previous = tree(self.source)
        for repo in (self.source, self.source / "new-repo", self.root):
            with self.subTest(repo=repo):
                self.create(repo=repo, good=False)
                self.assertEqual(tree(self.source), previous)
        self.create()
        previous_repo = tree(self.repo)
        self.restore(self.repo / "dest", good=False)
        self.restore(self.root, good=False)
        self.assertEqual(tree(self.repo), previous_repo)

    def test_05_nonempty_destination_is_preserved(self):
        """C07: rechazo conserva bytes y directorios protegidos."""
        self.fixture()
        self.create()
        dest = self.root / "protected"
        dest.mkdir()
        (dest / "sentinel").write_bytes(bytes(range(256)))
        (dest / "empty-subdir").mkdir()
        before = tree(dest)
        self.restore(dest, good=False)
        self.assertEqual(tree(dest), before)

    def test_06_symlinks_source_repo_dest_and_ancestors(self):
        """C05: raíz, ancestro, descendiente, enlace colgante y '..'."""
        self.fixture()
        protected = self.root / "protected"
        protected.mkdir()
        (protected / "sentinel").write_bytes(b"never change")
        before = tree(protected)
        for target in (protected / "sentinel", self.root / "does-not-exist"):
            link = self.source / "link"
            link.symlink_to(target)
            self.create(good=False)
            link.unlink()
        source_link = self.root / "source-link"
        source_link.symlink_to(self.source, target_is_directory=True)
        self.cli("create", "--source", source_link, "--repo", self.repo,
                 "--id", "one", good=False)
        # No normalizar a/../source antes de rechazar a cuando es un enlace.
        self.cli("create", "--source", str(source_link) + "/../" + self.source.name,
                 "--repo", self.repo, "--id", "one", good=False)
        repo_link = self.root / "repo-link"
        repo_link.symlink_to(protected, target_is_directory=True)
        for path in (repo_link, repo_link / "child"):
            self.create(repo=path, good=False)
            self.listed(repo=path, good=False)
        self.create()
        dest_link = self.root / "dest-link"
        dest_link.symlink_to(protected, target_is_directory=True)
        for path in (dest_link, dest_link / "child",
                     str(dest_link) + "/../protected"):
            self.restore(path, good=False)
        for subdir in (self.repo, self.repo / "snapshots" / "one" / "data"):
            link = subdir / "unsafe-link"
            link.symlink_to(protected / "sentinel")
            self.verify(good=False)
            self.listed(good=False)
            self.create("two", 100_000, good=False)
            self.restore(self.root / "must-not-exist", good=False)
            link.unlink()
        self.assertEqual(tree(protected), before)
        self.verify()

    def test_07_special_files_rejected_without_blocking(self):
        """C05: FIFO y socket en cada tipo de ruta gestionada."""
        self.fixture()
        fifo = self.source / "fifo"
        os.mkfifo(fifo)
        self.create(good=False)
        fifo.unlink()
        sock_path = self.source / "socket"
        with socket.socket(socket.AF_UNIX) as sock:
            sock.bind(str(sock_path))
            self.create(good=False)
        sock_path.unlink()
        self.create()
        for path in (self.repo / "fifo", self.repo / "snapshots" / "one" / "data" / "fifo"):
            os.mkfifo(path)
            self.verify(good=False)
            self.listed(good=False)
            self.restore(self.root / "absent", good=False)
            self.create("two", 100_000, good=False)
            path.unlink()
        dest = self.root / "dest-fifo"
        os.mkfifo(dest)
        self.restore(dest, good=False)
        self.assertTrue(stat.S_ISFIFO(dest.lstat().st_mode))
        fifo_repo = self.root / "fifo-repo"
        fifo_repo.mkdir()
        os.mkfifo(fifo_repo / ".lock")
        self.create(repo=fifo_repo, good=False)
        self.verify()

    def test_08_every_regular_snapshot_file_corrupted_or_deleted(self):
        """C08,C09: mutación, truncamiento y eliminación de datos y metadata."""
        self.fixture()
        self.create()
        pristine = self.root / "pristine"
        shutil.copytree(self.repo, pristine)
        regulars = [p.relative_to(self.repo) for p in
                    (self.repo / "snapshots" / "one").rglob("*") if p.is_file()]
        self.assertGreaterEqual(len(regulars), 3)
        empty = self.root / "empty-dest"
        empty.mkdir()
        protected = self.root / "protected"
        protected.mkdir()
        (protected / "sentinel").write_bytes(b"safe\x00\xff")
        before = tree(protected)
        for relative in regulars:
            for mutation in ("alter", "truncate", "delete"):
                with self.subTest(file=str(relative), mutation=mutation):
                    shutil.rmtree(self.repo)
                    shutil.copytree(pristine, self.repo)
                    target = self.repo / relative
                    data = target.read_bytes()
                    if mutation == "alter":
                        target.write_bytes(bytes([data[0] ^ 1]) + data[1:] if data else b"x")
                    elif mutation == "truncate":
                        target.write_bytes(data[:len(data) // 2] if data else b"x")
                    else:
                        target.unlink()
                    self.verify(good=False)
                    self.restore(self.root / "absent", good=False)
                    self.assertFalse((self.root / "absent").exists())
                    self.restore(empty, good=False)
                    self.assertEqual(tree(empty), {})
                    self.restore(protected, good=False)
                    self.assertEqual(tree(protected), before)
                    self.assertEqual(self.listed(), {"snapshots": []})

    def test_09_incomplete_structure_and_invalid_manifest(self):
        """C08,C09: no aceptar estructura extra ni rutas inválidas aun con sello."""
        self.fixture()
        self.create()
        snap = self.repo / "snapshots" / "one"
        extra = snap / "extra"
        extra.write_bytes(b"unexpected")
        self.verify(good=False)
        self.assertEqual(self.listed(), {"snapshots": []})
        extra.unlink()
        manifest_path = snap / "manifest.json"
        original = json.loads(manifest_path.read_text())
        invalid = []
        for path in ("../escape", "/absolute", "x/../escape", "missing-parent/file"):
            value = json.loads(json.dumps(original))
            value["files"][0]["path"] = path
            invalid.append(value)
        value = json.loads(json.dumps(original))
        value["id"] = "wrong-id"
        invalid.append(value)
        for value in invalid:
            with self.subTest(value=value):
                content = json.dumps(value).encode()
                manifest_path.write_bytes(content)
                (snap / "manifest.sha256").write_text(hashlib.sha256(content).hexdigest() + "\n")
                self.verify(good=False)
                self.restore(self.root / "absent", good=False)
                self.assertFalse((self.root / "absent").exists())
                self.assertFalse((self.root / "escape").exists())

    def test_10_high_and_exact_limits_include_all_metadata(self):
        """C13,C14: límite alto, luego exacto medido sin usar funciones del producto."""
        self.fixture()
        original = tree(self.source)
        sizing = self.root / "sizing"
        self.create("one", repo=sizing)
        needed = regular_bytes(sizing)
        payload = regular_bytes(self.source)
        self.assertGreater(needed, payload)
        self.assertEqual(self.create("one", needed), {"id": "one"})
        self.assertEqual(regular_bytes(self.repo), needed)
        self.verify()
        (self.source / "new").write_bytes(b"second snapshot")
        self.create("two", repo=sizing)
        total = regular_bytes(sizing)
        previous = tree(self.repo / "snapshots" / "one")
        self.create("two", total)
        self.assertEqual(regular_bytes(self.repo), total)
        self.assertEqual(tree(self.repo / "snapshots" / "one"), previous)
        self.verify("one")
        self.verify("two")
        dest = self.root / "restored-one"
        self.restore(dest)
        self.assertEqual(tree(dest), original)

    def test_11_insufficient_limits_leave_no_regular_residue(self):
        """C14,C15: falta de espacio para datos, manifiesto o checksum."""
        self.fixture()
        before = tree(self.source)
        sizing = self.root / "sizing"
        self.create(repo=sizing)
        needed = regular_bytes(sizing)
        self.listed()
        pristine = tree(self.repo)
        for limit in (0, 1, regular_bytes(self.source), needed - 1):
            with self.subTest(limit=limit):
                self.create(limit=limit, good=False)
                self.assertEqual(tree(self.repo), pristine)
                self.assertEqual(regular_bytes(self.repo), 0)
                self.assertEqual(list((self.repo / ".staging").iterdir()), [])
                self.assertEqual(self.listed(), {"snapshots": []})
                self.assertEqual(tree(self.source), before)
        self.create(limit=needed)
        self.verify()

    def test_12_below_existing_limit_preserves_bytes_including_lock(self):
        """C14,C15: contar metadata no perteneciente al snapshot y preservar previos."""
        self.fixture()
        self.create()
        (self.repo / ".lock").write_bytes(b"persistent metadata counted too")
        before = tree(self.repo)
        existing = regular_bytes(self.repo)
        for limit in (0, existing - 1, existing):
            with self.subTest(limit=limit):
                self.create("new", limit, good=False)
                self.assertEqual(regular_bytes(self.repo), existing)
                self.assertEqual(tree(self.repo), before)
                self.verify()
        sizing = self.root / "sizing"
        self.create("new", repo=sizing)
        self.create("new", existing + regular_bytes(sizing))
        self.assertEqual(regular_bytes(self.repo), existing + regular_bytes(sizing))

    def test_13_partial_copy_budget_failure_preserves_old_and_retries(self):
        """C11,C15: fallar después de copiar datos y repetir el mismo ID."""
        (self.source / "a").write_bytes(b"old")
        self.create("old")
        old = tree(self.repo)
        occupied = regular_bytes(self.repo)
        (self.source / "a").write_bytes(b"small")
        (self.source / "z").write_bytes(b"x" * (2 * 1024 * 1024))
        source = tree(self.source)
        self.create("new", occupied + 100, good=False)
        self.assertEqual(tree(self.repo), old)
        self.assertEqual(tree(self.source), source)
        self.create("new", occupied + 3 * 1024 * 1024)
        self.verify("old")
        self.verify("new")

    def kill_create(self, phase, sid):
        """Barrera solo en el proceso de prueba; SIGKILL real, sin hooks en backup.py."""
        marker = self.root / ("barrier-" + phase)
        # La primera barrera ocurre en el fsync del primer blob real; la otra
        # después de validar todo, inmediatamente antes del rename de publicación.
        code = r'''
import importlib.util, os, pathlib, signal, stat, sys
spec = importlib.util.spec_from_file_location("backup", sys.argv[1])
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)
phase, marker = sys.argv[2:4]
def barrier():
    pathlib.Path(marker).write_text("ready")
    os.kill(os.getpid(), signal.SIGSTOP)
if phase == "copy":
    original = backup.os.fsync
    def paused(fd):
        if stat.S_ISREG(os.fstat(fd).st_mode):
            barrier()
        return original(fd)
    backup.os.fsync = paused
else:
    original = backup.os.rename
    def paused(*args, **kwargs):
        barrier()
        return original(*args, **kwargs)
    backup.os.rename = paused
sys.exit(backup.main(sys.argv[4:]))
'''
        command = [sys.executable, "-c", code, str(BACKUP), phase, str(marker),
                   "create", "--source", str(self.source), "--repo", str(self.repo),
                   "--id", sid, "--max-bytes", "10000000"]
        process = subprocess.Popen(command, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 10
            while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.005)
            self.assertTrue(marker.exists(), "No se alcanzó la barrera de interrupción")
            self.assertIsNone(process.poll())
            process.kill()
            stdout, stderr = process.communicate(timeout=10)
            record(command, subprocess.CompletedProcess(command, process.returncode,
                                                        stdout, stderr))
            self.assertEqual(process.returncode, -signal.SIGKILL)
            self.assertEqual(stdout, "")
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=10)

    def test_14_sigkill_copy_and_prepublication_recover_with_exact_budget(self):
        """C10,C11,C14,C16: staging ignorado y mismo ID recuperable con N exacto."""
        self.fixture()
        self.create("old")
        previous = tree(self.repo / "snapshots" / "old")
        sizing = self.root / "sizing"
        self.create("old", repo=sizing)
        for phase, sid in (("copy", "new-copy"), ("publish", "new-publish")):
            with self.subTest(phase=phase):
                self.create(sid, repo=sizing)
                exact = regular_bytes(sizing)
                self.kill_create(phase, sid)
                self.assertGreater(regular_bytes(self.repo / ".staging"), 0)
                self.assertFalse((self.repo / "snapshots" / sid).exists())
                self.assertNotIn(sid, self.listed()["snapshots"])
                self.verify("old")
                self.create(sid, exact)
                self.assertEqual(regular_bytes(self.repo), exact)
                self.assertEqual(list((self.repo / ".staging").iterdir()), [])
                self.assertEqual(tree(self.repo / "snapshots" / "old"), previous)
                self.verify(sid)
                dest = self.root / (sid + "-dest")
                self.restore(dest, sid)
                self.assertEqual(tree(dest), tree(self.source))

    def test_15_sigkill_then_too_low_cleans_only_orphans(self):
        """C10,C15,C16: límite bajo tras interrupción no deja crecimiento permanente."""
        self.fixture()
        self.create("old")
        before = tree(self.repo)
        occupied = regular_bytes(self.repo)
        self.kill_create("publish", "new")
        self.create("new", occupied - 1, good=False)
        self.assertEqual(regular_bytes(self.repo), occupied)
        self.assertEqual(tree(self.repo), before)
        self.verify("old")
        self.assertEqual(self.listed(), {"snapshots": ["old"]})

    def test_16_concurrent_creates_share_budget_and_do_not_overwrite(self):
        """C04,C14,C16: exactamente uno cabe; ID repetido no se sobrescribe."""
        self.fixture()
        sizing = self.root / "sizing"
        self.create("aa", repo=sizing)
        limit = regular_bytes(sizing)
        commands = [[sys.executable, str(BACKUP), "create", "--source", str(self.source),
                     "--repo", str(self.repo), "--id", sid, "--max-bytes", str(limit)]
                    for sid in ("aa", "bb")]
        processes = [subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                      text=True) for command in commands]
        codes = []
        for command, process in zip(commands, processes):
            stdout, stderr = process.communicate(timeout=20)
            record(command, subprocess.CompletedProcess(command, process.returncode, stdout, stderr))
            codes.append(process.returncode)
            if process.returncode:
                self.assertEqual(stdout, "")
        self.assertEqual(sorted(codes), [0, 1])
        self.assertLessEqual(regular_bytes(self.repo), limit)
        ids = self.listed()["snapshots"]
        self.assertEqual(len(ids), 1)
        self.verify(ids[0])
        # El presupuesto ya está ocupado; quitarlo permite probar ID duplicado
        # concurrente, manteniendo la garantía de exclusión por sí misma.
        commands = [[sys.executable, str(BACKUP), "create", "--source", str(self.source),
                     "--repo", str(self.repo), "--id", "same"] for _ in range(2)]
        processes = [subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                      text=True) for command in commands]
        codes = []
        for command, process in zip(commands, processes):
            stdout, stderr = process.communicate(timeout=20)
            record(command, subprocess.CompletedProcess(command, process.returncode, stdout, stderr))
            codes.append(process.returncode)
        self.assertEqual(sorted(codes), [0, 1])
        self.verify("same")

    def test_17_regular_snapshot_replacement_is_invalid(self):
        """C08: reemplazar el directorio del snapshot por un regular no lo completa."""
        self.create()
        snapshot = self.repo / "snapshots" / "one"
        shutil.rmtree(snapshot)
        snapshot.write_bytes(b"not a snapshot")
        self.verify(good=False)
        self.restore(self.root / "absent", good=False)
        self.assertEqual(self.listed(), {"snapshots": []})

    def test_18_empty_tree_still_needs_persistent_metadata_budget(self):
        """C14,C15: ni siquiera fuente vacía elude el presupuesto de metadata."""
        sizing = self.root / "sizing"
        self.create(repo=sizing)
        needed = regular_bytes(sizing)
        self.assertGreater(needed, 0)
        self.create(limit=0, good=False)
        self.assertEqual(regular_bytes(self.repo), 0)
        self.create(limit=needed - 1, good=False)
        self.assertEqual(regular_bytes(self.repo), 0)
        self.create(limit=needed)
        self.assertEqual(regular_bytes(self.repo), needed)
        self.verify()


if __name__ == "__main__":
    unittest.main(verbosity=2)
