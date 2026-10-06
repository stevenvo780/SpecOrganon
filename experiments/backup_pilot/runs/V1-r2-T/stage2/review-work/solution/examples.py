"""Executable example; private temporary data, no original source on restore."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    program = str(Path(__file__).with_name("backup.py").resolve())
    with tempfile.TemporaryDirectory(prefix="backup-example-", dir="/trial") as folder:
        root = Path(folder)
        source, repo, dest = (root / name for name in ("source", "repo", "restore"))
        source.mkdir()
        (source / "vacío").mkdir()
        content = bytes(range(256)) + "documento ñ 漢字\n".encode()
        (source / "documento con espacios.bin").write_bytes(content)
        commands = [
            ["create", "--source", str(source), "--repo", str(repo), "--id", "v1", "--max-bytes", "1000000"],
            ["verify", "--repo", str(repo), "--id", "v1"],
            ["list", "--repo", str(repo)],
            ["restore", "--repo", str(repo), "--id", "v1", "--dest", str(dest)],
        ]
        expected = [{"id": "v1"}, {"id": "v1", "valid": True}, {"snapshots": ["v1"]}, {"id": "v1"}]
        for arguments, result in zip(commands, expected):
            if arguments[0] == "restore":
                (source / "documento con espacios.bin").unlink()
                (source / "vacío").rmdir()
                source.rmdir()
            argv = [sys.executable, program, *arguments]
            run = subprocess.run(argv, capture_output=True, timeout=30)
            print(json.dumps({"argv": argv, "exit_code": run.returncode,
                              "timed_out": False, "timeout_seconds": 30,
                              "stdout": run.stdout.decode(), "stderr": run.stderr.decode()}))
            assert run.returncode == 0, run.stderr
            assert json.loads(run.stdout) == result
        assert (dest / "documento con espacios.bin").read_bytes() == content
        assert (dest / "vacío").is_dir() and not any((dest / "vacío").iterdir())
        total = sum(p.stat().st_size for p in repo.rglob("*") if p.is_file())
        assert total <= 1_000_000
        print(json.dumps({"example_passed": True, "repository_bytes": total, "max_bytes": 1_000_000}))


if __name__ == "__main__":
    main()
