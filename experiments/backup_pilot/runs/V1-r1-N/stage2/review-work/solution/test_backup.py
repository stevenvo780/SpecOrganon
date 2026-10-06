"""Pruebas de caja negra; todos los datos temporales se crean en /trial."""

import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest


SCRIPT = Path(__file__).with_name("backup.py")
TRIAL = SCRIPT.parent.parent


def record(command, result):
    print("$ " + shlex.join(str(part) for part in command), flush=True)
    print(f"exit={result.returncode}", flush=True)
    print("stdout=" + repr(result.stdout), flush=True)
    print("stderr=" + repr(result.stderr), flush=True)


def inventory(root):
    entries = {}
    for parent, directories, files in os.walk(root):
        parent = Path(parent)
        for name in directories:
            entries[str((parent / name).relative_to(root))] = None
        for name in files:
            entries[str((parent / name).relative_to(root))] = (parent / name).read_bytes()
    return entries


def regular_bytes(root):
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="backup-tests-", dir=TRIAL)
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.source = self.base / "fuente con espacios"
        self.source.mkdir()
        self.repo = self.base / "repositorio"
        self.dest = self.base / "restaurado"
        self.identifier = "V1"

    def cli(self, operation, *, success=True, source=None, repo=None, identifier=None,
            dest=None, max_bytes=None):
        command = [sys.executable, str(SCRIPT), operation, "--repo", str(repo or self.repo)]
        if operation != "list":
            command += ["--id=" + (self.identifier if identifier is None else identifier)]
        if operation == "create":
            command += ["--source", str(source or self.source)]
            if max_bytes is not None:
                command += ["--max-bytes", str(max_bytes)]
        elif operation == "restore":
            command += ["--dest", str(dest or self.dest)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        record(command, result)
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            value = json.loads(result.stdout)
            self.assertIsInstance(value, dict)
            self.assertEqual(len(result.stdout.splitlines()), 1)
            expected = {"id": self.identifier if identifier is None else identifier}
            if operation == "verify":
                expected["valid"] = True
            if operation != "list":
                self.assertEqual(value, expected)
            return value
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("error", json.loads(result.stderr))
        return result

    def sample_source(self):
        (self.source / "vacío").mkdir()
        (self.source / "日本語 y español").mkdir()
        (self.source / "日本語 y español" / "vacío anidado").mkdir()
        (self.source / "todos los bytes.bin").write_bytes(bytes(range(256)) * 4097)
        (self.source / "日本語 y español" / "🚀 documento.txt").write_bytes("Hola\nñ 日本語 🚀\n".encode())
        (self.source / "cero bytes").touch()
        (self.source / "literal\\barra").write_bytes(b"backslash is a POSIX filename")

    @property
    def snapshot(self):
        return self.repo / "snapshots" / self.identifier

    def test_v1_round_trip_and_source_unchanged(self):
        self.sample_source()
        original = inventory(self.source)
        self.cli("create")
        self.assertEqual(inventory(self.source), original)
        self.cli("verify")
        self.cli("restore")
        self.assertEqual(inventory(self.dest), original)
        self.assertEqual(inventory(self.source), original)
        self.assertEqual(self.cli("list"), {"snapshots": ["V1"]})

    def test_empty_source_and_existing_empty_destination(self):
        self.dest.mkdir()
        self.cli("create")
        self.cli("verify")
        self.cli("restore")
        self.assertEqual(inventory(self.dest), {})

    def test_self_contained_after_source_deleted(self):
        self.sample_source()
        original = inventory(self.source)
        self.cli("create")
        shutil.rmtree(self.source)
        self.cli("verify")
        self.cli("restore", dest=self.base / "padres" / "nuevos" / "destino")
        self.assertEqual(inventory(self.base / "padres" / "nuevos" / "destino"), original)

    def test_multiple_versions_and_sorted_list(self):
        (self.source / "eliminado").write_bytes(b"old")
        (self.source / "editado").write_bytes(b"one")
        first = inventory(self.source)
        self.cli("create", identifier="zeta")
        (self.source / "eliminado").unlink()
        (self.source / "editado").write_bytes(b"two\0")
        (self.source / "añadido").write_bytes(b"new")
        (self.source / "directorio vacío").mkdir()
        second = inventory(self.source)
        self.cli("create", identifier="Alpha_2-3")
        self.assertEqual(self.cli("list"), {"snapshots": ["Alpha_2-3", "zeta"]})
        self.cli("restore", identifier="zeta", dest=self.base / "primero")
        self.cli("restore", identifier="Alpha_2-3", dest=self.base / "segundo")
        self.assertEqual(inventory(self.base / "primero"), first)
        self.assertEqual(inventory(self.base / "segundo"), second)

    def test_empty_repo_and_unknown_ids(self):
        self.repo.mkdir()
        self.assertEqual(self.cli("list"), {"snapshots": []})
        self.cli("verify", success=False)
        self.cli("restore", success=False)
        self.assertFalse(self.dest.exists())

    def test_missing_repository(self):
        for operation in ("list", "verify", "restore"):
            self.cli(operation, success=False)
        self.assertFalse(self.repo.exists())

    def test_usage_errors_never_report_success(self):
        for arguments in ([], ["create"], ["unknown"], ["list", "--repo", str(self.repo), "--unknown"]):
            command = [sys.executable, str(SCRIPT), *arguments]
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            record(command, result)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertTrue(result.stderr)

    def test_id_validation_and_maximum_length(self):
        self.cli("create", identifier="A" * 64)
        self.cli("verify", identifier="A" * 64)
        for identifier in ("", ".", "..", "a/b", "/absolute", "-bad", "_bad", "ñ", "a b", "A" * 65, "a\n"):
            for operation in ("create", "verify", "restore"):
                with self.subTest(identifier=identifier, operation=operation):
                    self.cli(operation, identifier=identifier, success=False)

    def test_duplicate_id_preserves_previous_snapshot(self):
        (self.source / "archivo").write_bytes(b"original")
        self.cli("create")
        original = inventory(self.repo)
        (self.source / "archivo").write_bytes(b"replacement")
        self.cli("create", success=False)
        self.assertEqual(inventory(self.repo), original)
        self.cli("verify")
        self.cli("restore")
        self.assertEqual((self.dest / "archivo").read_bytes(), b"original")

    def test_existing_incomplete_id_is_not_overwritten(self):
        self.repo.mkdir()
        (self.repo / "snapshots" / self.identifier).mkdir(parents=True)
        before = inventory(self.repo)
        self.cli("create", success=False)
        self.assertEqual(inventory(self.repo), before)
        self.assertEqual(self.cli("list"), {"snapshots": []})

    def test_nonempty_destination_preserved(self):
        self.sample_source()
        self.cli("create")
        self.dest.mkdir()
        (self.dest / "preservar").write_bytes(bytes(range(256)))
        (self.dest / "subdirectorio").mkdir()
        (self.dest / "subdirectorio" / "más").write_bytes(b"never change")
        before = inventory(self.dest)
        self.cli("restore", success=False)
        self.assertEqual(inventory(self.dest), before)

    def test_directory_only_destination_is_nonempty(self):
        self.cli("create")
        (self.dest / "empty").mkdir(parents=True)
        self.cli("restore", success=False)
        self.assertTrue((self.dest / "empty").is_dir())

    def test_overlapping_source_repository(self):
        self.cli("create", repo=self.source, success=False)
        self.cli("create", repo=self.source / "repo", success=False)
        self.repo.mkdir()
        inside = self.repo / "source"
        inside.mkdir()
        self.cli("create", source=inside, success=False)
        self.assertFalse((self.source / "repo").exists())
        self.assertEqual(inventory(self.repo), {"source": None})

    def test_destination_repository_overlap(self):
        self.cli("create")
        before = inventory(self.repo)
        self.cli("restore", dest=self.repo / "destination", success=False)
        self.assertEqual(inventory(self.repo), before)

    def test_source_symlinks_regular_directory_and_dangling(self):
        target = self.base / "target"
        target.write_bytes(b"outside")
        for link_target in (target, self.base, self.base / "missing"):
            with self.subTest(target=link_target):
                link = self.source / "link"
                link.symlink_to(link_target)
                self.cli("create", success=False)
                link.unlink()
        self.assertFalse(self.repo.exists())
        self.assertEqual(target.read_bytes(), b"outside")

    def test_symlink_in_path_ancestors_and_before_dotdot(self):
        link = self.base / "alias"
        link.symlink_to(self.source, target_is_directory=True)
        self.cli("create", source=link, success=False)
        self.cli("create", repo=link / "repo", success=False)
        # No normalizar '..' de forma que oculte el enlace de la entrada.
        raw = str(link) + "/../fuente con espacios"
        self.cli("create", source=raw, success=False)
        self.cli("create")
        repo_alias = self.base / "repo-alias"
        repo_alias.symlink_to(self.repo, target_is_directory=True)
        for operation in ("list", "verify", "restore"):
            self.cli(operation, repo=repo_alias, success=False)
        self.cli("restore", dest=link / "dest", success=False)

    def test_repo_and_snapshot_symlinks(self):
        self.sample_source()
        self.cli("create")
        external = self.base / "outside"
        external.write_bytes(b"outside")
        for link in (self.repo / "link", self.repo / ".staging" / "link", self.snapshot / "data" / "link"):
            with self.subTest(path=link):
                link.symlink_to(external)
                for operation in ("list", "verify", "restore", "create"):
                    self.cli(operation, success=False)
                link.unlink()
        data = self.snapshot / "data" / "0"
        original = data.read_bytes()
        data.unlink()
        data.symlink_to(external)
        self.cli("verify", success=False)
        self.cli("restore", success=False)
        data.unlink()
        data.write_bytes(original)
        self.cli("verify")
        self.assertEqual(external.read_bytes(), b"outside")

    def test_destination_symlinks(self):
        self.cli("create")
        external = self.base / "external"
        external.mkdir()
        self.dest.symlink_to(external, target_is_directory=True)
        self.cli("restore", success=False)
        self.assertEqual(inventory(external), {})
        self.dest.unlink()
        self.dest.symlink_to(self.base / "missing")
        self.cli("restore", success=False)
        self.assertFalse((self.base / "missing").exists())

    def test_special_files_rejected_without_hanging(self):
        fifo = self.source / "pipe"
        os.mkfifo(fifo)
        self.cli("create", success=False)
        fifo.unlink()
        self.cli("create")
        for path in (self.repo / ".staging" / "pipe", self.snapshot / "data" / "pipe"):
            os.mkfifo(path)
            self.cli("verify", success=False)
            self.cli("list", success=False)
            self.cli("restore", success=False)
            path.unlink()
        os.mkfifo(self.dest)
        self.cli("restore", success=False)
        self.assertTrue(self.dest.exists())

    def test_every_snapshot_regular_file_corruption_and_deletion(self):
        self.sample_source()
        self.cli("create")
        protected = self.base / "protected"
        protected.mkdir()
        for path in sorted(self.snapshot.rglob("*")):
            if not path.is_file():
                continue
            original = path.read_bytes()
            for mode in ("alter", "delete"):
                with self.subTest(path=path.relative_to(self.snapshot), mode=mode):
                    if mode == "alter":
                        changed = bytes([original[0] ^ 0xFF]) + original[1:] if original else b"corruption"
                        path.write_bytes(changed)
                    else:
                        path.unlink()
                    self.cli("verify", success=False)
                    self.cli("restore", dest=protected, success=False)
                    self.assertEqual(inventory(protected), {})
                    self.cli("restore", success=False)
                    self.assertFalse(self.dest.exists())
                    self.assertEqual(self.cli("list"), {"snapshots": []})
                    path.write_bytes(original)
                    self.cli("verify")

    def test_missing_and_extra_snapshot_entries(self):
        self.cli("create")
        extra = self.snapshot / "extra"
        extra.write_bytes(b"unlisted")
        self.cli("verify", success=False)
        self.cli("restore", success=False)
        extra.unlink()
        (self.snapshot / "data").rmdir()
        self.cli("verify", success=False)
        self.cli("restore", success=False)
        (self.snapshot / "data").mkdir()
        self.cli("verify")

    def test_sealed_invalid_manifests_rejected_without_path_escape(self):
        (self.source / "f").write_bytes(b"content")
        self.cli("create")
        manifest_path = self.snapshot / "manifest.json"
        seal_path = self.snapshot / "manifest.sha256"
        original = manifest_path.read_bytes()
        original_seal = seal_path.read_bytes()
        base_manifest = json.loads(original)
        mutations = [
            lambda m: m["files"][0].update(path=["..", "escape"]),
            lambda m: m["files"][0].update(path=["/absolute"]),
            lambda m: m["files"][0].update(path=["a/b"]),
            lambda m: m["files"][0].update(path=["missing", "child"]),
            lambda m: m["files"].append(m["files"][0].copy()),
            lambda m: m.update(directories=[["f"]]),
            lambda m: m.update(directories=[["a"], ["a"]]),
            lambda m: m.update(version=True),
            lambda m: m.update(id="other"),
            lambda m: m["files"][0].update(size=True),
            lambda m: m["files"][0].update(sha256="bad"),
            lambda m: m.update(extra="not allowed"),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                value = json.loads(json.dumps(base_manifest))
                mutate(value)
                raw = json.dumps(value).encode()
                manifest_path.write_bytes(raw)
                seal_path.write_bytes((hashlib.sha256(raw).hexdigest() + "\n").encode())
                self.cli("verify", success=False)
                self.cli("restore", success=False)
                self.assertFalse(self.dest.exists())
                self.assertFalse((self.base / "escape").exists())
        manifest_path.write_bytes(original)
        seal_path.write_bytes(original_seal)
        self.cli("verify")

    def test_incomplete_staging_never_listed_and_retry_allowed(self):
        self.cli("create", identifier="previous")
        abandoned = self.repo / ".staging" / "V1-interrupted"
        (abandoned / "data").mkdir(parents=True)
        (abandoned / "data" / "0").write_bytes(b"partial")
        self.assertEqual(self.cli("list"), {"snapshots": ["previous"]})
        self.cli("create")
        self.cli("verify", identifier="previous")
        self.cli("verify")
        self.assertEqual(list((self.repo / ".staging").iterdir()), [])

    def test_max_bytes_exact_boundary_and_metadata(self):
        self.sample_source()
        original = inventory(self.source)
        reference = self.base / "reference"
        self.cli("create", repo=reference)
        required = regular_bytes(reference)
        source_bytes = regular_bytes(self.source)
        self.assertGreater(required, source_bytes)
        print(f"Bytes fuente={source_bytes}; repositorio completo={required}", flush=True)
        self.cli("create", max_bytes=required - 1, success=False)
        self.assertEqual(regular_bytes(self.repo), 0)
        self.assertEqual(self.cli("list"), {"snapshots": []})
        self.cli("create", max_bytes=required)
        self.assertEqual(regular_bytes(self.repo), required)
        self.assertEqual(list((self.repo / ".staging").iterdir()), [])
        self.cli("verify")
        self.cli("restore")
        self.assertEqual(inventory(self.dest), original)
        self.assertEqual(inventory(self.source), original)

    def test_max_bytes_below_existing_no_growth_and_retry(self):
        self.sample_source()
        self.cli("create", identifier="previous")
        before = inventory(self.repo)
        existing = regular_bytes(self.repo)
        for limit in (0, existing - 1, existing, existing + 10):
            with self.subTest(limit=limit):
                self.cli("create", max_bytes=limit, success=False)
                self.assertEqual(inventory(self.repo), before)
                self.assertEqual(regular_bytes(self.repo), existing)
                self.cli("verify", identifier="previous")
        self.cli("create", max_bytes=existing * 3)
        self.assertLessEqual(regular_bytes(self.repo), existing * 3)
        self.cli("verify")
        self.cli("restore", identifier="previous")
        self.assertEqual(inventory(self.dest), inventory(self.source))

    def test_max_bytes_counts_regular_files_outside_chosen_snapshot(self):
        self.cli("create", identifier="previous")
        extra = self.repo / "snapshots" / "unpublished"
        extra.mkdir()
        (extra / "regular metadata").write_bytes(b"M" * 10000)
        before = inventory(self.repo)
        existing = regular_bytes(self.repo)
        self.cli("create", max_bytes=existing - 1, success=False)
        self.assertEqual(inventory(self.repo), before)
        self.cli("create", max_bytes=existing + 1000)
        self.assertLessEqual(regular_bytes(self.repo), existing + 1000)
        self.cli("verify", identifier="previous")
        self.cli("verify")
        self.assertEqual(self.cli("list"), {"snapshots": ["V1", "previous"]})

    def test_max_bytes_empty_and_directory_only_sources_need_metadata(self):
        for directories in (False, True):
            with self.subTest(directories=directories):
                if directories:
                    (self.source / "vacío" / "日本語").mkdir(parents=True)
                reference = self.base / ("reference" + str(directories))
                self.cli("create", repo=reference)
                required = regular_bytes(reference)
                repo = self.base / ("bounded" + str(directories))
                self.assertEqual(regular_bytes(self.source), 0)
                self.assertGreater(required, 65)
                for limit in (0, 65, required - 1):
                    self.cli("create", repo=repo, max_bytes=limit, success=False)
                    self.assertEqual(regular_bytes(repo), 0)
                self.cli("create", repo=repo, max_bytes=required)
                self.assertEqual(regular_bytes(repo), required)
                dest = self.base / ("restored" + str(directories))
                self.cli("restore", repo=repo, dest=dest)
                self.assertEqual(inventory(dest), inventory(self.source))

    def test_max_bytes_reclaims_abandoned_copies(self):
        self.sample_source()
        self.cli("create", identifier="previous")
        reference = self.base / "reference"
        self.cli("create", repo=reference)
        required = regular_bytes(self.repo) + regular_bytes(reference)
        abandoned = self.repo / ".staging" / "V1-interrupted"
        abandoned.mkdir()
        (abandoned / "partial").write_bytes(b"partial" * 200000)
        self.cli("create", max_bytes=required)
        self.assertEqual(regular_bytes(self.repo), required)
        self.assertFalse(abandoned.exists())
        self.cli("verify", identifier="previous")
        self.cli("verify")

    def test_max_bytes_invalid_arguments_do_not_mutate_repository(self):
        self.cli("create", identifier="previous")
        before = inventory(self.repo)
        for value in ("-1", "1.5", "abc", "", "+1", "1e6"):
            command = [sys.executable, str(SCRIPT), "create", "--source", str(self.source),
                       "--repo", str(self.repo), "--id", self.identifier, "--max-bytes=" + value]
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            record(command, result)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertTrue(result.stderr)
            self.assertEqual(inventory(self.repo), before)

    def test_max_bytes_concurrent_different_ids_share_limit(self):
        (self.source / "f").write_bytes(bytes(range(256)) * 4096)
        reference = self.base / "reference"
        self.cli("create", repo=reference, identifier="aa")
        limit = regular_bytes(reference)
        processes = []
        for identifier in ("aa", "bb"):
            command = [sys.executable, str(SCRIPT), "create", "--source", str(self.source),
                       "--repo", str(self.repo), "--id", identifier, "--max-bytes", str(limit)]
            processes.append((command, subprocess.Popen(command, stdout=subprocess.PIPE,
                                                        stderr=subprocess.PIPE, text=True)))
        codes = []
        successful = []
        for command, process in processes:
            stdout, stderr = process.communicate(timeout=30)
            record(command, subprocess.CompletedProcess(command, process.returncode, stdout, stderr))
            codes.append(process.returncode)
            if process.returncode == 0:
                successful.append(json.loads(stdout)["id"])
            else:
                self.assertEqual(stdout, "")
        self.assertEqual(sorted(codes), [0, 1])
        self.assertEqual(regular_bytes(self.repo), limit)
        self.assertEqual(self.cli("list"), {"snapshots": successful})
        self.cli("verify", identifier=successful[0])

    def test_sigkill_create_recovery_and_previous_snapshot_preserved(self):
        (self.source / "small").write_bytes(b"previous content")
        self.cli("create", identifier="previous")
        previous = inventory(self.repo / "snapshots" / "previous")
        with (self.source / "large").open("wb") as stream:
            stream.truncate(64 * 1024 * 1024)
        for attempt in range(2):
            identifier = "interrupted" + str(attempt)
            limit = regular_bytes(self.repo) + regular_bytes(self.source) + 100000
            command = [sys.executable, str(SCRIPT), "create", "--repo", str(self.repo),
                       "--id", identifier, "--source", str(self.source), "--max-bytes", str(limit)]
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            killed = False
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and process.poll() is None:
                stages = list((self.repo / ".staging").glob(identifier + "-*/data/0"))
                if any(path.exists() and path.stat().st_size > 0 for path in stages):
                    process.kill()
                    killed = True
                    break
                time.sleep(0.001)
            if process.poll() is None and not killed:
                process.kill()
            stdout, stderr = process.communicate(timeout=10)
            record(command, subprocess.CompletedProcess(command, process.returncode, stdout, stderr))
            print(f"SIGKILL enviado durante copia: {killed}", flush=True)
            self.assertTrue(killed, "La prueba no alcanzó la ventana de interrupción")
            self.assertEqual(process.returncode, -signal.SIGKILL)
            self.assertEqual(stdout, "")
            self.assertFalse((self.repo / "snapshots" / identifier).exists())
            self.assertNotIn(identifier, self.cli("list")["snapshots"])
            self.assertEqual(inventory(self.repo / "snapshots" / "previous"), previous)
            self.cli("verify", identifier="previous")
            self.cli("create", identifier=identifier, max_bytes=limit)
            self.assertLessEqual(regular_bytes(self.repo), limit)
            self.assertEqual(list((self.repo / ".staging").iterdir()), [])
            self.cli("verify", identifier=identifier)
        self.cli("restore", identifier="interrupted1")
        self.assertEqual(hashlib.sha256((self.dest / "large").read_bytes()).digest(), hashlib.sha256((self.source / "large").read_bytes()).digest())

    def test_concurrent_create_same_id_preserves_single_complete_snapshot(self):
        (self.source / "f").write_bytes(bytes(range(256)) * 4096)
        command = [sys.executable, str(SCRIPT), "create", "--source", str(self.source), "--repo", str(self.repo), "--id", self.identifier]
        processes = [subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
        codes = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=30)
            record(command, subprocess.CompletedProcess(command, process.returncode, stdout, stderr))
            codes.append(process.returncode)
            if process.returncode:
                self.assertEqual(stdout, "")
            else:
                self.assertEqual(json.loads(stdout), {"id": self.identifier})
        self.assertEqual(sorted(codes), [0, 1])
        self.cli("verify")
        self.assertEqual(self.cli("list"), {"snapshots": [self.identifier]})


if __name__ == "__main__":
    unittest.main(verbosity=2)
