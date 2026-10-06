#!/usr/bin/env python3
"""Reproducible CLI example; fixtures and retained results remain in /trial."""

import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile


HERE = Path(__file__).resolve().parent
PROGRAM = HERE / "backup.py"


def main():
    with (HERE / "examples-results-v3.log").open("w", encoding="utf-8") as log:
        def report(message):
            print(message)
            log.write(message + "\n")
            log.flush()

        report(f"$ python3 solution/examples.py\nPython: {sys.version}")
        with tempfile.TemporaryDirectory(prefix="example-", dir=HERE) as temporary:
            root = Path(temporary)
            source, repo, dest = (root / name for name in ("documentos ü", "repo", "restaurado"))
            source.mkdir()
            (source / "vacío").mkdir()
            content = bytes(range(256)) + b"\x00\xff\n"
            (source / "datos 日本語.bin").write_bytes(content)

            def run(*arguments, expected_code=0):
                command = [sys.executable, str(PROGRAM), *map(str, arguments)]
                result = subprocess.run(command, capture_output=True, text=True, timeout=30)
                report(f"$ {shlex.join(command)}\nexit={result.returncode}\n"
                       f"stdout={result.stdout.strip()}\nstderr={result.stderr.strip()}\n")
                assert result.returncode == expected_code, result
                if expected_code == 0:
                    return json.loads(result.stdout)
                assert not result.stdout and "error" in json.loads(result.stderr)

            run("list", "--repo", repo)
            run("create", "--source", source, "--repo", repo, "--id", "demo", "--max-bytes", "1000000")
            used = sum(path.stat().st_size for path in repo.rglob("*") if path.is_file())
            report(f"Regular repository bytes, including metadata: {used}")
            before = {str(path.relative_to(repo)): path.read_bytes() for path in repo.rglob("*") if path.is_file()}
            run("create", "--source", source, "--repo", repo, "--id", "too-small",
                "--max-bytes", used - 1, expected_code=1)
            after = {str(path.relative_to(repo)): path.read_bytes() for path in repo.rglob("*") if path.is_file()}
            assert before == after
            report("Rejected create preserved every repository file and byte.")
            run("verify", "--repo", repo, "--id", "demo")
            run("list", "--repo", repo)
            shutil.rmtree(source)
            run("restore", "--repo", repo, "--id", "demo", "--dest", dest)
            assert (dest / "datos 日本語.bin").read_bytes() == content
            assert list((dest / "vacío").iterdir()) == []
            report("Restoration matched all 259 data bytes and the empty directory after source removal.")


if __name__ == "__main__":
    main()
