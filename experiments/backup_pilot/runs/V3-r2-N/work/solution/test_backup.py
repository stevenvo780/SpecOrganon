"""Contract tests using private synthetic files, including deterministic SIGKILL."""

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


SCRIPT = Path(__file__).with_name("backup.py")
COMMAND_LOG = Path(__file__).with_name("TEST_COMMANDS.jsonl")


def tree(path):
    result = {}
    for item in sorted(path.rglob("*")):
        relative = item.relative_to(path).as_posix()
        if item.is_dir():
            result[relative] = ("dir",)
        else:
            result[relative] = ("file", hashlib.sha256(item.read_bytes()).hexdigest(), item.stat().st_size)
    return result


def regular_bytes(path):
    # Independent observation of the contractual sum, not of allocation blocks.
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="backup-test-", dir="/trial")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "fuente con espacios"
        self.source.mkdir()
        (self.source / "vacío ü").mkdir()
        (self.source / "nivel").mkdir()
        (self.source / "nivel" / "東京 café.txt").write_bytes("texto\n😀".encode())
        (self.source / "bytes.bin").write_bytes(bytes(range(256)) * 31)
        (self.source / "cero").write_bytes(b"")
        self.repo = self.root / "repo"
        self.dest = self.root / "dest"

    def cli(self, command, *, repo=None, snapshot_id="v1", source=None, dest=None,
            max_bytes=None, ok=True):
        argv = [sys.executable, str(SCRIPT), command, "--repo", str(repo or self.repo)]
        if command != "list":
            # Keep IDs beginning with '-' as values rather than argparse options.
            argv += ["--id=" + snapshot_id]
        if command == "create":
            argv += ["--source", str(source or self.source)]
            if max_bytes is not None:
                argv += ["--max-bytes=" + str(max_bytes)]
        if command == "restore":
            argv += ["--dest", str(dest or self.dest)]
        result = subprocess.run(argv, capture_output=True, text=True, timeout=30)
        with COMMAND_LOG.open("a", encoding="utf-8") as log:
            log.write(json.dumps({"command": argv, "returncode": result.returncode,
                                  "stdout": result.stdout, "stderr": result.stderr}, ensure_ascii=True) + "\n")
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            value = json.loads(result.stdout)
            self.assertIsInstance(value, dict)
            self.assertEqual(len(result.stdout.splitlines()), 1)
            return value
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.stdout, "")
        self.assertIn("error", json.loads(result.stderr))
        return result

    def make_snapshot(self, snapshot_id="v1", max_bytes=None):
        self.assertEqual(self.cli("create", snapshot_id=snapshot_id, max_bytes=max_bytes),
                         {"id": snapshot_id})
        return self.repo / "snapshots" / snapshot_id

    def test_round_trip_and_source_independence(self):
        original = tree(self.source)
        self.make_snapshot()
        self.assertEqual(tree(self.source), original)
        self.assertEqual(self.cli("verify"), {"id": "v1", "valid": True})
        shutil.rmtree(self.source)
        self.assertEqual(self.cli("restore"), {"id": "v1"})
        self.assertEqual(tree(self.dest), original)
        self.assertEqual(self.cli("list"), {"snapshots": ["v1"]})

    def test_empty_source_and_existing_empty_destination(self):
        shutil.rmtree(self.source)
        self.source.mkdir()
        self.make_snapshot()
        self.dest.mkdir()
        self.cli("restore")
        self.assertEqual(tree(self.dest), {})
        self.cli("verify")

    def test_versions_and_sorted_listing(self):
        expected = {}
        for index, snapshot_id in enumerate(("z3", "a1", "m2")):
            (self.source / "bytes.bin").write_bytes(bytes([index]) * (index + 1))
            (self.source / f"added-{index}").write_text(str(index))
            if index:
                (self.source / f"added-{index - 1}").unlink()
            expected[snapshot_id] = tree(self.source)
            self.make_snapshot(snapshot_id)
        self.assertEqual(self.cli("list"), {"snapshots": ["a1", "m2", "z3"]})
        for snapshot_id, contents in expected.items():
            destination = self.root / snapshot_id
            self.cli("restore", snapshot_id=snapshot_id, dest=destination)
            self.assertEqual(tree(destination), contents)

    def test_new_empty_repositories_and_unknown_ids(self):
        self.assertEqual(self.cli("list"), {"snapshots": []})
        self.assertFalse(self.repo.exists())
        self.repo.mkdir()
        self.assertEqual(self.cli("list"), {"snapshots": []})
        for command in ("verify", "restore"):
            self.cli(command, ok=False)
        self.assertFalse(self.dest.exists())

    def test_invalid_ids(self):
        for snapshot_id in ("", ".", "..", "../outside", "/absolute", "-bad", "a/b", "é", "a" * 65):
            for command in ("create", "verify", "restore"):
                with self.subTest(snapshot_id=snapshot_id, command=command):
                    self.cli(command, snapshot_id=snapshot_id, ok=False)
        self.assertFalse(self.repo.exists())
        self.make_snapshot("A" + "_" * 63)

    def test_existing_id_never_overwritten(self):
        self.make_snapshot()
        before = tree(self.repo)
        (self.source / "bytes.bin").write_bytes(b"new version")
        self.cli("create", ok=False)
        self.assertEqual(tree(self.repo), before)
        self.cli("verify")
        empty = self.repo / "snapshots" / "reserved"
        empty.mkdir()
        self.cli("create", snapshot_id="reserved", ok=False)
        self.assertEqual(list(empty.iterdir()), [])

    def test_protected_destination(self):
        self.make_snapshot()
        self.dest.mkdir()
        (self.dest / "important.bin").write_bytes(bytes(range(256)))
        (self.dest / "empty").mkdir()
        original = tree(self.dest)
        self.cli("restore", ok=False)
        self.assertEqual(tree(self.dest), original)
        (self.dest / "important.bin").unlink()
        self.cli("restore", ok=False)  # A directory alone is also nonempty.
        self.assertEqual(tree(self.dest), {"empty": ("dir",)})

    def test_overlap_rejected_before_mutation(self):
        original = tree(self.source)
        for repo in (self.source, self.source / "new" / "repo", self.root):
            self.cli("create", repo=repo, ok=False)
            self.assertEqual(tree(self.source), original)
        self.make_snapshot()
        before = tree(self.repo)
        for dest in (self.repo, self.repo / "restored", self.root):
            self.cli("restore", dest=dest, ok=False)
            self.assertEqual(tree(self.repo), before)

    def test_corruption_every_regular_file(self):
        self.make_snapshot()
        self.make_snapshot("good")
        snapshot = self.repo / "snapshots" / "v1"
        regular_files = [path.relative_to(self.repo) for path in snapshot.rglob("*") if path.is_file()]
        for relative in regular_files:
            for mutation in ("flip", "truncate", "append", "delete"):
                with self.subTest(file=str(relative), mutation=mutation):
                    clone = self.root / "clone"
                    if clone.exists():
                        shutil.rmtree(clone)
                    shutil.copytree(self.repo, clone)
                    target = clone / relative
                    content = target.read_bytes()
                    if mutation == "delete":
                        target.unlink()
                    elif mutation == "append":
                        target.write_bytes(content + b"corruption")
                    elif mutation == "truncate":
                        if not content:
                            target.write_bytes(b"x")
                        else:
                            target.write_bytes(content[:-1])
                    else:
                        target.write_bytes(bytes([content[0] ^ 1]) + content[1:] if content else b"x")
                    self.cli("verify", repo=clone, ok=False)
                    self.dest.mkdir(exist_ok=True)
                    self.cli("restore", repo=clone, ok=False)
                    self.assertEqual(tree(self.dest), {})
                    self.assertEqual(self.cli("list", repo=clone), {"snapshots": ["good"]})
                    self.cli("verify", repo=clone, snapshot_id="good")
                    shutil.rmtree(clone)
        self.cli("verify")

    def test_corruption_does_not_publish_missing_destination(self):
        snapshot = self.make_snapshot()
        (snapshot / "objects" / "0000000000000000").write_bytes(b"bad")
        nested_dest = self.root / "missing-parent" / "dest"
        self.cli("restore", dest=nested_dest, ok=False)
        self.assertFalse(nested_dest.parent.exists())

    def test_extra_object_or_missing_manifest_is_incomplete(self):
        snapshot = self.make_snapshot()
        (snapshot / "objects" / "unexpected").write_bytes(b"extra")
        self.cli("verify", ok=False)
        self.cli("restore", ok=False)
        self.assertEqual(self.cli("list"), {"snapshots": []})
        (snapshot / "objects" / "unexpected").unlink()
        (snapshot / "manifest.json").unlink()
        self.cli("verify", ok=False)
        self.assertEqual(self.cli("list"), {"snapshots": []})

    def test_source_links_and_special_files(self):
        outside = self.root / "outside"
        outside.write_bytes(b"protected")
        for link_target in (outside, self.source / "nivel", self.root / "missing"):
            link = self.source / "link"
            link.symlink_to(link_target)
            self.cli("create", ok=False)
            self.assertFalse(self.repo.exists())
            link.unlink()
        fifo = self.source / "fifo"
        os.mkfifo(fifo)
        self.cli("create", ok=False)
        self.assertFalse(self.repo.exists())
        fifo.unlink()
        self.assertEqual(outside.read_bytes(), b"protected")

    def test_links_in_roots_ancestors_repo_snapshot_and_destination(self):
        source_link = self.root / "source-link"
        source_link.symlink_to(self.source, target_is_directory=True)
        self.cli("create", source=source_link, ok=False)
        ancestor_link = self.root / "ancestor-link"
        ancestor_link.symlink_to(self.root, target_is_directory=True)
        self.cli("create", source=ancestor_link / self.source.name, ok=False)
        self.cli("create", source=ancestor_link / ".." / self.root.name / self.source.name, ok=False)
        actual_repo = self.root / "actual-repo"
        actual_repo.mkdir()
        self.repo.symlink_to(actual_repo, target_is_directory=True)
        self.cli("create", ok=False)
        self.cli("list", ok=False)
        self.repo.unlink()
        self.make_snapshot()
        actual_dest = self.root / "actual-dest"
        actual_dest.mkdir()
        self.dest.symlink_to(actual_dest, target_is_directory=True)
        self.cli("restore", ok=False)
        self.assertEqual(tree(actual_dest), {})
        self.dest.unlink()
        snapshot = self.repo / "snapshots" / "v1"
        payload = next((snapshot / "objects").iterdir())
        saved = payload.read_bytes()
        payload.unlink()
        payload.symlink_to(self.source / "bytes.bin")
        for command in ("verify", "restore", "list"):
            self.cli(command, ok=False)
        payload.unlink()
        payload.write_bytes(saved)
        stale = self.repo / ".staging" / "stale"
        stale.mkdir()
        (stale / "link").symlink_to(actual_dest, target_is_directory=True)
        self.cli("create", snapshot_id="v2", ok=False)

    def test_special_files_in_repo_and_destination(self):
        self.make_snapshot()
        fifo = self.repo / "fifo"
        os.mkfifo(fifo)
        for command in ("create", "verify", "restore", "list"):
            self.cli(command, snapshot_id="v2" if command == "create" else "v1", ok=False)
        fifo.unlink()
        os.mkfifo(self.dest)
        self.cli("restore", ok=False)
        self.assertTrue(self.dest.exists())

    def test_arbitrary_names_and_nested_missing_parent(self):
        (self.source / "a\\b\nnewline").write_bytes(b"name")
        (self.source / "é").write_bytes(b"NFC")
        (self.source / "e\u0301").write_bytes(b"NFD")
        original = tree(self.source)
        self.make_snapshot()
        destination = self.root / "new" / "nested" / "dest"
        self.cli("restore", dest=destination)
        self.assertEqual(tree(destination), original)

    def test_multiple_stream_chunks(self):
        (self.source / "large.bin").write_bytes(bytes(range(256)) * 12301)
        original = tree(self.source)
        self.make_snapshot()
        self.cli("verify")
        self.cli("restore")
        self.assertEqual(tree(self.dest), original)

    def test_manifest_validation_and_traversal(self):
        snapshot = self.make_snapshot()
        manifest = snapshot / "manifest.json"
        original = json.loads(manifest.read_bytes())
        mutations = (
            lambda doc: doc["entries"][0].update(path=["..", "escaped"]),
            lambda doc: doc["entries"][0].update(path=["/absolute"]),
            lambda doc: doc["entries"][0].update(size=True),
            lambda doc: doc["entries"][0].update(path=["missing", "child"]),
            lambda doc: doc.update(id="other"),
            lambda doc: doc["entries"].append(doc["entries"][0].copy()),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                doc = json.loads(json.dumps(original))
                mutation(doc)
                raw = json.dumps(doc).encode()
                manifest.write_bytes(raw)
                (snapshot / "manifest.sha256").write_text(hashlib.sha256(raw).hexdigest() + "\n")
                self.cli("verify", ok=False)
                self.cli("restore", ok=False)
                self.assertFalse(self.dest.exists())
                self.assertFalse((self.root / "escaped").exists())

    def test_max_bytes_exact_boundary_includes_metadata(self):
        original = tree(self.source)
        reference = self.root / "reference"
        self.cli("create", repo=reference)
        required = regular_bytes(reference)
        payload_only = regular_bytes(self.source)
        self.assertGreater(required, payload_only)
        for limit in (0, payload_only, required - 1):
            for _ in range(2):
                self.cli("create", max_bytes=limit, ok=False)
                self.assertEqual(regular_bytes(self.repo), 0)
                self.assertEqual(self.cli("list"), {"snapshots": []})
                self.assertEqual(list((self.repo / ".staging").iterdir()), [])
                self.assertEqual(tree(self.source), original)
        self.make_snapshot(max_bytes=required)
        self.assertEqual(regular_bytes(self.repo), required)
        self.cli("verify")
        self.cli("restore")
        self.assertEqual(tree(self.dest), original)

    def test_max_bytes_empty_source_still_needs_metadata(self):
        shutil.rmtree(self.source)
        self.source.mkdir()
        reference = self.root / "reference"
        self.cli("create", repo=reference)
        required = regular_bytes(reference)
        self.assertGreater(required, 0)
        for limit in (0, required - 1):
            self.cli("create", max_bytes=limit, ok=False)
            self.assertEqual(regular_bytes(self.repo), 0)
        self.make_snapshot(max_bytes=required)
        self.assertEqual(regular_bytes(self.repo), required)
        self.cli("restore")
        self.assertEqual(tree(self.dest), {})

    def test_max_bytes_existing_total_and_failure_leave_previous_unchanged(self):
        previous = self.make_snapshot("previous", max_bytes=100_000)
        previous_contents = tree(previous)
        original = tree(self.repo)
        existing = regular_bytes(self.repo)
        (self.source / "bytes.bin").write_bytes(b"changed" * 1000)
        reference = self.root / "reference"
        shutil.copytree(self.repo, reference)
        self.cli("create", repo=reference, snapshot_id="next")
        required = regular_bytes(reference)
        for limit in (existing - 1, existing, required - 1):
            for _ in range(3):
                self.cli("create", snapshot_id="next", max_bytes=limit, ok=False)
                self.assertEqual(tree(self.repo), original)
                self.assertEqual(regular_bytes(self.repo), existing)
                self.assertEqual(self.cli("list"), {"snapshots": ["previous"]})
                self.cli("verify", snapshot_id="previous")
        self.make_snapshot("next", max_bytes=required)
        self.assertEqual(regular_bytes(self.repo), required)
        self.assertEqual(tree(previous), previous_contents)
        self.cli("verify", snapshot_id="previous")
        self.cli("restore", snapshot_id="next")
        self.assertEqual(tree(self.dest), tree(self.source))

    def test_max_bytes_counts_unrelated_nested_regular_files_and_hardlinks(self):
        self.repo.mkdir()
        extra = self.repo / "extra"
        extra.mkdir()
        (extra / "blob").write_bytes(b"extra data" * 123)
        os.link(extra / "blob", self.repo / "same-inode")
        (extra / "empty").write_bytes(b"")
        protected = tree(self.repo)
        reference = self.root / "reference"
        shutil.copytree(self.repo, reference)
        self.cli("create", repo=reference)
        required = regular_bytes(reference)
        self.cli("create", max_bytes=required - 1, ok=False)
        self.assertEqual(tree(extra), {key.removeprefix("extra/"): value
                                     for key, value in protected.items() if key.startswith("extra/")})
        self.assertEqual(regular_bytes(self.repo), 2 * (extra / "blob").stat().st_size)
        self.make_snapshot(max_bytes=required)
        self.assertEqual(regular_bytes(self.repo), required)
        self.cli("verify")

    def test_max_bytes_invalid_values_do_not_mutate(self):
        self.make_snapshot()
        original = tree(self.repo)
        for value in ("-1", "1.0", "NaN", "1e6", "", "+1", "１２", " 20", "9" * 5000):
            self.cli("create", snapshot_id="invalid", max_bytes=value, ok=False)
            self.assertEqual(tree(self.repo), original)

    def test_max_bytes_retry_after_sigkill_fits_without_orphan_bytes(self):
        self.make_snapshot("previous")
        previous = tree(self.repo / "snapshots" / "previous")
        source_before = tree(self.source)
        completed = ["previous"]
        for index, point in enumerate(("payload", "manifest", "checksum", "verified", "before-rename")):
            with self.subTest(point=point):
                snapshot_id = f"retry{index}"
                reference = self.root / f"reference{index}"
                shutil.copytree(self.repo, reference)
                self.cli("create", repo=reference, snapshot_id=snapshot_id)
                required = regular_bytes(reference)
                self.stopped_create(snapshot_id, point, max_bytes=required)
                self.assertEqual(self.cli("list"), {"snapshots": sorted(completed)})
                self.cli("verify", snapshot_id=snapshot_id, ok=False)
                self.make_snapshot(snapshot_id, max_bytes=required)
                self.assertEqual(regular_bytes(self.repo), required)
                self.assertEqual(list((self.repo / ".staging").iterdir()), [])
                self.assertEqual(tree(self.repo / "snapshots" / "previous"), previous)
                self.cli("verify", snapshot_id=snapshot_id)
                self.cli("restore", snapshot_id=snapshot_id, dest=self.root / f"restored{index}")
                self.assertEqual(tree(self.root / f"restored{index}"), source_before)
                completed.append(snapshot_id)
        self.assertEqual(tree(self.source), source_before)

    def test_max_bytes_rejection_also_reclaims_killed_stage(self):
        self.make_snapshot("previous")
        original = tree(self.repo)
        existing = regular_bytes(self.repo)
        self.stopped_create("retry", "before-rename", max_bytes=100_000)
        self.assertGreater(regular_bytes(self.repo), existing)
        self.cli("create", snapshot_id="retry", max_bytes=existing - 1, ok=False)
        self.assertEqual(tree(self.repo), original)
        self.assertEqual(regular_bytes(self.repo), existing)
        self.cli("verify", snapshot_id="previous")
        self.make_snapshot("retry", max_bytes=100_000)

    def test_concurrent_creators_do_not_delete_live_stages_or_exceed_limit(self):
        self.make_snapshot("previous")
        previous = tree(self.repo / "snapshots" / "previous")
        reference = self.root / "reference"
        shutil.copytree(self.repo, reference)
        self.cli("create", repo=reference, snapshot_id="alpha")
        limit = regular_bytes(reference)
        marker = self.root / "paused"
        code = '''
import os, signal, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import backup
original = backup.verify_snapshot
def pause(*args):
    result = original(*args)
    Path(sys.argv[4]).write_text("ready")
    os.kill(os.getpid(), signal.SIGSTOP)
    return result
backup.verify_snapshot = pause
sys.exit(backup.main(["create", "--source", sys.argv[2], "--repo", sys.argv[3],
                     "--id", "alpha", "--max-bytes", sys.argv[5]]))
'''
        first_argv = [sys.executable, "-c", code, str(SCRIPT.parent), str(self.source),
                      str(self.repo), str(marker), str(limit)]
        second_argv = [sys.executable, str(SCRIPT), "create", "--source", str(self.source),
                       "--repo", str(self.repo), "--id", "bravo", "--max-bytes", str(limit)]
        first = subprocess.Popen(first_argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        second = None
        try:
            deadline = time.monotonic() + 15
            while not marker.exists() and first.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(marker.exists(), f"Creator exited with {first.poll()}")
            live_stage = tree(self.repo / ".staging")
            second = subprocess.Popen(second_argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            time.sleep(0.2)
            self.assertIsNone(second.poll(), "Competing creator did not wait for the live stage")
            self.assertEqual(tree(self.repo / ".staging"), live_stage)
            first.send_signal(signal.SIGCONT)
            first_out, first_err = first.communicate(timeout=10)
            second_out, second_err = second.communicate(timeout=10)
            with COMMAND_LOG.open("a", encoding="utf-8") as log:
                for argv, process, out, err in ((first_argv, first, first_out, first_err),
                                                (second_argv, second, second_out, second_err)):
                    log.write(json.dumps({"command": argv, "returncode": process.returncode,
                                          "stdout": out.decode(), "stderr": err.decode()}) + "\n")
            self.assertEqual(first.returncode, 0, first_err)
            self.assertEqual(json.loads(first_out), {"id": "alpha"})
            self.assertNotEqual(second.returncode, 0)
            self.assertEqual(second_out, b"")
            self.assertEqual(self.cli("list"), {"snapshots": ["alpha", "previous"]})
            self.assertEqual(regular_bytes(self.repo), limit)
            self.assertEqual(tree(self.repo / "snapshots" / "previous"), previous)
            self.assertEqual(list((self.repo / ".staging").iterdir()), [])
        finally:
            for process in (first, second):
                if process is not None and process.poll() is None:
                    process.kill()
                    process.communicate(timeout=5)

    def test_failure_during_create_cleans_stage_and_preserves_previous(self):
        self.make_snapshot("previous")
        original = tree(self.repo)
        code = '''
import sys
sys.path.insert(0, sys.argv[1])
import backup
original_write = backup.write_all
def fail(fd, data):
    original_write(fd, data[:3])
    raise OSError("injected write failure")
if sys.argv[4] == "payload":
    backup.write_all = fail
else:
    original_copy = backup.copy_source
    def copied(*args):
        backup.copy_source = original_copy
        result = original_copy(*args)
        backup.write_all = fail
        return result
    backup.copy_source = copied
sys.exit(backup.main(["create", "--source", sys.argv[2], "--repo", sys.argv[3],
                     "--id", "retry", "--max-bytes", "100000"]))
'''
        for point in ("payload", "manifest"):
            argv = [sys.executable, "-c", code, str(SCRIPT.parent), str(self.source),
                    str(self.repo), point]
            result = subprocess.run(argv, capture_output=True, text=True, timeout=30)
            with COMMAND_LOG.open("a", encoding="utf-8") as log:
                log.write(json.dumps({"command": argv, "returncode": result.returncode,
                                      "stdout": result.stdout, "stderr": result.stderr}) + "\n")
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertIn("injected write failure", result.stderr)
            self.assertEqual(tree(self.repo), original)
            self.assertEqual(self.cli("list"), {"snapshots": ["previous"]})
        self.make_snapshot("retry", max_bytes=100_000)
        self.cli("verify", snapshot_id="retry")

    def stopped_create(self, snapshot_id, point, max_bytes=None):
        marker = self.root / "stopped"
        marker.unlink(missing_ok=True)
        # These wrappers stop the real implementation at deterministic boundaries;
        # the parent delivers SIGKILL while no exception/finally cleanup can run.
        code = '''
import os, signal, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import backup
source, repo, ident, marker, point, limit = sys.argv[2:]
def stop():
    Path(marker).write_text("ready")
    os.kill(os.getpid(), signal.SIGSTOP)
if point in ("payload", "manifest", "checksum"):
    original = backup.write_all
    def partial(fd, data):
        original(fd, data[:17])
        stop()
        original(fd, data[17:])
    if point == "payload":
        backup.write_all = partial
    elif point == "manifest":
        original_copy = backup.copy_source
        def copied(*args):
            result = original_copy(*args)
            backup.write_all = partial
            return result
        # Set the wrapper only after the entire top-level source copy finishes.
        def top_copy(*args):
            backup.copy_source = original_copy
            return copied(*args)
        backup.copy_source = top_copy
    else:
        original_write = backup.write_all
        def checksum_write(fd, data):
            if len(data) == 65 and data.endswith(b"\\n"):
                original_write(fd, data[:17])
                stop()
                original_write(fd, data[17:])
            else:
                original_write(fd, data)
        backup.write_all = checksum_write
elif point == "verified":
    original = backup.verify_snapshot
    def verified(*args):
        result = original(*args)
        stop()
        return result
    backup.verify_snapshot = verified
else:
    original = backup.os.rename
    def rename(*args, **kwargs):
        if point == "before-rename":
            stop()
        original(*args, **kwargs)
        if point == "after-rename":
            stop()
    backup.os.rename = rename
arguments = ["create", "--source", source, "--repo", repo, "--id", ident]
if limit:
    arguments += ["--max-bytes", limit]
sys.exit(backup.main(arguments))
'''
        argv = [sys.executable, "-c", code, str(SCRIPT.parent), str(self.source),
                str(self.repo), snapshot_id, str(marker), point,
                "" if max_bytes is None else str(max_bytes)]
        process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 15
            while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            stopped = marker.exists()
            if process.poll() is None:
                process.kill()
            stdout, stderr = process.communicate(timeout=5)
            with COMMAND_LOG.open("a", encoding="utf-8") as log:
                log.write(json.dumps({"command": argv, "signal": "SIGKILL", "point": point,
                                      "returncode": process.returncode,
                                      "stdout": stdout.decode(), "stderr": stderr.decode()}) + "\n")
            self.assertTrue(stopped, f"No stop marker at {point}; stderr={stderr!r}")
            self.assertEqual(process.returncode, -signal.SIGKILL)
            self.assertEqual(stdout, b"")
            self.assertEqual(stderr, b"")
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)

    def test_sigkill_before_publication_retries_and_preserves_previous_snapshots(self):
        original_source = tree(self.source)
        self.make_snapshot("previous")
        previous = tree(self.repo / "snapshots" / "previous")
        completed = ["previous"]
        for index, point in enumerate(("payload", "manifest", "checksum", "verified", "before-rename")):
            snapshot_id = f"interrupted-{index}"
            with self.subTest(point=point):
                self.stopped_create(snapshot_id, point)
                self.assertEqual(self.cli("list"), {"snapshots": sorted(completed)})
                self.cli("verify", snapshot_id=snapshot_id, ok=False)
                self.cli("restore", snapshot_id=snapshot_id, ok=False)
                self.assertFalse(self.dest.exists())
                self.assertEqual(tree(self.repo / "snapshots" / "previous"), previous)
                self.cli("verify", snapshot_id="previous")
                self.make_snapshot(snapshot_id)
                self.cli("verify", snapshot_id=snapshot_id)
                destination = self.root / f"restored-{index}"
                self.cli("restore", snapshot_id=snapshot_id, dest=destination)
                self.assertEqual(tree(destination), original_source)
                completed.append(snapshot_id)
        self.assertEqual(tree(self.source), original_source)
        self.assertEqual(list((self.repo / ".staging").iterdir()), [])

    def test_sigkill_after_publication_leaves_complete_snapshot(self):
        self.make_snapshot("previous")
        self.stopped_create("committed", "after-rename")
        self.assertEqual(self.cli("list"), {"snapshots": ["committed", "previous"]})
        self.cli("verify", snapshot_id="committed")
        self.cli("restore", snapshot_id="committed")
        self.assertEqual(tree(self.dest), tree(self.source))
        self.cli("create", snapshot_id="committed", ok=False)
        self.cli("verify", snapshot_id="previous")

    def test_failure_during_restore_leaves_destination_and_cleans_stage(self):
        self.make_snapshot()
        self.dest.mkdir()
        code = '''
import sys
sys.path.insert(0, sys.argv[1])
import backup
original = backup.write_all
def fail(fd, data):
    original(fd, data[:3])
    raise OSError("injected write failure")
backup.write_all = fail
sys.exit(backup.main(["restore", "--repo", sys.argv[2], "--id", "v1", "--dest", sys.argv[3]]))
'''
        argv = [sys.executable, "-c", code, str(SCRIPT.parent), str(self.repo), str(self.dest)]
        result = subprocess.run(argv, capture_output=True, text=True, timeout=30)
        with COMMAND_LOG.open("a", encoding="utf-8") as log:
            log.write(json.dumps({"command": argv, "returncode": result.returncode,
                                  "stdout": result.stdout, "stderr": result.stderr}) + "\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(tree(self.dest), {})
        self.assertEqual(list(self.root.glob(".backup-restore-*")), [])
        self.cli("restore")
        self.assertEqual(tree(self.dest), tree(self.source))


if __name__ == "__main__":
    unittest.main(verbosity=2)
