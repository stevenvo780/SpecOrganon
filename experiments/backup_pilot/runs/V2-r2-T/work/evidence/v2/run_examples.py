"""Execute documented V2 examples and retain every command/result."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "evidence" / "v2"
CALLS = []


def cli(operation, success=True, **options):
    argv = [sys.executable, str(ROOT / "solution" / "backup.py"), operation]
    for key, value in options.items():
        argv.extend(["--" + key, str(value)])
    run = subprocess.run(argv, capture_output=True, timeout=30)
    CALLS.append({"argv": argv, "exit_code": run.returncode, "timed_out": False,
                  "timeout_seconds": 30, "stdout": run.stdout.decode(),
                  "stderr": run.stderr.decode()})
    assert (run.returncode == 0) == success, CALLS[-1]
    if success:
        assert not run.stderr
        return json.loads(run.stdout)
    assert not run.stdout


def tree(root):
    return {p.relative_to(root).as_posix(): None if p.is_dir() else p.read_bytes()
            for p in root.rglob("*")}


def main():
    with tempfile.TemporaryDirectory(prefix="examples-", dir=EVIDENCE) as temporary:
        root = Path(temporary)
        source, repo = root / "source", root / "repo"
        source.mkdir()
        (source / "vacío").mkdir()
        (source / "documento con espacios.txt").write_bytes(b"version one\x00\xff")
        versions = []
        for version in range(1, 4):
            if version == 2:
                (source / "documento con espacios.txt").write_bytes(b"modified")
                (source / "added").write_bytes(bytes(range(256)))
            elif version == 3:
                (source / "added").unlink()
            id = f"v{version}"
            versions.append((id, tree(source)))
            assert cli("create", source=source, repo=repo, id=id,
                       **{"max-bytes": 1000000}) == {"id": id}
        protected = tree(repo)
        total = sum(p.stat().st_size for p in repo.rglob("*") if p.is_file())
        cli("create", success=False, source=source, repo=repo, id="too-small",
            **{"max-bytes": total - 1})
        assert tree(repo) == protected
        shutil.rmtree(source)
        assert cli("list", repo=repo) == {"snapshots": ["v1", "v2", "v3"]}
        for id, expected in versions:
            assert cli("verify", repo=repo, id=id) == {"id": id, "valid": True}
            dest = root / ("restore-" + id)
            assert cli("restore", repo=repo, id=id, dest=dest) == {"id": id}
            assert tree(dest) == expected
        summary = {"passed": True, "versions_restored": 3,
                   "repository_bytes": total, "limit": 1000000,
                   "cli_calls": len(CALLS)}
        print(json.dumps(summary, sort_keys=True))
        (EVIDENCE / "examples_summary.json").write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    try:
        main()
    finally:
        (EVIDENCE / "example_calls.json").write_text(json.dumps(CALLS, indent=2) + "\n")
