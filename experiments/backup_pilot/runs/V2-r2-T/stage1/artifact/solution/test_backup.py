"""Contract tests; only temporary synthetic data under /trial/evidence."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parent.parent
PROGRAM = ROOT / "solution" / "backup.py"
LOG = []


def tree(path):
    result = {}
    for p in path.rglob("*"):
        if p.is_dir():
            value = None
        else:
            with p.open("rb") as stream:
                value = (p.stat().st_size, hashlib.file_digest(stream, "sha256").hexdigest())
        result[p.relative_to(path).as_posix()] = value
    return result


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="contract-", dir=ROOT / "evidence")
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        (self.source / "empty dir").mkdir()
        (self.source / "ñ 文.bin").write_bytes(bytes(range(256)) + b"\x00\xff\n")
        self.repo = self.root / "repo"

    def tearDown(self):
        self.temp.cleanup()

    def cli(self, operation, *, success=True, **args):
        args.setdefault("repo", self.repo)
        argv = [sys.executable, str(PROGRAM), operation]
        for key, value in args.items():
            argv.extend(["--" + key, str(value)])
        started = time.monotonic()
        run = subprocess.run(argv, capture_output=True, timeout=30)
        LOG.append({"argv": argv, "exit_code": run.returncode, "timed_out": False,
                    "stdout": run.stdout.decode(), "stderr": run.stderr.decode(),
                    "elapsed_seconds": time.monotonic() - started})
        self.assertEqual(run.returncode == 0, success, run.stderr.decode())
        if success:
            self.assertEqual(run.stderr, b"")
            value = json.loads(run.stdout)
            self.assertIsInstance(value, dict)
            self.assertEqual(len(run.stdout.splitlines()), 1)
            return value
        self.assertEqual(run.stdout, b"")

    def create(self, id="v1", **kwargs):
        return self.cli("create", source=self.source, id=id, **kwargs)

    def test_v2_versions_and_source_independence(self):
        expectations = []
        initial = tree(self.source)
        self.assertEqual(self.create("z-first"), {"id": "z-first"})
        self.assertEqual(tree(self.source), initial)
        expectations.append(("z-first", initial))
        (self.source / "ñ 文.bin").write_bytes(b"modified")
        (self.source / "new.txt").write_bytes(b"added")
        (self.source / "empty dir").rmdir()
        (self.source / "empty dir").write_bytes(b"directory became file")
        self.create("a-second")
        expectations.append(("a-second", tree(self.source)))
        (self.source / "new.txt").unlink()
        (self.source / "ñ 文.bin").unlink()
        (self.source / "empty dir").unlink()
        (self.source / "empty dir").mkdir()
        (self.source / "empty dir" / "nested empty").mkdir()
        self.create("m-third")
        expectations.append(("m-third", tree(self.source)))
        shutil.rmtree(self.source)
        self.assertEqual(self.cli("list"), {"snapshots": ["a-second", "m-third", "z-first"]})
        for id, expected in expectations:
            self.assertEqual(self.cli("verify", id=id), {"id": id, "valid": True})
            dest = self.root / ("restore " + id)
            self.assertEqual(self.cli("restore", id=id, dest=dest), {"id": id})
            self.assertEqual(tree(dest), expected)

    def test_empty_source_and_empty_destination(self):
        shutil.rmtree(self.source)
        self.source.mkdir()
        self.assertEqual(self.cli("list"), {"snapshots": []})
        self.repo.mkdir()
        self.assertEqual(self.cli("list"), {"snapshots": []})
        self.create()
        dest = self.root / "empty-dest"
        dest.mkdir()
        self.cli("restore", id="v1", dest=dest)
        self.assertEqual(tree(dest), {})

    def test_duplicate_id_does_not_replace(self):
        self.create()
        archive = self.repo / "snapshots" / "v1.bak"
        before = archive.read_bytes()
        (self.source / "new").write_bytes(b"new")
        self.create(success=False)
        self.assertEqual(archive.read_bytes(), before)
        self.cli("verify", id="v1")

    def test_invalid_and_missing_ids(self):
        for id in ("", "../escape", "a/b", ".", "-abc", "á", "a" * 65, "a\n"):
            for op in ("create", "verify", "restore"):
                kw = {"id": id}
                if op == "create":
                    kw["source"] = self.source
                if op == "restore":
                    kw["dest"] = self.root / "dest"
                self.cli(op, success=False, **kw)
        self.create("A" + "_" * 63)
        self.cli("verify", id="missing", success=False)
        self.cli("restore", id="missing", dest=self.root / "dest", success=False)
        self.assertFalse((self.root / "dest").exists())

    def test_overlaps_are_rejected(self):
        before = tree(self.source)
        for repo in (self.source, self.source / "repo", self.root):
            self.create(repo=repo, success=False)
        self.assertEqual(tree(self.source), before)
        self.create()
        for dest in (self.repo, self.repo / "dest", self.root):
            self.cli("restore", id="v1", dest=dest, success=False)
        self.cli("verify", id="v1")

    def test_nonempty_destination_unchanged(self):
        self.create()
        for suffix in ("file", "empty-subdir"):
            dest = self.root / suffix
            dest.mkdir()
            if suffix == "file":
                (dest / "protected").write_bytes(bytes(range(256)))
            else:
                (dest / "empty").mkdir()
            before = tree(dest)
            self.cli("restore", id="v1", dest=dest, success=False)
            self.assertEqual(tree(dest), before)

    def test_source_symlinks_and_special_files(self):
        external = self.root / "external"
        external.write_bytes(b"protected")
        link = self.source / "link"
        link.symlink_to(external)
        self.create(success=False)
        link.unlink()
        link.symlink_to(self.root / "missing")
        self.create(success=False)
        link.unlink()
        link.symlink_to(self.source, target_is_directory=True)
        self.create(success=False)
        link.unlink()
        os.mkfifo(link)
        self.create(success=False)
        self.assertFalse(self.repo.exists())
        self.assertEqual(external.read_bytes(), b"protected")

    def test_managed_path_symlink_components(self):
        link = self.root / "alias"
        link.symlink_to(self.source, target_is_directory=True)
        for spelling in (str(link), str(link / ".." / "source"),
                         str(self.root / "absent" / ".." / "alias")):
            self.cli("create", source=spelling, id="v1", success=False)
        self.create()
        link.unlink()
        link.symlink_to(self.repo, target_is_directory=True)
        self.cli("list", repo=link, success=False)
        self.cli("verify", repo=link, id="v1", success=False)
        link.unlink()
        link.symlink_to(self.root / "absent", target_is_directory=True)
        self.cli("restore", id="v1", dest=link, success=False)
        self.cli("restore", id="v1", dest=link / "child", success=False)

    def test_snapshot_and_repo_special_entries(self):
        self.create()
        archive = self.repo / "snapshots" / "v1.bak"
        content = archive.read_bytes()
        archive.unlink()
        archive.symlink_to(self.source / "ñ 文.bin")
        self.cli("verify", id="v1", success=False)
        self.cli("restore", id="v1", dest=self.root / "dest", success=False)
        self.cli("list", success=False)
        archive.unlink()
        archive.write_bytes(content)
        special = self.repo / "special"
        os.mkfifo(special)
        self.cli("list", success=False)
        self.create("v2", success=False)
        special.unlink()
        dest = self.root / "dest"
        dest.mkdir()
        os.mkfifo(dest / "fifo")
        self.cli("restore", id="v1", dest=dest, success=False)
        self.assertTrue(stat_fifo(dest / "fifo"))

    def test_corruption_is_never_published(self):
        self.create()
        archive = self.repo / "snapshots" / "v1.bak"
        pristine = archive.read_bytes()
        header_length = int.from_bytes(pristine[8:16], "big")
        for position in (0, 16, 16 + header_length, len(pristine) - 1):
            corrupt = bytearray(pristine)
            corrupt[position] ^= 1
            archive.write_bytes(corrupt)
            self.cli("verify", id="v1", success=False)
            dest = self.root / "dest"
            self.cli("restore", id="v1", dest=dest, success=False)
            self.assertFalse(dest.exists())
            dest.mkdir()
            self.cli("restore", id="v1", dest=dest, success=False)
            self.assertEqual(tree(dest), {})
            dest.rmdir()
        for corrupt in (pristine[:-1], pristine + b"extra", b""):
            archive.write_bytes(corrupt)
            self.cli("verify", id="v1", success=False)
            self.cli("restore", id="v1", dest=self.root / "dest", success=False)
        archive.unlink()
        self.cli("verify", id="v1", success=False)
        self.cli("restore", id="v1", dest=self.root / "dest", success=False)
        archive.write_bytes(pristine)
        self.cli("verify", id="v1")

    def test_interrupted_create_can_be_repeated(self):
        self.create("previous")
        previous = (self.repo / "snapshots" / "previous.bak").read_bytes()
        large = self.source / "large"
        with large.open("wb") as stream:
            stream.truncate(256 * 1024 * 1024)
        argv = [sys.executable, str(PROGRAM), "create", "--source", str(self.source),
                "--repo", str(self.repo), "--id", "interrupted"]
        process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        deadline = time.monotonic() + 10
        observed = False
        try:
            while process.poll() is None and time.monotonic() < deadline:
                temps = list((self.repo / ".work").glob("create-*"))
                if any(p.stat().st_size >= 1024 * 1024 for p in temps):
                    observed = True
                    process.send_signal(signal.SIGKILL)
                    break
                time.sleep(0.001)
            stdout, stderr = process.communicate(timeout=10)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
        LOG.append({"argv": argv, "exit_code": process.returncode, "timed_out": False,
                    "stdout": stdout.decode(), "stderr": stderr.decode(),
                    "intentional_signal": "SIGKILL", "partial_file_observed": observed})
        self.assertTrue(observed, "could not observe incomplete create")
        self.assertEqual(process.returncode, -signal.SIGKILL)
        self.assertEqual(self.cli("list"), {"snapshots": ["previous"]})
        self.assertEqual((self.repo / "snapshots" / "previous.bak").read_bytes(), previous)
        self.create("interrupted")
        self.cli("verify", id="previous")
        self.cli("verify", id="interrupted")
        dest = self.root / "restored"
        self.cli("restore", id="interrupted", dest=dest)
        self.assertEqual(tree(dest), tree(self.source))


def stat_fifo(path):
    import stat
    return stat.S_ISFIFO(path.lstat().st_mode)


if __name__ == "__main__":
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(unittest.defaultTestLoader.loadTestsFromTestCase(ContractTests))
    (ROOT / "evidence" / "cli_calls.json").write_text(
        json.dumps(LOG, ensure_ascii=True, indent=2) + "\n")
    (ROOT / "evidence" / "test_summary.json").write_text(json.dumps({
        "tests_run": result.testsRun, "failures": len(result.failures),
        "errors": len(result.errors), "passed": result.wasSuccessful(),
        "cli_calls": len(LOG)}, indent=2) + "\n")
    sys.exit(0 if result.wasSuccessful() else 1)
